//! NBT のファイル・バイト列・ストリームからの読み書き
//!
//! 仕様: `docs/spec/10-nbt-binary.md` 3章〜6章

use std::fmt;
use std::io::{Read, Write};
use std::path::Path;

use flate2::read::{GzDecoder, ZlibDecoder};
use flate2::write::{GzEncoder, ZlibEncoder};
use flate2::Compression as FlateLevel;

use crate::error::{Error, ErrorCode, Result};
use crate::nbt::mutf8;
use crate::nbt::tag::{NbtCompound, NbtList, NbtString, NbtTag, TagType};

/// NBT のルートタグの並び方
///
/// 仕様: `docs/spec/10-nbt-binary.md` 3章
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NbtFormat {
    /// ファイル形式
    /// ルートは「タグID + 名前長 + 名前 + ペイロード」の順に並ぶ
    Java,
    /// ネットワーク形式 (1.20.2 以降)
    /// ルートに名前が付かない
    Network,
}

/// 圧縮方式
///
/// 仕様: `docs/spec/10-nbt-binary.md` 4章
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Compression {
    /// 無圧縮
    None,
    /// GZip (RFC 1952)
    Gzip,
    /// Zlib (RFC 1950)
    Zlib,
    /// 先頭バイトから自動判定する
    /// 読み込み時のみ指定できる
    Auto,
}

/// ルート名とルートタグの組
#[derive(Debug, Clone, PartialEq)]
pub struct NamedTag {
    /// ルート名
    /// `Java` 形式では通常空文字列だが、読んだ値をそのまま保持する
    pub name: String,
    /// ルートタグ
    pub tag: NbtCompound,
}

impl NamedTag {
    /// ルート名とルートタグを指定して作る
    pub fn new(name: impl Into<String>, tag: NbtCompound) -> NamedTag {
        NamedTag { name: name.into(), tag }
    }
}

/// NBT 読み込みのオプション
#[derive(Debug, Clone, Copy)]
pub struct NbtReadOptions {
    /// ルートタグの並び方
    pub format: NbtFormat,
    /// 圧縮方式
    /// 既定は自動判定
    pub compression: Compression,
    /// ネストの深さ上限
    /// 既定は 512
    pub max_depth: i32,
    /// 展開後の総バイト数の上限
    /// 負値なら無制限
    pub max_decompressed_size: i64,
}

impl Default for NbtReadOptions {
    fn default() -> Self {
        NbtReadOptions {
            format: NbtFormat::Java,
            compression: Compression::Auto,
            max_depth: 512,
            max_decompressed_size: -1,
        }
    }
}

/// NBT 書き込みのオプション
#[derive(Debug, Clone, Copy)]
pub struct NbtWriteOptions {
    /// ルートタグの並び方
    pub format: NbtFormat,
    /// 圧縮方式
    /// 既定は GZip
    pub compression: Compression,
}

impl Default for NbtWriteOptions {
    fn default() -> Self {
        NbtWriteOptions { format: NbtFormat::Java, compression: Compression::Gzip }
    }
}

impl NbtWriteOptions {
    /// 無圧縮で書き出すオプション
    pub fn uncompressed() -> NbtWriteOptions {
        NbtWriteOptions { format: NbtFormat::Java, compression: Compression::None }
    }
}

// ---------------------------------------------------------------------------
// 読み込み
// ---------------------------------------------------------------------------

/// 位置を指定した読み込みの結果
///
/// 読んだタグと、その直後の位置を持つ
/// 続けて読むときは `end` を次の開始位置として渡す
///
/// 仕様: `docs/spec/10-nbt-binary.md` 3.1章
#[derive(Debug, Clone, PartialEq)]
pub struct NbtReadResult {
    /// 読んだタグ
    pub tag: NamedTag,
    /// 読み終わった直後の位置
    pub end: usize,
}

/// 展開済みのバイト列から NBT を読み出す
///
/// 入力全体をあらかじめメモリに持つ設計にしている
/// 「宣言された長さが残り入力長を超えていないか」を確保前に検査できるようにするため
struct Reader<'a> {
    data: &'a [u8],
    max_depth: i32,
    position: usize,
}

impl<'a> Reader<'a> {
    fn new(data: &'a [u8], max_depth: i32) -> Reader<'a> {
        Reader { data, max_depth, position: 0 }
    }

    fn at(data: &'a [u8], max_depth: i32, start: usize) -> Reader<'a> {
        Reader { data, max_depth, position: start }
    }

    fn remaining(&self) -> usize {
        self.data.len() - self.position
    }

    fn has_more(&self) -> bool {
        self.remaining() > 0
    }

    /// ルートタグを読み、末尾に余りが無いことを確かめる
    fn read_root(&mut self, format: NbtFormat) -> Result<NamedTag> {
        let tag = self.read_root_tag(format)?;

        // 末尾に余分なバイトが残っていたら、読み違えている可能性が高い
        if self.remaining() != 0 {
            return Err(Error::malformed(format!(
                "ルートタグの後に {} バイトの余分な入力がある",
                self.remaining()
            )));
        }

        Ok(tag)
    }

    /// ルートタグを 1 つ読む
    /// 末尾の余りは見ない
    fn read_root_tag(&mut self, format: NbtFormat) -> Result<NamedTag> {
        let tag_type = TagType::from_id(self.read_byte()?)?;

        // Java版のファイル形式でもネットワーク形式でも、ルートは必ず TAG_Compound
        if tag_type != TagType::Compound {
            return Err(Error::new(
                ErrorCode::MalformedData,
                format!(
                    "ルートタグは compound でなければならないが {} だった",
                    tag_type.as_str()
                ),
            ));
        }

        let name = if format == NbtFormat::Java {
            // ファイル形式のルートには名前が付く（通常は空文字列）
            match self.read_string()?.as_str() {
                Some(text) => text.to_string(),
                None => {
                    return Err(Error::new(
                        ErrorCode::MalformedData,
                        "ルート名が UTF-8 に写せない（孤立サロゲートを含む）",
                    ))
                }
            }
        } else {
            // ネットワーク形式 (1.20.2+) のルートに名前は無い
            String::new()
        };

        let root = self.read_compound_payload(1)?;
        Ok(NamedTag { name, tag: root })
    }

    fn read_payload(&mut self, tag_type: TagType, depth: i32) -> Result<NbtTag> {
        // 深さ上限は再帰する型に入る手前で検査する
        if depth > self.max_depth {
            return Err(Error::new(
                ErrorCode::LimitExceeded,
                format!("ネストが深すぎる (上限 {})", self.max_depth),
            ));
        }

        match tag_type {
            TagType::Byte => Ok(NbtTag::Byte(self.read_byte()? as i8)),
            TagType::Short => Ok(NbtTag::Short(self.read_unsigned(2)? as i16)),
            TagType::Int => Ok(NbtTag::Int(self.read_unsigned(4)? as i32)),
            TagType::Long => Ok(NbtTag::Long(self.read_unsigned(8)? as i64)),
            TagType::Float => Ok(NbtTag::Float(f32::from_bits(self.read_unsigned(4)? as u32))),
            TagType::Double => Ok(NbtTag::Double(f64::from_bits(self.read_unsigned(8)?))),
            TagType::ByteArray => {
                let count = self.read_length()?;
                self.ensure_available(count as u64)?;
                let mut values = Vec::with_capacity(count);

                // バイト単位でそのまま写す
                for offset in 0..count {
                    values.push(self.data[self.position + offset] as i8);
                }

                self.position += count;
                Ok(NbtTag::ByteArray(values))
            }
            TagType::String => Ok(NbtTag::String(self.read_string()?)),
            TagType::List => Ok(NbtTag::List(self.read_list_payload(depth)?)),
            TagType::Compound => Ok(NbtTag::Compound(self.read_compound_payload(depth)?)),
            TagType::IntArray => {
                let count = self.read_length()?;
                self.ensure_available(count as u64 * 4)?;
                let mut values = Vec::with_capacity(count);

                // 4 バイトずつビッグエンディアンで読む
                for _ in 0..count {
                    values.push(self.read_unsigned(4)? as i32);
                }

                Ok(NbtTag::IntArray(values))
            }
            TagType::LongArray => {
                let count = self.read_length()?;
                self.ensure_available(count as u64 * 8)?;
                let mut values = Vec::with_capacity(count);

                // 8 バイトずつビッグエンディアンで読む
                for _ in 0..count {
                    values.push(self.read_unsigned(8)? as i64);
                }

                Ok(NbtTag::LongArray(values))
            }
            TagType::End => Err(Error::new(
                ErrorCode::MalformedData,
                "TAG_End のペイロードを読もうとした",
            )),
        }
    }

    fn read_compound_payload(&mut self, depth: i32) -> Result<NbtCompound> {
        let mut compound = NbtCompound::new();

        // TAG_End が現れるまで名前付きタグを読み続ける
        loop {
            let tag_type = TagType::from_id(self.read_byte()?)?;

            if tag_type == TagType::End {
                return Ok(compound);
            }

            let name = match self.read_string()?.as_str() {
                Some(text) => text.to_string(),
                None => {
                    return Err(Error::new(
                        ErrorCode::MalformedData,
                        "Compound のキーが UTF-8 に写せない（孤立サロゲートを含む）",
                    ))
                }
            };

            let value = self.read_payload(tag_type, depth + 1)?;
            compound.set(name, value);
        }
    }

    fn read_list_payload(&mut self, depth: i32) -> Result<NbtList> {
        let element_type = TagType::from_id(self.read_byte()?)?;
        let count = self.read_length()?;

        if element_type == TagType::End {
            // 要素型 End のリストは空でなければならない
            if count != 0 {
                return Err(Error::new(
                    ErrorCode::MalformedData,
                    format!("要素型 End のリストに {count} 個の要素が宣言されている"),
                ));
            }

            return Ok(NbtList::with_element_type(TagType::End));
        }

        // 1 要素の最小バイト数から、宣言された個数が入力に収まるかを先に検査する
        self.ensure_available(count as u64 * minimum_payload_size(element_type))?;

        let mut list = NbtList::with_element_type(element_type);

        // 宣言された個数だけペイロードを読む
        for _ in 0..count {
            let item = self.read_payload(element_type, depth + 1)?;
            list.push(item)?;
        }

        Ok(list)
    }

    fn read_string(&mut self) -> Result<NbtString> {
        let length = self.read_unsigned(2)? as usize;
        self.ensure_available(length as u64)?;

        let units = mutf8::decode_to_utf16(&self.data[self.position..self.position + length])?;
        self.position += length;
        Ok(NbtString::from_utf16(units))
    }

    fn read_length(&mut self) -> Result<usize> {
        let length = self.read_unsigned(4)? as i32;

        // 長さは i32 だが、負値は仕様上ありえない
        if length < 0 {
            return Err(Error::new(
                ErrorCode::MalformedData,
                format!("長さが負値: {length}"),
            ));
        }

        Ok(length as usize)
    }

    fn read_byte(&mut self) -> Result<u8> {
        self.ensure_available(1)?;
        let value = self.data[self.position];
        self.position += 1;
        Ok(value)
    }

    /// 指定バイト数をビッグエンディアンで読み進める
    fn read_unsigned(&mut self, count: usize) -> Result<u64> {
        self.ensure_available(count as u64)?;
        let mut value: u64 = 0;

        // 上位バイトから順に積み上げる
        for offset in 0..count {
            value = (value << 8) | self.data[self.position + offset] as u64;
        }

        self.position += count;
        Ok(value)
    }

    /// 残り入力が必要バイト数を満たすか検査する
    /// メモリを確保する前に呼ぶ
    fn ensure_available(&self, required: u64) -> Result<()> {
        if required > self.remaining() as u64 {
            return Err(Error::new(
                ErrorCode::MalformedData,
                format!(
                    "入力が足りない: {required} バイト必要だが残り {} バイト",
                    self.remaining()
                ),
            ));
        }

        Ok(())
    }
}

/// その型のペイロードが最低何バイトになるかを返す
/// 長さの先行検証に使う
fn minimum_payload_size(tag_type: TagType) -> u64 {
    match tag_type {
        TagType::Byte => 1,
        TagType::Short => 2,
        TagType::Int | TagType::Float => 4,
        TagType::Long | TagType::Double => 8,
        // 長さフィールドの 4 バイトは必ずある
        TagType::ByteArray | TagType::IntArray | TagType::LongArray => 4,
        // 長さフィールドの 2 バイトは必ずある
        TagType::String => 2,
        // 要素型 1 バイト + 個数 4 バイト
        TagType::List => 5,
        // 終端の TAG_End 1 バイトは必ずある
        TagType::Compound | TagType::End => 1,
    }
}

// ---------------------------------------------------------------------------
// 書き込み
// ---------------------------------------------------------------------------

/// NBT を展開済みのバイト列へ書き出す
///
/// 出力は一意でなければならない（ラウンドトリップ検証が成立するため）
/// Compound は挿入順のまま、浮動小数点はビットパターンのまま書き出す
struct Writer {
    buffer: Vec<u8>,
}

impl Writer {
    fn new() -> Writer {
        Writer { buffer: Vec::new() }
    }

    fn write_root(mut self, named: &NamedTag, format: NbtFormat) -> Result<Vec<u8>> {
        self.buffer.push(TagType::Compound.id());

        if format == NbtFormat::Java {
            // ファイル形式のルートには名前が付く
            self.write_string(&NbtString::new(named.name.clone()))?;
        }

        self.write_compound_payload(&named.tag)?;
        Ok(self.buffer)
    }

    fn write_payload(&mut self, tag: &NbtTag) -> Result<()> {
        match tag {
            NbtTag::Byte(value) => self.buffer.push(*value as u8),
            NbtTag::Short(value) => self.write_unsigned(*value as u16 as u64, 2),
            NbtTag::Int(value) => self.write_unsigned(*value as u32 as u64, 4),
            NbtTag::Long(value) => self.write_unsigned(*value as u64, 8),
            // NaN や -0.0 を保つため、ビットパターンをそのまま書く
            NbtTag::Float(value) => self.write_unsigned(value.to_bits() as u64, 4),
            NbtTag::Double(value) => self.write_unsigned(value.to_bits(), 8),
            NbtTag::ByteArray(values) => {
                self.write_unsigned(values.len() as u64, 4);

                // 1 バイトずつそのまま書く
                for value in values {
                    self.buffer.push(*value as u8);
                }
            }
            NbtTag::String(value) => self.write_string(value)?,
            NbtTag::List(value) => self.write_list_payload(value)?,
            NbtTag::Compound(value) => self.write_compound_payload(value)?,
            NbtTag::IntArray(values) => {
                self.write_unsigned(values.len() as u64, 4);

                // 4 バイトずつビッグエンディアンで書く
                for value in values {
                    self.write_unsigned(*value as u32 as u64, 4);
                }
            }
            NbtTag::LongArray(values) => {
                self.write_unsigned(values.len() as u64, 4);

                // 8 バイトずつビッグエンディアンで書く
                for value in values {
                    self.write_unsigned(*value as u64, 8);
                }
            }
        }

        Ok(())
    }

    fn write_compound_payload(&mut self, compound: &NbtCompound) -> Result<()> {
        // 挿入順のまま「タグID + 名前 + ペイロード」を並べる
        for (key, value) in compound.iter() {
            self.buffer.push(value.tag_type().id());
            self.write_string(&NbtString::new(key.clone()))?;
            self.write_payload(value)?;
        }

        self.buffer.push(TagType::End.id());
        Ok(())
    }

    fn write_list_payload(&mut self, list: &NbtList) -> Result<()> {
        self.buffer.push(list.element_type().id());
        self.write_unsigned(list.len() as u64, 4);

        // 要素型は共通なので、ペイロードだけを並べる
        for item in list.iter() {
            self.write_payload(item)?;
        }

        Ok(())
    }

    fn write_string(&mut self, value: &NbtString) -> Result<()> {
        let encoded = value.to_mutf8();

        // 長さフィールドは u16
        // 65535 を超えると書き出せない
        if encoded.len() > mutf8::MAX_BYTE_LENGTH {
            return Err(Error::new(
                ErrorCode::InvalidArgument,
                format!("文字列が長すぎる: MUTF-8 で {} バイト (上限 {})", encoded.len(), mutf8::MAX_BYTE_LENGTH),
            ));
        }

        self.write_unsigned(encoded.len() as u64, 2);
        self.buffer.extend_from_slice(&encoded);
        Ok(())
    }

    /// 値をビッグエンディアンで指定バイト数ぶん書く
    fn write_unsigned(&mut self, value: u64, count: usize) {
        // 上位バイトから順に取り出す
        for index in (0..count).rev() {
            self.buffer.push(((value >> (index * 8)) & 0xFF) as u8);
        }
    }
}

// ---------------------------------------------------------------------------
// 圧縮
// ---------------------------------------------------------------------------

/// 先頭バイトから圧縮方式を判定する
pub fn detect_compression(bytes: &[u8]) -> Result<Compression> {
    if bytes.is_empty() {
        return Err(Error::new(
            ErrorCode::MalformedData,
            "入力が空で圧縮方式を判定できない",
        ));
    }

    // GZip は必ず 1F 8B で始まる
    if bytes.len() >= 2 && bytes[0] == 0x1F && bytes[1] == 0x8B {
        return Ok(Compression::Gzip);
    }

    if bytes.len() >= 2 {
        // zlib ヘッダは「圧縮法が 8 (deflate)」かつ「先頭2バイトが 31 の倍数」
        let is_deflate = (bytes[0] & 0x0F) == 0x08;
        let header = ((bytes[0] as u32) << 8) | bytes[1] as u32;

        if is_deflate && header % 31 == 0 {
            return Ok(Compression::Zlib);
        }
    }

    // 無圧縮なら先頭は TAG_Compound のタグID
    if bytes[0] == TagType::Compound.id() {
        return Ok(Compression::None);
    }

    Err(Error::new(
        ErrorCode::MalformedData,
        format!("圧縮方式を判定できない (先頭バイト 0x{:02X})", bytes[0]),
    ))
}

fn decompress(bytes: &[u8], options: &NbtReadOptions) -> Result<Vec<u8>> {
    let method = if options.compression == Compression::Auto {
        detect_compression(bytes)?
    } else {
        options.compression
    };

    if method == Compression::None {
        return Ok(bytes.to_vec());
    }

    let mut plain = Vec::new();

    match method {
        Compression::Gzip => {
            let mut decoder = GzDecoder::new(bytes);
            read_with_limit(&mut decoder, &mut plain, options.max_decompressed_size)?;
        }
        Compression::Zlib => {
            let mut decoder = ZlibDecoder::new(bytes);
            read_with_limit(&mut decoder, &mut plain, options.max_decompressed_size)?;
        }
        _ => {
            return Err(Error::new(
                ErrorCode::InvalidArgument,
                format!("展開できない圧縮方式: {method:?}"),
            ))
        }
    }

    Ok(plain)
}

/// 展開後のサイズ上限を見ながら読み出す
fn read_with_limit(source: &mut impl Read, destination: &mut Vec<u8>, max_size: i64) -> Result<()> {
    let mut chunk = [0u8; 81920];

    // 展開しながら、上限を超えた時点で打ち切る
    loop {
        let read = match source.read(&mut chunk) {
            Ok(read) => read,
            Err(error) => {
                return Err(Error::with_source(
                    ErrorCode::MalformedData,
                    "圧縮データを展開できない",
                    error,
                ))
            }
        };

        if read == 0 {
            return Ok(());
        }

        if max_size >= 0 && (destination.len() + read) as i64 > max_size {
            return Err(Error::new(
                ErrorCode::LimitExceeded,
                format!("展開後のサイズが上限 {max_size} バイトを超えた"),
            ));
        }

        destination.extend_from_slice(&chunk[..read]);
    }
}

fn compress(plain: Vec<u8>, method: Compression) -> Result<Vec<u8>> {
    match method {
        Compression::None => Ok(plain),
        Compression::Gzip => {
            let mut encoder = GzEncoder::new(Vec::new(), FlateLevel::best());
            encoder.write_all(&plain)?;
            Ok(encoder.finish()?)
        }
        Compression::Zlib => {
            let mut encoder = ZlibEncoder::new(Vec::new(), FlateLevel::best());
            encoder.write_all(&plain)?;
            Ok(encoder.finish()?)
        }
        Compression::Auto => Err(Error::new(
            ErrorCode::InvalidArgument,
            "書き込みで Compression::Auto は指定できない",
        )),
    }
}

// ---------------------------------------------------------------------------
// 公開 API
// ---------------------------------------------------------------------------

/// バイト列から NBT を読む
pub fn read_bytes(bytes: &[u8], options: &NbtReadOptions) -> Result<NamedTag> {
    let plain = decompress(bytes, options)?;
    Reader::new(&plain, options.max_depth).read_root(options.format)
}

/// バイト列の指定した位置から NBT を 1 つ読む
///
/// 複数の NBT が連なっているデータを、先頭から順に読み進めるために使う
/// 戻り値の `end` が次の開始位置になる
///
/// 位置は渡したバイト列そのものを指すので、圧縮されたデータは扱えない
pub fn read_bytes_at(
    bytes: &[u8],
    offset: usize,
    options: &NbtReadOptions,
) -> Result<NbtReadResult> {
    require_plain_input(options)?;

    if offset > bytes.len() {
        return Err(Error::invalid_argument(format!(
            "読み始める位置が範囲外: {} (長さ {})",
            offset,
            bytes.len()
        )));
    }

    let mut reader = Reader::at(bytes, options.max_depth, offset);
    let tag = reader.read_root_tag(options.format)?;
    Ok(NbtReadResult { tag, end: reader.position })
}

/// バイト列に連なっている NBT をすべて読む
///
/// 入力を使い切るまで読み続ける
/// 空のバイト列なら空の一覧を返す
///
/// 圧縮は入力全体に 1 回かかっているものとして扱う
pub fn read_bytes_all(bytes: &[u8], options: &NbtReadOptions) -> Result<Vec<NamedTag>> {
    let mut tags: Vec<NamedTag> = Vec::new();

    // 空の入力は「0 個」であってエラーではない
    if bytes.is_empty() {
        return Ok(tags);
    }

    let plain = decompress(bytes, options)?;
    let mut reader = Reader::new(&plain, options.max_depth);

    // 入力を使い切るまでルートタグを読み続ける
    while reader.has_more() {
        tags.push(reader.read_root_tag(options.format)?);
    }

    Ok(tags)
}

/// 位置を指定する読み込みは、展開済みのバイト列だけを扱う
fn require_plain_input(options: &NbtReadOptions) -> Result<()> {
    if options.compression == Compression::Gzip || options.compression == Compression::Zlib {
        return Err(Error::invalid_argument(
            "位置を指定した読み込みでは圧縮を扱えない。展開してから渡すこと",
        ));
    }

    Ok(())
}

/// ファイルから NBT を読む
pub fn read_file(path: impl AsRef<Path>, options: &NbtReadOptions) -> Result<NamedTag> {
    let raw = std::fs::read(path.as_ref()).map_err(|error| {
        // 下位の入出力エラーは情報を失わないよう原因として保持する
        Error::with_source(
            ErrorCode::Io,
            format!("ファイルを読めない: {}", path.as_ref().display()),
            error,
        )
    })?;

    read_bytes(&raw, options)
}

/// リーダから NBT を読む
/// 最後まで読み切る
pub fn read_reader(source: &mut impl Read, options: &NbtReadOptions) -> Result<NamedTag> {
    let mut raw = Vec::new();
    source.read_to_end(&mut raw)?;
    read_bytes(&raw, options)
}

/// NBT をバイト列へ書き出す
pub fn write_bytes(named: &NamedTag, options: &NbtWriteOptions) -> Result<Vec<u8>> {
    // 書き込み時に Auto は決められない
    if options.compression == Compression::Auto {
        return Err(Error::new(
            ErrorCode::InvalidArgument,
            "書き込みで Compression::Auto は指定できない",
        ));
    }

    let plain = Writer::new().write_root(named, options.format)?;
    compress(plain, options.compression)
}

/// NBT をファイルへ書き出す
pub fn write_file(
    path: impl AsRef<Path>,
    named: &NamedTag,
    options: &NbtWriteOptions,
) -> Result<()> {
    let bytes = write_bytes(named, options)?;

    std::fs::write(path.as_ref(), bytes).map_err(|error| {
        Error::with_source(
            ErrorCode::Io,
            format!("ファイルへ書けない: {}", path.as_ref().display()),
            error,
        )
    })
}

/// NBT をライタへ書き出す
pub fn write_writer(
    destination: &mut impl Write,
    named: &NamedTag,
    options: &NbtWriteOptions,
) -> Result<()> {
    let bytes = write_bytes(named, options)?;
    destination.write_all(&bytes)?;
    Ok(())
}

impl fmt::Display for NamedTag {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "NamedTag(\"{}\", {})", self.name, self.tag)
    }
}

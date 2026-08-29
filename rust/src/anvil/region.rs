//! Anvil のリージョンファイル (`r.X.Z.mca`)
//! 32×32 チャンクを格納する
//!
//! ファイル全体をメモリに読み込んで扱う
//! 実データのリージョンは数 MB 程度で、
//! この方が「触っていないチャンクのバイト配置をそのまま保つ」ことを保証しやすい
//! 開いて何も変えずに [`RegionFile::flush`] すると、バイト単位で元と同じファイルになる
//!
//! 仕様: `docs/spec/20-anvil-region.md`

use std::collections::HashMap;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use flate2::read::{GzDecoder, ZlibDecoder};
use flate2::write::{GzEncoder, ZlibEncoder};
use flate2::Compression as FlateLevel;

use crate::error::{Error, ErrorCode, Result};
use crate::nbt::tag::NbtCompound;
use crate::nbt::{read_bytes, write_bytes, Compression, NamedTag, NbtReadOptions, NbtWriteOptions};

/// セクタ長
pub const SECTOR_SIZE: usize = 4096;

/// ロケーションテーブルとタイムスタンプテーブルが占めるセクタ数
const HEADER_SECTORS: usize = 2;

/// 1リージョンに入るチャンク数
const CHUNK_COUNT: usize = 1024;

/// 1チャンクが確保できるセクタ数の上限（長さフィールドが u8 のため）
const MAX_SECTORS: usize = 255;

/// リージョン内に収められるペイロードの上限
/// 超えると外部ファイルへ退避する
const MAX_INLINE_PAYLOAD: usize = (MAX_SECTORS * SECTOR_SIZE) - 5;

/// リージョンファイル内でチャンクに使われる圧縮方式
///
/// NBT 層の [`Compression`] とは別物であることに注意
/// あちらはファイル全体の圧縮を表し、こちらはリージョン内の 1 チャンクに付く
/// 1 バイトのIDを表す
///
/// 仕様: `docs/spec/20-anvil-region.md` 3.1章
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ChunkCompression {
    /// GZip (RFC 1952)
    /// 実データではほぼ使われない
    Gzip,
    /// Zlib (RFC 1950)
    /// Minecraft が実際に書き出す方式
    Zlib,
    /// 無圧縮
    None,
    /// LZ4（ブロック形式）
    /// 任意依存
    Lz4,
    /// サードパーティ製サーバのカスタム方式
    /// 中身は解釈できない
    Custom,
}

impl ChunkCompression {
    /// 仕様が定める圧縮方式ID
    pub fn id(self) -> u8 {
        match self {
            ChunkCompression::Gzip => 1,
            ChunkCompression::Zlib => 2,
            ChunkCompression::None => 3,
            ChunkCompression::Lz4 => 4,
            ChunkCompression::Custom => 127,
        }
    }

    /// 適合性テストで言語間比較に使う識別子
    pub fn as_str(self) -> &'static str {
        match self {
            ChunkCompression::Gzip => "gzip",
            ChunkCompression::Zlib => "zlib",
            ChunkCompression::None => "none",
            ChunkCompression::Lz4 => "lz4",
            ChunkCompression::Custom => "custom",
        }
    }

    /// 圧縮方式IDから [`ChunkCompression`] を得る
    /// 未知のIDならエラー
    pub fn from_id(id: u8) -> Result<ChunkCompression> {
        // 仕様が定めるのは 1・2・3・4・127 の 5 種類だけ
        match id {
            1 => Ok(ChunkCompression::Gzip),
            2 => Ok(ChunkCompression::Zlib),
            3 => Ok(ChunkCompression::None),
            4 => Ok(ChunkCompression::Lz4),
            127 => Ok(ChunkCompression::Custom),
            other => Err(Error::new(
                ErrorCode::MalformedData,
                format!("未知の圧縮方式ID: {other}"),
            )),
        }
    }
}

/// リージョンファイルを開くときの動作
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RegionFileMode {
    /// 読み取り専用
    /// 書き込み系の操作はエラーになる
    ReadOnly,
    /// 読み書き
    /// ファイルが無ければ空のリージョンとして扱う
    ReadWrite,
}

/// リージョンの座標
/// 1リージョンは 32×32 チャンクを担当する
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct RegionPos {
    /// リージョンX座標
    pub x: i32,
    /// リージョンZ座標
    pub z: i32,
}

impl RegionPos {
    /// 座標を指定して作る
    pub fn new(x: i32, z: i32) -> RegionPos {
        RegionPos { x, z }
    }

    /// このリージョンのファイル名（`r.X.Z.mca`）
    pub fn file_name(&self) -> String {
        format!("r.{}.{}.mca", self.x, self.z)
    }

    /// `r.X.Z.mca` 形式のファイル名から座標を得る
    /// 解釈できなければ `None`
    pub fn from_file_name(file_name: &str) -> Option<RegionPos> {
        let parts: Vec<&str> = file_name.split('.').collect();

        // "r" "<x>" "<z>" "mca" の 4 つに分かれるはず
        if parts.len() != 4 || parts[0] != "r" || parts[3] != "mca" {
            return None;
        }

        let x = match parts[1].parse::<i32>() {
            Ok(value) => value,
            Err(_) => return None,
        };

        let z = match parts[2].parse::<i32>() {
            Ok(value) => value,
            Err(_) => return None,
        };

        Some(RegionPos { x, z })
    }
}

/// チャンクの絶対座標
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct ChunkPos {
    /// 絶対チャンクX座標
    pub x: i32,
    /// 絶対チャンクZ座標
    pub z: i32,
}

impl ChunkPos {
    /// 座標を指定して作る
    pub fn new(x: i32, z: i32) -> ChunkPos {
        ChunkPos { x, z }
    }

    /// このチャンクを含むリージョンの座標
    ///
    /// Rust の `>>` は符号付き整数では算術右シフトなので、負の座標でも正しく求まる
    pub fn region(&self) -> RegionPos {
        RegionPos::new(self.x >> 5, self.z >> 5)
    }

    /// リージョン内でのX位置 (0..31)
    pub fn local_x(&self) -> i32 {
        self.x & 31
    }

    /// リージョン内でのZ位置 (0..31)
    pub fn local_z(&self) -> i32 {
        self.z & 31
    }

    /// ロケーションテーブル内の添字 (0..1023)
    pub fn index(&self) -> usize {
        (self.local_x() + (self.local_z() * 32)) as usize
    }
}

/// リージョンファイルに格納されたままの、圧縮済みチャンクデータ
///
/// 本ライブラリが解釈できない圧縮方式（LZ4 未導入、カスタム方式）でも
/// これなら取り出せる
/// バックアップや別ツールへの受け渡しに使う
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RawChunk {
    /// この本体に使われている圧縮方式
    pub compression: ChunkCompression,
    /// 圧縮されたままの本体
    pub data: Vec<u8>,
    /// 外部ファイル `c.X.Z.mcc` に格納されていたか
    pub external: bool,
}

impl RawChunk {
    /// 内部格納のチャンクとして作る
    pub fn new(compression: ChunkCompression, data: Vec<u8>) -> RawChunk {
        RawChunk { compression, data, external: false }
    }
}

/// リージョンファイル 1 つ分
pub struct RegionFile {
    path: PathBuf,
    directory: PathBuf,
    mode: RegionFileMode,
    region_x: i32,
    region_z: i32,
    offsets: Vec<usize>,
    sector_counts: Vec<usize>,
    timestamps: Vec<i32>,
    data: Vec<u8>,
    dirty: bool,
    closed: bool,
}

impl RegionFile {
    /// リージョンファイルを開く
    ///
    /// `path` は `r.X.Z.mca` という名前でなければならない
    /// 座標はファイル名から読み取る
    pub fn open(path: impl AsRef<Path>, mode: RegionFileMode) -> Result<RegionFile> {
        let path = path.as_ref();

        let file_name = match path.file_name() {
            Some(name) => name.to_string_lossy().into_owned(),
            None => String::new(),
        };

        let position = match RegionPos::from_file_name(&file_name) {
            Some(value) => value,
            None => {
                return Err(Error::new(
                    ErrorCode::InvalidArgument,
                    format!("リージョンファイル名として解釈できない: {file_name}"),
                ))
            }
        };

        let data = if path.exists() {
            match std::fs::read(path) {
                Ok(bytes) => bytes,
                Err(error) => {
                    return Err(Error::with_source(
                        ErrorCode::Io,
                        format!("ファイルを読めない: {}", path.display()),
                        error,
                    ))
                }
            }
        } else if mode == RegionFileMode::ReadWrite {
            // 読み書きモードなら、存在しないファイルは空のリージョンとして扱う
            vec![0u8; HEADER_SECTORS * SECTOR_SIZE]
        } else {
            return Err(Error::new(
                ErrorCode::Io,
                format!("ファイルが存在しない: {}", path.display()),
            ));
        };

        let directory = match path.parent() {
            Some(parent) if !parent.as_os_str().is_empty() => parent.to_path_buf(),
            _ => PathBuf::from("."),
        };

        let mut region = RegionFile {
            path: path.to_path_buf(),
            directory,
            mode,
            region_x: position.x,
            region_z: position.z,
            offsets: vec![0; CHUNK_COUNT],
            sector_counts: vec![0; CHUNK_COUNT],
            timestamps: vec![0; CHUNK_COUNT],
            data,
            dirty: false,
            closed: false,
        };

        region.parse_header()?;
        Ok(region)
    }

    /// このリージョンのX座標
    pub fn region_x(&self) -> i32 {
        self.region_x
    }

    /// このリージョンのZ座標
    pub fn region_z(&self) -> i32 {
        self.region_z
    }

    /// ヘッダを解析し、ロケーションとタイムスタンプを取り込む
    fn parse_header(&mut self) -> Result<()> {
        // 空ファイルは「チャンクが 1 つも無いリージョン」として受け入れる
        if self.data.is_empty() {
            self.data = vec![0u8; HEADER_SECTORS * SECTOR_SIZE];
            return Ok(());
        }

        if self.data.len() < HEADER_SECTORS * SECTOR_SIZE {
            return Err(Error::new(
                ErrorCode::MalformedData,
                format!(
                    "ヘッダが足りない: {} バイト（最低 {} バイト必要）",
                    self.data.len(),
                    HEADER_SECTORS * SECTOR_SIZE
                ),
            ));
        }

        if self.data.len() % SECTOR_SIZE != 0 {
            return Err(Error::new(
                ErrorCode::MalformedData,
                format!("ファイル長がセクタ境界に揃っていない: {} バイト", self.data.len()),
            ));
        }

        let total_sectors = self.data.len() / SECTOR_SIZE;
        let mut sector_owner: HashMap<usize, usize> = HashMap::new();

        // ロケーションテーブルの 1024 エントリを順に取り込む
        for index in 0..CHUNK_COUNT {
            let entry = self.read_unsigned(index * 4, 4);
            let offset = (entry >> 8) as usize;
            let count = (entry & 0xFF) as usize;

            self.timestamps[index] =
                self.read_unsigned(SECTOR_SIZE + (index * 4), 4) as u32 as i32;

            if offset == 0 && count == 0 {
                continue;
            }

            if offset < HEADER_SECTORS {
                return Err(Error::new(
                    ErrorCode::MalformedData,
                    format!("チャンク {index} のオフセットがヘッダ領域を指している: {offset}"),
                ));
            }

            if count == 0 {
                return Err(Error::new(
                    ErrorCode::MalformedData,
                    format!("チャンク {index} のセクタ数が 0 なのにオフセットが設定されている"),
                ));
            }

            if offset + count > total_sectors {
                return Err(Error::new(
                    ErrorCode::MalformedData,
                    format!("チャンク {index} の割り当てがファイル外へはみ出している"),
                ));
            }

            // 同じセクタを 2 つのチャンクが指していたら、どちらかが壊れている
            for sector in offset..offset + count {
                if let Some(owner) = sector_owner.insert(sector, index) {
                    return Err(Error::new(
                        ErrorCode::MalformedData,
                        format!("セクタ {sector} がチャンク {owner} とチャンク {index} で重複している"),
                    ));
                }
            }

            self.offsets[index] = offset;
            self.sector_counts[index] = count;
        }

        Ok(())
    }

    /// ロケーションテーブルとタイムスタンプテーブルを先頭 2 セクタへ書き戻す
    fn write_header(&mut self) {
        // 位置表とタイムスタンプ表を、添字順に組み立て直す
        for index in 0..CHUNK_COUNT {
            let entry = ((self.offsets[index] as u64) << 8) | (self.sector_counts[index] as u64);
            self.write_unsigned(index * 4, entry, 4);
            self.write_unsigned(
                SECTOR_SIZE + (index * 4),
                self.timestamps[index] as u32 as u64,
                4,
            );
        }
    }

    /// 指定した座標がこのリージョンの担当範囲にあるか確認し、添字を返す
    fn index_of(&self, chunk_x: i32, chunk_z: i32) -> Result<usize> {
        let position = ChunkPos::new(chunk_x, chunk_z);
        let region = position.region();

        if region.x != self.region_x || region.z != self.region_z {
            return Err(Error::new(
                ErrorCode::InvalidArgument,
                format!(
                    "チャンク ({chunk_x}, {chunk_z}) はリージョン ({}, {}) の担当外",
                    self.region_x, self.region_z
                ),
            ));
        }

        Ok(position.index())
    }

    fn ensure_writable(&self) -> Result<()> {
        if self.mode == RegionFileMode::ReadOnly {
            return Err(Error::new(
                ErrorCode::InvalidArgument,
                "読み取り専用で開いたリージョンには書き込めない",
            ));
        }

        Ok(())
    }

    fn ensure_open(&self) -> Result<()> {
        if self.closed {
            return Err(Error::new(
                ErrorCode::InvalidArgument,
                "既に閉じられたリージョンファイル",
            ));
        }

        Ok(())
    }

    /// チャンクが存在するか
    pub fn has_chunk(&self, chunk_x: i32, chunk_z: i32) -> Result<bool> {
        self.ensure_open()?;
        let index = self.index_of(chunk_x, chunk_z)?;
        Ok(self.sector_counts[index] > 0)
    }

    /// 存在するチャンクの座標を、ロケーションテーブルの並び順で返す
    pub fn chunk_positions(&self) -> Result<Vec<ChunkPos>> {
        self.ensure_open()?;
        let mut result = Vec::new();

        // 添字の昇順に走査する（local_z が外、local_x が内）
        for index in 0..CHUNK_COUNT {
            if self.sector_counts[index] == 0 {
                continue;
            }

            let local_x = (index % 32) as i32;
            let local_z = (index / 32) as i32;
            result.push(ChunkPos::new(
                (self.region_x * 32) + local_x,
                (self.region_z * 32) + local_z,
            ));
        }

        Ok(result)
    }

    /// チャンクの最終更新時刻（Unix 秒）
    /// 存在しなければ 0
    pub fn timestamp(&self, chunk_x: i32, chunk_z: i32) -> Result<i32> {
        self.ensure_open()?;
        let index = self.index_of(chunk_x, chunk_z)?;
        Ok(self.timestamps[index])
    }

    /// チャンクの最終更新時刻を設定する
    pub fn set_timestamp(&mut self, chunk_x: i32, chunk_z: i32, value: i32) -> Result<()> {
        self.ensure_open()?;
        self.ensure_writable()?;
        let index = self.index_of(chunk_x, chunk_z)?;
        self.timestamps[index] = value;
        self.dirty = true;
        Ok(())
    }

    /// チャンクを圧縮されたまま取り出す
    /// 存在しなければ `None`
    pub fn read_chunk_raw(&self, chunk_x: i32, chunk_z: i32) -> Result<Option<RawChunk>> {
        self.ensure_open()?;
        let index = self.index_of(chunk_x, chunk_z)?;

        if self.sector_counts[index] == 0 {
            return Ok(None);
        }

        let start = self.offsets[index] * SECTOR_SIZE;
        let length = self.read_unsigned(start, 4) as u32 as i32;
        let scheme_byte = self.data[start + 4];

        if length < 1 {
            return Err(Error::new(
                ErrorCode::MalformedData,
                format!("チャンク ({chunk_x}, {chunk_z}) の length が不正: {length}"),
            ));
        }

        if 4 + (length as usize) > self.sector_counts[index] * SECTOR_SIZE {
            return Err(Error::new(
                ErrorCode::MalformedData,
                format!("チャンク ({chunk_x}, {chunk_z}) の length が確保セクタ数を超えている"),
            ));
        }

        let external = (scheme_byte & 0x80) != 0;
        let compression = ChunkCompression::from_id(scheme_byte & 0x7F)?;

        if external {
            // 最上位ビットが立っている場合、本体は c.X.Z.mcc にある
            let payload = self.read_external_file(chunk_x, chunk_z)?;
            return Ok(Some(RawChunk { compression, data: payload, external: true }));
        }

        let body = self.data[start + 5..start + 4 + length as usize].to_vec();
        Ok(Some(RawChunk { compression, data: body, external: false }))
    }

    /// チャンクを NBT として読む
    /// 存在しなければ `None`
    pub fn read_chunk(&self, chunk_x: i32, chunk_z: i32) -> Result<Option<NbtCompound>> {
        let raw = match self.read_chunk_raw(chunk_x, chunk_z)? {
            Some(value) => value,
            None => return Ok(None),
        };

        let plain = decompress_chunk(&raw)?;
        let options =
            NbtReadOptions { compression: Compression::None, ..NbtReadOptions::default() };
        Ok(Some(read_bytes(&plain, &options)?.tag))
    }

    /// チャンクを NBT として書き込む
    pub fn write_chunk(
        &mut self,
        chunk_x: i32,
        chunk_z: i32,
        tag: &NbtCompound,
        compression: ChunkCompression,
    ) -> Result<()> {
        let options = NbtWriteOptions::uncompressed();
        let plain = write_bytes(&NamedTag::new("", tag.clone()), &options)?;
        let payload = compress_chunk(&plain, compression)?;
        self.write_chunk_raw(chunk_x, chunk_z, &RawChunk::new(compression, payload))
    }

    /// 圧縮済みのチャンクをそのまま書き込む
    pub fn write_chunk_raw(&mut self, chunk_x: i32, chunk_z: i32, raw: &RawChunk) -> Result<()> {
        self.ensure_open()?;
        self.ensure_writable()?;

        let index = self.index_of(chunk_x, chunk_z)?;
        let use_external = raw.data.len() > MAX_INLINE_PAYLOAD;

        let payload: Vec<u8>;
        let scheme_byte: u8;

        if use_external {
            // 1MiB を超えるチャンクは外部ファイルへ退避し、リージョンには目印だけ残す
            self.write_external_file(chunk_x, chunk_z, &raw.data)?;
            payload = Vec::new();
            scheme_byte = raw.compression.id() | 0x80;
        } else {
            self.delete_external_file(chunk_x, chunk_z)?;
            payload = raw.data.clone();
            scheme_byte = raw.compression.id();
        }

        let needed = (4 + 1 + payload.len()).div_ceil(SECTOR_SIZE);

        if needed > MAX_SECTORS {
            return Err(Error::new(
                ErrorCode::InvalidArgument,
                format!("チャンクが大きすぎる: {needed} セクタ（上限 {MAX_SECTORS}）"),
            ));
        }

        let start = self.allocate_sectors(index, needed);

        // 確保した領域をゼロで埋めてから書く（前の内容を残さないため）
        for offset in start * SECTOR_SIZE..(start + needed) * SECTOR_SIZE {
            self.data[offset] = 0;
        }

        let position = start * SECTOR_SIZE;
        self.write_unsigned(position, (1 + payload.len()) as u64, 4);
        self.data[position + 4] = scheme_byte;
        self.data[position + 5..position + 5 + payload.len()].copy_from_slice(&payload);

        self.offsets[index] = start;
        self.sector_counts[index] = needed;
        self.timestamps[index] = current_unix_seconds();
        self.dirty = true;
        Ok(())
    }

    /// チャンクを削除する
    /// 削除できたら `true`
    pub fn delete_chunk(&mut self, chunk_x: i32, chunk_z: i32) -> Result<bool> {
        self.ensure_open()?;
        self.ensure_writable()?;

        let index = self.index_of(chunk_x, chunk_z)?;

        if self.sector_counts[index] == 0 {
            return Ok(false);
        }

        self.delete_external_file(chunk_x, chunk_z)?;
        self.offsets[index] = 0;
        self.sector_counts[index] = 0;
        self.timestamps[index] = 0;
        self.dirty = true;
        Ok(true)
    }

    /// 必要なセクタ数を確保し、開始セクタ番号を返す
    ///
    /// 既存の割り当てがちょうど同じ大きさならその場を使い、
    /// そうでなければ先頭から空き領域を探し、無ければ末尾へ追加する
    fn allocate_sectors(&mut self, index: usize, needed: usize) -> usize {
        // 大きさが変わらないなら動かさない
        // 触っていないチャンクの配置を保つため
        if self.sector_counts[index] == needed {
            return self.offsets[index];
        }

        let used = self.build_sector_usage(index);
        let total_sectors = self.data.len() / SECTOR_SIZE;
        let mut run = 0usize;

        // 先頭から連続した空き領域を探す
        for sector in HEADER_SECTORS..total_sectors {
            // 使用中のセクタに当たったら、空きの連続はそこで途切れる
            if used[sector] {
                run = 0;
                continue;
            }

            run += 1;

            if run == needed {
                return sector - needed + 1;
            }
        }

        // 見つからなければ末尾へ追加する
        // 末尾の空きは再利用できる
        let start = total_sectors - run;
        self.data.resize((start + needed) * SECTOR_SIZE, 0);
        start
    }

    /// セクタの使用状況を作る
    /// `ignore_index` のチャンクは空きとして扱う
    fn build_sector_usage(&self, ignore_index: usize) -> Vec<bool> {
        let total_sectors = self.data.len() / SECTOR_SIZE;
        let mut used = vec![false; total_sectors];

        // ヘッダの 2 セクタは常に使用中
        for sector in used.iter_mut().take(HEADER_SECTORS.min(total_sectors)) {
            *sector = true;
        }

        // 他のチャンクが占めているセクタに印を付ける
        for other in 0..CHUNK_COUNT {
            if other == ignore_index || self.sector_counts[other] == 0 {
                continue;
            }

            let start = self.offsets[other];

            // 他のチャンクが占めるセクタに印を付ける
            for sector in start..start + self.sector_counts[other] {
                // ファイル長を超える位置は既に検証で弾いているが、念のため範囲を確かめる
                if sector < total_sectors {
                    used[sector] = true;
                }
            }
        }

        used
    }

    /// 全チャンクを隙間なく詰め直す
    /// 断片化したファイルを縮めたいときに使う
    pub fn optimize(&mut self) -> Result<()> {
        self.ensure_open()?;
        self.ensure_writable()?;

        let mut collected: Vec<(usize, RawChunk)> = Vec::new();

        // 先に全チャンクを取り出してから、新しい配置で書き直す
        for index in 0..CHUNK_COUNT {
            if self.sector_counts[index] == 0 {
                continue;
            }

            let local_x = (index % 32) as i32;
            let local_z = (index / 32) as i32;
            let raw = self.read_chunk_raw(
                (self.region_x * 32) + local_x,
                (self.region_z * 32) + local_z,
            )?;

            // 存在するチャンクだけを集める
            if let Some(value) = raw {
                collected.push((index, value));
            }
        }

        let saved_timestamps = self.timestamps.clone();
        self.data = vec![0u8; HEADER_SECTORS * SECTOR_SIZE];
        self.offsets = vec![0; CHUNK_COUNT];
        self.sector_counts = vec![0; CHUNK_COUNT];

        let mut next_sector = HEADER_SECTORS;

        // 添字の昇順に、先頭から詰めて配置する
        for (index, raw) in collected {
            let payload: Vec<u8>;
            let scheme_byte: u8;

            // 外部ファイルへ退避したチャンクは、本体を持たず印だけを書く
            if raw.external {
                payload = Vec::new();
                scheme_byte = raw.compression.id() | 0x80;
            } else {
                payload = raw.data;
                scheme_byte = raw.compression.id();
            }

            let needed = (4 + 1 + payload.len()).div_ceil(SECTOR_SIZE);
            self.data.resize((next_sector + needed) * SECTOR_SIZE, 0);

            let position = next_sector * SECTOR_SIZE;
            self.write_unsigned(position, (1 + payload.len()) as u64, 4);
            self.data[position + 4] = scheme_byte;
            self.data[position + 5..position + 5 + payload.len()].copy_from_slice(&payload);

            self.offsets[index] = next_sector;
            self.sector_counts[index] = needed;
            next_sector += needed;
        }

        self.timestamps = saved_timestamps;
        self.dirty = true;
        Ok(())
    }

    /// 変更をファイルへ書き出す
    pub fn flush(&mut self) -> Result<()> {
        self.ensure_open()?;

        if self.mode == RegionFileMode::ReadOnly {
            return Ok(());
        }

        self.write_header();

        match std::fs::write(&self.path, &self.data) {
            Ok(()) => {
                self.dirty = false;
                Ok(())
            }
            Err(error) => Err(Error::with_source(
                ErrorCode::Io,
                format!("ファイルへ書けない: {}", self.path.display()),
                error,
            )),
        }
    }

    /// 現在の内容をバイト列として組み立てる
    /// ファイルには書かない
    pub fn to_bytes(&mut self) -> Result<Vec<u8>> {
        self.ensure_open()?;
        self.write_header();
        Ok(self.data.clone())
    }

    /// 変更があれば書き出してから閉じる
    pub fn close(&mut self) -> Result<()> {
        if self.closed {
            return Ok(());
        }

        // 読み書きで開いていて変更があるなら、閉じる前に書き出す
        if self.dirty && self.mode == RegionFileMode::ReadWrite {
            self.flush()?;
        }

        self.closed = true;
        Ok(())
    }

    // -- バイト操作 ---------------------------------------------------------

    /// 指定位置からビッグエンディアンで読む
    fn read_unsigned(&self, position: usize, count: usize) -> u64 {
        let mut value: u64 = 0;

        // 上位バイトから順に積み上げる
        for offset in 0..count {
            value = (value << 8) | self.data[position + offset] as u64;
        }

        value
    }

    /// 指定位置へビッグエンディアンで書く
    fn write_unsigned(&mut self, position: usize, value: u64, count: usize) {
        // 上位バイトから順に取り出す
        for offset in 0..count {
            self.data[position + offset] =
                ((value >> ((count - 1 - offset) * 8)) & 0xFF) as u8;
        }
    }

    // -- 外部ファイル (.mcc) ------------------------------------------------

    fn external_path(&self, chunk_x: i32, chunk_z: i32) -> PathBuf {
        self.directory.join(format!("c.{chunk_x}.{chunk_z}.mcc"))
    }

    fn read_external_file(&self, chunk_x: i32, chunk_z: i32) -> Result<Vec<u8>> {
        let external = self.external_path(chunk_x, chunk_z);

        if !external.exists() {
            return Err(Error::new(
                ErrorCode::MalformedData,
                format!("外部チャンクファイルが無い: {}", external.display()),
            ));
        }

        std::fs::read(&external).map_err(|error| {
            Error::with_source(
                ErrorCode::Io,
                format!("外部チャンクファイルを読めない: {}", external.display()),
                error,
            )
        })
    }

    fn write_external_file(&self, chunk_x: i32, chunk_z: i32, payload: &[u8]) -> Result<()> {
        let external = self.external_path(chunk_x, chunk_z);

        std::fs::write(&external, payload).map_err(|error| {
            Error::with_source(
                ErrorCode::Io,
                format!("外部チャンクファイルへ書けない: {}", external.display()),
                error,
            )
        })
    }

    fn delete_external_file(&self, chunk_x: i32, chunk_z: i32) -> Result<()> {
        let external = self.external_path(chunk_x, chunk_z);

        // 縮んで内部へ戻ったチャンクの残骸を消す
        if external.exists() {
            return std::fs::remove_file(&external).map_err(|error| {
                Error::with_source(
                    ErrorCode::Io,
                    format!("外部チャンクファイルを削除できない: {}", external.display()),
                    error,
                )
            });
        }

        Ok(())
    }
}

impl Drop for RegionFile {
    fn drop(&mut self) {
        // 書き忘れを防ぐため、破棄時にも書き出しを試みる
        // 失敗は握り潰すしかない
        let _ = self.close();
    }
}

fn current_unix_seconds() -> i32 {
    match SystemTime::now().duration_since(UNIX_EPOCH) {
        Ok(elapsed) => elapsed.as_secs() as i32,
        Err(_) => 0,
    }
}

/// 圧縮済みペイロードを展開する
fn decompress_chunk(raw: &RawChunk) -> Result<Vec<u8>> {
    match raw.compression {
        ChunkCompression::None => Ok(raw.data.clone()),
        ChunkCompression::Gzip => {
            let mut decoder = GzDecoder::new(raw.data.as_slice());
            let mut plain = Vec::new();
            read_all(&mut decoder, &mut plain)?;
            Ok(plain)
        }
        ChunkCompression::Zlib => {
            let mut decoder = ZlibDecoder::new(raw.data.as_slice());
            let mut plain = Vec::new();
            read_all(&mut decoder, &mut plain)?;
            Ok(plain)
        }
        other => Err(Error::new(
            ErrorCode::UnsupportedFeature,
            format!(
                "{} 圧縮のチャンクは扱えない。生バイトAPI (read_chunk_raw) を使うこと",
                other.as_str()
            ),
        )),
    }
}

fn read_all(source: &mut impl Read, destination: &mut Vec<u8>) -> Result<()> {
    match source.read_to_end(destination) {
        Ok(_) => Ok(()),
        Err(error) => Err(Error::with_source(
            ErrorCode::MalformedData,
            "チャンクの圧縮データを展開できない",
            error,
        )),
    }
}

/// ペイロードを指定の方式で圧縮する
fn compress_chunk(plain: &[u8], compression: ChunkCompression) -> Result<Vec<u8>> {
    match compression {
        ChunkCompression::None => Ok(plain.to_vec()),
        ChunkCompression::Gzip => {
            let mut encoder = GzEncoder::new(Vec::new(), FlateLevel::best());
            encoder.write_all(plain)?;
            Ok(encoder.finish()?)
        }
        ChunkCompression::Zlib => {
            let mut encoder = ZlibEncoder::new(Vec::new(), FlateLevel::best());
            encoder.write_all(plain)?;
            Ok(encoder.finish()?)
        }
        other => Err(Error::new(
            ErrorCode::UnsupportedFeature,
            format!("この圧縮方式では書き込めない: {}", other.as_str()),
        )),
    }
}

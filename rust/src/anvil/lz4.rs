//! 圧縮方式ID 4 (LZ4) のチャンクを展開する
//!
//! 素の LZ4 ブロックでも LZ4 フレーム形式でもなく、
//! 独自ヘッダを持つブロックの連結である
//!
//! 書き込みには対応しない
//! 書き戻すときは Zlib になる
//!
//! 仕様: `docs/spec/20-anvil-region.md` 3.1.1 / 3.1.2

use crate::error::{Error, Result};

/// ブロックの先頭に必ず置かれる 8 バイト
const MAGIC: &[u8; 8] = b"LZ4Block";

/// ブロックヘッダの長さ
const HEADER_LENGTH: usize = 21;

/// トークン上位 4 ビット: 本体が無圧縮
const METHOD_STORED: u8 = 0x10;

/// トークン上位 4 ビット: 本体が LZ4 圧縮
const METHOD_COMPRESSED: u8 = 0x20;

/// マッチの最小長
const MIN_MATCH: usize = 4;

/// LZ4Block の連結を展開する
pub fn decompress(payload: &[u8]) -> Result<Vec<u8>> {
    let mut output: Vec<u8> = Vec::new();
    let mut position = 0usize;

    // 入力を使い切るまでブロックを読み続ける
    while position < payload.len() {
        position = decompress_block(payload, position, &mut output)?;
    }

    Ok(output)
}

/// ブロックを 1 つ展開し、次のブロックの開始位置を返す
fn decompress_block(payload: &[u8], position: usize, output: &mut Vec<u8>) -> Result<usize> {
    if position + HEADER_LENGTH > payload.len() {
        return Err(Error::malformed(format!(
            "LZ4: ブロックヘッダが足りない（{} バイト）",
            payload.len() - position
        )));
    }

    // マジックが違えばそもそも LZ4Block ではない
    if &payload[position..position + MAGIC.len()] != MAGIC.as_slice() {
        return Err(Error::malformed("LZ4: ブロックが LZ4Block で始まっていない"));
    }

    let method = payload[position + 8] & 0xF0;
    let compressed_length = read_i32_le(payload, position + 9);
    let original_length = read_i32_le(payload, position + 13);

    validate_lengths(compressed_length, original_length)?;

    let body = position + HEADER_LENGTH;
    let compressed_length = compressed_length as usize;
    let original_length = original_length as usize;

    if body + compressed_length > payload.len() {
        return Err(Error::malformed("LZ4: ブロック本体が入力からはみ出している"));
    }

    if method == METHOD_STORED {
        // 無圧縮なら 2 つの長さは一致していなければならない
        if compressed_length != original_length {
            return Err(Error::malformed(format!(
                "LZ4: 無圧縮ブロックの長さが食い違う（{compressed_length} と {original_length}）"
            )));
        }

        output.extend_from_slice(&payload[body..body + compressed_length]);
    } else if method == METHOD_COMPRESSED {
        let block =
            decompress_raw_block(&payload[body..body + compressed_length], original_length)?;
        output.extend_from_slice(&block);
    } else {
        return Err(Error::malformed(format!("LZ4: 未知の圧縮方式 0x{method:02X}")));
    }

    Ok(body + compressed_length)
}

/// ヘッダに書かれた 2 つの長さが妥当か調べる
fn validate_lengths(compressed_length: i32, original_length: i32) -> Result<()> {
    if compressed_length < 0 || original_length < 0 {
        return Err(Error::malformed("LZ4: ブロックの長さが負値"));
    }

    // 片方だけが 0 になることはない
    if (compressed_length == 0) != (original_length == 0) {
        return Err(Error::malformed("LZ4: ブロックの長さが片方だけ 0"));
    }

    Ok(())
}

/// 素の LZ4 ブロックを展開する
fn decompress_raw_block(source: &[u8], original_length: usize) -> Result<Vec<u8>> {
    let mut output: Vec<u8> = vec![0; original_length];
    let mut input = 0usize;
    let mut written = 0usize;

    // シーケンスを順に読む
    while input < source.len() {
        let token = source[input];
        input += 1;

        let mut literal_length = (token >> 4) as usize;

        // 15 なら追加バイトで長さが続く
        if literal_length == 15 {
            literal_length += read_length(source, &mut input)?;
        }

        written = copy_literals(source, &mut input, &mut output, written, literal_length)?;

        // リテラルを出し切って入力が尽きたら、そこで終わり
        if input >= source.len() {
            break;
        }

        if input + 2 > source.len() {
            return Err(Error::malformed("LZ4: オフセットが入力からはみ出している"));
        }

        let offset = (source[input] as usize) | ((source[input + 1] as usize) << 8);
        input += 2;

        if offset == 0 || offset > written {
            return Err(Error::malformed(format!("LZ4: マッチのオフセットが不正: {offset}")));
        }

        let mut match_length = (token & 0x0F) as usize + MIN_MATCH;

        // 下位 4 ビットが 15 なら追加バイトで長さが続く
        if (token & 0x0F) == 15 {
            match_length += read_length(source, &mut input)?;
        }

        written = copy_match(&mut output, written, offset, match_length)?;
    }

    if written != original_length {
        return Err(Error::malformed(format!(
            "LZ4: 展開後の長さが合わない（{written} と {original_length}）"
        )));
    }

    Ok(output)
}

/// 255 が続く形式の追加長さを読む
fn read_length(source: &[u8], input: &mut usize) -> Result<usize> {
    let mut total = 0usize;

    // 255 未満のバイトが出るまで足し続ける
    loop {
        if *input >= source.len() {
            return Err(Error::malformed("LZ4: 長さの追加バイトが途中で切れた"));
        }

        let value = source[*input];
        *input += 1;
        total += value as usize;

        if value != 255 {
            return Ok(total);
        }
    }
}

/// リテラルをそのまま出力へ写し、書き込み済みの長さを返す
fn copy_literals(
    source: &[u8],
    input: &mut usize,
    output: &mut [u8],
    written: usize,
    length: usize,
) -> Result<usize> {
    if *input + length > source.len() {
        return Err(Error::malformed("LZ4: リテラルが入力からはみ出している"));
    }

    if written + length > output.len() {
        return Err(Error::malformed("LZ4: 展開後の長さを超えた"));
    }

    output[written..written + length].copy_from_slice(&source[*input..*input + length]);
    *input += length;
    Ok(written + length)
}

/// 出力済みのバイト列からマッチを写し、書き込み済みの長さを返す
fn copy_match(output: &mut [u8], written: usize, offset: usize, length: usize) -> Result<usize> {
    if written + length > output.len() {
        return Err(Error::malformed("LZ4: 展開後の長さを超えた"));
    }

    let from = written - offset;

    // コピー元と先は重なりうるので 1 バイトずつ写す
    for index in 0..length {
        output[written + index] = output[from + index];
    }

    Ok(written + length)
}

/// リトルエンディアンの i32 を読む
/// この形式だけ他と逆になる
fn read_i32_le(source: &[u8], position: usize) -> i32 {
    i32::from_le_bytes([
        source[position],
        source[position + 1],
        source[position + 2],
        source[position + 3],
    ])
}

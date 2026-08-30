//! Modified UTF-8 (MUTF-8) の符号化・復号
//!
//! 標準 UTF-8 との違いは 2 点だけ
//!  - `U+0000` を `C0 80` の 2 バイトで表す
//!  - `U+10000` 以上をサロゲートペアへ分解し、3 バイト × 2 で表す (CESU-8)
//!
//! 仕様: `docs/spec/10-nbt-binary.md` 2章

use crate::error::{Error, ErrorCode, Result};

/// 長さフィールドが `u16` のため、1 つの文字列は符号化後 65535 バイトまで
pub const MAX_BYTE_LENGTH: usize = 65535;

/// Rust の `char` へ写せない値も表せるよう、復号結果は UTF-16 コード単位の列で返す
///
/// 孤立サロゲートを含む文字列は `String` にできないため、
/// 呼び出し側が `NbtString` としてどう保持するかを決められるようにしている
pub fn decode_to_utf16(bytes: &[u8]) -> Result<Vec<u16>> {
    let mut units: Vec<u16> = Vec::with_capacity(bytes.len());
    let mut i = 0usize;

    // 先頭から 1 文字ずつ取り出す
    while i < bytes.len() {
        let b0 = bytes[i];

        if b0 & 0x80 == 0x00 {
            // 1 バイト形式: 0xxxxxxx (U+0001..U+007F)
            if b0 == 0x00 {
                // 素の 0x00 は MUTF-8 では現れてはならない (C0 80 を使う)
                return Err(Error::new(
                    ErrorCode::MalformedData,
                    "MUTF-8: 素の 0x00 が現れた (U+0000 は C0 80 で表す)",
                ));
            }
            units.push(b0 as u16);
            i += 1;
        } else if b0 & 0xE0 == 0xC0 {
            // 2 バイト形式: 110xxxxx 10xxxxxx
            if i + 1 >= bytes.len() {
                return Err(Error::new(ErrorCode::MalformedData, "MUTF-8: 2バイト形式が途中で切れた"));
            }
            let b1 = bytes[i + 1];
            if b1 & 0xC0 != 0x80 {
                return Err(Error::new(ErrorCode::MalformedData, "MUTF-8: 2バイト形式の継続バイトが不正"));
            }
            let value = (((b0 & 0x1F) as u32) << 6) | ((b1 & 0x3F) as u32);
            // C0 80 (U+0000) だけは正当
            // それ以外の 0x80 未満は冗長符号化
            if value < 0x80 && !(b0 == 0xC0 && b1 == 0x80) {
                return Err(Error::new(ErrorCode::MalformedData, "MUTF-8: 冗長な2バイト符号化"));
            }
            units.push(value as u16);
            i += 2;
        } else if b0 & 0xF0 == 0xE0 {
            // 3 バイト形式: 1110xxxx 10xxxxxx 10xxxxxx
            if i + 2 >= bytes.len() {
                return Err(Error::new(ErrorCode::MalformedData, "MUTF-8: 3バイト形式が途中で切れた"));
            }
            let b1 = bytes[i + 1];
            let b2 = bytes[i + 2];
            if b1 & 0xC0 != 0x80 || b2 & 0xC0 != 0x80 {
                return Err(Error::new(ErrorCode::MalformedData, "MUTF-8: 3バイト形式の継続バイトが不正"));
            }
            let value = (((b0 & 0x0F) as u32) << 12) | (((b1 & 0x3F) as u32) << 6) | ((b2 & 0x3F) as u32);
            // 3 バイトで表すべき範囲は U+0800 以上
            if value < 0x800 {
                return Err(Error::new(ErrorCode::MalformedData, "MUTF-8: 冗長な3バイト符号化"));
            }
            units.push(value as u16);
            i += 3;
        } else {
            // 4 バイト形式 (標準 UTF-8) や継続バイト単独は MUTF-8 では不正
            return Err(Error::new(
                ErrorCode::MalformedData,
                format!("MUTF-8: 不正な先頭バイト 0x{b0:02X}"),
            ));
        }
    }

    Ok(units)
}

/// UTF-16 コード単位の列を MUTF-8 バイト列へ符号化する
///
/// サロゲートは対になっているかどうかに関わらず 1 つずつ 3 バイトで符号化されるため、
/// 孤立サロゲートもそのまま往復できる
pub fn encode_from_utf16(units: &[u16]) -> Vec<u8> {
    let mut out: Vec<u8> = Vec::with_capacity(units.len() + units.len() / 2);

    // コード単位ごとに 1〜3 バイトへ展開する
    for &unit in units {
        // U+0001..U+007F だけが 1 バイト
        // U+0000 は 2 バイトになる
        if unit >= 0x0001 && unit <= 0x007F {
            out.push(unit as u8);
        } else if unit == 0x0000 || unit <= 0x07FF {
            // U+0000 もこの経路で C0 80 になる
            out.push(0xC0 | ((unit >> 6) as u8 & 0x1F));
            out.push(0x80 | (unit as u8 & 0x3F));
        } else {
            out.push(0xE0 | ((unit >> 12) as u8 & 0x0F));
            out.push(0x80 | ((unit >> 6) as u8 & 0x3F));
            out.push(0x80 | (unit as u8 & 0x3F));
        }
    }

    out
}

/// Rust の `str` を MUTF-8 バイト列へ符号化する
pub fn encode(text: &str) -> Vec<u8> {
    let units: Vec<u16> = text.encode_utf16().collect();
    encode_from_utf16(&units)
}

/// MUTF-8 バイト列を `String` へ復号する
///
/// 孤立サロゲートを含む入力は `String` にできないため `MALFORMED_DATA` になる
/// そのまま保持したい場合は [`decode_to_utf16`] を使う
pub fn decode(bytes: &[u8]) -> Result<String> {
    let units = decode_to_utf16(bytes)?;

    match utf16_to_string(&units) {
        Some(text) => Ok(text),
        None => Err(Error::new(
            ErrorCode::MalformedData,
            "MUTF-8: 孤立サロゲートを含むため String へ写せない",
        )),
    }
}

/// MUTF-8 へ符号化したときのバイト数を数える
///
/// 実際に符号化せずに長さだけを求める
pub fn byte_length(text: &str) -> usize {
    let mut total = 0usize;

    // コード単位ごとに 1〜3 バイトへ展開される
    for unit in text.encode_utf16() {
        // U+0001..U+007F だけが 1 バイト
        // U+0000 は 2 バイトになる
        if unit >= 0x0001 && unit <= 0x007F {
            total += 1;
        } else if unit == 0x0000 || unit <= 0x07FF {
            total += 2;
        } else {
            total += 3;
        }
    }

    total
}

/// UTF-16 コード単位の列を `String` へ変換する
/// 孤立サロゲートがあれば `None`
pub fn utf16_to_string(units: &[u16]) -> Option<String> {
    match String::from_utf16(units) {
        Ok(text) => Some(text),
        Err(_) => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ascii_roundtrip() {
        let bytes = encode("Bananrama");
        assert_eq!(bytes, b"Bananrama");
        let units = decode_to_utf16(&bytes).unwrap();
        assert_eq!(utf16_to_string(&units).unwrap(), "Bananrama");
    }

    #[test]
    fn nul_is_two_bytes() {
        let bytes = encode("a\u{0000}b");
        assert_eq!(bytes, vec![b'a', 0xC0, 0x80, b'b']);
        let units = decode_to_utf16(&bytes).unwrap();
        assert_eq!(utf16_to_string(&units).unwrap(), "a\u{0000}b");
    }

    #[test]
    fn supplementary_char_is_cesu8() {
        // U+1F600 は UTF-16 では D83D DE00
        // MUTF-8 では 3 バイト × 2 になる
        let bytes = encode("\u{1F600}");
        assert_eq!(bytes, vec![0xED, 0xA0, 0xBD, 0xED, 0xB8, 0x80]);
        let units = decode_to_utf16(&bytes).unwrap();
        assert_eq!(utf16_to_string(&units).unwrap(), "\u{1F600}");
    }

    #[test]
    fn lone_surrogate_survives_roundtrip() {
        // 孤立した上位サロゲート D83D
        // String にはできないが往復はできる
        let original: Vec<u16> = vec![0xD83D];
        let bytes = encode_from_utf16(&original);
        assert_eq!(bytes, vec![0xED, 0xA0, 0xBD]);
        let units = decode_to_utf16(&bytes).unwrap();
        assert_eq!(units, original);
        assert!(utf16_to_string(&units).is_none());
    }

    #[test]
    fn decode_returns_string() {
        assert_eq!(decode(b"Bananrama").unwrap(), "Bananrama");
        assert_eq!(decode(&[0x61, 0xC0, 0x80, 0x62]).unwrap(), "a\u{0000}b");
    }

    #[test]
    fn decode_rejects_lone_surrogate() {
        // 孤立サロゲートは String へ写せない
        let err = decode(&[0xED, 0xA0, 0xBD]).unwrap_err();
        assert_eq!(err.code(), ErrorCode::MalformedData);
    }

    #[test]
    fn byte_length_matches_encoded_length() {
        // 1〜3 バイトになる各パターンで、数えた長さと符号化結果を突き合わせる
        for text in ["", "Bananrama", "a\u{0000}b", "あいう", "\u{1F600}"] {
            assert_eq!(byte_length(text), encode(text).len(), "{text}");
        }
    }

    #[test]
    fn raw_nul_is_rejected() {
        let err = decode_to_utf16(&[0x00]).unwrap_err();
        assert_eq!(err.code(), ErrorCode::MalformedData);
    }

    #[test]
    fn overlong_two_byte_is_rejected() {
        // U+0041 を 2 バイトで表した冗長符号化
        let err = decode_to_utf16(&[0xC1, 0x81]).unwrap_err();
        assert_eq!(err.code(), ErrorCode::MalformedData);
    }

    #[test]
    fn four_byte_utf8_is_rejected() {
        // 標準 UTF-8 の 4 バイト形式は MUTF-8 では不正
        let err = decode_to_utf16(&[0xF0, 0x9F, 0x98, 0x80]).unwrap_err();
        assert_eq!(err.code(), ErrorCode::MalformedData);
    }

    #[test]
    fn truncated_input_is_rejected() {
        let err = decode_to_utf16(&[0xE3, 0x81]).unwrap_err();
        assert_eq!(err.code(), ErrorCode::MalformedData);
    }
}

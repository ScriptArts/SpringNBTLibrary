//! Modified UTF-8 (MUTF-8)の符号化・復号
//!
//! 標準UTF-8との違いは2点だけ
//!  - `U+0000`を`C0 80`の2バイトで表す
//!  - `U+10000`以上をサロゲートペアへ分解し、3バイト × 2で表す (CESU-8)

use crate::error::{Error, ErrorCode, Result};

/// 長さフィールドが`u16`のため、1つの文字列は符号化後65535バイトまで
pub const MAX_BYTE_LENGTH: usize = 65535;

/// Rustの`char`へ写せない値も表せるよう、復号結果はUTF-16コード単位の列で返す
///
/// 孤立サロゲートを含む文字列は`String`にできないため、呼び出し側が`NbtString`としてどう保持するかを決められるようにしている
pub fn decode_to_utf16(bytes: &[u8]) -> Result<Vec<u16>> {
    let mut units: Vec<u16> = Vec::with_capacity(bytes.len());
    let mut i = 0usize;

    // 先頭から1文字ずつ取り出す
    while i < bytes.len() {
        let b0 = bytes[i];

        if b0 & 0x80 == 0x00 {
            // 1バイト形式: 0xxxxxxx (U+0001..U+007F)
            if b0 == 0x00 {
                // 素の0x00はMUTF-8では現れてはならない (C0 80を使う)
                return Err(Error::new(
                    ErrorCode::MalformedData,
                    "MUTF-8: 素の 0x00 が現れた (U+0000 は C0 80 で表す)",
                ));
            }
            units.push(b0 as u16);
            i += 1;
        } else if b0 & 0xE0 == 0xC0 {
            // 2バイト形式: 110xxxxx 10xxxxxx
            if i + 1 >= bytes.len() {
                return Err(Error::new(ErrorCode::MalformedData, "MUTF-8: 2バイト形式が途中で切れた"));
            }
            let b1 = bytes[i + 1];
            if b1 & 0xC0 != 0x80 {
                return Err(Error::new(ErrorCode::MalformedData, "MUTF-8: 2バイト形式の継続バイトが不正"));
            }
            let value = (((b0 & 0x1F) as u32) << 6) | ((b1 & 0x3F) as u32);
            // C0 80 (U+0000)だけは正当
            // それ以外の0x80未満は冗長符号化
            if value < 0x80 && !(b0 == 0xC0 && b1 == 0x80) {
                return Err(Error::new(ErrorCode::MalformedData, "MUTF-8: 冗長な2バイト符号化"));
            }
            units.push(value as u16);
            i += 2;
        } else if b0 & 0xF0 == 0xE0 {
            // 3バイト形式: 1110xxxx 10xxxxxx 10xxxxxx
            if i + 2 >= bytes.len() {
                return Err(Error::new(ErrorCode::MalformedData, "MUTF-8: 3バイト形式が途中で切れた"));
            }
            let b1 = bytes[i + 1];
            let b2 = bytes[i + 2];
            if b1 & 0xC0 != 0x80 || b2 & 0xC0 != 0x80 {
                return Err(Error::new(ErrorCode::MalformedData, "MUTF-8: 3バイト形式の継続バイトが不正"));
            }
            let value = (((b0 & 0x0F) as u32) << 12) | (((b1 & 0x3F) as u32) << 6) | ((b2 & 0x3F) as u32);
            // 3バイトで表すべき範囲はU+0800以上
            if value < 0x800 {
                return Err(Error::new(ErrorCode::MalformedData, "MUTF-8: 冗長な3バイト符号化"));
            }
            units.push(value as u16);
            i += 3;
        } else {
            // 4バイト形式 (標準UTF-8)や継続バイト単独はMUTF-8では不正
            return Err(Error::new(
                ErrorCode::MalformedData,
                format!("MUTF-8: 不正な先頭バイト 0x{b0:02X}"),
            ));
        }
    }

    Ok(units)
}

/// UTF-16コード単位の列をMUTF-8バイト列へ符号化する
///
/// サロゲートは対になっているかどうかに関わらず1つずつ3バイトで符号化されるため、孤立サロゲートもそのまま往復できる
pub fn encode_from_utf16(units: &[u16]) -> Vec<u8> {
    let mut out: Vec<u8> = Vec::with_capacity(units.len() + units.len() / 2);

    // コード単位ごとに1〜3バイトへ展開する
    for &unit in units {
        // U+0001..U+007Fだけが1バイト
        // U+0000は2バイトになる
        if unit >= 0x0001 && unit <= 0x007F {
            out.push(unit as u8);
        } else if unit == 0x0000 || unit <= 0x07FF {
            // U+0000もこの経路でC0 80になる
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

/// Rustの`str`をMUTF-8バイト列へ符号化する
pub fn encode(text: &str) -> Vec<u8> {
    let units: Vec<u16> = text.encode_utf16().collect();
    encode_from_utf16(&units)
}

/// MUTF-8バイト列を`String`へ復号する
///
/// 孤立サロゲートを含む入力は`String`にできないため`MALFORMED_DATA`になる
/// そのまま保持したい場合は[`decode_to_utf16`]を使う
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

/// MUTF-8へ符号化したときのバイト数を数える
///
/// 実際に符号化せずに長さだけを求める
pub fn byte_length(text: &str) -> usize {
    let mut total = 0usize;

    // 各コード単位が何バイトになるかを数える
    for unit in text.encode_utf16() {
        // U+0001..U+007Fだけが1バイト
        // U+0000は2バイトになる
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

/// UTF-16コード単位の列を`String`へ変換する
/// 孤立サロゲートがあれば`None`
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
        // U+1F600はUTF-16ではD83D DE00
        // MUTF-8では3バイト × 2になる
        let bytes = encode("\u{1F600}");
        assert_eq!(bytes, vec![0xED, 0xA0, 0xBD, 0xED, 0xB8, 0x80]);
        let units = decode_to_utf16(&bytes).unwrap();
        assert_eq!(utf16_to_string(&units).unwrap(), "\u{1F600}");
    }

    #[test]
    fn lone_surrogate_survives_roundtrip() {
        // 孤立した上位サロゲートD83D
        // Stringにはできないが往復はできる
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
        // 孤立サロゲートはStringへ写せない
        let err = decode(&[0xED, 0xA0, 0xBD]).unwrap_err();
        assert_eq!(err.code(), ErrorCode::MalformedData);
    }

    #[test]
    fn byte_length_matches_encoded_length() {
        // 1〜3バイトになる各パターンで、数えた長さと符号化結果を比べる
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
        // U+0041を2バイトで表した冗長符号化
        let err = decode_to_utf16(&[0xC1, 0x81]).unwrap_err();
        assert_eq!(err.code(), ErrorCode::MalformedData);
    }

    #[test]
    fn four_byte_utf8_is_rejected() {
        // 標準UTF-8の4バイト形式はMUTF-8では不正
        let err = decode_to_utf16(&[0xF0, 0x9F, 0x98, 0x80]).unwrap_err();
        assert_eq!(err.code(), ErrorCode::MalformedData);
    }

    #[test]
    fn truncated_input_is_rejected() {
        let err = decode_to_utf16(&[0xE3, 0x81]).unwrap_err();
        assert_eq!(err.code(), ErrorCode::MalformedData);
    }
}

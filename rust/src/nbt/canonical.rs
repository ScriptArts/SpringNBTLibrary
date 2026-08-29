//! 浮動小数点の正準10進表記。
//!
//! 各言語の標準の数値書式（C# の `"R"`、Java の `Float.toString`、
//! Python の `repr`、Rust の `{}`）は互いに一致しない。
//! 指数表記へ切り替わる閾値も、指数部の桁数も、`E` の大文字小文字も処理系ごとに違う。
//! そのままでは SNBT 出力の言語間一致が成立しないため、書式をここで固定する。
//!
//! 仕様: `docs/spec/11-snbt.md` 5.1章

/// 固定小数点表記を使う10進指数の下限。
const MIN_FIXED_EXPONENT: i32 = -4;

/// 固定小数点表記を使う10進指数の上限。
const MAX_FIXED_EXPONENT: i32 = 16;

/// binary32 を正準10進表記へ変換する。
pub fn from_f32(value: f32) -> String {
    if value.is_nan() {
        return "NaN".to_string();
    }

    if value.is_infinite() {
        if value.is_sign_positive() {
            return "Infinity".to_string();
        }

        return "-Infinity".to_string();
    }

    let target = value.to_bits();

    // 有効数字を 1 桁ずつ増やし、読み戻してビット一致する最短の表記を探す
    for precision in 1..=9usize {
        let candidate = format!("{:.*e}", precision - 1, value);

        match candidate.parse::<f32>() {
            Ok(parsed) => {
                if parsed.to_bits() == target {
                    return format_exponential(&candidate);
                }
            }
            Err(_) => continue,
        }
    }

    // 9 桁あれば binary32 は必ず往復するので、ここへは来ない
    format_exponential(&format!("{:.8e}", value))
}

/// binary64 を正準10進表記へ変換する。
pub fn from_f64(value: f64) -> String {
    if value.is_nan() {
        return "NaN".to_string();
    }

    if value.is_infinite() {
        if value.is_sign_positive() {
            return "Infinity".to_string();
        }

        return "-Infinity".to_string();
    }

    let target = value.to_bits();

    // 有効数字を 1 桁ずつ増やし、読み戻してビット一致する最短の表記を探す
    for precision in 1..=17usize {
        let candidate = format!("{:.*e}", precision - 1, value);

        match candidate.parse::<f64>() {
            Ok(parsed) => {
                if parsed.to_bits() == target {
                    return format_exponential(&candidate);
                }
            }
            Err(_) => continue,
        }
    }

    // 17 桁あれば binary64 は必ず往復するので、ここへは来ない
    format_exponential(&format!("{:.16e}", value))
}

/// 指数表記の文字列（Rust の `{:e}` は `7.5e-1` 形式）から、仕様が定める正準表記を組み立てる。
fn format_exponential(exponential: &str) -> String {
    let bytes: Vec<char> = exponential.chars().collect();
    let mut negative = false;
    let mut index = 0usize;

    // 先頭の符号を取り除き、数字の並びだけを読めるようにする
    if bytes[0] == '-' || bytes[0] == '+' {
        negative = bytes[0] == '-';
        index = 1;
    }

    let mut digits = String::new();

    // 仮数部の数字だけを集める
    while index < bytes.len() && bytes[index] != 'e' && bytes[index] != 'E' {
        if bytes[index].is_ascii_digit() {
            digits.push(bytes[index]);
        }

        index += 1;
    }

    let exponent_text: String = bytes[index + 1..].iter().collect();
    let exponent: i32 = exponent_text.trim_start_matches('+').parse().unwrap_or(0);

    compose(negative, trim_trailing_zeros(&digits), exponent)
}

/// 末尾のゼロを取り除く。すべてゼロなら "0" を残す。
fn trim_trailing_zeros(digits: &str) -> String {
    let chars: Vec<char> = digits.chars().collect();
    let mut end = chars.len();

    // 末尾から連続するゼロを削る
    while end > 1 && chars[end - 1] == '0' {
        end -= 1;
    }

    chars[..end].iter().collect()
}

/// 数字列と10進指数から最終的な文字列を組み立てる。
fn compose(negative: bool, digits: String, exponent: i32) -> String {
    let mut result = String::new();

    // 符号は数字の前に置く
    if negative {
        result.push('-');
    }

    // 値が 0 のときは指数に関わらず 0.0 と書く
    if digits == "0" {
        result.push_str("0.0");
        return result;
    }

    if exponent < MIN_FIXED_EXPONENT || exponent > MAX_FIXED_EXPONENT {
        // 指数表記
        result.push_str(&digits[0..1]);
        result.push('.');

        // 2 桁目以降があれば小数点のうしろへ回す
        if digits.len() > 1 {
            result.push_str(&digits[1..]);
        } else {
            result.push('0');
        }

        result.push('E');
        result.push_str(&exponent.to_string());
        return result;
    }

    if exponent >= 0 {
        // 整数部は先頭 (exponent + 1) 桁。足りなければゼロで右詰めする
        let integer_digits = (exponent + 1) as usize;

        // 整数部が数字の並びに収まるなら、そのまま切り出す
        if digits.len() >= integer_digits {
            result.push_str(&digits[..integer_digits]);
        } else {
            result.push_str(&digits);

            // 数字が足りない分は 0 で埋めて桁を合わせる
            for _ in digits.len()..integer_digits {
                result.push('0');
            }
        }

        result.push('.');

        // 整数部で使い切らなかった数字が小数部になる
        if digits.len() > integer_digits {
            result.push_str(&digits[integer_digits..]);
        } else {
            result.push('0');
        }

        return result;
    }

    // 指数が負なら "0." に続けてゼロを詰めてから数字を置く
    result.push_str("0.");

    // 指数のぶんだけ 0.000... と 0 を並べる
    for _ in 0..((-exponent) - 1) {
        result.push('0');
    }

    result.push_str(&digits);
    result
}

//! SNBT (Stringified NBT) のパースと出力。
//!
//! 対応範囲は「バイナリ NBT へ損失なく写せる部分集合」。
//! 1.21.5 以降の異種リスト（`[1, "a"]`）は受理しない。
//!
//! 仕様: `docs/spec/11-snbt.md` / `docs/adr/0006-snbt-scope.md`

use crate::error::{Error, ErrorCode, Result};
use crate::nbt::canonical;
use crate::nbt::tag::{NbtCompound, NbtList, NbtString, NbtTag, TagType};

const INDENT_UNIT: &str = "    ";

const WIDTH_SUFFIXES: &str = "bBsSlLfFdD";

/// SNBT 文字列をタグへ変換する。
pub fn parse(text: &str) -> Result<NbtTag> {
    Parser::new(text).parse_whole()
}

/// SNBT 文字列を Compound へ変換する。
pub fn parse_compound(text: &str) -> Result<NbtCompound> {
    match parse(text)? {
        NbtTag::Compound(compound) => Ok(compound),
        other => Err(Error::new(
            ErrorCode::UnexpectedTagType,
            format!("ルートが compound でない: {}", other.tag_type().as_str()),
        )),
    }
}

/// タグを 1 行の SNBT へ変換する。
pub fn write(tag: &NbtTag) -> String {
    let mut out = String::new();
    write_tag(&mut out, tag, -1);
    out
}

/// タグを整形した SNBT へ変換する。インデントは空白 4 個。
pub fn write_pretty(tag: &NbtTag) -> String {
    let mut out = String::new();
    write_tag(&mut out, tag, 0);
    out
}

// ---------------------------------------------------------------------------
// パーサ
// ---------------------------------------------------------------------------

struct Parser {
    chars: Vec<char>,
    position: usize,
}

impl Parser {
    fn new(text: &str) -> Parser {
        Parser { chars: text.chars().collect(), position: 0 }
    }

    fn parse_whole(&mut self) -> Result<NbtTag> {
        let value = self.parse_value()?;
        self.skip_whitespace();

        // 値の後に余分な文字が残っていたら、書き手の意図と違う解釈をしている
        if self.position < self.chars.len() {
            return Err(self.malformed(format!(
                "値の後に余分な文字がある: '{}'",
                self.chars[self.position]
            )));
        }

        Ok(value)
    }

    fn parse_value(&mut self) -> Result<NbtTag> {
        self.skip_whitespace();

        if self.position >= self.chars.len() {
            return Err(self.malformed("値が来るべき位置で入力が尽きた".to_string()));
        }

        let c = self.chars[self.position];

        if c == '{' {
            return Ok(NbtTag::Compound(self.parse_compound_value()?));
        }

        if c == '[' {
            return self.parse_list_or_array();
        }

        if c == '"' || c == '\'' {
            let text = self.parse_quoted_string()?;
            return Ok(NbtTag::String(NbtString::from_utf16(text)));
        }

        self.parse_unquoted()
    }

    fn parse_compound_value(&mut self) -> Result<NbtCompound> {
        self.expect('{')?;
        let mut compound = NbtCompound::new();
        self.skip_whitespace();

        // 空の Compound
        if self.peek()? == '}' {
            self.position += 1;
            return Ok(compound);
        }

        // 要素を 1 つずつ読む
        loop {
            self.skip_whitespace();

            // 末尾カンマの直後に閉じ括弧が来る形を許す
            if self.peek()? == '}' {
                self.position += 1;
                return Ok(compound);
            }

            let key = self.parse_key()?;
            self.skip_whitespace();
            self.expect(':')?;
            let value = self.parse_value()?;
            compound.set(key, value);

            self.skip_whitespace();
            let next = self.peek()?;

            if next == ',' {
                self.position += 1;
            } else if next == '}' {
                self.position += 1;
                return Ok(compound);
            } else {
                return Err(self.malformed(format!("Compound の区切りが不正: '{next}'")));
            }
        }
    }

    fn parse_list_or_array(&mut self) -> Result<NbtTag> {
        self.expect('[')?;

        // "[B;" のような型付き配列かどうかを先に判定する
        if self.position + 1 < self.chars.len() && self.chars[self.position + 1] == ';' {
            let marker = self.chars[self.position];

            if marker == 'B' || marker == 'I' || marker == 'L' {
                self.position += 2;
                return self.parse_typed_array(marker);
            }
        }

        Ok(NbtTag::List(self.parse_list()?))
    }

    fn parse_list(&mut self) -> Result<NbtList> {
        let mut list = NbtList::new();
        self.skip_whitespace();

        // 空のリスト
        if self.peek()? == ']' {
            self.position += 1;
            return Ok(list);
        }

        // 要素を 1 つずつ読む
        loop {
            self.skip_whitespace();

            // 末尾カンマの直後に閉じ括弧が来る形を許す
            if self.peek()? == ']' {
                self.position += 1;
                return Ok(list);
            }

            let value = self.parse_value()?;

            // 異種リストはバイナリ NBT へ写せないため受理しない (adr/0006)
            if list.element_type() != TagType::End && list.element_type() != value.tag_type() {
                return Err(self.malformed(format!(
                    "リストに異なる型が混在している: {} と {}",
                    list.element_type().as_str(),
                    value.tag_type().as_str()
                )));
            }

            list.push(value)?;

            self.skip_whitespace();
            let next = self.peek()?;

            if next == ',' {
                self.position += 1;
            } else if next == ']' {
                self.position += 1;
                return Ok(list);
            } else {
                return Err(self.malformed(format!("リストの区切りが不正: '{next}'")));
            }
        }
    }

    fn parse_typed_array(&mut self, marker: char) -> Result<NbtTag> {
        let mut values: Vec<i64> = Vec::new();
        self.skip_whitespace();

        // 空でなければ要素を読む
        if self.peek()? == ']' {
            self.position += 1;
        } else {
            loop {
                self.skip_whitespace();

                // 末尾カンマの直後に閉じ括弧が来る形を許す
                if self.peek()? == ']' {
                    self.position += 1;
                    break;
                }

                let element = self.parse_value()?;
                values.push(self.to_integral(&element)?);

                self.skip_whitespace();
                let next = self.peek()?;

                if next == ',' {
                    self.position += 1;
                } else if next == ']' {
                    self.position += 1;
                    break;
                } else {
                    return Err(self.malformed(format!("配列の区切りが不正: '{next}'")));
                }
            }
        }

        if marker == 'B' {
            let mut result: Vec<i8> = Vec::with_capacity(values.len());

            // 各要素が Byte の範囲に収まるか確認しながら詰める
            for value in &values {
                if *value < i8::MIN as i64 || *value > i8::MAX as i64 {
                    return Err(self.malformed(format!("ByteArray の要素が範囲外: {value}")));
                }

                result.push(*value as i8);
            }

            return Ok(NbtTag::ByteArray(result));
        }

        if marker == 'I' {
            let mut result: Vec<i32> = Vec::with_capacity(values.len());

            // 各要素が Int の範囲に収まるか確認しながら詰める
            for value in &values {
                if *value < i32::MIN as i64 || *value > i32::MAX as i64 {
                    return Err(self.malformed(format!("IntArray の要素が範囲外: {value}")));
                }

                result.push(*value as i32);
            }

            return Ok(NbtTag::IntArray(result));
        }

        Ok(NbtTag::LongArray(values))
    }

    /// 整数タグから値を取り出す。整数以外ならエラー。
    fn to_integral(&self, tag: &NbtTag) -> Result<i64> {
        match tag {
            NbtTag::Byte(value) => Ok(*value as i64),
            NbtTag::Short(value) => Ok(*value as i64),
            NbtTag::Int(value) => Ok(*value as i64),
            NbtTag::Long(value) => Ok(*value),
            other => Err(self.malformed(format!(
                "型付き配列の要素が整数でない: {}",
                other.tag_type().as_str()
            ))),
        }
    }

    fn parse_key(&mut self) -> Result<String> {
        let c = self.peek()?;

        if c == '"' || c == '\'' {
            let units = self.parse_quoted_string()?;

            return match String::from_utf16(&units) {
                Ok(text) => Ok(text),
                Err(_) => Err(self.malformed(
                    "Compound のキーが UTF-8 に写せない（孤立サロゲートを含む）".to_string(),
                )),
            };
        }

        let bare = self.read_bare_token();

        if bare.is_empty() {
            return Err(self.malformed("Compound のキーが空".to_string()));
        }

        Ok(bare)
    }

    /// 引用符つき文字列を UTF-16 コード単位の列として読む。
    ///
    /// `\uXXXX` で孤立サロゲートを書けるため、`String` ではなくコード単位で受ける。
    fn parse_quoted_string(&mut self) -> Result<Vec<u16>> {
        let quote = self.chars[self.position];
        self.position += 1;
        let mut units: Vec<u16> = Vec::new();

        // 閉じ引用符が来るまで読む
        loop {
            if self.position >= self.chars.len() {
                return Err(self.malformed("文字列が閉じられていない".to_string()));
            }

            let c = self.chars[self.position];

            if c == quote {
                self.position += 1;
                return Ok(units);
            }

            if c == '\\' {
                self.position += 1;
                self.read_escape(&mut units)?;
            } else {
                let mut buffer = [0u16; 2];
                units.extend_from_slice(c.encode_utf16(&mut buffer));
                self.position += 1;
            }
        }
    }

    fn read_escape(&mut self, units: &mut Vec<u16>) -> Result<()> {
        if self.position >= self.chars.len() {
            return Err(self.malformed("エスケープが途中で切れている".to_string()));
        }

        let c = self.chars[self.position];
        self.position += 1;

        let simple = match c {
            '\\' => Some('\\'),
            '"' => Some('"'),
            '\'' => Some('\''),
            'b' => Some('\u{0008}'),
            's' => Some(' '),
            't' => Some('\t'),
            'n' => Some('\n'),
            'f' => Some('\u{000C}'),
            'r' => Some('\r'),
            _ => None,
        };

        if let Some(value) = simple {
            let mut buffer = [0u16; 2];
            units.extend_from_slice(value.encode_utf16(&mut buffer));
            return Ok(());
        }

        if c == 'x' {
            units.push(self.read_hex_digits(2)? as u16);
            return Ok(());
        }

        if c == 'u' {
            // \uXXXX は UTF-16 コード単位を直接指定する。孤立サロゲートもここで書ける
            units.push(self.read_hex_digits(4)? as u16);
            return Ok(());
        }

        if c == 'U' {
            let code_point = self.read_hex_digits(8)?;

            // Unicode のコードポイント範囲を外れていないか確認する
            let value = match char::from_u32(code_point as u32) {
                Some(value) => value,
                None => {
                    return Err(
                        self.malformed(format!("コードポイントが範囲外: U+{code_point:X}"))
                    )
                }
            };

            let mut buffer = [0u16; 2];
            units.extend_from_slice(value.encode_utf16(&mut buffer));
            return Ok(());
        }

        if c == 'N' {
            return Err(self.read_named_character());
        }

        Err(self.malformed(format!("未知のエスケープ: '\\{c}'")))
    }

    fn read_hex_digits(&mut self, count: usize) -> Result<u64> {
        if self.position + count > self.chars.len() {
            return Err(self.malformed("エスケープの16進数字が足りない".to_string()));
        }

        let mut value: u64 = 0;

        // 指定桁数ぶん 16進数字を読む
        for offset in 0..count {
            let c = self.chars[self.position + offset];
            let digit = hex_digit_value(c);

            if digit < 0 {
                return Err(
                    self.malformed(format!("エスケープに16進数字でない文字がある: '{c}'"))
                );
            }

            value = (value * 16) + digit as u64;
        }

        self.position += count;
        Ok(value)
    }

    /// Unicode 文字名によるエスケープ `\N{...}` を読む。
    fn read_named_character(&mut self) -> Error {
        // 実装間で Unicode 文字名の表が揃わないため対応しない（C# / Rust には表が無い）
        let start = self.position;

        // 閉じ波括弧まで読み飛ばす
        while self.position < self.chars.len() && self.chars[self.position] != '}' {
            self.position += 1;
        }

        let name: String = self.chars[start..self.position].iter().collect();

        Error::new(
            ErrorCode::UnsupportedFeature,
            format!("文字名によるエスケープには対応していない: \\N{name}"),
        )
    }

    fn parse_unquoted(&mut self) -> Result<NbtTag> {
        let token = self.read_bare_token();

        if token.is_empty() {
            return Err(self.malformed(format!(
                "値が来るべき位置に解釈できない文字がある: '{}'",
                self.peek_or_nul()
            )));
        }

        // bool(...) / uuid(...) の関数呼び出し
        self.skip_whitespace();
        if self.peek_or_nul() == '(' && (token == "bool" || token == "uuid") {
            return self.parse_function(&token);
        }

        if token == "true" {
            return Ok(NbtTag::Byte(1));
        }

        if token == "false" {
            return Ok(NbtTag::Byte(0));
        }

        match self.try_parse_number(&token)? {
            Some(number) => Ok(number),
            None => Ok(NbtTag::String(NbtString::new(token))),
        }
    }

    fn parse_function(&mut self, name: &str) -> Result<NbtTag> {
        self.expect('(')?;
        let argument = self.parse_value()?;
        self.skip_whitespace();
        self.expect(')')?;

        if name == "bool" {
            // 0 以外を真とする
            if self.to_integral(&argument)? != 0 {
                return Ok(NbtTag::Byte(1));
            }

            return Ok(NbtTag::Byte(0));
        }

        self.uuid_to_int_array(&argument)
    }

    fn uuid_to_int_array(&self, argument: &NbtTag) -> Result<NbtTag> {
        let text = match argument {
            NbtTag::String(value) => match value.as_str() {
                Some(text) => text,
                None => {
                    return Err(self.malformed("uuid() の引数が UTF-8 に写せない".to_string()))
                }
            },
            _ => {
                return Err(
                    self.malformed("uuid() の引数は文字列でなければならない".to_string())
                )
            }
        };

        let hex: String = text.chars().filter(|c| *c != '-').collect();

        if hex.len() != 32 {
            return Err(self.malformed(format!("UUID として解釈できない: {text}")));
        }

        let mut values: Vec<i32> = Vec::with_capacity(4);

        // UUID を上位から 32bit ずつ 4 要素の IntArray へ写す
        for index in 0..4 {
            let chunk = &hex[index * 8..(index + 1) * 8];

            match u32::from_str_radix(chunk, 16) {
                Ok(value) => values.push(value as i32),
                Err(_) => return Err(self.malformed(format!("UUID として解釈できない: {text}"))),
            }
        }

        Ok(NbtTag::IntArray(values))
    }

    /// 数値トークンを解釈する。数値として読めなければ `None`（文字列として扱われる）。
    fn try_parse_number(&self, token: &str) -> Result<Option<NbtTag>> {
        let chars: Vec<char> = token.chars().collect();
        let mut negative = false;
        let mut start = 0usize;

        if chars[0] == '+' || chars[0] == '-' {
            negative = chars[0] == '-';
            start = 1;
        }

        let mut body: String = chars[start..].iter().collect();

        if body.is_empty() {
            return Ok(None);
        }

        let mut width_suffix = '\0';
        let mut unsigned_suffix = false;

        let is_hex = is_hex_body(&body);

        // 幅接尾辞を末尾から剥がす。16進では b/d/f が数字と紛れるため s/l だけを認める
        let last = body.chars().last().unwrap();
        let suffix_allowed = if is_hex {
            last == 's' || last == 'S' || last == 'l' || last == 'L'
        } else {
            WIDTH_SUFFIXES.contains(last)
        };

        if suffix_allowed && body.chars().count() >= 2 {
            width_suffix = last.to_ascii_lowercase();
            body.pop();

            // 符号接尾辞 u / s は幅接尾辞の手前に置かれる
            if body.chars().count() >= 2 {
                let sign_char = body.chars().last().unwrap();

                if sign_char == 'u' || sign_char == 'U' {
                    unsigned_suffix = true;
                    body.pop();
                } else if sign_char == 's' || sign_char == 'S' {
                    body.pop();
                }
            }
        }

        body = body.replace('_', "");

        if body.is_empty() {
            return Ok(None);
        }

        // 特殊な浮動小数点値
        if body == "Infinity" {
            return Ok(Some(self.make_floating(f64::INFINITY, negative, width_suffix)?));
        }

        if body == "NaN" {
            return Ok(Some(self.make_floating(f64::NAN, negative, width_suffix)?));
        }

        if is_hex_body(&body) {
            return self.parse_radix(&body[2..], 16, negative, width_suffix, unsigned_suffix);
        }

        if is_binary_body(&body) {
            return self.parse_radix(&body[2..], 2, negative, width_suffix, unsigned_suffix);
        }

        let looks_floating =
            body.contains('.') || body.contains('e') || body.contains('E');

        if looks_floating || width_suffix == 'f' || width_suffix == 'd' {
            return match body.parse::<f64>() {
                Ok(parsed) => Ok(Some(self.make_floating(parsed, negative, width_suffix)?)),
                Err(_) => Ok(None),
            };
        }

        self.parse_radix(&body, 10, negative, width_suffix, unsigned_suffix)
    }

    fn make_floating(&self, value: f64, negative: bool, width_suffix: char) -> Result<NbtTag> {
        let signed = if negative { -value } else { value };

        if width_suffix == 'f' {
            return Ok(NbtTag::Float(signed as f32));
        }

        // 接尾辞なしの小数は Double
        if width_suffix == '\0' || width_suffix == 'd' {
            return Ok(NbtTag::Double(signed));
        }

        Err(self.malformed(format!(
            "小数に整数の接尾辞 '{width_suffix}' は付けられない"
        )))
    }

    fn parse_radix(
        &self,
        digits: &str,
        radix: u64,
        negative: bool,
        width_suffix: char,
        unsigned_suffix: bool,
    ) -> Result<Option<NbtTag>> {
        if digits.is_empty() {
            return Ok(None);
        }

        let mut magnitude: u64 = 0;

        // 桁を1つずつ積み上げる。桁あふれはその場で検出する
        for c in digits.chars() {
            let digit = digit_value(c, radix);

            if digit < 0 {
                return Ok(None);
            }

            magnitude = match magnitude
                .checked_mul(radix)
                .and_then(|value| value.checked_add(digit as u64))
            {
                Some(value) => value,
                None => return Err(self.malformed(format!("整数が大きすぎる: {digits}"))),
            };
        }

        Ok(Some(self.make_integral(
            magnitude,
            negative,
            width_suffix,
            unsigned_suffix,
        )?))
    }

    fn make_integral(
        &self,
        magnitude: u64,
        negative: bool,
        width_suffix: char,
        unsigned_suffix: bool,
    ) -> Result<NbtTag> {
        if unsigned_suffix {
            // 符号なし指定は、その幅の符号なし最大値までを受け付けて符号付きへ読み替える
            return match width_suffix {
                'b' => Ok(NbtTag::Byte(
                    self.check_unsigned(magnitude, u8::MAX as u64)? as u8 as i8
                )),
                's' => Ok(NbtTag::Short(
                    self.check_unsigned(magnitude, u16::MAX as u64)? as u16 as i16,
                )),
                'l' => Ok(NbtTag::Long(magnitude as i64)),
                _ => Ok(NbtTag::Int(
                    self.check_unsigned(magnitude, u32::MAX as u64)? as u32 as i32
                )),
            };
        }

        let value = self.to_signed(magnitude, negative)?;

        match width_suffix {
            'b' => Ok(NbtTag::Byte(
                self.check_range(value, i8::MIN as i64, i8::MAX as i64, "byte")? as i8,
            )),
            's' => Ok(NbtTag::Short(
                self.check_range(value, i16::MIN as i64, i16::MAX as i64, "short")? as i16,
            )),
            'l' => Ok(NbtTag::Long(value)),
            'f' => Ok(NbtTag::Float(value as f32)),
            'd' => Ok(NbtTag::Double(value as f64)),
            // 接尾辞なしの整数は Int。暗黙に Long へ格上げしない
            _ => Ok(NbtTag::Int(self.check_range(
                value,
                i32::MIN as i64,
                i32::MAX as i64,
                "int",
            )? as i32)),
        }
    }

    fn check_unsigned(&self, magnitude: u64, max: u64) -> Result<u64> {
        if magnitude > max {
            return Err(self.malformed(format!(
                "符号なし整数が範囲外: {magnitude} (上限 {max})"
            )));
        }

        Ok(magnitude)
    }

    fn to_signed(&self, magnitude: u64, negative: bool) -> Result<i64> {
        if negative {
            // i64::MIN の絶対値は i64 に収まらないため個別に扱う
            if magnitude == 9223372036854775808 {
                return Ok(i64::MIN);
            }

            if magnitude > i64::MAX as u64 {
                return Err(self.malformed(format!("整数が小さすぎる: -{magnitude}")));
            }

            return Ok(-(magnitude as i64));
        }

        if magnitude > i64::MAX as u64 {
            return Err(self.malformed(format!("整数が大きすぎる: {magnitude}")));
        }

        Ok(magnitude as i64)
    }

    fn check_range(&self, value: i64, min: i64, max: i64, type_name: &str) -> Result<i64> {
        if value < min || value > max {
            return Err(self.malformed(format!("{type_name} の範囲外: {value}")));
        }

        Ok(value)
    }

    fn read_bare_token(&mut self) -> String {
        let start = self.position;

        // 引用符なしトークンに使える文字を読み進める
        while self.position < self.chars.len() && is_bare_char(self.chars[self.position]) {
            self.position += 1;
        }

        self.chars[start..self.position].iter().collect()
    }

    fn skip_whitespace(&mut self) {
        // 空白・改行・タブを読み飛ばす
        while self.position < self.chars.len() && self.chars[self.position].is_whitespace() {
            self.position += 1;
        }
    }

    fn peek(&self) -> Result<char> {
        if self.position >= self.chars.len() {
            return Err(self.malformed("入力が途中で尽きた".to_string()));
        }

        Ok(self.chars[self.position])
    }

    /// 末尾でもエラーにしない先読み。入力が尽きていれば NUL を返す。
    fn peek_or_nul(&self) -> char {
        if self.position >= self.chars.len() {
            return '\0';
        }

        self.chars[self.position]
    }

    fn expect(&mut self, expected: char) -> Result<()> {
        self.skip_whitespace();

        if self.position >= self.chars.len() {
            return Err(self.malformed(format!("'{expected}' が来るべき位置で入力が尽きた")));
        }

        if self.chars[self.position] != expected {
            return Err(self.malformed(format!(
                "'{expected}' を期待したが '{}' だった",
                self.chars[self.position]
            )));
        }

        self.position += 1;
        Ok(())
    }

    fn malformed(&self, message: String) -> Error {
        Error::new(
            ErrorCode::MalformedData,
            format!("SNBT ({} 文字目): {message}", self.position),
        )
    }
}

fn is_hex_body(body: &str) -> bool {
    let chars: Vec<char> = body.chars().collect();
    chars.len() > 2 && chars[0] == '0' && (chars[1] == 'x' || chars[1] == 'X')
}

fn is_binary_body(body: &str) -> bool {
    let chars: Vec<char> = body.chars().collect();

    if !(chars.len() > 2 && chars[0] == '0' && (chars[1] == 'b' || chars[1] == 'B')) {
        return false;
    }

    // 2進リテラルの本体は 0 と 1 だけ
    for c in &chars[2..] {
        if *c != '0' && *c != '1' {
            return false;
        }
    }

    true
}

fn digit_value(c: char, radix: u64) -> i32 {
    let value = hex_digit_value(c);

    if value < 0 || value as u64 >= radix {
        return -1;
    }

    value
}

fn hex_digit_value(c: char) -> i32 {
    if c.is_ascii_digit() {
        return c as i32 - '0' as i32;
    }

    if ('a'..='f').contains(&c) {
        return c as i32 - 'a' as i32 + 10;
    }

    if ('A'..='F').contains(&c) {
        return c as i32 - 'A' as i32 + 10;
    }

    -1
}

/// 引用符なしで書ける文字か。
fn is_bare_char(c: char) -> bool {
    if c.is_ascii_alphanumeric() {
        return true;
    }

    c == '_' || c == '-' || c == '.' || c == '+'
}

// ---------------------------------------------------------------------------
// ライタ
// ---------------------------------------------------------------------------

/// タグを書き出す。`depth` が負なら 1 行、0 以上なら整形して出力する。
fn write_tag(out: &mut String, tag: &NbtTag, depth: i32) {
    match tag {
        NbtTag::Byte(value) => {
            out.push_str(&value.to_string());
            out.push('b');
        }
        NbtTag::Short(value) => {
            out.push_str(&value.to_string());
            out.push('s');
        }
        NbtTag::Int(value) => out.push_str(&value.to_string()),
        NbtTag::Long(value) => {
            out.push_str(&value.to_string());
            out.push('L');
        }
        NbtTag::Float(value) => {
            out.push_str(&canonical::from_f32(*value));
            out.push('f');
        }
        NbtTag::Double(value) => {
            out.push_str(&canonical::from_f64(*value));
            out.push('d');
        }
        NbtTag::String(value) => out.push_str(&quote_string(&value.to_utf16())),
        NbtTag::ByteArray(values) => write_typed_array(out, 'B', values, "B"),
        NbtTag::IntArray(values) => write_typed_array(out, 'I', values, ""),
        NbtTag::LongArray(values) => write_typed_array(out, 'L', values, "L"),
        NbtTag::List(value) => write_list(out, value, depth),
        NbtTag::Compound(value) => write_compound(out, value, depth),
    }
}

fn write_compound(out: &mut String, compound: &NbtCompound, depth: i32) {
    if compound.is_empty() {
        out.push_str("{}");
        return;
    }

    out.push('{');
    let mut first = true;

    // 挿入順のまま「キー: 値」を並べる
    for (key, value) in compound.iter() {
        if !first {
            out.push(',');
        }

        first = false;
        append_separator(out, next_depth(depth));
        out.push_str(&quote_key(key));
        out.push(':');

        // 整形時はコロンの後に空白を入れて読みやすくする
        if depth >= 0 {
            out.push(' ');
        }

        write_tag(out, value, next_depth(depth));
    }

    append_separator(out, depth);
    out.push('}');
}

fn write_list(out: &mut String, list: &NbtList, depth: i32) {
    if list.is_empty() {
        out.push_str("[]");
        return;
    }

    out.push('[');
    let mut first = true;

    // 要素型は共通なので値だけを並べる
    for item in list.iter() {
        if !first {
            out.push(',');
        }

        first = false;
        append_separator(out, next_depth(depth));
        write_tag(out, item, next_depth(depth));
    }

    append_separator(out, depth);
    out.push(']');
}

fn write_typed_array<T: std::fmt::Display>(
    out: &mut String,
    marker: char,
    values: &[T],
    element_suffix: &str,
) {
    out.push('[');
    out.push(marker);
    out.push(';');

    // 型付き配列は 1 行に収める
    for (index, value) in values.iter().enumerate() {
        if index > 0 {
            out.push(',');
        }

        out.push_str(&value.to_string());
        out.push_str(element_suffix);
    }

    out.push(']');
}

/// 整形出力なら改行とインデントを、1 行出力なら何も入れない。
fn append_separator(out: &mut String, depth: i32) {
    if depth < 0 {
        return;
    }

    out.push('\n');

    // 深さぶんインデントを積む
    for _ in 0..depth {
        out.push_str(INDENT_UNIT);
    }
}

/// 整形出力のときだけ深さを 1 段進める。
fn next_depth(depth: i32) -> i32 {
    if depth < 0 {
        return -1;
    }

    depth + 1
}

/// キーを出力する。引用符なしで書ける場合はそのまま出す。
fn quote_key(key: &str) -> String {
    if is_bare_writable(key) {
        return key.to_string();
    }

    quote_string(&key.encode_utf16().collect::<Vec<u16>>())
}

fn is_bare_writable(text: &str) -> bool {
    if text.is_empty() {
        return false;
    }

    // 引用符なしで書ける文字だけで構成されているか調べる
    for c in text.chars() {
        if !is_bare_char(c) {
            return false;
        }
    }

    true
}

/// 文字列を二重引用符で囲み、必要な文字だけエスケープする。
///
/// UTF-16 コード単位で処理するのは、正しいサロゲートペアと孤立サロゲートを
/// 区別するため。C# / Java と同じ判定にしないと出力が食い違う。
fn quote_string(units: &[u16]) -> String {
    let mut out = String::from("\"");
    let mut index = 0usize;

    // 1 コード単位ずつ見てエスケープが要るものだけ置き換える
    while index < units.len() {
        let unit = units[index];

        match unit {
            0x22 => out.push_str("\\\""),
            0x5C => out.push_str("\\\\"),
            0x08 => out.push_str("\\b"),
            0x09 => out.push_str("\\t"),
            0x0A => out.push_str("\\n"),
            0x0C => out.push_str("\\f"),
            0x0D => out.push_str("\\r"),
            _ => {
                // 正しいサロゲートペアはそのまま出す
                if (0xD800..=0xDBFF).contains(&unit)
                    && index + 1 < units.len()
                    && (0xDC00..=0xDFFF).contains(&units[index + 1])
                {
                    let code = 0x10000
                        + (((unit as u32) - 0xD800) << 10)
                        + ((units[index + 1] as u32) - 0xDC00);

                    if let Some(value) = char::from_u32(code) {
                        out.push(value);
                    }

                    index += 1;
                } else if unit < 0x20 || unit == 0x7F || (0xD800..=0xDFFF).contains(&unit) {
                    // 制御文字と孤立サロゲートは \uXXXX で表す
                    out.push_str(&format!("\\u{unit:04x}"));
                } else if let Some(value) = char::from_u32(unit as u32) {
                    out.push(value);
                }
            }
        }

        index += 1;
    }

    out.push('"');
    out
}

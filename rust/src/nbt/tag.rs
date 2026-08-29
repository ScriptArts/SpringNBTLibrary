//! NBT のタグ型と値モデル。
//!
//! 仕様: `docs/spec/10-nbt-binary.md` 1章・7章

use std::collections::HashMap;

use crate::error::{Error, ErrorCode, Result};
use crate::nbt::mutf8;

/// NBT のタグ型。値は仕様が定めるタグIDと一致する。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum TagType {
    /// TAG_End (0)。Compound の終端を表す。
    End,
    /// TAG_Byte (1)。
    Byte,
    /// TAG_Short (2)。
    Short,
    /// TAG_Int (3)。
    Int,
    /// TAG_Long (4)。
    Long,
    /// TAG_Float (5)。
    Float,
    /// TAG_Double (6)。
    Double,
    /// TAG_Byte_Array (7)。
    ByteArray,
    /// TAG_String (8)。
    String,
    /// TAG_List (9)。
    List,
    /// TAG_Compound (10)。
    Compound,
    /// TAG_Int_Array (11)。
    IntArray,
    /// TAG_Long_Array (12)。
    LongArray,
}

impl TagType {
    /// 仕様が定めるタグID。
    pub fn id(self) -> u8 {
        match self {
            TagType::End => 0,
            TagType::Byte => 1,
            TagType::Short => 2,
            TagType::Int => 3,
            TagType::Long => 4,
            TagType::Float => 5,
            TagType::Double => 6,
            TagType::ByteArray => 7,
            TagType::String => 8,
            TagType::List => 9,
            TagType::Compound => 10,
            TagType::IntArray => 11,
            TagType::LongArray => 12,
        }
    }

    /// 適合性テストで言語間比較に使う識別子。
    pub fn as_str(self) -> &'static str {
        match self {
            TagType::End => "end",
            TagType::Byte => "byte",
            TagType::Short => "short",
            TagType::Int => "int",
            TagType::Long => "long",
            TagType::Float => "float",
            TagType::Double => "double",
            TagType::ByteArray => "byte_array",
            TagType::String => "string",
            TagType::List => "list",
            TagType::Compound => "compound",
            TagType::IntArray => "int_array",
            TagType::LongArray => "long_array",
        }
    }

    /// タグIDから [`TagType`] を得る。未知のIDならエラー。
    pub fn from_id(id: u8) -> Result<TagType> {
        match id {
            0 => Ok(TagType::End),
            1 => Ok(TagType::Byte),
            2 => Ok(TagType::Short),
            3 => Ok(TagType::Int),
            4 => Ok(TagType::Long),
            5 => Ok(TagType::Float),
            6 => Ok(TagType::Double),
            7 => Ok(TagType::ByteArray),
            8 => Ok(TagType::String),
            9 => Ok(TagType::List),
            10 => Ok(TagType::Compound),
            11 => Ok(TagType::IntArray),
            12 => Ok(TagType::LongArray),
            // 0..12 の範囲外はすべて不正なタグID
            other => Err(Error::new(
                ErrorCode::MalformedData,
                format!("未知のタグID: {other}"),
            )),
        }
    }
}

/// TAG_String の値。
///
/// Rust の [`String`] は UTF-8 の不変条件を持つため、
/// 孤立サロゲートを含む文字列をそのまま保持できない。
/// 他の3言語（C# / Java / Python）は UTF-16 相当でそれを保持できてしまうので、
/// ここだけ表現を分けて往復性を保っている。
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum NbtString {
    /// UTF-8 として表せる通常の文字列。実データはほぼすべてこちら。
    Text(String),
    /// UTF-8 に写せない UTF-16 コード単位の列（孤立サロゲートを含む場合）。
    Surrogates(Vec<u16>),
}

impl NbtString {
    /// 文字列から作る。
    pub fn new(text: impl Into<String>) -> NbtString {
        NbtString::Text(text.into())
    }

    /// UTF-16 コード単位の列から作る。UTF-8 に写せなければ [`NbtString::Surrogates`] になる。
    pub fn from_utf16(units: Vec<u16>) -> NbtString {
        match String::from_utf16(&units) {
            Ok(text) => NbtString::Text(text),
            // 孤立サロゲートを含む場合はコード単位のまま保持する
            Err(_) => NbtString::Surrogates(units),
        }
    }

    /// UTF-8 として表せる場合だけ文字列を返す。
    pub fn as_str(&self) -> Option<&str> {
        match self {
            NbtString::Text(text) => Some(text.as_str()),
            NbtString::Surrogates(_) => None,
        }
    }

    /// UTF-16 コード単位の列を返す。
    pub fn to_utf16(&self) -> Vec<u16> {
        match self {
            NbtString::Text(text) => text.encode_utf16().collect(),
            NbtString::Surrogates(units) => units.clone(),
        }
    }

    /// MUTF-8 バイト列を返す。
    pub fn to_mutf8(&self) -> Vec<u8> {
        mutf8::encode_from_utf16(&self.to_utf16())
    }

    /// MUTF-8 で符号化したときのバイト長。
    pub fn mutf8_len(&self) -> usize {
        self.to_mutf8().len()
    }
}

impl From<&str> for NbtString {
    fn from(value: &str) -> Self {
        NbtString::Text(value.to_string())
    }
}

impl From<String> for NbtString {
    fn from(value: String) -> Self {
        NbtString::Text(value)
    }
}

/// NBT のタグ。
///
/// 仕様: `docs/spec/10-nbt-binary.md` 1章
#[derive(Debug, Clone)]
pub enum NbtTag {
    /// TAG_Byte。
    Byte(i8),
    /// TAG_Short。
    Short(i16),
    /// TAG_Int。
    Int(i32),
    /// TAG_Long。
    Long(i64),
    /// TAG_Float。
    Float(f32),
    /// TAG_Double。
    Double(f64),
    /// TAG_Byte_Array。
    ByteArray(Vec<i8>),
    /// TAG_String。
    String(NbtString),
    /// TAG_List。
    List(NbtList),
    /// TAG_Compound。
    Compound(NbtCompound),
    /// TAG_Int_Array。
    IntArray(Vec<i32>),
    /// TAG_Long_Array。
    LongArray(Vec<i64>),
}

impl NbtTag {
    /// このタグの型。
    pub fn tag_type(&self) -> TagType {
        match self {
            NbtTag::Byte(_) => TagType::Byte,
            NbtTag::Short(_) => TagType::Short,
            NbtTag::Int(_) => TagType::Int,
            NbtTag::Long(_) => TagType::Long,
            NbtTag::Float(_) => TagType::Float,
            NbtTag::Double(_) => TagType::Double,
            NbtTag::ByteArray(_) => TagType::ByteArray,
            NbtTag::String(_) => TagType::String,
            NbtTag::List(_) => TagType::List,
            NbtTag::Compound(_) => TagType::Compound,
            NbtTag::IntArray(_) => TagType::IntArray,
            NbtTag::LongArray(_) => TagType::LongArray,
        }
    }
}

impl PartialEq for NbtTag {
    fn eq(&self, other: &Self) -> bool {
        match (self, other) {
            (NbtTag::Byte(a), NbtTag::Byte(b)) => a == b,
            (NbtTag::Short(a), NbtTag::Short(b)) => a == b,
            (NbtTag::Int(a), NbtTag::Int(b)) => a == b,
            (NbtTag::Long(a), NbtTag::Long(b)) => a == b,
            // NaN や -0.0 を区別するため、値ではなくビットパターンで比較する
            (NbtTag::Float(a), NbtTag::Float(b)) => a.to_bits() == b.to_bits(),
            (NbtTag::Double(a), NbtTag::Double(b)) => a.to_bits() == b.to_bits(),
            (NbtTag::ByteArray(a), NbtTag::ByteArray(b)) => a == b,
            (NbtTag::String(a), NbtTag::String(b)) => a == b,
            (NbtTag::List(a), NbtTag::List(b)) => a == b,
            (NbtTag::Compound(a), NbtTag::Compound(b)) => a == b,
            (NbtTag::IntArray(a), NbtTag::IntArray(b)) => a == b,
            (NbtTag::LongArray(a), NbtTag::LongArray(b)) => a == b,
            _ => false,
        }
    }
}

/// TAG_List。要素型が 1 つに固定されたタグの列。
///
/// 空リストの要素型は [`TagType::End`]。最初の要素を追加した時点で型が確定する。
/// 全要素を削除しても確定済みの要素型は維持される
/// （読み書きの往復で型が消えないようにするため）。
#[derive(Debug, Clone, PartialEq)]
pub struct NbtList {
    element_type: TagType,
    items: Vec<NbtTag>,
}

impl NbtList {
    /// 空のリストを作る。要素型は未確定。
    pub fn new() -> NbtList {
        NbtList { element_type: TagType::End, items: Vec::new() }
    }

    /// 要素型を明示して空のリストを作る。
    pub fn with_element_type(element_type: TagType) -> NbtList {
        NbtList { element_type, items: Vec::new() }
    }

    /// 要素の型。空で未確定なら [`TagType::End`]。
    pub fn element_type(&self) -> TagType {
        self.element_type
    }

    /// 要素数。
    pub fn len(&self) -> usize {
        self.items.len()
    }

    /// 空かどうか。
    pub fn is_empty(&self) -> bool {
        self.items.is_empty()
    }

    /// 位置を指定して取り出す。
    pub fn get(&self, index: usize) -> Option<&NbtTag> {
        self.items.get(index)
    }

    /// 末尾に追加する。要素型と一致しなければエラー。
    pub fn push(&mut self, item: NbtTag) -> Result<()> {
        self.ensure_element_type(&item)?;
        self.items.push(item);
        Ok(())
    }

    /// 位置を指定して挿入する。
    pub fn insert(&mut self, index: usize, item: NbtTag) -> Result<()> {
        self.ensure_element_type(&item)?;
        self.items.insert(index, item);
        Ok(())
    }

    /// 位置を指定して削除する。
    pub fn remove_at(&mut self, index: usize) -> NbtTag {
        self.items.remove(index)
    }

    /// 全要素を削除する。確定済みの要素型は維持する。
    pub fn clear(&mut self) {
        self.items.clear();
    }

    /// 要素を順に走査する。
    pub fn iter(&self) -> std::slice::Iter<'_, NbtTag> {
        self.items.iter()
    }

    /// 追加しようとしているタグが要素型と一致するか調べる。
    fn ensure_element_type(&mut self, item: &NbtTag) -> Result<()> {
        let incoming = item.tag_type();

        if self.element_type == TagType::End {
            // 未確定のリストは最初の要素で型が決まる
            self.element_type = incoming;
            Ok(())
        } else if self.element_type != incoming {
            Err(Error::new(
                ErrorCode::UnexpectedTagType,
                format!(
                    "リストの要素型は {} だが {} を追加しようとした",
                    self.element_type.as_str(),
                    incoming.as_str()
                ),
            ))
        } else {
            Ok(())
        }
    }
}

impl Default for NbtList {
    fn default() -> Self {
        NbtList::new()
    }
}

impl<'a> IntoIterator for &'a NbtList {
    type Item = &'a NbtTag;
    type IntoIter = std::slice::Iter<'a, NbtTag>;

    fn into_iter(self) -> Self::IntoIter {
        self.items.iter()
    }
}

/// TAG_Compound。挿入順を保持する、名前付きタグのマップ。
///
/// 既存キーへの再設定は位置を維持したまま値だけを置き換える。
/// これにより読み込んだ順序が書き出しでも保たれ、ラウンドトリップが成立する。
#[derive(Debug, Clone, Default)]
pub struct NbtCompound {
    entries: Vec<(String, NbtTag)>,
    index: HashMap<String, usize>,
}

impl NbtCompound {
    /// 空の Compound を作る。
    pub fn new() -> NbtCompound {
        NbtCompound { entries: Vec::new(), index: HashMap::new() }
    }

    /// 要素数。
    pub fn len(&self) -> usize {
        self.entries.len()
    }

    /// 空かどうか。
    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    /// キーが存在するか。
    pub fn contains_key(&self, key: &str) -> bool {
        self.index.contains_key(key)
    }

    /// 挿入順のキー一覧。
    pub fn keys(&self) -> impl Iterator<Item = &str> {
        self.entries.iter().map(|entry| entry.0.as_str())
    }

    /// 挿入順の (キー, タグ) の並び。
    pub fn iter(&self) -> std::slice::Iter<'_, (String, NbtTag)> {
        self.entries.iter()
    }

    /// 値を設定する。既存キーなら位置を維持して値だけ置き換える。
    pub fn set(&mut self, key: impl Into<String>, value: NbtTag) {
        let key = key.into();

        match self.index.get(&key) {
            // 既存キーは順序を変えずに値だけ差し替える
            Some(&position) => {
                self.entries[position].1 = value;
            }
            None => {
                self.index.insert(key.clone(), self.entries.len());
                self.entries.push((key, value));
            }
        }
    }

    /// キーに対応するタグを返す。存在しなければ `None`。
    pub fn opt(&self, key: &str) -> Option<&NbtTag> {
        match self.index.get(key) {
            Some(&position) => Some(&self.entries[position].1),
            None => None,
        }
    }

    /// キーに対応するタグを返す。存在しなければエラー。
    pub fn get(&self, key: &str) -> Result<&NbtTag> {
        match self.opt(key) {
            Some(tag) => Ok(tag),
            None => Err(Error::new(
                ErrorCode::InvalidArgument,
                format!("キーが存在しない: {key}"),
            )),
        }
    }

    /// キーを削除する。削除できたら `true`。
    pub fn remove(&mut self, key: &str) -> bool {
        let position = match self.index.remove(key) {
            Some(position) => position,
            None => return false,
        };

        self.entries.remove(position);

        // 削除位置より後ろのキーは添字がひとつ前へずれる
        for (offset, entry) in self.entries.iter().enumerate().skip(position) {
            self.index.insert(entry.0.clone(), offset);
        }

        true
    }

    /// 全要素を削除する。
    pub fn clear(&mut self) {
        self.entries.clear();
        self.index.clear();
    }
}

impl PartialEq for NbtCompound {
    fn eq(&self, other: &Self) -> bool {
        // 順序も含めて一致することを確認する
        self.entries == other.entries
    }
}

impl<'a> IntoIterator for &'a NbtCompound {
    type Item = &'a (String, NbtTag);
    type IntoIter = std::slice::Iter<'a, (String, NbtTag)>;

    fn into_iter(self) -> Self::IntoIter {
        self.entries.iter()
    }
}

/// 型付き取得子。
///
/// 「キーが無い」と「型が違う」は区別する。
/// `opt_*` はキーが無ければ `None` を返し、`get_*` はエラーにする。
/// どちらも型が違えば必ず [`ErrorCode::UnexpectedTagType`] になる。
impl NbtCompound {
    fn wrong_type(key: &str, actual: TagType, expected: &str) -> Error {
        Error::new(
            ErrorCode::UnexpectedTagType,
            format!(
                "キー \"{key}\" は {} だが {expected} として取り出そうとした",
                actual.as_str()
            ),
        )
    }

    fn missing(key: &str) -> Error {
        Error::new(ErrorCode::InvalidArgument, format!("キーが存在しない: {key}"))
    }
}

/// スカラ型の取得子を生やすためのマクロ。
///
/// 6 種類ぶんを手で書くと差分が生まれやすいので、1 か所から展開する。
/// 参照を返す取得子は寿命の注釈が要るため、マクロにせず個別に書く。
macro_rules! scalar_accessors {
    ($opt:ident, $get:ident, $variant:ident, $ret:ty, $label:literal) => {
        impl NbtCompound {
            #[doc = concat!("TAG_", $label, " を取得する。キーが無ければ `None`。")]
            pub fn $opt(&self, key: &str) -> Result<Option<$ret>> {
                match self.opt(key) {
                    None => Ok(None),
                    Some(NbtTag::$variant(value)) => Ok(Some(*value)),
                    Some(other) => Err(NbtCompound::wrong_type(key, other.tag_type(), $label)),
                }
            }

            #[doc = concat!("TAG_", $label, " を取得する。キーが無ければエラー。")]
            pub fn $get(&self, key: &str) -> Result<$ret> {
                match self.$opt(key)? {
                    Some(value) => Ok(value),
                    None => Err(NbtCompound::missing(key)),
                }
            }
        }
    };
}

scalar_accessors!(opt_byte, get_byte, Byte, i8, "Byte");
scalar_accessors!(opt_short, get_short, Short, i16, "Short");
scalar_accessors!(opt_int, get_int, Int, i32, "Int");
scalar_accessors!(opt_long, get_long, Long, i64, "Long");
scalar_accessors!(opt_float, get_float, Float, f32, "Float");
scalar_accessors!(opt_double, get_double, Double, f64, "Double");

/// 参照を返す取得子を生やすためのマクロ。
macro_rules! ref_accessors {
    ($opt:ident, $get:ident, $variant:ident, $ret:ty, $label:literal, $convert:ident) => {
        impl NbtCompound {
            #[doc = concat!("TAG_", $label, " を取得する。キーが無ければ `None`。")]
            pub fn $opt(&self, key: &str) -> Result<Option<&$ret>> {
                match self.opt(key) {
                    None => Ok(None),
                    Some(NbtTag::$variant(value)) => Ok(Some(value.$convert())),
                    Some(other) => Err(NbtCompound::wrong_type(key, other.tag_type(), $label)),
                }
            }

            #[doc = concat!("TAG_", $label, " を取得する。キーが無ければエラー。")]
            pub fn $get(&self, key: &str) -> Result<&$ret> {
                match self.$opt(key)? {
                    Some(value) => Ok(value),
                    None => Err(NbtCompound::missing(key)),
                }
            }
        }
    };
}

ref_accessors!(opt_byte_array, get_byte_array, ByteArray, [i8], "Byte_Array", as_slice);
ref_accessors!(opt_int_array, get_int_array, IntArray, [i32], "Int_Array", as_slice);
ref_accessors!(opt_long_array, get_long_array, LongArray, [i64], "Long_Array", as_slice);

impl NbtCompound {
    /// TAG_String を [`NbtString`] のまま取得する。キーが無ければ `None`。
    pub fn opt_string_tag(&self, key: &str) -> Result<Option<&NbtString>> {
        match self.opt(key) {
            None => Ok(None),
            Some(NbtTag::String(value)) => Ok(Some(value)),
            Some(other) => Err(NbtCompound::wrong_type(key, other.tag_type(), "String")),
        }
    }

    /// TAG_String を [`NbtString`] のまま取得する。キーが無ければエラー。
    pub fn get_string_tag(&self, key: &str) -> Result<&NbtString> {
        match self.opt_string_tag(key)? {
            Some(value) => Ok(value),
            None => Err(NbtCompound::missing(key)),
        }
    }

    /// TAG_List を取得する。キーが無ければ `None`。
    pub fn opt_list(&self, key: &str) -> Result<Option<&NbtList>> {
        match self.opt(key) {
            None => Ok(None),
            Some(NbtTag::List(value)) => Ok(Some(value)),
            Some(other) => Err(NbtCompound::wrong_type(key, other.tag_type(), "List")),
        }
    }

    /// TAG_List を取得する。キーが無ければエラー。
    pub fn get_list(&self, key: &str) -> Result<&NbtList> {
        match self.opt_list(key)? {
            Some(value) => Ok(value),
            None => Err(NbtCompound::missing(key)),
        }
    }

    /// TAG_Compound を取得する。キーが無ければ `None`。
    pub fn opt_compound(&self, key: &str) -> Result<Option<&NbtCompound>> {
        match self.opt(key) {
            None => Ok(None),
            Some(NbtTag::Compound(value)) => Ok(Some(value)),
            Some(other) => Err(NbtCompound::wrong_type(key, other.tag_type(), "Compound")),
        }
    }

    /// TAG_Compound を取得する。キーが無ければエラー。
    pub fn get_compound(&self, key: &str) -> Result<&NbtCompound> {
        match self.opt_compound(key)? {
            Some(value) => Ok(value),
            None => Err(NbtCompound::missing(key)),
        }
    }
}

impl NbtCompound {
    /// TAG_String を UTF-8 文字列として取得する。キーが無ければ `None`。
    ///
    /// 孤立サロゲートを含む文字列はエラーになる。その場合は
    /// [`NbtCompound::opt_string_tag`] で [`NbtString`] のまま取り出す。
    pub fn opt_string(&self, key: &str) -> Result<Option<&str>> {
        match self.opt_string_tag(key)? {
            None => Ok(None),
            Some(tag) => match tag.as_str() {
                Some(text) => Ok(Some(text)),
                None => Err(Error::new(
                    ErrorCode::UnexpectedTagType,
                    format!("キー \"{key}\" の文字列は UTF-8 に写せない（孤立サロゲートを含む）"),
                )),
            },
        }
    }

    /// TAG_String を UTF-8 文字列として取得する。キーが無ければエラー。
    pub fn get_string(&self, key: &str) -> Result<&str> {
        match self.opt_string(key)? {
            Some(text) => Ok(text),
            None => Err(NbtCompound::missing(key)),
        }
    }

    /// TAG_Byte を真偽値として取得する。0 以外が `true`。キーが無ければ `None`。
    pub fn opt_bool(&self, key: &str) -> Result<Option<bool>> {
        match self.opt_byte(key)? {
            Some(value) => Ok(Some(value != 0)),
            None => Ok(None),
        }
    }

    /// TAG_Byte を真偽値として取得する。0 以外が `true`。キーが無ければエラー。
    pub fn get_bool(&self, key: &str) -> Result<bool> {
        Ok(self.get_byte(key)? != 0)
    }
}

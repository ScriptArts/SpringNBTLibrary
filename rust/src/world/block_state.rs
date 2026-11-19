//! ブロックの状態
//! 名前と、任意のプロパティの組
//!
//! プロパティは**常に名前の昇順で保持する**
//! こうしておくと文字列表現が一意になり、全言語で同じ出力になる
//! Minecraftが書き出した並び順は、[`super::PalettedContainer`]がパレットを生のNBTのまま持つことで守られる
//! そのため、触っていないブロックの並びが崩れることはない

use std::borrow::Cow;
use std::collections::BTreeMap;
use std::fmt;

use crate::error::{Error, ErrorCode, Result};
use crate::nbt::tag::{NbtCompound, NbtString, NbtTag};

use super::chunk_format::{OLDEST_FORMAT_DATA_VERSION, PALETTE_ID_FORMAT_DATA_VERSION};
use super::paletted_container::unwrap_list_element;

/// ブロックの状態
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BlockState {
    name: String,
    properties: BTreeMap<String, String>,
}

/// [`Chunk::set_block`](crate::world::Chunk::set_block)へ渡せるもの
///
/// 他の言語ではオーバーロードで済むが、Rustには無いのでトレイトで受ける
/// `&BlockState`と`&str`の両方をそのまま渡せる
///
/// [`Cow`]を返すのは、すでに[`BlockState`]を持っているときに複製を作らないようにするためである
/// 1ブロックずつ置く用途では、この複製が積み重なって無視できなくなる
pub trait IntoBlockState {
    /// ブロック状態として借りる
    /// 文字列から作った場合だけ、その場で組み立てたものを返す
    fn as_block_state(&self) -> Result<Cow<'_, BlockState>>;
}

impl IntoBlockState for BlockState {
    fn as_block_state(&self) -> Result<Cow<'_, BlockState>> {
        Ok(Cow::Borrowed(self))
    }
}

impl IntoBlockState for str {
    fn as_block_state(&self) -> Result<Cow<'_, BlockState>> {
        Ok(Cow::Owned(BlockState::parse(self)?))
    }
}

impl BlockState {
    /// 名前とプロパティを指定して作る
    ///
    /// 名前空間が省略されていたら`minecraft:`を補う
    pub fn new(name: impl AsRef<str>, properties: BTreeMap<String, String>) -> BlockState {
        BlockState { name: normalize(name.as_ref()), properties }
    }

    /// プロパティを持たない状態を作る
    pub fn of(name: impl AsRef<str>) -> BlockState {
        BlockState::new(name, BTreeMap::new())
    }

    /// ブロックID（名前空間つき）
    pub fn name(&self) -> &str {
        &self.name
    }

    /// プロパティ
    /// 名前の昇順
    pub fn properties(&self) -> &BTreeMap<String, String> {
        &self.properties
    }

    /// プロパティを取得する
    /// 無ければ`None`
    pub fn property(&self, key: &str) -> Option<&str> {
        self.properties.get(key).map(|value| value.as_str())
    }

    /// プロパティを1つ差し替えた新しい状態を返す
    pub fn with(&self, key: impl Into<String>, value: impl Into<String>) -> BlockState {
        let mut result = self.clone();
        result.properties.insert(key.into(), value.into());
        result
    }

    /// `minecraft:oak_stairs[facing=north,half=top]`形式の文字列から作る
    pub fn parse(text: &str) -> Result<BlockState> {
        let bracket = match text.find('[') {
            Some(position) => position,
            None => {
                if text.is_empty() {
                    return Err(Error::new(ErrorCode::InvalidArgument, "ブロック名が空"));
                }

                return Ok(BlockState::of(text));
            }
        };

        if !text.ends_with(']') {
            return Err(Error::new(
                ErrorCode::InvalidArgument,
                format!("角括弧が閉じられていない: {text}"),
            ));
        }

        let body = &text[bracket + 1..text.len() - 1];
        let mut properties = BTreeMap::new();

        if !body.is_empty() {
            // "key=value"をカンマ区切りで読む
            for pair in body.split(',') {
                let equals = match pair.find('=') {
                    Some(position) => position,
                    None => {
                        return Err(Error::new(
                            ErrorCode::InvalidArgument,
                            format!("プロパティに '=' が無い: {pair}"),
                        ))
                    }
                };

                let key = pair[..equals].trim();

                if key.is_empty() {
                    return Err(Error::new(
                        ErrorCode::InvalidArgument,
                        format!("プロパティ名が空: {pair}"),
                    ));
                }

                // どちらが採用されたか分からないまま書き込まれるのを避けるため、重複は弾く
                if properties.contains_key(key) {
                    return Err(Error::new(
                        ErrorCode::InvalidArgument,
                        format!("プロパティ名が重複している: {key}"),
                    ));
                }

                properties.insert(key.to_string(), pair[equals + 1..].trim().to_string());
            }
        }

        Ok(BlockState::new(&text[..bracket], properties))
    }

    /// パレット要素のNBTから作る
    ///
    /// [`TARGET_DATA_VERSION`](crate::TARGET_DATA_VERSION)の形式で読む
    /// DataVersionを指定するときは[`BlockState::from_nbt_for_data_version`]を使う
    ///
    /// 文字列でもCompoundでもない、`id`が無い、または`properties`の値が文字列でない場合はエラー
    pub fn from_nbt(nbt: &NbtTag) -> Result<BlockState> {
        from_palette_id(nbt)
    }

    /// DataVersionを指定して、パレット要素のNBTから作る
    ///
    /// 26.3（DataVersion 5006）以降は、既定の状態がブロックIDだけの文字列で、それ以外は`id`と`properties`を持つCompoundで入っている
    /// 異種リストの要素を包む`{"": <値>}`は外してから読む
    /// 1519以上5006未満は、`Name`と`Properties`を持つCompoundを読む
    /// 文字列は受け付けない
    ///
    /// `data_version`はパレット要素を含むチャンクのDataVersionで、1519以上でなければならない
    /// 1519未満の場合（`InvalidArgument`）、要素が形式に合うタグでない場合、`id` / `Name`が無い場合、またはプロパティの値が文字列でない場合はエラー
    pub fn from_nbt_for_data_version(nbt: &NbtTag, data_version: i32) -> Result<BlockState> {
        check_data_version(data_version)?;

        // 26.3より前は、Name / Propertiesの形式で入っている
        if data_version < PALETTE_ID_FORMAT_DATA_VERSION {
            return from_name_properties(nbt);
        }

        from_palette_id(nbt)
    }

    /// パレット要素のNBTへ変換する
    ///
    /// [`TARGET_DATA_VERSION`](crate::TARGET_DATA_VERSION)の形式で書く
    /// DataVersionを指定するときは[`BlockState::to_nbt_for_data_version`]を使う
    pub fn to_nbt(&self) -> NbtTag {
        self.to_palette_id()
    }

    /// DataVersionを指定して、パレット要素のNBTへ変換する
    ///
    /// 26.3（DataVersion 5006）以降は、プロパティが空ならブロックIDだけの文字列にし、それ以外は`id`と`properties`を持つCompoundにする
    /// 1519以上5006未満は、`Name`を持つCompoundにし、プロパティが空なら`Properties`キー自体を出力しない
    /// いずれもMinecraftと同じ振る舞い
    ///
    /// `data_version`は書き込み先のチャンクのDataVersionで、1519以上でなければならない
    /// 1519未満の場合はエラー（`InvalidArgument`）
    pub fn to_nbt_for_data_version(&self, data_version: i32) -> Result<NbtTag> {
        check_data_version(data_version)?;

        // 26.3より前は、Name / Propertiesの形式で書く
        if data_version < PALETTE_ID_FORMAT_DATA_VERSION {
            return Ok(self.to_name_properties());
        }

        Ok(self.to_palette_id())
    }

    /// 26.3以降の`id` / `properties`の形式へ変換する
    fn to_palette_id(&self) -> NbtTag {
        // プロパティが無ければ、Minecraftが既定の状態を書くときと同じく文字列にする
        if self.properties.is_empty() {
            return NbtTag::String(NbtString::new(self.name.clone()));
        }

        let mut result = NbtCompound::new();
        result.set("id", NbtTag::String(NbtString::new(self.name.clone())));
        let mut properties_tag = NbtCompound::new();

        // 名前の昇順で並ぶ
        for (key, value) in &self.properties {
            properties_tag.set(key.clone(), NbtTag::String(NbtString::new(value.clone())));
        }

        result.set("properties", NbtTag::Compound(properties_tag));
        NbtTag::Compound(result)
    }

    /// 26.2までの`Name` / `Properties`の形式へ変換する
    fn to_name_properties(&self) -> NbtTag {
        let mut result = NbtCompound::new();
        result.set("Name", NbtTag::String(NbtString::new(self.name.clone())));

        // プロパティが無ければ、Propertiesキー自体を出力しない
        if self.properties.is_empty() {
            return NbtTag::Compound(result);
        }

        let mut properties_tag = NbtCompound::new();

        // 名前の昇順で並ぶ
        for (key, value) in &self.properties {
            properties_tag.set(key.clone(), NbtTag::String(NbtString::new(value.clone())));
        }

        result.set("Properties", NbtTag::Compound(properties_tag));
        NbtTag::Compound(result)
    }
}

impl fmt::Display for BlockState {
    /// `minecraft:oak_stairs[facing=north,half=top]`形式の文字列を返す
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.name)?;

        if self.properties.is_empty() {
            return Ok(());
        }

        f.write_str("[")?;
        let mut first = true;

        // 名前の昇順で並べるので、同じ状態なら必ず同じ文字列になる
        for (key, value) in &self.properties {
            // 2つ目以降の前に区切りのカンマを置く
            if !first {
                f.write_str(",")?;
            }

            first = false;
            write!(f, "{key}={value}")?;
        }

        f.write_str("]")
    }
}

/// 名前空間が省略されていたら`minecraft:`を補う
fn normalize(name: &str) -> String {
    if name.contains(':') {
        return name.to_string();
    }

    format!("minecraft:{name}")
}

/// 指定されたDataVersionが、読み書きできる下限以上であることを確かめる
fn check_data_version(data_version: i32) -> Result<()> {
    if data_version < OLDEST_FORMAT_DATA_VERSION {
        return Err(Error::new(
            ErrorCode::InvalidArgument,
            format!("DataVersionは{OLDEST_FORMAT_DATA_VERSION}以上でなければならない: {data_version}"),
        ));
    }

    Ok(())
}

/// 26.3以降の`id` / `properties`の形式から読む
fn from_palette_id(nbt: &NbtTag) -> Result<BlockState> {
    let compound = match unwrap_list_element(nbt) {
        // 既定の状態は、ブロックIDだけの文字列で入っている
        NbtTag::String(text) => match text.as_str() {
            Some(plain) => return Ok(BlockState::new(plain, BTreeMap::new())),
            None => {
                return Err(Error::new(
                    ErrorCode::UnexpectedTagType,
                    "ブロックのパレット要素の文字列は UTF-8 に写せない（孤立サロゲートを含む）",
                ))
            }
        },
        NbtTag::Compound(compound) => compound,
        other => {
            return Err(Error::new(
                ErrorCode::UnexpectedTagType,
                format!(
                    "ブロックのパレット要素が string でも compound でもない: {}",
                    other.tag_type().as_str()
                ),
            ))
        }
    };

    let name = match compound.opt_string("id")? {
        Some(name) => name.to_string(),
        None => {
            // Name / Propertiesは26.2までの形式で、読み替えると誤った状態を返しかねない
            if compound.contains_key("Name") {
                return Err(Error::new(
                    ErrorCode::MalformedData,
                    "ブロックのパレット要素に id が無い。NameはDataVersion 5006より前の形式なので、5006未満のDataVersionで読むこと",
                ));
            }

            return Err(Error::new(ErrorCode::MalformedData, "ブロックのパレット要素に id が無い"));
        }
    };

    let mut properties = BTreeMap::new();

    if let Some(properties_tag) = compound.opt_compound("properties")? {
        // propertiesの値はすべて文字列（数値や真偽値も文字列で入る）
        for (key, value) in properties_tag.iter() {
            match value {
                NbtTag::String(text) => match text.as_str() {
                    Some(plain) => {
                        properties.insert(key.clone(), plain.to_string());
                    }
                    None => {
                        return Err(Error::new(
                            ErrorCode::MalformedData,
                            format!("properties の \"{key}\" が UTF-8 に写せない"),
                        ))
                    }
                },
                other => {
                    return Err(Error::new(
                        ErrorCode::UnexpectedTagType,
                        format!(
                            "properties の \"{key}\" が文字列でない: {}",
                            other.tag_type().as_str()
                        ),
                    ))
                }
            }
        }
    }

    Ok(BlockState::new(name, properties))
}

/// 26.2までの`Name` / `Properties`の形式から読む
fn from_name_properties(nbt: &NbtTag) -> Result<BlockState> {
    // 26.2までは文字列のパレット要素も、異種リストの包みも無い
    let compound = match nbt {
        NbtTag::Compound(compound) => compound,
        other => {
            return Err(Error::new(
                ErrorCode::UnexpectedTagType,
                format!("ブロックのパレット要素が compound でない: {}", other.tag_type().as_str()),
            ))
        }
    };

    let name = match compound.opt_string("Name")? {
        Some(name) => name.to_string(),
        None => {
            return Err(Error::new(ErrorCode::MalformedData, "ブロックのパレット要素に Name が無い"))
        }
    };

    let mut properties = BTreeMap::new();

    if let Some(properties_tag) = compound.opt_compound("Properties")? {
        // Propertiesの値はすべて文字列（数値や真偽値も文字列で入る）
        for (key, value) in properties_tag.iter() {
            match value {
                NbtTag::String(text) => match text.as_str() {
                    Some(plain) => {
                        properties.insert(key.clone(), plain.to_string());
                    }
                    None => {
                        return Err(Error::new(
                            ErrorCode::MalformedData,
                            format!("Properties の \"{key}\" が UTF-8 に写せない"),
                        ))
                    }
                },
                other => {
                    return Err(Error::new(
                        ErrorCode::UnexpectedTagType,
                        format!(
                            "Properties の \"{key}\" が文字列でない: {}",
                            other.tag_type().as_str()
                        ),
                    ))
                }
            }
        }
    }

    Ok(BlockState::new(name, properties))
}

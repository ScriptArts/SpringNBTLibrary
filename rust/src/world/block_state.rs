//! ブロックの状態
//! 名前と、任意のプロパティの組
//!
//! プロパティは**常に名前の昇順で保持する**
//! こうしておくと文字列表現が一意になり、
//! 全言語で同じ出力になる
//! Minecraft が書き出した並び順は
//! [`super::PalettedContainer`] がパレットを生の NBT のまま持つことで守られるので、
//! 触っていないブロックの並びが崩れることはない
//!
//! 仕様: `docs/spec/30-chunk-format.md` 2.1章

use std::collections::BTreeMap;
use std::fmt;

use crate::error::{Error, ErrorCode, Result};
use crate::nbt::tag::{NbtCompound, NbtString, NbtTag};

/// ブロックの状態
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BlockState {
    name: String,
    properties: BTreeMap<String, String>,
}

/// [`Chunk::set_block`](crate::world::Chunk::set_block) へ渡せるもの
///
/// 他の言語ではオーバーロードで済むが、Rust には無いのでトレイトで受ける
/// `&BlockState` と `&str` の両方をそのまま渡せる
pub trait IntoBlockState {
    /// ブロック状態へ変換する
    fn into_block_state(self) -> Result<BlockState>;
}

impl IntoBlockState for BlockState {
    fn into_block_state(self) -> Result<BlockState> {
        Ok(self)
    }
}

impl IntoBlockState for &BlockState {
    fn into_block_state(self) -> Result<BlockState> {
        Ok(self.clone())
    }
}

impl IntoBlockState for &str {
    fn into_block_state(self) -> Result<BlockState> {
        BlockState::parse(self)
    }
}

impl BlockState {
    /// 名前とプロパティを指定して作る
    ///
    /// 名前空間が省略されていたら `minecraft:` を補う
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
    /// 無ければ `None`
    pub fn property(&self, key: &str) -> Option<&str> {
        self.properties.get(key).map(|value| value.as_str())
    }

    /// プロパティを 1 つ差し替えた新しい状態を返す
    pub fn with(&self, key: impl Into<String>, value: impl Into<String>) -> BlockState {
        let mut result = self.clone();
        result.properties.insert(key.into(), value.into());
        result
    }

    /// `minecraft:oak_stairs[facing=north,half=top]` 形式の文字列から作る
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
            // "key=value" をカンマ区切りで読む
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

    /// パレット要素の NBT から作る
    pub fn from_nbt(nbt: &NbtCompound) -> Result<BlockState> {
        let name = nbt.get_string("Name")?.to_string();
        let mut properties = BTreeMap::new();

        if let Some(properties_tag) = nbt.opt_compound("Properties")? {
            // Properties の値はすべて文字列（数値や真偽値も文字列で入る）
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

    /// パレット要素の NBT へ変換する
    ///
    /// プロパティが空なら `Properties` キー自体を出力しない
    /// Minecraft と同じ振る舞い
    pub fn to_nbt(&self) -> NbtCompound {
        let mut result = NbtCompound::new();
        result.set("Name", NbtTag::String(NbtString::new(self.name.clone())));

        if self.properties.is_empty() {
            return result;
        }

        let mut properties_tag = NbtCompound::new();

        // 名前の昇順で並ぶ
        for (key, value) in &self.properties {
            properties_tag.set(key.clone(), NbtTag::String(NbtString::new(value.clone())));
        }

        result.set("Properties", NbtTag::Compound(properties_tag));
        result
    }
}

impl fmt::Display for BlockState {
    /// `minecraft:oak_stairs[facing=north,half=top]` 形式の文字列を返す
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.name)?;

        if self.properties.is_empty() {
            return Ok(());
        }

        f.write_str("[")?;
        let mut first = true;

        // 名前の昇順で並べるので、同じ状態なら必ず同じ文字列になる
        for (key, value) in &self.properties {
            // 2 つ目以降の前に区切りのカンマを置く
            if !first {
                f.write_str(",")?;
            }

            first = false;
            write!(f, "{key}={value}")?;
        }

        f.write_str("]")
    }
}

/// 名前空間が省略されていたら `minecraft:` を補う
fn normalize(name: &str) -> String {
    if name.contains(':') {
        return name.to_string();
    }

    format!("minecraft:{name}")
}

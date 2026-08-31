//! チャンク 1 つ分
//! 地形の読み書きの入口
//!
//! 読んだ NBT をそのまま保持し、変更した部分だけを書き戻す
//! 未知のキーを落とさないので、将来の追加要素があってもデータを壊さない
//!
//! 仕様: `docs/spec/30-chunk-format.md`

use std::collections::BTreeMap;

use crate::error::{Error, ErrorCode, Result};
use crate::nbt::tag::{NbtCompound, NbtList, NbtString, NbtTag, TagType};
use crate::TARGET_DATA_VERSION;

use super::block_state::{BlockState, IntoBlockState};
use super::paletted_container::PalettedContainer;

/// セクション 1 つに入るブロック数
pub const BLOCKS_PER_SECTION: usize = 4096;

/// セクション 1 つに入るバイオームのエントリ数（4×4×4 単位）
pub const BIOMES_PER_SECTION: usize = 64;

/// ブロックに紐づく付随データのキー
/// ブロックを置き換えたら整合が崩れる
const BLOCK_DATA_KEYS: [&str; 3] = ["block_entities", "block_ticks", "fluid_ticks"];

/// 付随データの要素が、指定の絶対座標を指しているか
fn matches_position(entry: &NbtCompound, x: i32, y: i32, z: i32) -> bool {
    // 座標を持たない要素は、対象かどうか判断できないので触らない
    let entry_x = match entry.opt_int("x") {
        Ok(Some(value)) => value,
        _ => return false,
    };
    let entry_y = match entry.opt_int("y") {
        Ok(Some(value)) => value,
        _ => return false,
    };
    let entry_z = match entry.opt_int("z") {
        Ok(Some(value)) => value,
        _ => return false,
    };

    entry_x == x && entry_y == y && entry_z == z
}

/// DataVersion が対象と違ったときの動作
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum VersionMismatchAction {
    /// 警告コールバックを呼んで続行する
    /// 既定
    Warn,
    /// [`ErrorCode::UnsupportedDataVersion`] の例外にする
    Error,
    /// 何もしない
    Ignore,
}

/// チャンク読み込みのオプション
///
/// 仕様: `docs/spec/30-chunk-format.md` 5章
pub struct ChunkReadOptions {
    /// DataVersion が対象と違うときの動作
    pub on_version_mismatch: VersionMismatchAction,
    /// 警告の通知先
    /// `None` なら何もしない
    pub on_warning: Option<Box<dyn Fn(&str)>>,
    /// data の長さが期待値と違うとき、長さからビット幅を逆算して読むか
    pub lenient_bit_storage: bool,
}

impl Default for ChunkReadOptions {
    fn default() -> Self {
        ChunkReadOptions {
            on_version_mismatch: VersionMismatchAction::Warn,
            on_warning: None,
            lenient_bit_storage: false,
        }
    }
}

impl std::fmt::Debug for ChunkReadOptions {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("ChunkReadOptions")
            .field("on_version_mismatch", &self.on_version_mismatch)
            .field("lenient_bit_storage", &self.lenient_bit_storage)
            .finish()
    }
}

/// チャンク書き込みのオプション
#[derive(Debug, Clone, Copy, Default)]
pub struct ChunkWriteOptions {
    /// 対象バージョン以外の DataVersion を持つチャンクの書き戻しを許すか
    ///
    /// 既定は `false`
    /// 古いワールドを黙って新形式で上書きし、
    /// 利用者が気づかないうちに壊すことを防ぐため（`docs/adr/0003-version-policy.md`）
    pub allow_foreign_data_version: bool,
}

/// チャンクを Y 方向に 16 ブロックずつ区切った 16×16×16 の立方体
///
/// `BlockLight` / `SkyLight` などの解釈していないキーは元の NBT に残り、
/// 書き戻しでそのまま出力される
#[derive(Debug, Clone)]
pub struct ChunkSection {
    raw: NbtCompound,
    y: i32,
    block_states: Option<PalettedContainer>,
    biomes: Option<PalettedContainer>,
}

impl ChunkSection {
    /// セクションのY位置
    /// オーバーワールドは -5..20
    pub fn y(&self) -> i32 {
        self.y
    }

    /// ブロック状態
    /// 持たないセクション（光源専用）では `None`
    pub fn block_states(&self) -> Option<&PalettedContainer> {
        self.block_states.as_ref()
    }

    /// ブロック状態への可変参照
    pub fn block_states_mut(&mut self) -> Option<&mut PalettedContainer> {
        self.block_states.as_mut()
    }

    /// バイオーム
    /// 持たないセクションでは `None`
    pub fn biomes(&self) -> Option<&PalettedContainer> {
        self.biomes.as_ref()
    }

    /// バイオームへの可変参照
    pub fn biomes_mut(&mut self) -> Option<&mut PalettedContainer> {
        self.biomes.as_mut()
    }

    /// ブロック状態を持つか
    pub fn has_block_states(&self) -> bool {
        self.block_states.is_some()
    }

    /// バイオームを持つか
    pub fn has_biomes(&self) -> bool {
        self.biomes.is_some()
    }

    /// 元の NBT
    /// 解釈していないキーもここに残っている
    pub fn raw(&self) -> &NbtCompound {
        &self.raw
    }

    /// NBT からセクションを読む
    pub fn from_nbt(nbt: &NbtCompound, options: &ChunkReadOptions) -> Result<ChunkSection> {
        let mut section = ChunkSection {
            raw: nbt.clone(),
            y: nbt.get_byte("Y")? as i32,
            block_states: None,
            biomes: None,
        };

        // 光源専用のセクションは block_states を持たない
        if let Some(block_states) = nbt.opt_compound("block_states")? {
            section.block_states = Some(PalettedContainer::from_nbt(
                block_states,
                BLOCKS_PER_SECTION,
                4,
                options.lenient_bit_storage,
            )?);
        }

        // 光源だけを持つセクションにはバイオームが無い
        if let Some(biomes) = nbt.opt_compound("biomes")? {
            section.biomes = Some(PalettedContainer::from_nbt(
                biomes,
                BIOMES_PER_SECTION,
                1,
                options.lenient_bit_storage,
            )?);
        }

        Ok(section)
    }

    /// NBT へ書き戻す
    /// 解釈していないキーはそのまま残る
    pub fn to_nbt(&self) -> Result<NbtCompound> {
        let mut result = self.raw.clone();

        // 解釈したコンテナだけを書き戻す
        // 持たないキーは元のまま残す
        if let Some(block_states) = &self.block_states {
            result.set("block_states", NbtTag::Compound(block_states.to_nbt()?));
        }

        // 解釈したコンテナだけを書き戻す
        // 持たないキーは元のまま残す
        if let Some(biomes) = &self.biomes {
            result.set("biomes", NbtTag::Compound(biomes.to_nbt()?));
        }

        Ok(result)
    }

    /// 使われていないパレット要素を取り除く
    pub fn compact(&mut self) -> Result<()> {
        // 持っているコンテナだけを掃除する
        if let Some(block_states) = &mut self.block_states {
            block_states.compact()?;
        }

        // 持っているコンテナだけを掃除する
        if let Some(biomes) = &mut self.biomes {
            biomes.compact()?;
        }

        Ok(())
    }
}

/// チャンク 1 つ分
#[derive(Debug, Clone)]
pub struct Chunk {
    raw: NbtCompound,
    sections: BTreeMap<i32, ChunkSection>,
    modified: bool,
}

impl Chunk {
    /// チャンク構造のバージョン
    pub fn data_version(&self) -> Result<i32> {
        self.raw.get_int("DataVersion")
    }

    /// 絶対チャンクX座標
    pub fn x(&self) -> Result<i32> {
        self.raw.get_int("xPos")
    }

    /// 絶対チャンクZ座標
    pub fn z(&self) -> Result<i32> {
        self.raw.get_int("zPos")
    }

    /// 最下段セクションのY位置
    /// オーバーワールドは -4
    pub fn min_section_y(&self) -> Result<i32> {
        self.raw.get_int("yPos")
    }

    /// 生成段階（`minecraft:full` など）
    pub fn status(&self) -> Result<&str> {
        self.raw.get_string("Status")
    }

    /// 生成が完了しているか
    /// ブロック改変の対象にしてよいのはこれだけ
    pub fn is_fully_generated(&self) -> bool {
        match self.status() {
            Ok(status) => status == "minecraft:full",
            Err(_) => false,
        }
    }

    /// このチャンクに変更が加わったか
    ///
    /// ブロックやバイオームを書き換えると立つ
    /// [`Dimension::flush`](crate::world::Dimension::flush) は
    /// これが立っているチャンクだけを書き戻す
    ///
    /// [`Chunk::raw`] を直接いじった場合はここが立たないので、
    /// 自分で [`Chunk::set_is_modified`] を呼ぶこと
    pub fn is_modified(&self) -> bool {
        self.modified
    }

    /// 変更の印を付け外しする
    pub fn set_is_modified(&mut self, value: bool) {
        self.modified = value;
    }

    /// 存在するセクションのY位置
    /// 昇順
    pub fn section_ys(&self) -> Vec<i32> {
        self.sections.keys().copied().collect()
    }

    /// 元の NBT
    /// 解釈していないキーもここに残っている
    pub fn raw(&self) -> &NbtCompound {
        &self.raw
    }

    /// NBT からチャンクを読む
    pub fn from_nbt(nbt: NbtCompound, options: &ChunkReadOptions) -> Result<Chunk> {
        let mut chunk = Chunk { raw: nbt, sections: BTreeMap::new(), modified: false };
        chunk.check_data_version(options)?;

        let section_list = match chunk.raw.opt_list("sections")? {
            Some(list) => list.clone(),
            None => return Ok(chunk),
        };

        // 並び順に依存しないよう、Y から索引を作る
        for entry in section_list.iter() {
            let section_tag = match entry {
                NbtTag::Compound(compound) => compound,
                other => {
                    return Err(Error::new(
                        ErrorCode::UnexpectedTagType,
                        format!(
                            "sections の要素が compound でない: {}",
                            other.tag_type().as_str()
                        ),
                    ))
                }
            };

            let section = ChunkSection::from_nbt(section_tag, options)?;
            chunk.sections.insert(section.y, section);
        }

        Ok(chunk)
    }

    /// DataVersion を検査し、オプションに従って警告またはエラーにする
    fn check_data_version(&self, options: &ChunkReadOptions) -> Result<()> {
        let version = self.data_version()?;

        if version == TARGET_DATA_VERSION {
            return Ok(());
        }

        let message =
            format!("DataVersion が対象と違う: {version}（対象は {TARGET_DATA_VERSION}）");

        if options.on_version_mismatch == VersionMismatchAction::Error {
            return Err(Error::new(ErrorCode::UnsupportedDataVersion, message));
        }

        // 警告として扱う設定のときだけ知らせる
        if options.on_version_mismatch == VersionMismatchAction::Warn {
            // 通知先が設定されているときだけ呼ぶ
            if let Some(callback) = &options.on_warning {
                callback(&message);
            }
        }

        Ok(())
    }

    /// NBT へ書き戻す
    /// 変更したセクションだけを反映し、他のキーはそのまま残す
    pub fn to_nbt(&self, options: &ChunkWriteOptions) -> Result<NbtCompound> {
        let version = self.data_version()?;

        if version != TARGET_DATA_VERSION && !options.allow_foreign_data_version {
            return Err(Error::new(
                ErrorCode::UnsupportedDataVersion,
                format!(
                    "DataVersion {version} のチャンクは書き戻せない（対象は {TARGET_DATA_VERSION}）。\
                     許可するなら ChunkWriteOptions.allow_foreign_data_version を立てること"
                ),
            ));
        }

        let mut result = self.raw.clone();

        // 常に対象バージョンを書く
        result.set("DataVersion", NbtTag::Int(TARGET_DATA_VERSION));

        if self.sections.is_empty() {
            return Ok(result);
        }

        let mut section_list = NbtList::with_element_type(TagType::Compound);

        // Y の昇順で書き出す
        for section in self.sections.values() {
            section_list.push(NbtTag::Compound(section.to_nbt()?))?;
        }

        result.set("sections", NbtTag::List(section_list));
        Ok(result)
    }

    /// Y位置からセクションを得る
    /// 無ければ `None`
    pub fn section(&self, section_y: i32) -> Option<&ChunkSection> {
        self.sections.get(&section_y)
    }

    /// Y位置からセクションへの可変参照を得る
    pub fn section_mut(&mut self, section_y: i32) -> Option<&mut ChunkSection> {
        self.sections.get_mut(&section_y)
    }

    /// ブロックを取得する
    /// X と Z はチャンク内相対 (0..15)、Y は絶対座標
    pub fn get_block(&self, x: i32, y: i32, z: i32) -> Result<Option<BlockState>> {
        check_local_coordinates(x, z)?;

        let section = match self.section(y >> 4) {
            Some(section) if section.has_block_states() => section,
            _ => return Ok(None),
        };

        let entry = section.block_states().unwrap().get(block_index(x, y, z))?;

        match entry {
            NbtTag::Compound(compound) => Ok(Some(BlockState::from_nbt(compound)?)),
            other => Err(Error::new(
                ErrorCode::UnexpectedTagType,
                format!(
                    "ブロックのパレット要素が compound でない: {}",
                    other.tag_type().as_str()
                ),
            )),
        }
    }

    /// ブロックを設定する
    ///
    /// `&BlockState` のほか、`"minecraft:oak_stairs[facing=north]"` の形の
    /// 文字列でも指定できる
    pub fn set_block<S>(&mut self, x: i32, y: i32, z: i32, state: &S) -> Result<()>
    where
        S: IntoBlockState + ?Sized,
    {
        // すでに BlockState を持っているなら借りるだけで済ませる
        let borrowed = state.as_block_state()?;
        let state: &BlockState = &borrowed;
        check_local_coordinates(x, z)?;
        let section_y = y >> 4;
        let index = block_index(x, y, z);

        // 同じ状態を置き直すだけなら、付随データを触る理由がない
        // プロパティの並び順に左右されないよう、NBT ではなく BlockState として比べる
        if let Some(current) = self.get_block(x, y, z)? {
            if &current == state {
                return Ok(());
            }
        }

        let section = match self.sections.get_mut(&section_y) {
            Some(section) if section.has_block_states() => section,
            _ => {
                return Err(Error::new(
                    ErrorCode::InvalidArgument,
                    format!(
                        "Y={y} を含むセクション（Y={section_y}）が無いか、ブロックを持たない。\
                         本ライブラリはセクションを新規生成しない"
                    ),
                ))
            }
        };

        section
            .block_states_mut()
            .unwrap()
            .set(index, NbtTag::Compound(state.to_nbt()))?;

        self.remove_block_data(x, y, z)?;
        self.modified = true;
        Ok(())
    }

    /// その座標を指す付随データを取り除く
    ///
    /// `block_entities` / `block_ticks` / `fluid_ticks` の要素は
    /// いずれも `x` `y` `z` を**絶対座標**で持つ
    fn remove_block_data(&mut self, x: i32, y: i32, z: i32) -> Result<()> {
        let absolute_x = (self.x()? * 16) + x;
        let absolute_z = (self.z()? * 16) + z;

        // 3 つのリストは形が同じなので、まとめて同じ処理をかける
        for key in BLOCK_DATA_KEYS {
            let filtered = match self.raw.opt_list(key)? {
                Some(list) if !list.is_empty() => {
                    // 全要素を消しても要素型が変わらないよう、元の型で作り直す
                    let mut kept = NbtList::with_element_type(list.element_type());

                    // 座標を持つ要素のうち、指定の位置を指すものだけを取り除く
                    for entry in list.iter() {
                        let keep = match entry {
                            NbtTag::Compound(compound) => {
                                !matches_position(compound, absolute_x, y, absolute_z)
                            }
                            // 座標を持たない要素は、対象か判断できないので触らない
                            _ => true,
                        };

                        // 残す要素だけを新しいリストへ積む
                        if keep {
                            kept.push(entry.clone())?;
                        }
                    }

                    // 何も減っていないなら書き戻す必要がない
                    if kept.len() == list.len() {
                        None
                    } else {
                        Some(kept)
                    }
                }
                _ => None,
            };

            // 減ったときだけ書き戻す
            if let Some(kept) = filtered {
                self.raw.set(key, NbtTag::List(kept));
            }
        }

        Ok(())
    }

    /// バイオームを取得する
    /// 4×4×4 の単位なので、座標は自動的に丸められる
    pub fn get_biome(&self, x: i32, y: i32, z: i32) -> Result<Option<String>> {
        check_local_coordinates(x, z)?;

        let section = match self.section(y >> 4) {
            Some(section) if section.has_biomes() => section,
            _ => return Ok(None),
        };

        let entry = section.biomes().unwrap().get(biome_index(x, y, z))?;

        match entry {
            NbtTag::String(text) => match text.as_str() {
                Some(plain) => Ok(Some(plain.to_string())),
                None => Err(Error::new(
                    ErrorCode::MalformedData,
                    "バイオーム名が UTF-8 に写せない",
                )),
            },
            other => Err(Error::new(
                ErrorCode::UnexpectedTagType,
                format!(
                    "バイオームのパレット要素が string でない: {}",
                    other.tag_type().as_str()
                ),
            )),
        }
    }

    /// バイオームを設定する
    /// 4×4×4 の単位
    pub fn set_biome(&mut self, x: i32, y: i32, z: i32, biome: &str) -> Result<()> {
        check_local_coordinates(x, z)?;
        let section_y = y >> 4;
        let index = biome_index(x, y, z);

        let section = match self.sections.get_mut(&section_y) {
            Some(section) if section.has_biomes() => section,
            _ => {
                return Err(Error::new(
                    ErrorCode::InvalidArgument,
                    format!("Y={y} を含むセクション（Y={section_y}）が無いか、バイオームを持たない"),
                ))
            }
        };

        section
            .biomes_mut()
            .unwrap()
            .set(index, NbtTag::String(NbtString::new(biome)))?;

        self.modified = true;
        Ok(())
    }

    /// `Heightmaps` を削除し、Minecraft に再計算させる
    ///
    /// 本ライブラリは高さマップを再計算しない
    /// ブロックを改変したら呼ぶこと
    /// （`docs/adr/0004-defer-heightmap-recalc.md`）
    pub fn clear_heightmaps(&mut self) {
        self.raw.remove("Heightmaps");
        self.modified = true;
    }

    /// `isLightOn` を 0 にし、光源の再計算を促す
    pub fn invalidate_lighting(&mut self) {
        self.raw.set_byte("isLightOn", 0);
        self.modified = true;
    }

    /// 使われていないパレット要素を全セクションから取り除く
    pub fn compact(&mut self) -> Result<()> {
        // 全セクションのパレットをまとめて掃除する
        for section in self.sections.values_mut() {
            section.compact()?;
        }

        Ok(())
    }
}

/// セクション内のブロック添字
///
/// `& 15` により負のY座標でも正しく求まる
pub fn block_index(x: i32, y: i32, z: i32) -> usize {
    (((y & 15) * 256) + ((z & 15) * 16) + (x & 15)) as usize
}

/// セクション内のバイオーム添字
/// 1 エントリが 4×4×4 ブロック
pub fn biome_index(x: i32, y: i32, z: i32) -> usize {
    ((((y & 15) / 4) * 16) + (((z & 15) / 4) * 4) + ((x & 15) / 4)) as usize
}

fn check_local_coordinates(x: i32, z: i32) -> Result<()> {
    // チャンク内相対座標は 0..15 でなければならない
    if !(0..=15).contains(&x) || !(0..=15).contains(&z) {
        return Err(Error::new(
            ErrorCode::InvalidArgument,
            format!("チャンク内相対座標が範囲外: ({x}, {z})。X も Z も 0..15 であること"),
        ));
    }

    Ok(())
}

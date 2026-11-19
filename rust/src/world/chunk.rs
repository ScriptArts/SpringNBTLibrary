//! チャンク1つ分
//! 地形の読み書きはここから行う
//!
//! 読んだNBTをそのまま保持し、書き戻すときに作り直すのはセクションだけにする
//! 未知のキーを落とさないので、将来の追加要素があってもデータをおかしくしない

use std::collections::BTreeMap;

use crate::error::{Error, ErrorCode, Result};
use crate::nbt::tag::{NbtCompound, NbtList, NbtString, NbtTag, TagType};
use crate::MIN_SUPPORTED_DATA_VERSION;

use super::block_state::{BlockState, IntoBlockState};
use super::chunk_format::{ChunkFormat, OLDEST_FORMAT_DATA_VERSION};
use super::paletted_container::PalettedContainer;

/// セクション1つに入るブロック数
pub const BLOCKS_PER_SECTION: usize = 4096;

/// セクション1つに入るバイオームのエントリ数（4×4×4単位）
pub const BIOMES_PER_SECTION: usize = 64;

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

/// DataVersionが扱える形式より古いときの動作
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum VersionMismatchAction {
    /// 警告コールバックを呼んで続行する
    /// 既定
    Warn,
    /// [`ErrorCode::UnsupportedDataVersion`]の例外にする
    Error,
    /// 何もしない
    Ignore,
}

/// チャンク読み込みのオプション
pub struct ChunkReadOptions {
    /// DataVersionが扱える形式より古いときの動作
    pub on_version_mismatch: VersionMismatchAction,
    /// 警告の通知先
    /// `None`なら何もしない
    pub on_warning: Option<Box<dyn Fn(&str)>>,
    /// dataの長さが期待値と違うとき、長さからビット幅を逆算して読むか
    pub lenient_bit_storage: bool,
    /// チャンクの形式の世代を選ぶDataVersion
    ///
    /// `None`なら、チャンク自身のDataVersionで選ぶ
    /// 1519以上でなければならない
    /// 扱える形式の下限との比較には使わず、常にチャンク自身のDataVersionで比べる
    pub format_data_version: Option<i32>,
}

impl Default for ChunkReadOptions {
    fn default() -> Self {
        ChunkReadOptions {
            on_version_mismatch: VersionMismatchAction::Warn,
            on_warning: None,
            lenient_bit_storage: false,
            format_data_version: None,
        }
    }
}

impl std::fmt::Debug for ChunkReadOptions {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("ChunkReadOptions")
            .field("on_version_mismatch", &self.on_version_mismatch)
            .field("lenient_bit_storage", &self.lenient_bit_storage)
            .field("format_data_version", &self.format_data_version)
            .finish()
    }
}

/// チャンク書き込みのオプション
#[derive(Debug, Clone, Copy, Default)]
pub struct ChunkWriteOptions {
    /// 扱える形式より古いDataVersionを持つチャンクの書き戻しを許すか
    ///
    /// 既定は`false`
    /// エラーを出さずに古いワールドを新形式で上書きし、
    /// 利用者が気づかないうちに使えなくすることを防ぐため
    pub allow_foreign_data_version: bool,
}

/// チャンクをY方向に16ブロックずつ区切った16×16×16の立方体
///
/// `BlockLight` / `SkyLight`などの解釈していないキーは元のNBTに残り、
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
    /// オーバーワールドは-5..20
    pub fn y(&self) -> i32 {
        self.y
    }

    /// ブロック状態
    /// 持たないセクション（光源専用）では`None`
    pub fn block_states(&self) -> Option<&PalettedContainer> {
        self.block_states.as_ref()
    }

    /// ブロック状態への可変参照
    pub fn block_states_mut(&mut self) -> Option<&mut PalettedContainer> {
        self.block_states.as_mut()
    }

    /// バイオーム
    /// 持たないセクションでは`None`
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

    /// 元のNBT
    /// 解釈していないキーもここに残っている
    pub fn raw(&self) -> &NbtCompound {
        &self.raw
    }

    /// NBTからセクションを読む
    pub fn from_nbt(nbt: &NbtCompound, options: &ChunkReadOptions) -> Result<ChunkSection> {
        let mut section = ChunkSection {
            raw: nbt.clone(),
            y: nbt.get_byte("Y")? as i32,
            block_states: None,
            biomes: None,
        };

        // 光源専用のセクションはblock_statesを持たない
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

    /// NBTへ書き戻す
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

/// チャンクの本体に手を加える
/// 1.17までの形式では`Level`の中、1.18以降はルートが本体
fn update_body(root: &mut NbtCompound, update: impl FnOnce(&mut NbtCompound)) -> Result<()> {
    let mut level = match root.opt_compound("Level")? {
        Some(level) => level.clone(),
        None => {
            update(root);
            return Ok(());
        }
    };

    // Levelの中は借りたまま書き換えられないので、複製を書き換えて置き直す
    update(&mut level);
    root.set("Level", NbtTag::Compound(level));
    Ok(())
}

/// チャンク1つ分
#[derive(Debug, Clone)]
pub struct Chunk {
    raw: NbtCompound,
    sections: BTreeMap<i32, ChunkSection>,
    modified: bool,
    /// チャンクの形式の世代
    /// 引けなかったチャンクは`None`のままで、元のNBTだけを持つ
    format: Option<&'static ChunkFormat>,
    format_data_version: i32,
}

impl Chunk {
    /// チャンク構造のバージョン
    pub fn data_version(&self) -> Result<i32> {
        self.raw.get_int("DataVersion")
    }

    /// チャンクの形式の世代を選ぶのに使ったDataVersion
    ///
    /// 読み込みのオプションで指定していればその値、指定が無ければ[`Chunk::data_version`]
    pub fn format_data_version(&self) -> i32 {
        self.format_data_version
    }

    /// 絶対チャンクX座標
    pub fn x(&self) -> Result<i32> {
        self.body()?.get_int("xPos")
    }

    /// 絶対チャンクZ座標
    pub fn z(&self) -> Result<i32> {
        self.body()?.get_int("zPos")
    }

    /// 最下段セクションのY位置
    /// オーバーワールドは-4
    pub fn min_section_y(&self) -> Result<i32> {
        self.raw.get_int("yPos")
    }

    /// 生成段階（`minecraft:full`など）
    pub fn status(&self) -> Result<&str> {
        self.body()?.get_string("Status")
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
    /// [`Dimension::flush`](crate::world::Dimension::flush)は
    /// これが立っているチャンクだけを書き戻す
    ///
    /// [`Chunk::raw`]を直接いじった場合は立たないので、自分で[`Chunk::set_is_modified`]を呼ぶこと
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

    /// 元のNBT
    /// 解釈していないキーもここに残っている
    pub fn raw(&self) -> &NbtCompound {
        &self.raw
    }

    /// NBTからチャンクを読む
    ///
    /// 形式の世代は、オプションで指定したDataVersionか、チャンク自身のDataVersionで選ぶ
    /// DataVersionが1519未満のチャンクは、指定があってもどの世代でも解釈せず、元のNBTだけを持つ
    ///
    /// 世代を選ぶDataVersionが1519未満なら[`ErrorCode::InvalidArgument`]、
    /// 選んだ世代とチャンクの構造が合わなければ[`ErrorCode::MalformedData`]を返す
    pub fn from_nbt(nbt: NbtCompound, options: &ChunkReadOptions) -> Result<Chunk> {
        // 1.13より前の形式は、どの世代の部品でも読めない
        if let Some(requested) = options.format_data_version {
            // 下限より古い値は指定として受け付けない
            if requested < OLDEST_FORMAT_DATA_VERSION {
                return Err(Error::new(
                    ErrorCode::InvalidArgument,
                    format!(
                        "世代を選ぶDataVersionは{OLDEST_FORMAT_DATA_VERSION}以上でなければならない: {requested}"
                    ),
                ));
            }
        }

        let mut chunk = Chunk {
            raw: nbt,
            sections: BTreeMap::new(),
            modified: false,
            format: None,
            format_data_version: 0,
        };
        chunk.check_data_version(options)?;
        let data_version = chunk.data_version()?;
        chunk.format_data_version = data_version;

        // 指定があれば、チャンク自身のDataVersionの代わりにその値で世代を選ぶ
        if let Some(requested) = options.format_data_version {
            chunk.format_data_version = requested;
        }

        // 1.13より前のチャンクはブロックが数値IDで、どの世代で読んでも誤った値になる
        if data_version < OLDEST_FORMAT_DATA_VERSION {
            return Ok(chunk);
        }

        // 表に無い世代のチャンクは、解釈せずに元のNBTだけを持つ
        let format = match ChunkFormat::for_data_version(chunk.format_data_version) {
            Some(format) => format,
            None => return Ok(chunk),
        };

        chunk.format = Some(format);
        let has_level = chunk.raw.opt_compound("Level")?.is_some();

        // 選んだ世代と本体の包み方が食い違うなら、黙って空のチャンクとして読まずに弾く
        if has_level != format.wrapped_in_level {
            return Err(Error::new(
                ErrorCode::MalformedData,
                format!(
                    "DataVersion {}で選んだ形式と、ルートのLevelの有無が合わない",
                    chunk.format_data_version
                ),
            ));
        }

        let section_list = match chunk.body()?.opt_list(format.sections_key)? {
            Some(list) => list.clone(),
            None => return Ok(chunk),
        };

        // 並び順に依存しないよう、Yから索引を作る
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

    /// DataVersionを検査し、オプションに従って警告またはエラーにする
    fn check_data_version(&self, options: &ChunkReadOptions) -> Result<()> {
        let version = self.data_version()?;

        // 形式が同じであれば、新しいバージョンでもそのまま読める
        if version >= MIN_SUPPORTED_DATA_VERSION {
            return Ok(());
        }

        let message = format!(
            "DataVersion {version} はこのライブラリが扱う形式より古い\
             （{MIN_SUPPORTED_DATA_VERSION} 以降が対象）"
        );

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

    /// NBTへ書き戻す
    /// 全セクションを読んだときの世代の形式で書き戻し、他のキーはそのまま残す
    pub fn to_nbt(&self, options: &ChunkWriteOptions) -> Result<NbtCompound> {
        let version = self.data_version()?;

        // 形式の違う古いチャンクは、書き戻すと使えなくなりかねない
        if version < MIN_SUPPORTED_DATA_VERSION && !options.allow_foreign_data_version {
            return Err(Error::new(
                ErrorCode::UnsupportedDataVersion,
                format!(
                    "DataVersion {version} のチャンクは書き戻せない\
                     （{MIN_SUPPORTED_DATA_VERSION} 以降が対象）。\
                     許可するなら ChunkWriteOptions.allow_foreign_data_version を立てること"
                ),
            ));
        }

        // DataVersionは読んだ値のまま残す
        // 書き換えると、そのワールドを開くゲーム側の判断を誤らせる
        let mut result = self.raw.clone();

        // 元のNBTだけを持つチャンクは、セクションも読んでいないのでそのまま返す
        let format = match self.format {
            Some(format) if !self.sections.is_empty() => format,
            _ => return Ok(result),
        };

        let mut section_list = NbtList::with_element_type(TagType::Compound);

        // Yの昇順で書き出す
        for section in self.sections.values() {
            section_list.push(NbtTag::Compound(section.to_nbt()?))?;
        }

        update_body(&mut result, |body| {
            body.set(format.sections_key, NbtTag::List(section_list))
        })?;
        Ok(result)
    }

    /// チャンクの本体
    /// 1.17までの形式では`Level`の中、1.18以降はルート
    fn body(&self) -> Result<&NbtCompound> {
        // 世代とLevelの有無は読み込みで突き合わせてあるので、Levelがあればその中が本体
        match self.raw.opt_compound("Level")? {
            Some(level) => Ok(level),
            None => Ok(&self.raw),
        }
    }

    /// チャンクの形式の世代を返す
    ///
    /// 世代を引けず、元のNBTだけを持つチャンクなら[`ErrorCode::UnsupportedDataVersion`]を返す
    fn require_format(&self) -> Result<&'static ChunkFormat> {
        match self.format {
            Some(format) => Ok(format),
            None => Err(Error::new(
                ErrorCode::UnsupportedDataVersion,
                format!(
                    "DataVersion {}のチャンクは形式を解釈せず元のNBTだけを持つので、この操作はできない",
                    self.data_version()?
                ),
            )),
        }
    }

    /// Y位置からセクションを得る
    /// 無ければ`None`
    pub fn section(&self, section_y: i32) -> Option<&ChunkSection> {
        self.sections.get(&section_y)
    }

    /// Y位置からセクションへの可変参照を得る
    pub fn section_mut(&mut self, section_y: i32) -> Option<&mut ChunkSection> {
        self.sections.get_mut(&section_y)
    }

    /// ブロックを取得する
    /// XとZはチャンク内相対 (0..15)、Yは絶対座標
    ///
    /// 元のNBTだけを持つチャンクなら[`ErrorCode::UnsupportedDataVersion`]を返す
    pub fn get_block(&self, x: i32, y: i32, z: i32) -> Result<Option<BlockState>> {
        let format = self.require_format()?;
        check_local_coordinates(x, z)?;

        let section = match self.section(y >> 4) {
            Some(section) if section.has_block_states() => section,
            _ => return Ok(None),
        };

        let entry = section.block_states().unwrap().get(block_index(x, y, z))?;

        // パレットの要素の形は世代で違うので、世代ごとに決めたDataVersionで読む
        Ok(Some(BlockState::from_nbt_for_data_version(
            entry,
            format.palette_data_version,
        )?))
    }

    /// ブロックを設定する
    ///
    /// `&BlockState`のほか、`"minecraft:oak_stairs[facing=north]"`の形の文字列でも指定できる
    ///
    /// 置き換えによって不整合になる付随データ（`block_entities` /
    /// `block_ticks` / `fluid_ticks`のうち、その座標を指すもの）は同時に取り除く
    /// パレットには、チャンクを読んだときの世代の形式で入れる
    ///
    /// 元のNBTだけを持つチャンクなら[`ErrorCode::UnsupportedDataVersion`]を返す
    pub fn set_block<S>(&mut self, x: i32, y: i32, z: i32, state: &S) -> Result<()>
    where
        S: IntoBlockState + ?Sized,
    {
        // すでにBlockStateを持っているなら借りるだけで済ませる
        let borrowed = state.as_block_state()?;
        let state: &BlockState = &borrowed;
        let format = self.require_format()?;
        check_local_coordinates(x, z)?;
        let section_y = y >> 4;
        let index = block_index(x, y, z);

        // 同じ状態を置き直すだけなら、付随データを触る理由がない
        // プロパティの並び順に左右されないよう、NBTではなくBlockStateとして比べる
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

        // 書き戻すときに読んだときと同じ形式になるよう、世代ごとに決めたDataVersionで変換する
        section.block_states_mut().unwrap().set(
            index,
            state.to_nbt_for_data_version(format.palette_data_version)?,
        )?;

        self.remove_block_data(format, x, y, z)?;
        self.modified = true;
        Ok(())
    }

    /// その座標を指す付随データを取り除く
    ///
    /// `block_entities` / `block_ticks` / `fluid_ticks`の要素は
    /// いずれも`x` `y` `z`を**絶対座標**で持つ
    fn remove_block_data(&mut self, format: &ChunkFormat, x: i32, y: i32, z: i32) -> Result<()> {
        let absolute_x = (self.x()? * 16) + x;
        let absolute_z = (self.z()? * 16) + z;

        // 3つのリストは形が同じなので、まとめて同じ処理をかける
        for key in format.block_data_keys {
            let filtered = match self.body()?.opt_list(key)? {
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
                update_body(&mut self.raw, |body| body.set(key, NbtTag::List(kept)))?;
            }
        }

        Ok(())
    }

    /// バイオームを取得する
    /// 4×4×4の単位なので、座標は自動的に丸められる
    ///
    /// 元のNBTだけを持つチャンクなら[`ErrorCode::UnsupportedDataVersion`]を返す
    pub fn get_biome(&self, x: i32, y: i32, z: i32) -> Result<Option<String>> {
        self.require_format()?;
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
    /// 4×4×4の単位
    ///
    /// 元のNBTだけを持つチャンクなら[`ErrorCode::UnsupportedDataVersion`]を返す
    pub fn set_biome(&mut self, x: i32, y: i32, z: i32, biome: &str) -> Result<()> {
        self.require_format()?;
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

    /// `Heightmaps`を削除し、Minecraftに再計算させる
    ///
    /// 本ライブラリは高さマップを再計算しない
    /// ブロックを改変したら呼ぶこと
    ///
    /// 元のNBTだけを持つチャンクなら[`ErrorCode::UnsupportedDataVersion`]を返す
    pub fn clear_heightmaps(&mut self) -> Result<()> {
        self.require_format()?;
        update_body(&mut self.raw, |body| {
            body.remove("Heightmaps");
        })?;
        self.modified = true;
        Ok(())
    }

    /// `isLightOn`を0にし、光源の再計算を促す
    ///
    /// 元のNBTだけを持つチャンクなら[`ErrorCode::UnsupportedDataVersion`]を返す
    pub fn invalidate_lighting(&mut self) -> Result<()> {
        self.require_format()?;
        update_body(&mut self.raw, |body| body.set_byte("isLightOn", 0))?;
        self.modified = true;
        Ok(())
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
/// `& 15`により負のY座標でも正しく求まる
pub fn block_index(x: i32, y: i32, z: i32) -> usize {
    (((y & 15) * 256) + ((z & 15) * 16) + (x & 15)) as usize
}

/// セクション内のバイオーム添字
/// 1エントリが4×4×4ブロック
pub fn biome_index(x: i32, y: i32, z: i32) -> usize {
    ((((y & 15) / 4) * 16) + (((z & 15) / 4) * 4) + ((x & 15) / 4)) as usize
}

fn check_local_coordinates(x: i32, z: i32) -> Result<()> {
    // チャンク内相対座標は0..15でなければならない
    if !(0..=15).contains(&x) || !(0..=15).contains(&z) {
        return Err(Error::new(
            ErrorCode::InvalidArgument,
            format!("チャンク内相対座標が範囲外: ({x}, {z})。X も Z も 0..15 であること"),
        ));
    }

    Ok(())
}

//! Minecraft Java版のセーブデータ 1 つ分と、その中の次元。
//!
//! 26.x では構成が大きく変わっており、標準の3次元も
//! `dimensions/<名前空間>/<パス>/` の下に並ぶ。
//!
//! 仕様: `docs/spec/40-world-layout.md`

use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};

use crate::anvil::{ChunkPos, RegionFileMode, RegionFolder};
use crate::error::{Error, ErrorCode, Result};
use crate::nbt::tag::NbtCompound;
use crate::nbt::{read_file, write_file, NamedTag, NbtReadOptions, NbtWriteOptions};

use super::block_state::BlockState;
use super::chunk::{Chunk, ChunkReadOptions, ChunkWriteOptions};

/// ワールドを開くときの動作。
#[derive(Debug, Default)]
pub struct WorldOpenOptions {
    /// 読み書きで開くか。既定は読み取り専用。
    pub writable: bool,
    /// `session.lock` の確認を飛ばすか。
    ///
    /// **Rust 版はこの確認を行わない。** 標準ライブラリだけでは
    /// ファイルの排他ロックを扱えないため（`docs/adr/0008-session-lock.md`）。
    /// 他言語版との API を揃えるためにフィールドだけ用意してある。
    ///
    /// Minecraft が起動中のワールドへ書き込むとデータが壊れるので、
    /// 起動していないことは呼び出し側で担保すること。
    pub ignore_session_lock: bool,
    /// チャンク読み込みのオプション。
    pub chunk_read: ChunkReadOptions,
    /// チャンク書き込みのオプション。
    pub chunk_write: ChunkWriteOptions,
}

/// `level.dat` の内容。
///
/// 26.x では大幅に軽量化されており、ゲームルールやワールド生成設定は
/// `data/minecraft/` 配下の個別ファイルへ分離されている。
///
/// 仕様: `docs/spec/40-world-layout.md` 2章
#[derive(Debug, Clone)]
pub struct LevelData {
    root_name: String,
    raw: NbtCompound,
}

impl LevelData {
    /// ルートの NBT。`Data` を含む。
    pub fn raw(&self) -> &NbtCompound {
        &self.raw
    }

    /// `Data` の中身。実際の設定はここに入っている。
    pub fn data(&self) -> Result<&NbtCompound> {
        self.raw.get_compound("Data")
    }

    /// チャンク構造のバージョン。
    pub fn data_version(&self) -> Result<i32> {
        self.data()?.get_int("DataVersion")
    }

    /// ワールド名。
    pub fn level_name(&self) -> Result<&str> {
        self.data()?.get_string("LevelName")
    }

    /// ワールドの経過時間（tick）。
    pub fn time(&self) -> Result<i64> {
        self.data()?.get_long("Time")
    }

    /// ゲームモード。0=サバイバル 1=クリエイティブ 2=アドベンチャー 3=スペクテイター。
    pub fn game_type(&self) -> Result<i32> {
        self.data()?.get_int("GameType")
    }

    /// スポーン地点の `[x, y, z]`。
    pub fn spawn_pos(&self) -> Result<&[i32]> {
        self.data()?.get_compound("spawn")?.get_int_array("pos")
    }

    /// スポーン地点の次元ID。
    pub fn spawn_dimension(&self) -> Result<&str> {
        self.data()?.get_compound("spawn")?.get_string("dimension")
    }

    /// 難易度（`normal` など）。
    pub fn difficulty(&self) -> Result<&str> {
        self.data()?
            .get_compound("difficulty_settings")?
            .get_string("difficulty")
    }

    /// ハードコアか。
    pub fn is_hardcore(&self) -> Result<bool> {
        self.data()?
            .get_compound("difficulty_settings")?
            .get_bool("hardcore")
    }

    /// バージョン名（`26.2` など）。
    pub fn version_name(&self) -> Result<&str> {
        self.data()?.get_compound("Version")?.get_string("Name")
    }

    /// 書き出し用の [`NamedTag`] を作る。
    pub fn to_named_tag(&self) -> NamedTag {
        NamedTag::new(self.root_name.clone(), self.raw.clone())
    }
}

/// ワールド内の次元 1 つ分。`region/` `entities/` `poi/` をまとめて扱う。
///
/// ブロックの取得・設定は**絶対ワールド座標**で行い、
/// リージョン・チャンク・セクションの解決は内部で済ませる。
///
/// 仕様: `docs/spec/40-world-layout.md` 4章
pub struct Dimension {
    id: String,
    directory: PathBuf,
    writable: bool,
    chunk_read: ChunkReadOptions,
    chunk_write: ChunkWriteOptions,
    regions: Option<RegionFolder>,
    entities: Option<RegionFolder>,
    poi: Option<RegionFolder>,
    chunk_cache: HashMap<(i32, i32), Chunk>,
    modified: HashSet<(i32, i32)>,
    closed: bool,
}

impl Dimension {
    fn new(id: String, directory: PathBuf, options: &WorldOpenOptions) -> Dimension {
        Dimension {
            id,
            directory,
            writable: options.writable,
            chunk_read: ChunkReadOptions {
                on_version_mismatch: options.chunk_read.on_version_mismatch,
                on_warning: None,
                lenient_bit_storage: options.chunk_read.lenient_bit_storage,
            },
            chunk_write: options.chunk_write,
            regions: None,
            entities: None,
            poi: None,
            chunk_cache: HashMap::new(),
            modified: HashSet::new(),
            closed: false,
        }
    }

    /// 次元ID（`minecraft:overworld` など）。
    pub fn id(&self) -> &str {
        &self.id
    }

    /// この次元のディレクトリ。
    pub fn directory(&self) -> &Path {
        &self.directory
    }

    /// 地形のリージョンフォルダ。無ければ `None`。
    pub fn region_folder(&mut self) -> Result<Option<&mut RegionFolder>> {
        self.ensure_open()?;

        if self.regions.is_none() {
            self.regions = self.open_folder("region")?;
        }

        Ok(self.regions.as_mut())
    }

    /// エンティティのリージョンフォルダ。無ければ `None`。
    pub fn entity_folder(&mut self) -> Result<Option<&mut RegionFolder>> {
        self.ensure_open()?;

        if self.entities.is_none() {
            self.entities = self.open_folder("entities")?;
        }

        Ok(self.entities.as_mut())
    }

    /// POI のリージョンフォルダ。無ければ `None`。
    pub fn poi_folder(&mut self) -> Result<Option<&mut RegionFolder>> {
        self.ensure_open()?;

        if self.poi.is_none() {
            self.poi = self.open_folder("poi")?;
        }

        Ok(self.poi.as_mut())
    }

    /// `data/minecraft/<name>.dat` を読む。存在しなければ `None`。
    pub fn data_file(&self, name: &str) -> Result<Option<NbtCompound>> {
        let path = self
            .directory
            .join("data")
            .join("minecraft")
            .join(format!("{name}.dat"));

        if !path.exists() {
            return Ok(None);
        }

        Ok(Some(read_file(&path, &NbtReadOptions::default())?.tag))
    }

    /// この次元に存在する全チャンクの座標を返す。
    pub fn chunk_positions(&mut self) -> Result<Vec<ChunkPos>> {
        match self.region_folder()? {
            Some(folder) => folder.chunk_positions(),
            None => Ok(Vec::new()),
        }
    }

    /// チャンクを読む。読み込んだチャンクはキャッシュされる。
    pub fn chunk(&mut self, chunk_x: i32, chunk_z: i32) -> Result<Option<&Chunk>> {
        self.ensure_open()?;
        let key = (chunk_x, chunk_z);

        if !self.chunk_cache.contains_key(&key) {
            let nbt = match self.region_folder()? {
                Some(folder) => folder.read_chunk(chunk_x, chunk_z)?,
                None => None,
            };

            let nbt = match nbt {
                Some(value) => value,
                None => return Ok(None),
            };

            let options = ChunkReadOptions {
                on_version_mismatch: self.chunk_read.on_version_mismatch,
                on_warning: None,
                lenient_bit_storage: self.chunk_read.lenient_bit_storage,
            };
            self.chunk_cache.insert(key, Chunk::from_nbt(nbt, &options)?);
        }

        Ok(self.chunk_cache.get(&key))
    }

    /// チャンクへの可変参照を得る。変更したら [`Dimension::mark_modified`] を呼ぶこと。
    pub fn chunk_mut(&mut self, chunk_x: i32, chunk_z: i32) -> Result<Option<&mut Chunk>> {
        self.chunk(chunk_x, chunk_z)?;
        Ok(self.chunk_cache.get_mut(&(chunk_x, chunk_z)))
    }

    /// チャンクを「変更あり」として記録する。次の `flush` で書き戻される。
    pub fn mark_modified(&mut self, chunk_x: i32, chunk_z: i32) {
        self.modified.insert((chunk_x, chunk_z));
    }

    /// 絶対座標でブロックを取得する。チャンクが無ければ `None`。
    pub fn get_block(&mut self, x: i32, y: i32, z: i32) -> Result<Option<BlockState>> {
        match self.chunk(x >> 4, z >> 4)? {
            Some(chunk) => chunk.get_block(x & 15, y, z & 15),
            None => Ok(None),
        }
    }

    /// 絶対座標でブロックを設定する。
    ///
    /// 変更したチャンクは記録され、[`Dimension::flush`] でまとめて書き戻される。
    /// 本ライブラリはチャンクを新規生成しないので、存在しない座標はエラーになる。
    pub fn set_block(&mut self, x: i32, y: i32, z: i32, state: &BlockState) -> Result<()> {
        self.ensure_writable()?;
        let chunk_x = x >> 4;
        let chunk_z = z >> 4;

        match self.chunk_mut(chunk_x, chunk_z)? {
            Some(chunk) => chunk.set_block(x & 15, y, z & 15, state)?,
            None => {
                return Err(Error::new(
                    ErrorCode::InvalidArgument,
                    format!(
                        "チャンク ({chunk_x}, {chunk_z}) が存在しない。\
                         本ライブラリはチャンクを生成しない"
                    ),
                ))
            }
        }

        self.modified.insert((chunk_x, chunk_z));
        Ok(())
    }

    /// 絶対座標でバイオームを取得する。4×4×4 の単位。
    pub fn get_biome(&mut self, x: i32, y: i32, z: i32) -> Result<Option<String>> {
        match self.chunk(x >> 4, z >> 4)? {
            Some(chunk) => chunk.get_biome(x & 15, y, z & 15),
            None => Ok(None),
        }
    }

    /// 絶対座標でバイオームを設定する。4×4×4 の単位。
    pub fn set_biome(&mut self, x: i32, y: i32, z: i32, biome: &str) -> Result<()> {
        self.ensure_writable()?;
        let chunk_x = x >> 4;
        let chunk_z = z >> 4;

        match self.chunk_mut(chunk_x, chunk_z)? {
            Some(chunk) => chunk.set_biome(x & 15, y, z & 15, biome)?,
            None => {
                return Err(Error::new(
                    ErrorCode::InvalidArgument,
                    format!(
                        "チャンク ({chunk_x}, {chunk_z}) が存在しない。\
                         本ライブラリはチャンクを生成しない"
                    ),
                ))
            }
        }

        self.modified.insert((chunk_x, chunk_z));
        Ok(())
    }

    /// 変更したチャンクをすべて書き戻し、リージョンをディスクへ反映する。
    pub fn flush(&mut self) -> Result<()> {
        self.ensure_open()?;

        if !self.writable {
            return Ok(());
        }

        // 変更のあったチャンクだけを書き戻す
        let modified: Vec<(i32, i32)> = self.modified.iter().copied().collect();
        let write_options = self.chunk_write;

        for key in modified {
            let nbt = match self.chunk_cache.get(&key) {
                Some(chunk) => Some(chunk.to_nbt(&write_options)?),
                None => None,
            };

            if let Some(nbt) = nbt {
                if let Some(folder) = self.region_folder()? {
                    folder.write_chunk_nbt(key.0, key.1, &nbt)?;
                }
            }
        }

        self.modified.clear();

        for folder in [&mut self.regions, &mut self.entities, &mut self.poi]
            .into_iter()
            .flatten()
        {
            folder.flush()?;
        }

        Ok(())
    }

    /// 変更を書き戻してから閉じる。
    pub fn close(&mut self) -> Result<()> {
        if self.closed {
            return Ok(());
        }

        if self.writable {
            self.flush()?;
        }

        for folder in [&mut self.regions, &mut self.entities, &mut self.poi]
            .into_iter()
            .flatten()
        {
            folder.close()?;
        }

        self.chunk_cache.clear();
        self.closed = true;
        Ok(())
    }

    /// フォルダを開く。存在しなければ `None`。
    fn open_folder(&self, name: &str) -> Result<Option<RegionFolder>> {
        let path = self.directory.join(name);

        // 生成されていない次元にはディレクトリ自体が無い
        if !path.is_dir() && !self.writable {
            return Ok(None);
        }

        let mode = if self.writable {
            RegionFileMode::ReadWrite
        } else {
            RegionFileMode::ReadOnly
        };

        Ok(Some(RegionFolder::open(&path, mode)?))
    }

    fn ensure_writable(&self) -> Result<()> {
        if !self.writable {
            return Err(Error::new(
                ErrorCode::InvalidArgument,
                "読み取り専用で開いたワールドには書き込めない",
            ));
        }

        Ok(())
    }

    fn ensure_open(&self) -> Result<()> {
        if self.closed {
            return Err(Error::new(ErrorCode::InvalidArgument, "既に閉じられた次元"));
        }

        Ok(())
    }
}

/// Minecraft Java版のセーブデータ 1 つ分。
pub struct MinecraftWorld {
    directory: PathBuf,
    options: WorldOpenOptions,
    level: LevelData,
    dimensions: HashMap<String, Dimension>,
    closed: bool,
}

impl MinecraftWorld {
    /// ワールドを開く。
    pub fn open(directory: impl AsRef<Path>, options: WorldOpenOptions) -> Result<MinecraftWorld> {
        let directory = directory.as_ref().to_path_buf();

        if !directory.is_dir() {
            return Err(Error::new(
                ErrorCode::Io,
                format!("ワールドディレクトリが無い: {}", directory.display()),
            ));
        }

        let level_path = directory.join("level.dat");

        if !level_path.exists() {
            return Err(Error::new(
                ErrorCode::Io,
                format!("level.dat が無い: {}", level_path.display()),
            ));
        }

        let named = read_file(&level_path, &NbtReadOptions::default())?;

        Ok(MinecraftWorld {
            directory,
            options,
            level: LevelData { root_name: named.name, raw: named.tag },
            dimensions: HashMap::new(),
            closed: false,
        })
    }

    /// ワールドディレクトリのパス。
    pub fn directory(&self) -> &Path {
        &self.directory
    }

    /// `level.dat` の内容。
    pub fn level(&self) -> &LevelData {
        &self.level
    }

    /// `data/minecraft/<name>.dat` を読む。存在しなければ `None`。
    ///
    /// 26.x では `game_rules` / `weather` / `world_gen_settings` などが
    /// この形で `level.dat` から分離されている。
    pub fn data_file(&self, name: &str) -> Result<Option<NbtCompound>> {
        let path = self
            .directory
            .join("data")
            .join("minecraft")
            .join(format!("{name}.dat"));

        if !path.exists() {
            return Ok(None);
        }

        Ok(Some(read_file(&path, &NbtReadOptions::default())?.tag))
    }

    /// 存在する次元のIDを返す。
    pub fn dimension_ids(&self) -> Result<Vec<String>> {
        let root = self.directory.join("dimensions");
        let mut found = Vec::new();

        if !root.is_dir() {
            return Ok(found);
        }

        // dimensions/<名前空間>/<パス>/ の 2 段を辿る
        for namespace in std::fs::read_dir(&root)?.flatten() {
            if !namespace.path().is_dir() {
                continue;
            }

            let namespace_name = namespace.file_name().to_string_lossy().into_owned();

            for entry in std::fs::read_dir(namespace.path())?.flatten() {
                if entry.path().is_dir() {
                    found.push(format!(
                        "{namespace_name}:{}",
                        entry.file_name().to_string_lossy()
                    ));
                }
            }
        }

        // 走査順がファイルシステム依存にならないよう並べる
        found.sort();
        Ok(found)
    }

    /// 次元を得る。ディレクトリが無ければ `None`。
    pub fn dimension(&mut self, dimension_id: &str) -> Result<Option<&mut Dimension>> {
        self.ensure_open()?;
        let normalized = normalize_dimension_id(dimension_id);

        if !self.dimensions.contains_key(&normalized) {
            let colon = normalized.find(':').unwrap_or(0);
            let path = self
                .directory
                .join("dimensions")
                .join(&normalized[..colon])
                .join(&normalized[colon + 1..]);

            if !path.is_dir() {
                return Ok(None);
            }

            let opened = Dimension::new(normalized.clone(), path, &self.options);
            self.dimensions.insert(normalized.clone(), opened);
        }

        Ok(self.dimensions.get_mut(&normalized))
    }

    /// プレイヤーのUUID一覧。
    pub fn player_ids(&self) -> Result<Vec<String>> {
        let path = self.directory.join("players").join("data");
        let mut found = Vec::new();

        if !path.is_dir() {
            return Ok(found);
        }

        for entry in std::fs::read_dir(&path)?.flatten() {
            let name = entry.file_name().to_string_lossy().into_owned();

            if let Some(stripped) = name.strip_suffix(".dat") {
                found.push(stripped.to_string());
            }
        }

        found.sort();
        Ok(found)
    }

    /// プレイヤーデータを読む。存在しなければ `None`。
    pub fn player(&self, uuid: &str) -> Result<Option<NbtCompound>> {
        let path = self
            .directory
            .join("players")
            .join("data")
            .join(format!("{uuid}.dat"));

        if !path.exists() {
            return Ok(None);
        }

        Ok(Some(read_file(&path, &NbtReadOptions::default())?.tag))
    }

    /// `level.dat` を書き戻す。
    ///
    /// 壊れるとワールド全体が開けなくなるため、
    /// 一時ファイルへ書いてから `level.dat_old` へ退避し、最後に置き換える。
    pub fn save_level(&mut self) -> Result<()> {
        self.ensure_open()?;

        if !self.options.writable {
            return Err(Error::new(
                ErrorCode::InvalidArgument,
                "読み取り専用で開いたワールドには書き込めない",
            ));
        }

        let path = self.directory.join("level.dat");
        let temporary = self.directory.join("level.dat.tmp");
        let backup = self.directory.join("level.dat_old");

        write_file(&temporary, &self.level.to_named_tag(), &NbtWriteOptions::default())?;

        if path.exists() {
            std::fs::copy(&path, &backup)?;
        }

        std::fs::rename(&temporary, &path)?;
        Ok(())
    }

    /// 開いている次元をすべて閉じる。
    pub fn close(&mut self) -> Result<()> {
        if self.closed {
            return Ok(());
        }

        for dimension in self.dimensions.values_mut() {
            dimension.close()?;
        }

        self.dimensions.clear();
        self.closed = true;
        Ok(())
    }

    fn ensure_open(&self) -> Result<()> {
        if self.closed {
            return Err(Error::new(ErrorCode::InvalidArgument, "既に閉じられたワールド"));
        }

        Ok(())
    }
}

/// 名前空間が省略されていたら `minecraft:` を補う。
fn normalize_dimension_id(dimension_id: &str) -> String {
    if dimension_id.contains(':') {
        return dimension_id.to_string();
    }

    format!("minecraft:{dimension_id}")
}

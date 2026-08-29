//! リージョンファイルが並ぶディレクトリ 1 つ分。
//!
//! `region/`、`entities/`、`poi/` のいずれかを表す。
//! 開いたリージョンファイルはキャッシュし、[`RegionFolder::close`] でまとめて閉じる。
//! チャンク座標からリージョンを解決するので、利用側はリージョンの存在を意識しなくてよい。
//!
//! [`RegionFile`] はファイル全体をメモリへ載せるため、キャッシュには
//! [`RegionFolder::max_cached_regions`] 件の上限がある。上限を超えると、
//! 最も長く使われていないものから書き出して閉じる。
//! 大きなワールドを端から走査してもメモリを使い切らない。
//!
//! このため [`RegionFolder::region`] が返した参照は、
//! **別のリージョンへアクセスすると閉じられている場合がある**。
//! 参照を保持せず、必要なたびに取得すること。
//!
//! 仕様: `docs/spec/20-anvil-region.md` 5章

use std::collections::{HashMap, VecDeque};
use std::path::{Path, PathBuf};

use crate::error::{Error, ErrorCode, Result};
use crate::nbt::tag::NbtCompound;

use super::region::{ChunkPos, RegionFile, RegionFileMode, RegionPos};

/// 同時に開いておくリージョンファイル数の既定の上限。
///
/// 1 リージョンは最大 255 セクタ × 1024 チャンク＝理論上 1GiB になりうる。
/// 実データでは数 MB から数十 MB 程度。8 件なら通常のワールドで数百 MB に収まる。
pub const DEFAULT_MAX_CACHED_REGIONS: usize = 8;

/// リージョンフォルダ 1 つ分。
pub struct RegionFolder {
    directory: PathBuf,
    mode: RegionFileMode,
    cache: HashMap<RegionPos, RegionFile>,
    /// 最近使った順のリージョン座標。末尾がいちばん新しい。
    recently_used: VecDeque<RegionPos>,
    max_cached_regions: usize,
    closed: bool,
}

impl RegionFolder {
    /// リージョンフォルダを開く。
    pub fn open(directory: impl AsRef<Path>, mode: RegionFileMode) -> Result<RegionFolder> {
        RegionFolder::open_with_limit(directory, mode, DEFAULT_MAX_CACHED_REGIONS)
    }

    /// 上限を指定してリージョンフォルダを開く。
    pub fn open_with_limit(
        directory: impl AsRef<Path>,
        mode: RegionFileMode,
        max_cached_regions: usize,
    ) -> Result<RegionFolder> {
        let directory = directory.as_ref().to_path_buf();

        if max_cached_regions < 1 {
            return Err(Error::new(
                ErrorCode::InvalidArgument,
                "max_cached_regions は 1 以上でなければならない",
            ));
        }

        if !directory.is_dir() && mode == RegionFileMode::ReadOnly {
            return Err(Error::new(
                ErrorCode::Io,
                format!("リージョンフォルダが存在しない: {}", directory.display()),
            ));
        }

        Ok(RegionFolder {
            directory,
            mode,
            cache: HashMap::new(),
            recently_used: VecDeque::new(),
            max_cached_regions,
            closed: false,
        })
    }

    /// 同時に開いておくリージョンファイル数の上限。
    pub fn max_cached_regions(&self) -> usize {
        self.max_cached_regions
    }

    /// いま開いているリージョンファイル数。
    pub fn cached_region_count(&self) -> usize {
        self.cache.len()
    }

    /// このフォルダのパス。
    pub fn directory(&self) -> &Path {
        &self.directory
    }

    /// このフォルダに存在するリージョンの座標を返す。
    pub fn region_positions(&self) -> Result<Vec<RegionPos>> {
        self.ensure_open()?;

        if !self.directory.is_dir() {
            return Ok(Vec::new());
        }

        let entries = match std::fs::read_dir(&self.directory) {
            Ok(value) => value,
            Err(error) => {
                return Err(Error::with_source(
                    ErrorCode::Io,
                    format!("リージョンフォルダを走査できない: {}", self.directory.display()),
                    error,
                ))
            }
        };

        let mut found = Vec::new();

        // r.X.Z.mca として解釈できるファイルだけを拾う
        for entry in entries.flatten() {
            let name = entry.file_name().to_string_lossy().into_owned();

            if let Some(position) = RegionPos::from_file_name(&name) {
                found.push(position);
            }
        }

        // 走査順がファイルシステム依存にならないよう、座標で並べる
        found.sort_by(|left, right| left.z.cmp(&right.z).then(left.x.cmp(&right.x)));
        Ok(found)
    }

    /// リージョンファイルを取得する。読み取り専用で存在しなければ `None`。
    pub fn region(&mut self, region_x: i32, region_z: i32) -> Result<Option<&mut RegionFile>> {
        self.ensure_open()?;
        let position = RegionPos::new(region_x, region_z);

        if !self.cache.contains_key(&position) {
            let path = self.directory.join(position.file_name());

            // 読み取り専用では、存在しないリージョンは「チャンクが無い」として None を返す
            if !path.exists() && self.mode == RegionFileMode::ReadOnly {
                return Ok(None);
            }

            // 開く前に空きを作る。開いてからだと一瞬だけ上限を超える
            self.evict_until_below_limit()?;

            let opened = RegionFile::open(&path, self.mode)?;
            self.cache.insert(position, opened);
        }

        self.touch(position);
        Ok(self.cache.get_mut(&position))
    }

    /// 使ったリージョンを、最近使った列の末尾へ移す。
    fn touch(&mut self, position: RegionPos) {
        // 同じ座標が列に残っていたら、先に取り除いてから末尾へ積む
        if let Some(index) = self.recently_used.iter().position(|item| *item == position) {
            self.recently_used.remove(index);
        }

        self.recently_used.push_back(position);
    }

    /// 新しく 1 件開けるよう、上限を下回るまで古いものを閉じる。
    fn evict_until_below_limit(&mut self) -> Result<()> {
        // 上限に達している間、いちばん長く使っていないものから閉じる
        while self.cache.len() >= self.max_cached_regions {
            let oldest = match self.recently_used.pop_front() {
                Some(position) => position,
                None => break,
            };

            if let Some(mut file) = self.cache.remove(&oldest) {
                // 閉じる前に必ず書き出す。捨てると変更が失われる
                file.close()?;
            }
        }

        Ok(())
    }

    /// チャンクが存在するか。
    pub fn has_chunk(&mut self, chunk_x: i32, chunk_z: i32) -> Result<bool> {
        let position = ChunkPos::new(chunk_x, chunk_z).region();

        match self.region(position.x, position.z)? {
            Some(file) => file.has_chunk(chunk_x, chunk_z),
            None => Ok(false),
        }
    }

    /// チャンクを NBT として読む。存在しなければ `None`。
    pub fn read_chunk(&mut self, chunk_x: i32, chunk_z: i32) -> Result<Option<NbtCompound>> {
        let position = ChunkPos::new(chunk_x, chunk_z).region();

        match self.region(position.x, position.z)? {
            Some(file) => file.read_chunk(chunk_x, chunk_z),
            None => Ok(None),
        }
    }

    /// チャンクを NBT として書き込む。
    pub fn write_chunk(
        &mut self,
        chunk_x: i32,
        chunk_z: i32,
        tag: &NbtCompound,
        compression: super::region::ChunkCompression,
    ) -> Result<()> {
        let position = ChunkPos::new(chunk_x, chunk_z).region();
        let directory = self.directory.clone();

        match self.region(position.x, position.z)? {
            Some(file) => file.write_chunk(chunk_x, chunk_z, tag, compression),
            None => Err(Error::new(
                ErrorCode::InvalidArgument,
                format!("読み取り専用のフォルダには書き込めない: {}", directory.display()),
            )),
        }
    }

    /// すでに組み立て済みの NBT をチャンクとして書き込む。
    ///
    /// 既定の Zlib 圧縮を使う。World 層から呼ぶための入口。
    pub fn write_chunk_nbt(
        &mut self,
        chunk_x: i32,
        chunk_z: i32,
        tag: &NbtCompound,
    ) -> Result<()> {
        self.write_chunk(chunk_x, chunk_z, tag, super::region::ChunkCompression::Zlib)
    }

    /// チャンクを削除する。削除できたら `true`。
    pub fn delete_chunk(&mut self, chunk_x: i32, chunk_z: i32) -> Result<bool> {
        let position = ChunkPos::new(chunk_x, chunk_z).region();

        match self.region(position.x, position.z)? {
            Some(file) => file.delete_chunk(chunk_x, chunk_z),
            None => Ok(false),
        }
    }

    /// このフォルダに存在する全チャンクの座標を返す。
    pub fn chunk_positions(&mut self) -> Result<Vec<ChunkPos>> {
        let positions = self.region_positions()?;
        let mut result = Vec::new();

        // リージョンごとに、その中のチャンクを順に集める
        for position in positions {
            if let Some(file) = self.region(position.x, position.z)? {
                result.extend(file.chunk_positions()?);
            }
        }

        Ok(result)
    }

    /// 開いている全リージョンの変更を書き出す。
    pub fn flush(&mut self) -> Result<()> {
        self.ensure_open()?;

        for file in self.cache.values_mut() {
            file.flush()?;
        }

        Ok(())
    }

    /// 開いている全リージョンを閉じる。
    pub fn close(&mut self) -> Result<()> {
        if self.closed {
            return Ok(());
        }

        for file in self.cache.values_mut() {
            file.close()?;
        }

        self.cache.clear();
        self.recently_used.clear();
        self.closed = true;
        Ok(())
    }

    fn ensure_open(&self) -> Result<()> {
        if self.closed {
            return Err(Error::new(
                ErrorCode::InvalidArgument,
                "既に閉じられたリージョンフォルダ",
            ));
        }

        Ok(())
    }
}

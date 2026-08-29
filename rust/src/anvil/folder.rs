//! リージョンファイルが並ぶディレクトリ 1 つ分。
//!
//! `region/`、`entities/`、`poi/` のいずれかを表す。
//! 開いたリージョンファイルはキャッシュし、[`RegionFolder::close`] でまとめて閉じる。
//! チャンク座標からリージョンを解決するので、利用側はリージョンの存在を意識しなくてよい。
//!
//! 仕様: `docs/spec/20-anvil-region.md` 5章

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use crate::error::{Error, ErrorCode, Result};
use crate::nbt::tag::NbtCompound;

use super::region::{ChunkPos, RegionFile, RegionFileMode, RegionPos};

/// リージョンフォルダ 1 つ分。
pub struct RegionFolder {
    directory: PathBuf,
    mode: RegionFileMode,
    cache: HashMap<RegionPos, RegionFile>,
    closed: bool,
}

impl RegionFolder {
    /// リージョンフォルダを開く。
    pub fn open(directory: impl AsRef<Path>, mode: RegionFileMode) -> Result<RegionFolder> {
        let directory = directory.as_ref().to_path_buf();

        if !directory.is_dir() && mode == RegionFileMode::ReadOnly {
            return Err(Error::new(
                ErrorCode::Io,
                format!("リージョンフォルダが存在しない: {}", directory.display()),
            ));
        }

        Ok(RegionFolder { directory, mode, cache: HashMap::new(), closed: false })
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

            let opened = RegionFile::open(&path, self.mode)?;
            self.cache.insert(position, opened);
        }

        Ok(self.cache.get_mut(&position))
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

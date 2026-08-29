//! Anvil のリージョンファイル (.mca) の読み書き
//!
//! 仕様: `docs/spec/20-anvil-region.md`

pub mod folder;
pub mod region;

pub use folder::{RegionFolder, DEFAULT_MAX_CACHED_REGIONS};
pub use region::{
    ChunkCompression, ChunkPos, RawChunk, RegionFile, RegionFileMode, RegionPos, SECTOR_SIZE,
};

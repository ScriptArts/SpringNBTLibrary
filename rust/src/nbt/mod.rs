//! NBT (Named Binary Tag) の読み書き
//!
//! このレイヤは Minecraft のバージョンに一切依存しない
//!
//! 仕様: `docs/spec/10-nbt-binary.md`

pub mod canonical;
pub mod io;
pub mod mutf8;
pub mod snbt;
pub mod tag;

pub use io::{
    detect_compression, read_bytes, read_bytes_all, read_bytes_at, read_file, read_reader,
    write_bytes, write_file, write_writer, Compression, NamedTag, NbtFormat, NbtReadOptions,
    NbtReadResult, NbtWriteOptions,
};
pub use tag::{NbtCompound, NbtList, NbtString, NbtTag, TagType};

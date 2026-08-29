//! SpringNBTLibrary — Minecraft Java版の NBT / Anvil ワールドデータを読み書きするライブラリ。
//!
//! 仕様は `docs/spec/` を唯一の正とする。
//! 対象バージョンは Java版 26.2 (DataVersion 4903)。

#![forbid(unsafe_code)]
#![warn(missing_docs)]

/// 本ライブラリが対象とする Minecraft Java版の DataVersion (26.2)。
pub const TARGET_DATA_VERSION: i32 = 4903;
pub mod anvil;
pub mod error;
pub mod nbt;
pub mod world;

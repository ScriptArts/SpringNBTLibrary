//! SpringNBTLibrary — Minecraft Java版の NBT / Anvil ワールドデータを読み書きするライブラリ
//!
//! 仕様は `docs/spec/` を唯一の正とする
//! 対象バージョンは Java版 26.2 (DataVersion 4903)

#![forbid(unsafe_code)]
#![warn(missing_docs)]

/// このライブラリが扱えるワールド形式の下限となる DataVersion (26.1)
///
/// 26.1 で次元とプレイヤーデータの置き場が変わり、いまの形式になった
/// これ以降のバージョンは、形式が同じであればそのまま読み書きできる
///
/// これより古いワールドは構成そのものが違うので、
/// 読み込み時に `UNSUPPORTED_DATA_VERSION` の対象になる
pub const MIN_SUPPORTED_DATA_VERSION: i32 = 4786;

/// 動作を確かめた Minecraft Java版の DataVersion (26.2)
pub const TARGET_DATA_VERSION: i32 = 4903;

pub mod anvil;
pub mod error;
pub mod nbt;
pub mod world;

//! SpringNBTLibraryは、Minecraft Java版のNBT / Anvilワールドデータを読み書きするライブラリ
//!
//! 対象は26.3で導入されたワールド形式 (DataVersion 5006以降)

#![forbid(unsafe_code)]
#![warn(missing_docs)]

/// このライブラリが扱えるワールド形式の下限となるDataVersion (26.3)
///
/// 26.3でブロックのパレットの形式が変わり、いまの形式になった
/// 5006はMinecraftがこの形式へ変換するDataVersionで、26.3 Snapshot 7で入った
/// これ以降のバージョンは、形式が同じであればそのまま読み書きできる
///
/// これより古いワールドはパレットの書き方が違う
/// そうしたチャンクは、読み込み時は既定で警告を出し、書き戻しは既定で`UNSUPPORTED_DATA_VERSION`にする
pub const MIN_SUPPORTED_DATA_VERSION: i32 = 5006;

/// 動作を確かめたMinecraft Java版のDataVersion (26.3)
pub const TARGET_DATA_VERSION: i32 = 5023;

pub mod anvil;
pub mod error;
pub mod nbt;
pub mod world;

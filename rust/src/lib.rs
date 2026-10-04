//! SpringNBTLibraryは、Minecraft Java版のNBT / Anvilワールドデータを読み書きするライブラリ
//!
//! 対象は26.1で導入されたワールド形式 (DataVersion 4786以降)

#![forbid(unsafe_code)]
#![warn(missing_docs)]

/// このライブラリが扱えるワールド形式の下限となるDataVersion (26.1)
///
/// 26.1で次元とプレイヤーデータの置き場が変わり、いまの形式になった
/// これ以降のバージョンは、形式が同じであればそのまま読み書きできる
///
/// これより古いワールドは構成そのものが違う
/// そうしたチャンクは、読み込み時は既定で警告を出し、書き戻しは既定で`UNSUPPORTED_DATA_VERSION`にする
pub const MIN_SUPPORTED_DATA_VERSION: i32 = 4786;

/// 動作を確かめたMinecraft Java版のDataVersion (26.2)
pub const TARGET_DATA_VERSION: i32 = 4903;

pub mod anvil;
pub mod error;
pub mod nbt;
pub mod world;

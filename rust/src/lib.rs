//! SpringNBTLibraryは、Minecraft Java版のNBT / Anvilワールドデータを読み書きするライブラリ
//!
//! 対象は1.18以降のワールド形式 (DataVersion 2844以降)

#![forbid(unsafe_code)]
#![warn(missing_docs)]

/// このライブラリが扱えるワールド形式の下限となるDataVersion (1.18)
///
/// 1.18でチャンクの本体が`Level`の外へ出て、セクションがパレット付きのコンテナになった
/// 2844はMinecraftがこの形式へ変換するDataVersionで、1.18の開発版で入った
/// これ以降のチャンクは、読んだときの形式のまま読み書きできる
/// 26.3（DataVersion 5006）でパレットの要素の形が変わったが、どちらの形式も扱う
///
/// これより古いチャンクは形式が違う
/// そうしたチャンクは、読み込み時は既定で警告を出し、書き戻しは既定で`UNSUPPORTED_DATA_VERSION`にする
pub const MIN_SUPPORTED_DATA_VERSION: i32 = 2844;

/// 動作を確かめたMinecraft Java版のDataVersion (26.3)
pub const TARGET_DATA_VERSION: i32 = 5023;

pub mod anvil;
pub mod error;
pub mod nbt;
pub mod world;

/**
 * SpringNBTLibraryは、Minecraft Java版のNBT / Anvilワールドデータを読み書きするライブラリ
 *
 * 対象は26.3で導入されたワールド形式 (DataVersion 5006以降)
 */

/**
 * このライブラリが扱えるワールド形式の下限となるDataVersion (26.3)
 *
 * 26.3でブロックのパレットの形式が変わり、いまの形式になった
 * 5006はMinecraftがこの形式へ変換するDataVersionで、26.3 Snapshot 7で入った
 * これ以降のバージョンは、形式が同じであればそのまま読み書きできる
 *
 * これより古いワールドはパレットの書き方が違う
 * そうしたチャンクは、読み込み時は既定で警告を出し、書き戻しは既定でUNSUPPORTED_DATA_VERSIONにする
 */
export const MIN_SUPPORTED_DATA_VERSION = 5006;

/** 動作を確かめたMinecraft Java版のDataVersion (26.3) */
export const TARGET_DATA_VERSION = 5023;

export { ErrorCode, SpringNbtError, errorCodeAsString } from "./errors.js";

// レイヤごとの名前空間
// 他言語のモジュール構成に対応する
export * as nbt from "./nbt/index.js";
export * as anvil from "./anvil/index.js";
export * as world from "./world/index.js";

// よく使う型はトップレベルからも直接取れるようにする
// 3つのレイヤで名前が衝突しないことはcheck_docs_syncが保証する
export * from "./nbt/index.js";
export * from "./anvil/index.js";
export * from "./world/index.js";

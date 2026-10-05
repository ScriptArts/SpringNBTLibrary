/**
 * SpringNBTLibraryは、Minecraft Java版のNBT / Anvilワールドデータを読み書きするライブラリ
 *
 * 対象は26.1で導入されたワールド形式 (DataVersion 4786以降)
 */

/**
 * このライブラリが扱えるワールド形式の下限となるDataVersion (26.1)
 *
 * 26.1で次元とプレイヤーデータの置き場が変わり、いまの形式になった
 * これ以降のバージョンは、形式が同じであればそのまま読み書きできる
 *
 * これより古いワールドは構成そのものが違う
 * そうしたチャンクは、読み込み時は既定で警告を出し、書き戻しは既定でUNSUPPORTED_DATA_VERSIONにする
 */
export const MIN_SUPPORTED_DATA_VERSION = 4786;

/** 動作を確かめたMinecraft Java版のDataVersion (26.2) */
export const TARGET_DATA_VERSION = 4903;

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

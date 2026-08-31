/**
 * SpringNBTLibrary — Minecraft Java版の NBT / Anvil ワールドデータを読み書きするライブラリ
 *
 * 仕様は `docs/spec/` を唯一の正とする
 * 対象バージョンは Java版 26.2 (DataVersion 4903)
 */

/**
 * このライブラリが扱えるワールド形式の下限となる DataVersion (26.1)
 *
 * 26.1 で次元とプレイヤーデータの置き場が変わり、いまの形式になった
 * これ以降のバージョンは、形式が同じであればそのまま読み書きできる
 *
 * これより古いワールドは構成そのものが違うので、
 * 読み込み時に UNSUPPORTED_DATA_VERSION の対象になる
 */
export const MIN_SUPPORTED_DATA_VERSION = 4786;

/** 動作を確かめた Minecraft Java版の DataVersion (26.2) */
export const TARGET_DATA_VERSION = 4903;

export { ErrorCode, SpringNbtError, errorCodeAsString } from "./errors.js";

// レイヤごとの名前空間
// 他言語のモジュール構成に対応する
export * as nbt from "./nbt/index.js";
export * as anvil from "./anvil/index.js";
export * as world from "./world/index.js";

// よく使う型はトップレベルからも直接取れるようにする
// 3 つのレイヤで名前が衝突しないことは check_docs_sync が保証する
export * from "./nbt/index.js";
export * from "./anvil/index.js";
export * from "./world/index.js";

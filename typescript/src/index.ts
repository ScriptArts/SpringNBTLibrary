/**
 * SpringNBTLibrary — Minecraft Java版の NBT / Anvil ワールドデータを読み書きするライブラリ
 *
 * 仕様は `docs/spec/` を唯一の正とする
 * 対象バージョンは Java版 26.2 (DataVersion 4903)
 */

/** 本ライブラリが対象とする Minecraft Java版の DataVersion (26.2)
/** */
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

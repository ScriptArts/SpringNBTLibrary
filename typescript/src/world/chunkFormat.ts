/**
 * チャンクの形式の世代の境界
 * ライブラリの内部だけで使う
 * `index.ts`からは出さない
 */

/**
 * ブロックのパレット要素が`id` / `properties`の形式になるDataVersion（26.3）
 * これ未満は`Name` / `Properties`の形式
 */
export const PALETTE_ID_FORMAT_DATA_VERSION = 5006;

/** DataVersionを指定して読み書きできる最も古いDataVersion（1.13の正式版） */
export const OLDEST_FORMAT_DATA_VERSION = 1519;

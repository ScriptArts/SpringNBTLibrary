/**
 * チャンクの形式の世代
 * ライブラリの内部だけで使う
 * `index.ts`からは出さない
 *
 * 世代ごとの違いはこの表に集める
 * チャンクの読み書きは表の値に従い、DataVersionによる分岐をほかの場所に書かない
 */

/**
 * ブロックのパレット要素が`id` / `properties`の形式になるDataVersion（26.3）
 * これ未満は`Name` / `Properties`の形式
 */
export const PALETTE_ID_FORMAT_DATA_VERSION = 5006;

/** DataVersionを指定して読み書きできる最も古いDataVersion（1.13の正式版） */
export const OLDEST_FORMAT_DATA_VERSION = 1519;

/** バイオームの持ち方 */
export enum BiomeStorage {
  /** セクションごとのパレット付きコンテナ */
  Paletted = "paletted",
  /** チャンクの列ごとの数値のバイオームID（`int[256]`） */
  Ids2D = "ids_2d",
  /** 4×4×4ブロックごとの数値のバイオームID（`int[1024]`） */
  Ids3D = "ids_3d",
}

/** ルートの直下に置かれる、ブロックに紐づく付随データのキー（1.18以降） */
const ROOT_BLOCK_DATA_KEYS: readonly string[] = ["block_entities", "block_ticks", "fluid_ticks"];

/** チャンクの形式の世代1つ分 */
export class ChunkFormat {
  constructor(
    /** この世代が始まるDataVersion */
    readonly minDataVersion: number,
    /** チャンクの本体が`Level`の中にあるか */
    readonly wrappedInLevel: boolean,
    /** セクションの一覧のキー */
    readonly sectionsKey: string,
    /** パレットの要素と`BlockState`の変換に渡すDataVersion */
    readonly paletteDataVersion: number,
    /** ビット詰めで値が64bitの境目をまたぐか */
    readonly spanningBitStorage: boolean,
    /** バイオームの持ち方 */
    readonly biomeStorage: BiomeStorage,
    /** ブロックを置き換えたときに取り除く付随データのキー */
    readonly blockDataKeys: readonly string[],
  ) {}

  /**
   * DataVersionから世代を引く
   * 表にあるどの世代よりも古ければundefined
   */
  static forDataVersion(dataVersion: number): ChunkFormat | undefined {
    let result: ChunkFormat | undefined = undefined;

    // 表は境界の昇順に並ぶので、境界以上の最後の世代が当てはまる
    for (const format of FORMATS) {
      // 境界に届いた世代だけを候補にする
      if (dataVersion >= format.minDataVersion) {
        result = format;
      }
    }

    return result;
  }
}

/**
 * 世代の表
 * 境界のDataVersionの昇順に並べる
 */
const FORMATS: readonly ChunkFormat[] = [
  // C4: 1.18〜26.2
  // Levelが無くなり、パレットの要素はName / Properties
  new ChunkFormat(2844, false, "sections", 2844, false, BiomeStorage.Paletted, ROOT_BLOCK_DATA_KEYS),
  // C5: 26.3以降
  // パレットの要素は文字列かid / properties
  new ChunkFormat(
    PALETTE_ID_FORMAT_DATA_VERSION,
    false,
    "sections",
    PALETTE_ID_FORMAT_DATA_VERSION,
    false,
    BiomeStorage.Paletted,
    ROOT_BLOCK_DATA_KEYS,
  ),
];

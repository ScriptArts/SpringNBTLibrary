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

/** セクションのブロックの持ち方 */
export enum BlockStorage {
  /**
   * セクションの`block_states`にあるパレット付きコンテナ（`palette` / `data`）
   * パレットが1要素なら`data`を持たない
   */
  Container = "container",
  /**
   * セクションの直下の`Palette`と`BlockStates`
   * `BlockStates`はパレットが1要素でも必ずある
   */
  SectionPalette = "section_palette",
}

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

/** `Level`の中に置かれる、ブロックに紐づく付随データのキー（1.17まで） */
const LEVEL_BLOCK_DATA_KEYS: readonly string[] = ["TileEntities", "TileTicks", "LiquidTicks"];

/**
 * 生成済みとみなす`Status`の値（名前空間を外した形）
 * 世代を引けないチャンクもこれで判定する
 */
export const DEFAULT_FULL_STATUSES: readonly string[] = ["full"];

/**
 * 1.14までの形式で生成済みとみなす`Status`の値
 * 1.13は生成を終えたチャンクを`fullchunk`や`postprocessed`で保存する
 */
const FULL_STATUSES_1_13: readonly string[] = ["full", "postprocessed", "fullchunk"];

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
    /** セクションのブロックの持ち方 */
    readonly blockStorage: BlockStorage,
    /** バイオームの持ち方 */
    readonly biomeStorage: BiomeStorage,
    /** ブロックを置き換えたときに取り除く付随データのキー */
    readonly blockDataKeys: readonly string[],
    /**
     * ルートに最下段セクションのY位置（`yPos`）があるか
     * 無い世代では、セクションは0段目から始まる
     */
    readonly hasYPos: boolean,
    /**
     * `isLightOn`の無いチャンクで光源を無効化するとき、`isLightOn`を書き足すか
     * 1.17までは生成途中のチャンクに`isLightOn`が無く（1.13はどのチャンクにも無い）、
     * 書き足すと元に無いキーが増えるので足さない
     */
    readonly addsLightFlag: boolean,
    /** 生成済みとみなす`Status`の値（名前空間を外した形） */
    readonly fullStatuses: readonly string[],
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
  // C1: 1.13〜1.14.x
  // C2と同じで、バイオームは列ごとの数値のID
  // 1.13の生成済みのチャンクはStatusがfullchunkかpostprocessed
  new ChunkFormat(
    OLDEST_FORMAT_DATA_VERSION,
    true,
    "Sections",
    OLDEST_FORMAT_DATA_VERSION,
    true,
    BlockStorage.SectionPalette,
    BiomeStorage.Ids2D,
    LEVEL_BLOCK_DATA_KEYS,
    false,
    false,
    FULL_STATUSES_1_13,
  ),
  // C2: 1.15〜1.15.2
  // C3と同じで、ビット詰めが値を64bitの境目でまたぐ
  new ChunkFormat(
    2203,
    true,
    "Sections",
    2203,
    true,
    BlockStorage.SectionPalette,
    BiomeStorage.Ids3D,
    LEVEL_BLOCK_DATA_KEYS,
    false,
    false,
    DEFAULT_FULL_STATUSES,
  ),
  // C3: 1.16〜1.17.x
  // 本体はLevelの中で、ブロックはセクションの直下のPalette / BlockStates
  // バイオームは4×4×4ブロックごとの数値のID
  new ChunkFormat(
    2529,
    true,
    "Sections",
    2529,
    false,
    BlockStorage.SectionPalette,
    BiomeStorage.Ids3D,
    LEVEL_BLOCK_DATA_KEYS,
    false,
    false,
    DEFAULT_FULL_STATUSES,
  ),
  // C4: 1.18〜26.2
  // Levelが無くなり、パレットの要素はName / Properties
  new ChunkFormat(
    2844,
    false,
    "sections",
    2844,
    false,
    BlockStorage.Container,
    BiomeStorage.Paletted,
    ROOT_BLOCK_DATA_KEYS,
    true,
    true,
    DEFAULT_FULL_STATUSES,
  ),
  // C5: 26.3以降
  // パレットの要素は文字列かid / properties
  new ChunkFormat(
    PALETTE_ID_FORMAT_DATA_VERSION,
    false,
    "sections",
    PALETTE_ID_FORMAT_DATA_VERSION,
    false,
    BlockStorage.Container,
    BiomeStorage.Paletted,
    ROOT_BLOCK_DATA_KEYS,
    true,
    true,
    DEFAULT_FULL_STATUSES,
  ),
];

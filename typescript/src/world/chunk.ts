/**
 * チャンク1つ分
 * 地形の読み書きはここから行う
 *
 * 読んだNBTをそのまま保持し、書き戻すときに作り直すのはセクションだけにする
 * 未知のキーを落とさないので、将来の追加要素があってもデータをおかしくしない
 */

import { MIN_SUPPORTED_DATA_VERSION } from "../index.js";
import { ErrorCode, SpringNbtError } from "../errors.js";
import {
  NbtByte,
  NbtCompound,
  NbtInt,
  NbtIntArray,
  NbtList,
  NbtString,
  NbtTag,
  TagType,
  tagTypeAsString,
} from "../nbt/index.js";
import { BlockState } from "./blockState.js";
import {
  BiomeStorage,
  BlockStorage,
  ChunkFormat,
  DEFAULT_FULL_STATUSES,
  OLDEST_FORMAT_DATA_VERSION,
} from "./chunkFormat.js";
import { PalettedContainer } from "./palettedContainer.js";

/** セクション1つに入るブロック数 */
export const BLOCKS_PER_SECTION = 4096;

/** セクション1つに入るバイオームのエントリ数（4×4×4単位） */
export const BIOMES_PER_SECTION = 64;

/** 1.15から1.17までの形式で、チャンクの`Biomes`が持つ数値のバイオームIDの数（4×4×4単位で高さ256まで） */
const BIOME_IDS_3D_LENGTH = 1024;

/** 1.14までの形式で、チャンクの`Biomes`が持つ数値のバイオームIDの数（列ごと） */
const BIOME_IDS_2D_LENGTH = 256;

/** DataVersionの無いチャンクで、世代の指定も無いときの`Chunk.formatDataVersion` */
const MISSING_DATA_VERSION = -1;

/** 1.17までの形式で、バイオームIDを持つ最も高いY座標 */
const BIOME_IDS_MAX_Y = 255;

/** 生成段階の名前空間 */
const MINECRAFT_NAMESPACE = "minecraft:";

/** 付随データの要素が、指定の絶対座標を指しているか */
/**
 * パレット付きコンテナを、読んだときのキーの並びを保ってセクションへ書き戻す
 *
 * 読んだときにあったキーはその並びで置き、要らなくなった`data`は落とす
 * 読んだときに無かった`data`を足すときだけ、ライブラリの並び（`data`、`palette`の順）を先に置く
 * どちらの場合も、読んだときにあったほかのキーは残す
 * 並びは読んだときのキーで決めるので、何度書き戻しても同じ結果になる
 */
function writeContainer(
  section: NbtCompound,
  key: string,
  written: NbtCompound,
  readKeys: string[] | undefined,
): void {
  const current = section.optCompound(key);

  // 読んだときにコンテナが無ければ、書き出した形をそのまま置く
  if (current === undefined || readKeys === undefined) {
    section.set(key, written);
    return;
  }

  const order: string[] = [];
  // 読んだときに無かったdataを足すときだけ、ライブラリの並びを先に置く
  if (written.containsKey("data") && !readKeys.includes("data")) {
    order.push(...written.keys());
  }

  // 読んだときの並びで、残すキーを後ろに続ける
  for (const name of readKeys) {
    // 先に並べたキーは二度入れない
    if (order.includes(name)) {
      continue;
    }

    // 要らなくなったdataは落とす
    if (name === "data" && !written.containsKey("data")) {
      continue;
    }

    order.push(name);
  }

  const result = new NbtCompound();

  // 書き出した形にあるキーはその値で、ほかのキーは元の値で並べる
  for (const name of order) {
    // コンテナの中身は書き出した形の値にする
    if (written.containsKey(name)) {
      result.set(name, written.get(name));
    } else {
      result.set(name, current.get(name));
    }
  }

  section.set(key, result);
}

function matchesPosition(entry: NbtCompound, x: number, y: number, z: number): boolean {
  const entryX = entry.optInt("x");
  const entryY = entry.optInt("y");
  const entryZ = entry.optInt("z");

  // 座標を持たない要素は、対象かどうか判断できないので触らない
  if (entryX === undefined || entryY === undefined || entryZ === undefined) {
    return false;
  }

  return entryX === x && entryY === y && entryZ === z;
}

/** エラーや警告の文で、チャンクをDataVersionで言い表す */
function describeChunk(dataVersion: number | undefined): string {
  // 1.9より前のチャンクはDataVersionを持たない
  if (dataVersion === undefined) {
    return "DataVersionの無いチャンク";
  }

  return `DataVersion ${dataVersion}のチャンク`;
}

/**
 * ブロック状態を置くときに使うパレット要素を決める
 *
 * 同じ状態の要素がパレットにあれば、キーやプロパティの並びが違ってもそれを使う
 * 無ければ世代の形式で作る
 */
function paletteEntryFor(container: PalettedContainer, state: BlockState, dataVersion: number): NbtTag {
  // 実データの{Properties, Name}の並びの要素も、状態として比べて使い回す
  for (const entry of container.palette) {
    // 状態が同じ要素が見つかれば、パレットを増やさずにそれを置く
    if (BlockState.fromNbtForDataVersion(entry, dataVersion).equals(state)) {
      return entry;
    }
  }

  return state.toNbtForDataVersion(dataVersion);
}

/** DataVersionが扱える形式より古いときの動作 */
export enum VersionMismatchAction {
  /**
   * 警告コールバックを呼んで続行する
   * 既定
   */
  Warn = "warn",
  /** `UNSUPPORTED_DATA_VERSION`の例外にする */
  Error = "error",
  /** 何もしない */
  Ignore = "ignore",
}

/** チャンク読み込みのオプション */
export interface ChunkReadOptions {
  /**
   * DataVersionが扱える形式より古いときの動作
   * 既定は`Warn`
   */
  onVersionMismatch?: VersionMismatchAction;
  /** 警告の通知先 */
  onWarning?: (message: string) => void;
  /** dataの長さが期待値と違うとき、長さからビット幅を逆算して読むか */
  lenientBitStorage?: boolean;
  /**
   * チャンクの形式の世代を選ぶDataVersion
   *
   * 省略すると、チャンク自身のDataVersionで選ぶ
   * 1519以上でなければならない
   * 扱える形式の下限との比較には使わず、常にチャンク自身のDataVersionで比べる
   */
  formatDataVersion?: number;
}

/** チャンク書き込みのオプション */
export interface ChunkWriteOptions {
  /**
   * 扱える形式より古いDataVersionを持つチャンクの書き戻しを許すか
   *
   * 既定はfalse
   * エラーを出さずに古いワールドを新形式で上書きし、
   * 利用者が気づかないうちに使えなくすることを防ぐため
   */
  allowForeignDataVersion?: boolean;
}

/**
 * チャンクをY方向に16ブロックずつ区切った16×16×16の立方体
 *
 * `BlockLight` / `SkyLight`などの解釈していないキーは元のNBTに残り、
 * 書き戻しでそのまま出力される
 */
export class ChunkSection {
  #blockStates: PalettedContainer | undefined;
  #biomes: PalettedContainer | undefined;
  /**
   * ブロックの持ち方
   * 書き戻すときに読んだときと同じキーへ書くため、覚えておく
   */
  #blockStorage = BlockStorage.Container;
  /**
   * パレット付きコンテナを読んだときのキーの並び
   * 書き戻しで同じ並びにするため、コンテナのキーごとに覚えておく
   */
  readonly #containerKeys = new Map<string, string[]>();

  private constructor(
    readonly raw: NbtCompound,
    readonly y: number,
  ) {}

  /**
   * ブロック状態
   * 持たないセクション（光源専用）ではundefined
   */
  get blockStates(): PalettedContainer | undefined {
    return this.#blockStates;
  }

  /**
   * バイオーム
   * 持たないセクションではundefined
   */
  get biomes(): PalettedContainer | undefined {
    return this.#biomes;
  }

  /** ブロック状態を持つか */
  get hasBlockStates(): boolean {
    return this.#blockStates !== undefined;
  }

  /** バイオームを持つか */
  get hasBiomes(): boolean {
    return this.#biomes !== undefined;
  }

  /**
   * NBTからセクションを読む
   * 1.18以降の形式（`block_states` / `biomes`）として読む
   */
  static fromNbt(nbt: NbtCompound, lenientBitStorage: boolean): ChunkSection {
    const section = new ChunkSection(nbt, nbt.getByte("Y"));
    const blockStates = nbt.optCompound("block_states");

    // 光源専用のセクションはblock_statesを持たない
    if (blockStates !== undefined) {
      section.#blockStates = PalettedContainer.fromNbt(
        blockStates,
        BLOCKS_PER_SECTION,
        4,
        lenientBitStorage,
      );
      section.#containerKeys.set("block_states", [...blockStates.keys()]);
    }

    const biomes = nbt.optCompound("biomes");

    // 光源だけを持つセクションにはバイオームが無い
    if (biomes !== undefined) {
      section.#biomes = PalettedContainer.fromNbt(
        biomes,
        BIOMES_PER_SECTION,
        1,
        lenientBitStorage,
      );
      section.#containerKeys.set("biomes", [...biomes.keys()]);
    }

    return section;
  }

  /**
   * 世代の持ち方に従ってNBTからセクションを読む
   *
   * @internal
   */
  static fromNbtForFormat(nbt: NbtCompound, lenientBitStorage: boolean, format: ChunkFormat): ChunkSection {
    // 1.18以降の形式は公開の読み込みと同じ
    if (format.blockStorage === BlockStorage.Container) {
      return ChunkSection.fromNbt(nbt, lenientBitStorage);
    }

    const section = new ChunkSection(nbt, nbt.getByte("Y"));
    section.#blockStorage = format.blockStorage;
    const palette = nbt.optList("Palette");
    const blockStates = nbt.optLongArray("BlockStates");

    // Minecraftも両方がそろったセクションだけを読むので、
    // 片方しか無いセクション（光源だけを持つものなど）はブロックを持たない
    if (palette === undefined || blockStates === undefined) {
      return section;
    }

    const entries: NbtTag[] = [];

    // 書き戻すときにCompoundのリストとして書くので、要素の型をここで確かめる
    for (const entry of palette) {
      // Compound以外の要素は1.17までの形式に無い
      if (entry.type !== TagType.Compound) {
        throw SpringNbtError.unexpectedTagType(
          `Palette の要素が compound でない: ${tagTypeAsString(entry.type)}`,
        );
      }

      entries.push(entry);
    }

    // BlockStatesはパレットが1要素でも必ず書かれる
    section.#blockStates = PalettedContainer.fromParts(
      entries,
      blockStates,
      BLOCKS_PER_SECTION,
      4,
      format.spanningBitStorage,
      true,
      lenientBitStorage,
    );
    return section;
  }

  /**
   * NBTへ書き戻す
   * 解釈していないキーはそのまま残る
   */
  toNbt(): NbtCompound {
    // 1.17までの形式は、セクションの直下のPaletteとBlockStatesへ書き戻す
    if (this.#blockStates !== undefined && this.#blockStorage === BlockStorage.SectionPalette) {
      const parts = this.#blockStates.toParts();
      const paletteTag = new NbtList(TagType.Compound);

      // 要素は読んだときのまま並べる
      for (const entry of parts.palette) {
        paletteTag.add(entry);
      }

      // 既存のキーへ書くので、キーの並びは読んだときのまま残る
      this.raw.setLongArray("BlockStates", parts.data!);
      this.raw.set("Palette", paletteTag);
      return this.raw;
    }

    // 解釈したコンテナだけを書き戻す
    // 持たないキーは元のまま残す
    if (this.#blockStates !== undefined) {
      writeContainer(
        this.raw,
        "block_states",
        this.#blockStates.toNbt(),
        this.#containerKeys.get("block_states"),
      );
    }

    // 解釈したコンテナだけを書き戻す
    // 持たないキーは元のまま残す
    if (this.#biomes !== undefined) {
      writeContainer(this.raw, "biomes", this.#biomes.toNbt(), this.#containerKeys.get("biomes"));
    }

    return this.raw;
  }

  /** 使われていないパレット要素を取り除く */
  compact(): void {
    if (this.#blockStates !== undefined) {
      this.#blockStates.compact();
    }

    if (this.#biomes !== undefined) {
      this.#biomes.compact();
    }
  }
}

/**
 * チャンク1つ分
 * 地形の読み書きはここから行う
 *
 * 読んだNBTをそのまま保持し、書き戻すときに作り直すのはセクションだけにする
 * 未知のキーを落とさないので、将来の追加要素があってもデータをおかしくしない
 */
export class Chunk {
  // 書き戻しで読んだときと同じ並びにするため、Yを読んだ順に持つ
  readonly #sections = new Map<number, ChunkSection>();
  #modified = false;

  /**
   * チャンクの形式の世代
   * 引けなかったチャンクはundefinedのままで、元のNBTだけを持つ
   */
  #format: ChunkFormat | undefined = undefined;

  /**
   * チャンクの形式の世代を選ぶのに使ったDataVersion
   * 読み込みのオプションで指定していればその値、指定が無ければチャンク自身のDataVersion
   */
  #formatDataVersion = 0;

  private constructor(readonly raw: NbtCompound) {}

  /**
   * チャンク構造のバージョン
   *
   * @throws SpringNbtError `DataVersion`の無いチャンク（1.9より前）の場合
   */
  get dataVersion(): number {
    return this.raw.getInt("DataVersion");
  }

  /**
   * チャンクの形式の世代を選ぶのに使ったDataVersion
   *
   * 読み込みのオプションで指定していればその値、指定が無ければ`dataVersion`
   * `dataVersion`が1519未満のチャンクでは、世代を選ばずに指定の値をそのまま返す
   * `DataVersion`の無いチャンクで指定も無ければ-1
   */
  get formatDataVersion(): number {
    return this.#formatDataVersion;
  }

  /** 絶対チャンクX座標 */
  get x(): number {
    return this.#body().getInt("xPos");
  }

  /** 絶対チャンクZ座標 */
  get z(): number {
    return this.#body().getInt("zPos");
  }

  /**
   * 最下段セクションのY位置
   * オーバーワールドは-4
   * 1.17までの形式では0
   *
   * @throws SpringNbtError 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）
   */
  get minSectionY(): number {
    const format = this.#requireFormat();

    // 1.17までの形式はyPosを持たず、セクションは0段目から始まる
    if (!format.hasYPos) {
      return 0;
    }

    return this.raw.getInt("yPos");
  }

  /**
   * 生成段階（`minecraft:full`など）
   * 1.19までは名前空間の無い`full`などで入る
   */
  get status(): string {
    return this.#body().getString("Status");
  }

  /**
   * 生成が完了しているか
   * ブロック改変の対象にしてよいのはこれだけ
   *
   * 1.14までの形式では、1.13の`postprocessed`と`fullchunk`も生成済みとみなす
   * `Status`が無いか文字列でないチャンク（1.13より前のものなど）は生成済みとみなさない
   */
  get isFullyGenerated(): boolean {
    let status: string;

    // 1.13より前のチャンクなど、Statusを文字列として読めないものは生成済みとみなさない
    try {
      status = this.status;
    } catch (error) {
      // ライブラリのエラー以外は、そのまま呼び出し元へ伝える
      if (!(error instanceof SpringNbtError)) {
        throw error;
      }

      return false;
    }

    // 名前空間の有無はバージョンで違うので、外してから比べる
    if (status.startsWith(MINECRAFT_NAMESPACE)) {
      status = status.substring(MINECRAFT_NAMESPACE.length);
    }

    let fullStatuses = DEFAULT_FULL_STATUSES;

    // 生成済みとみなす値は世代で違う
    if (this.#format !== undefined) {
      fullStatuses = this.#format.fullStatuses;
    }

    return fullStatuses.includes(status);
  }

  /**
   * このチャンクに変更が加わったか
   *
   * ブロックやバイオームを書き換えると立つ
   * `Dimension.flush()`はこれが立っているチャンクだけを書き戻す
   *
   * `raw`を直接いじった場合は立たないので、自分でtrueにすること
   */
  get isModified(): boolean {
    return this.#modified;
  }

  /** 変更の印を付け外しする */
  set isModified(value: boolean) {
    this.#modified = value;
  }

  /**
   * 存在するセクションのY位置
   * 昇順
   */
  get sectionYs(): number[] {
    return [...this.#sections.keys()].sort((left, right) => left - right);
  }

  /**
   * NBTからチャンクを読む
   *
   * 形式の世代は、オプションで指定したDataVersionか、チャンク自身のDataVersionで選ぶ
   * DataVersionが1519未満のチャンクは、指定があってもどの世代でも解釈せず、元のNBTだけを持つ
   *
   * @throws SpringNbtError 世代を選ぶDataVersionが1519未満の場合（INVALID_ARGUMENT）、
   * 選んだ世代とチャンクの構造が合わない場合（MALFORMED_DATA）、
   * 必須のキーが無い、または構造が想定と違う場合
   */
  static fromNbt(nbt: NbtCompound, options?: ChunkReadOptions): Chunk {
    let requested: number | undefined = undefined;

    // 指定があるときだけ、その値で世代を選ぶ
    if (options !== undefined) {
      requested = options.formatDataVersion;
    }

    // 1.13より前の形式は、どの世代の部品でも読めない
    if (requested !== undefined && requested < OLDEST_FORMAT_DATA_VERSION) {
      throw SpringNbtError.invalidArgument(
        `世代を選ぶDataVersionは${OLDEST_FORMAT_DATA_VERSION}以上でなければならない: ${requested}`,
      );
    }

    const chunk = new Chunk(nbt);
    chunk.#checkDataVersion(options);
    const dataVersion = chunk.#ownDataVersion();
    chunk.#formatDataVersion = MISSING_DATA_VERSION;

    // DataVersionを持つチャンクは、指定が無ければそれで世代を選ぶ
    if (dataVersion !== undefined) {
      chunk.#formatDataVersion = dataVersion;
    }

    // 指定があれば、チャンク自身のDataVersionの代わりにその値で世代を選ぶ
    if (requested !== undefined) {
      chunk.#formatDataVersion = requested;
    }

    // 1.13より前のチャンクはブロックが数値IDで、どの世代で読んでも誤った値になる
    // DataVersionの無いチャンクは1.9より前のものなので、同じく解釈しない
    if (dataVersion === undefined || dataVersion < OLDEST_FORMAT_DATA_VERSION) {
      return chunk;
    }

    const format = ChunkFormat.forDataVersion(chunk.#formatDataVersion);

    // 表に無い世代のチャンクは、解釈せずに元のNBTだけを持つ
    if (format === undefined) {
      return chunk;
    }

    chunk.#format = format;
    const hasLevel = nbt.optCompound("Level") !== undefined;

    // 選んだ世代と本体の包み方が食い違うなら、空のチャンクとして読み進めずにエラーにする
    if (hasLevel !== format.wrappedInLevel) {
      throw SpringNbtError.malformed(
        `DataVersion ${chunk.#formatDataVersion}で選んだ形式と、ルートのLevelの有無が合わない`,
      );
    }

    let lenient = false;

    if (options !== undefined && options.lenientBitStorage === true) {
      lenient = true;
    }

    const sectionList = chunk.#body().optList(format.sectionsKey);

    if (sectionList === undefined) {
      return chunk;
    }

    // 並び順に依存しないよう、Yから索引を作る
    for (const entry of sectionList) {
      if (entry.type !== TagType.Compound) {
        throw SpringNbtError.unexpectedTagType("sections の要素が compound でない");
      }

      // セクションのブロックの持ち方は世代で違う
      const section = ChunkSection.fromNbtForFormat(entry as NbtCompound, lenient, format);
      chunk.#sections.set(section.y, section);
    }

    return chunk;
  }

  /**
   * チャンク自身のDataVersion
   * 無ければundefined
   */
  #ownDataVersion(): number | undefined {
    return this.raw.optInt("DataVersion");
  }

  /** DataVersionを検査し、オプションに従って警告またはエラーにする */
  #checkDataVersion(options?: ChunkReadOptions): void {
    const version = this.#ownDataVersion();

    // 形式が同じであれば、新しいバージョンでもそのまま読める
    if (version !== undefined && version >= MIN_SUPPORTED_DATA_VERSION) {
      return;
    }

    let action = VersionMismatchAction.Warn;

    if (options !== undefined && options.onVersionMismatch !== undefined) {
      action = options.onVersionMismatch;
    }

    const message =
      `${describeChunk(version)}はこのライブラリが扱う形式より古い` +
      `（${MIN_SUPPORTED_DATA_VERSION}以降が対象）`;

    if (action === VersionMismatchAction.Error) {
      throw new SpringNbtError(ErrorCode.UnsupportedDataVersion, message);
    }

    // 警告として扱う設定で、通知先があるときだけ知らせる
    if (action === VersionMismatchAction.Warn && options !== undefined
        && options.onWarning !== undefined) {
      options.onWarning(message);
    }
  }

  /**
   * NBTへ書き戻す
   * 全セクションを読んだときの世代の形式で、読んだときの並びのまま書き戻し、他のキーはそのまま残す
   */
  toNbt(options?: ChunkWriteOptions): NbtCompound {
    const version = this.#ownDataVersion();
    const supported = version !== undefined && version >= MIN_SUPPORTED_DATA_VERSION;
    let allowForeign = false;

    if (options !== undefined && options.allowForeignDataVersion === true) {
      allowForeign = true;
    }

    // 形式の違う古いチャンクは、書き戻すと使えなくなりかねない
    if (!supported && !allowForeign) {
      throw new SpringNbtError(
        ErrorCode.UnsupportedDataVersion,
        `${describeChunk(version)}は書き戻せない` +
          `（${MIN_SUPPORTED_DATA_VERSION}以降が対象）。` +
          "許可するなら allowForeignDataVersion を立てること",
      );
    }

    // DataVersionは読んだ値のまま残す
    // 書き換えると、そのワールドを開くゲーム側の判断を誤らせる

    // 元のNBTだけを持つチャンクは、セクションも読んでいないのでそのまま返す
    if (this.#format === undefined || this.#sections.size === 0) {
      return this.raw;
    }

    const sectionList = new NbtList(TagType.Compound);

    // 読んだときの並びで書き出す
    for (const section of this.#sections.values()) {
      sectionList.add(section.toNbt());
    }

    this.#body().set(this.#format.sectionsKey, sectionList);
    return this.raw;
  }

  /**
   * チャンクの本体
   * 1.17までの形式では`Level`の中、1.18以降はルート
   */
  #body(): NbtCompound {
    const level = this.raw.optCompound("Level");

    // 世代とLevelの有無は読み込みで突き合わせてあるので、Levelがあればその中が本体
    if (level !== undefined) {
      return level;
    }

    return this.raw;
  }

  /**
   * チャンクの形式の世代を返す
   *
   * @throws SpringNbtError 世代を引けず、元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）
   */
  #requireFormat(): ChunkFormat {
    // 世代を引けなかったチャンクは、ブロックなどの場所が分からない
    if (this.#format === undefined) {
      throw new SpringNbtError(
        ErrorCode.UnsupportedDataVersion,
        `${describeChunk(this.#ownDataVersion())}は形式を解釈せず元のNBTだけを持つので、この操作はできない`,
      );
    }

    return this.#format;
  }

  /**
   * バイオームを名前で読み書きできる世代を返す
   *
   * @throws SpringNbtError 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）、
   * バイオームを数値のIDで持つ世代の場合（UNSUPPORTED_FEATURE）
   */
  #requireNamedBiomes(): ChunkFormat {
    const format = this.#requireFormat();

    // 1.17まではバイオームを数値のIDで持ち、名前では読み書きできない
    if (format.biomeStorage !== BiomeStorage.Paletted) {
      throw SpringNbtError.unsupportedFeature(
        `DataVersion ${this.#formatDataVersion}のチャンクはバイオームを数値のIDで持つ。` +
          "getBiomeId / setBiomeIdを使うこと",
      );
    }

    return format;
  }

  /**
   * バイオームを数値のIDで読み書きできる世代を返す
   *
   * @throws SpringNbtError 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）、
   * バイオームを名前で持つ世代の場合（UNSUPPORTED_FEATURE）
   */
  #requireBiomeIds(): ChunkFormat {
    const format = this.#requireFormat();

    // 1.18以降はバイオームを名前で持ち、数値のIDでは読み書きできない
    if (format.biomeStorage === BiomeStorage.Paletted) {
      throw SpringNbtError.unsupportedFeature(
        `DataVersion ${this.#formatDataVersion}のチャンクはバイオームを名前で持つ。` +
          "getBiome / setBiomeを使うこと",
      );
    }

    return format;
  }

  /**
   * 本体の`Biomes`を返す
   * 無い、IntArrayでない、長さが世代と合わない場合はundefined
   */
  #biomeIds(format: ChunkFormat): Int32Array | undefined {
    const biomes = this.#body().opt("Biomes");

    // 生成途中のチャンクなどは、Biomesを持たないか別の形で持つ
    if (!(biomes instanceof NbtIntArray) || biomes.value.length !== biomeIdsLength(format)) {
      return undefined;
    }

    return biomes.value;
  }

  /**
   * Y位置からセクションを得る
   * 無ければundefined
   */
  section(sectionY: number): ChunkSection | undefined {
    return this.#sections.get(sectionY);
  }

  /**
   * ブロックを取得する
   *
   * @param x チャンク内相対X座標 (0..15)
   * @param y 絶対Y座標
   * @param z チャンク内相対Z座標 (0..15)
   * @throws SpringNbtError 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）
   */
  getBlock(x: number, y: number, z: number): BlockState | undefined {
    const format = this.#requireFormat();
    checkLocalCoordinates(x, z);
    const section = this.section(y >> 4);

    if (section === undefined || !section.hasBlockStates) {
      return undefined;
    }

    // パレットの要素の形は世代で違うので、世代ごとに決めたDataVersionで読む
    return BlockState.fromNbtForDataVersion(
      section.blockStates!.get(blockIndex(x, y, z)),
      format.paletteDataVersion,
    );
  }

  /**
   * ブロックを設定する
   *
   * `minecraft:oak_stairs[facing=north]`の形の文字列でも指定できる
   *
   * 置き換えによって不整合になる付随データ（`block_entities` /
   * `block_ticks` / `fluid_ticks`のうち、その座標を指すもの）は同時に取り除く
   * 1.17までの形式では、`Level`の中の`TileEntities` / `TileTicks` / `LiquidTicks`から取り除く
   * 残すとブロックと中身が食い違い、Minecraft側で予期しない挙動になるため
   *
   * パレットには、チャンクを読んだときの世代の形式で入れる
   *
   * @throws SpringNbtError 対象のセクションが無い、またはblock_statesを持たない場合、
   * 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）
   */
  setBlock(x: number, y: number, z: number, state: BlockState | string): void {
    // 文字列で渡されたらBlockStateへ直してから進む
    if (typeof state === "string") {
      this.setBlock(x, y, z, BlockState.parse(state));
      return;
    }

    const format = this.#requireFormat();
    checkLocalCoordinates(x, z);

    const sectionY = y >> 4;
    const section = this.section(sectionY);

    if (section === undefined || !section.hasBlockStates) {
      throw SpringNbtError.invalidArgument(
        `Y=${y} を含むセクション（Y=${sectionY}）が無いか、ブロックを持たない。` +
          "本ライブラリはセクションを新規生成しない",
      );
    }

    // 同じ状態を置き直すだけなら、付随データを触る理由がない
    const current = this.getBlock(x, y, z);

    if (current !== undefined && current.equals(state)) {
      return;
    }

    // 書き戻すときに読んだときと同じ形式になるよう、世代ごとに決めたDataVersionで読み書きする
    const entry = paletteEntryFor(section.blockStates!, state, format.paletteDataVersion);
    section.blockStates!.set(blockIndex(x, y, z), entry);
    this.#removeBlockData(format, x, y, z);
    this.#modified = true;
  }

  /**
   * その座標を指す付随データを取り除く
   *
   * `block_entities` / `block_ticks` / `fluid_ticks`の要素は
   * いずれも`x` `y` `z`を**絶対座標**で持つ
   * 1.17までの形式の`TileEntities` / `TileTicks` / `LiquidTicks`も同じ
   */
  #removeBlockData(format: ChunkFormat, x: number, y: number, z: number): void {
    const absoluteX = this.x * 16 + x;
    const absoluteZ = this.z * 16 + z;
    const body = this.#body();

    // 3つのリストは形が同じなので、まとめて同じ処理をかける
    for (const key of format.blockDataKeys) {
      const list = body.optList(key);

      if (list === undefined || list.size === 0) {
        continue;
      }

      // 後ろから削ると、削除しても残りの添字がずれない
      for (let position = list.size - 1; position >= 0; position--) {
        const element = list.get(position);

        // 座標を持つ要素のうち、指定の位置を指すものだけを取り除く
        if (element instanceof NbtCompound && matchesPosition(element, absoluteX, y, absoluteZ)) {
          list.removeAt(position);
        }
      }
    }
  }

  /**
   * バイオームを取得する
   * 4×4×4の単位なので、座標は自動的に丸められる
   *
   * @throws SpringNbtError 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）、
   * バイオームを数値のIDで持つ1.17までの形式の場合（UNSUPPORTED_FEATURE）
   */
  getBiome(x: number, y: number, z: number): string | undefined {
    this.#requireNamedBiomes();
    checkLocalCoordinates(x, z);
    const section = this.section(y >> 4);

    if (section === undefined || !section.hasBiomes) {
      return undefined;
    }

    const entry = section.biomes!.get(biomeIndex(x, y, z));

    if (entry.type !== TagType.String) {
      throw SpringNbtError.unexpectedTagType("バイオームのパレット要素が string でない");
    }

    return (entry as NbtString).value;
  }

  /**
   * バイオームを設定する
   * 4×4×4の単位
   *
   * @throws SpringNbtError 対象のセクションが無い、またはバイオームを持たない場合、
   * 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）、
   * バイオームを数値のIDで持つ1.17までの形式の場合（UNSUPPORTED_FEATURE）
   */
  setBiome(x: number, y: number, z: number, biome: string): void {
    this.#requireNamedBiomes();
    checkLocalCoordinates(x, z);

    const sectionY = y >> 4;
    const section = this.section(sectionY);

    if (section === undefined || !section.hasBiomes) {
      throw SpringNbtError.invalidArgument(
        `Y=${y} を含むセクション（Y=${sectionY}）が無いか、バイオームを持たない`,
      );
    }

    section.biomes!.set(biomeIndex(x, y, z), new NbtString(biome));
    this.#modified = true;
  }

  /**
   * 数値のバイオームIDを取得する（1.17までの形式）
   * 1.15以降の形式は4×4×4の単位なので、座標は自動的に丸められる
   * 1.14までの形式は列ごとに持つので、Yは見ない
   *
   * IDは名前に直さない
   * 1.16.2以降はデータパックで独自のバイオームを足せるので、固定の表では正しく引けないため
   *
   * @param x チャンク内相対X座標 (0..15)
   * @param y 絶対Y座標
   * @param z チャンク内相対Z座標 (0..15)
   * @returns バイオームID
   * 1.15以降の形式でYが0..255の外の場合と、`Biomes`が無いか形が違う場合はundefined
   * @throws SpringNbtError 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）、
   * バイオームを名前で持つ1.18以降の形式の場合（UNSUPPORTED_FEATURE）
   */
  getBiomeId(x: number, y: number, z: number): number | undefined {
    const format = this.#requireBiomeIds();
    checkLocalCoordinates(x, z);
    const biomes = this.#biomeIds(format);

    // Biomesを読めないチャンクは値を持たない
    if (biomes === undefined) {
      return undefined;
    }

    // 列ごとに持つ形式は高さを見ない
    if (format.biomeStorage === BiomeStorage.Ids2D) {
      return biomes[biomeId2DIndex(x, z)];
    }

    // 高さの範囲外は値を持たない
    if (y < 0 || y > BIOME_IDS_MAX_Y) {
      return undefined;
    }

    return biomes[biomeIdIndex(x, y, z)];
  }

  /**
   * 数値のバイオームIDを設定する（1.17までの形式）
   * 1.15以降の形式は4×4×4の単位
   * 1.14までの形式は列ごとに持つので、Yは見ない
   *
   * @throws SpringNbtError 1.15以降の形式でYが0..255の外の場合、`Biomes`が無いか形が違う場合、
   * IDがintの範囲に収まらない場合（INVALID_ARGUMENT）、
   * 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）、
   * バイオームを名前で持つ1.18以降の形式の場合（UNSUPPORTED_FEATURE）
   */
  setBiomeId(x: number, y: number, z: number, biomeId: number): void {
    const format = this.#requireBiomeIds();
    checkLocalCoordinates(x, z);
    let index = biomeId2DIndex(x, z);

    // 4×4×4ごとに持つ形式は、高さ0..255の分だけある
    if (format.biomeStorage === BiomeStorage.Ids3D) {
      // 範囲外の高さはどの値にも当たらない
      if (y < 0 || y > BIOME_IDS_MAX_Y) {
        throw SpringNbtError.invalidArgument(
          `Y=${y} はバイオームIDを持つ高さ（0..${BIOME_IDS_MAX_Y}）の外`,
        );
      }

      index = biomeIdIndex(x, y, z);
    }

    const biomes = this.#biomeIds(format);

    // 読めないBiomesを作り直すと元のデータを失うので、書き込まない
    if (biomes === undefined) {
      throw SpringNbtError.invalidArgument(
        `Biomes が無いか、int[${biomeIdsLength(format)}] でない`,
      );
    }

    // Int32Arrayへ入れると範囲外の値がエラーにならずに丸められるので、intの範囲の検査を先に通す
    biomes[index] = new NbtInt(biomeId).value;
    this.#modified = true;
  }

  /**
   * `Heightmaps`を削除し、Minecraftに再計算させる
   *
   * 本ライブラリは高さマップを再計算しない
   * ブロックを改変したら呼ぶこと
   *
   * @throws SpringNbtError 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）
   */
  clearHeightmaps(): void {
    this.#requireFormat();
    this.#body().remove("Heightmaps");
    this.#modified = true;
  }

  /**
   * `isLightOn`を0にし、光源の再計算を促す
   *
   * @throws SpringNbtError 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）、
   * `isLightOn`の無い1.17までの形式のチャンクの場合（UNSUPPORTED_FEATURE）
   */
  invalidateLighting(): void {
    const format = this.#requireFormat();
    const body = this.#body();

    // 書き足さない世代では、isLightOnの無いチャンクは光源の印を持たない
    if (!format.addsLightFlag && !body.containsKey("isLightOn")) {
      throw SpringNbtError.unsupportedFeature(
        `DataVersion ${this.#formatDataVersion}のチャンクは isLightOn を持たない`,
      );
    }

    body.setByte("isLightOn", 0);
    this.#modified = true;
  }

  /** 使われていないパレット要素を全セクションから取り除く */
  compact(): void {
    // 全セクションのパレットをまとめて掃除する
    for (const section of this.#sections.values()) {
      section.compact();
    }
  }
}

/**
 * セクション内のブロック添字
 *
 * `& 15`により負のY座標でも正しく求まる
 */
export function blockIndex(x: number, y: number, z: number): number {
  return (y & 15) * 256 + (z & 15) * 16 + (x & 15);
}

/**
 * セクション内のバイオーム添字
 * 1エントリが4×4×4ブロック
 */
export function biomeIndex(x: number, y: number, z: number): number {
  return Math.floor((y & 15) / 4) * 16 + Math.floor((z & 15) / 4) * 4 + Math.floor((x & 15) / 4);
}

/**
 * 1.15から1.17までの形式の`Biomes`の添字
 * 1エントリが4×4×4ブロック
 */
function biomeIdIndex(x: number, y: number, z: number): number {
  return ((y >> 2) & 63) * 16 + (z >> 2) * 4 + (x >> 2);
}

/**
 * 1.14までの形式の`Biomes`の添字
 * 1エントリが1列
 */
function biomeId2DIndex(x: number, z: number): number {
  return z * 16 + x;
}

/** 世代の`Biomes`が持つ数値のバイオームIDの数 */
function biomeIdsLength(format: ChunkFormat): number {
  // 列ごとに持つ形式は256個
  if (format.biomeStorage === BiomeStorage.Ids2D) {
    return BIOME_IDS_2D_LENGTH;
  }

  return BIOME_IDS_3D_LENGTH;
}

function checkLocalCoordinates(x: number, z: number): void {
  // チャンク内相対座標は0..15でなければならない
  if (x < 0 || x > 15 || z < 0 || z > 15) {
    throw SpringNbtError.invalidArgument(
      `チャンク内相対座標が範囲外: (${x}, ${z})。X も Z も 0..15 であること`,
    );
  }
}

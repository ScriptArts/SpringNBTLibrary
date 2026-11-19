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
  NbtList,
  NbtString,
  NbtTag,
  TagType,
} from "../nbt/index.js";
import { BlockState } from "./blockState.js";
import { ChunkFormat, OLDEST_FORMAT_DATA_VERSION } from "./chunkFormat.js";
import { PalettedContainer } from "./palettedContainer.js";

/** セクション1つに入るブロック数 */
export const BLOCKS_PER_SECTION = 4096;

/** セクション1つに入るバイオームのエントリ数（4×4×4単位） */
export const BIOMES_PER_SECTION = 64;

/** 付随データの要素が、指定の絶対座標を指しているか */
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

  /** NBTからセクションを読む */
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
    }

    const biomes = nbt.optCompound("biomes");

    if (biomes !== undefined) {
      section.#biomes = PalettedContainer.fromNbt(
        biomes,
        BIOMES_PER_SECTION,
        1,
        lenientBitStorage,
      );
    }

    return section;
  }

  /**
   * NBTへ書き戻す
   * 解釈していないキーはそのまま残る
   */
  toNbt(): NbtCompound {
    if (this.#blockStates !== undefined) {
      this.raw.set("block_states", this.#blockStates.toNbt());
    }

    if (this.#biomes !== undefined) {
      this.raw.set("biomes", this.#biomes.toNbt());
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
  readonly #sections = new Map<number, ChunkSection>();
  #modified = false;

  /**
   * チャンクの形式の世代
   * 引けなかったチャンクはundefinedのままで、元のNBTだけを持つ
   */
  #format: ChunkFormat | undefined = undefined;
  #formatDataVersion = 0;

  private constructor(readonly raw: NbtCompound) {}

  /** チャンク構造のバージョン */
  get dataVersion(): number {
    return this.raw.getInt("DataVersion");
  }

  /**
   * チャンクの形式の世代を選ぶのに使ったDataVersion
   *
   * 読み込みのオプションで指定していればその値、指定が無ければ`dataVersion`
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
   */
  get minSectionY(): number {
    return this.raw.getInt("yPos");
  }

  /** 生成段階（`minecraft:full`など） */
  get status(): string {
    return this.#body().getString("Status");
  }

  /**
   * 生成が完了しているか
   * ブロック改変の対象にしてよいのはこれだけ
   */
  get isFullyGenerated(): boolean {
    return this.status === "minecraft:full";
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
    const dataVersion = chunk.dataVersion;
    chunk.#formatDataVersion = dataVersion;

    // 指定があれば、チャンク自身のDataVersionの代わりにその値で世代を選ぶ
    if (requested !== undefined) {
      chunk.#formatDataVersion = requested;
    }

    // 1.13より前のチャンクはブロックが数値IDで、どの世代で読んでも誤った値になる
    if (dataVersion < OLDEST_FORMAT_DATA_VERSION) {
      return chunk;
    }

    const format = ChunkFormat.forDataVersion(chunk.#formatDataVersion);

    // 表に無い世代のチャンクは、解釈せずに元のNBTだけを持つ
    if (format === undefined) {
      return chunk;
    }

    chunk.#format = format;
    const hasLevel = nbt.optCompound("Level") !== undefined;

    // 選んだ世代と本体の包み方が食い違うなら、黙って空のチャンクとして読まずに弾く
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

      const section = ChunkSection.fromNbt(entry as NbtCompound, lenient);
      chunk.#sections.set(section.y, section);
    }

    return chunk;
  }

  /** DataVersionを検査し、オプションに従って警告またはエラーにする */
  #checkDataVersion(options?: ChunkReadOptions): void {
    const version = this.dataVersion;

    // 形式が同じであれば、新しいバージョンでもそのまま読める
    if (version >= MIN_SUPPORTED_DATA_VERSION) {
      return;
    }

    let action = VersionMismatchAction.Warn;

    if (options !== undefined && options.onVersionMismatch !== undefined) {
      action = options.onVersionMismatch;
    }

    const message =
      `DataVersion ${version} はこのライブラリが扱う形式より古い` +
      `（${MIN_SUPPORTED_DATA_VERSION} 以降が対象）`;

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
   * 全セクションを読んだときの世代の形式で書き戻し、他のキーはそのまま残す
   */
  toNbt(options?: ChunkWriteOptions): NbtCompound {
    const version = this.dataVersion;
    let allowForeign = false;

    if (options !== undefined && options.allowForeignDataVersion === true) {
      allowForeign = true;
    }

    // 形式の違う古いチャンクは、書き戻すと使えなくなりかねない
    if (version < MIN_SUPPORTED_DATA_VERSION && !allowForeign) {
      throw new SpringNbtError(
        ErrorCode.UnsupportedDataVersion,
        `DataVersion ${version} のチャンクは書き戻せない` +
          `（${MIN_SUPPORTED_DATA_VERSION} 以降が対象）。` +
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

    // Yの昇順で書き出す
    for (const sectionY of this.sectionYs) {
      sectionList.add(this.#sections.get(sectionY)!.toNbt());
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
    if (this.#format === undefined) {
      throw new SpringNbtError(
        ErrorCode.UnsupportedDataVersion,
        `DataVersion ${this.dataVersion}のチャンクは形式を解釈せず元のNBTだけを持つので、この操作はできない`,
      );
    }

    return this.#format;
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

    // 書き戻すときに読んだときと同じ形式になるよう、世代ごとに決めたDataVersionで変換する
    section.blockStates!.set(
      blockIndex(x, y, z),
      state.toNbtForDataVersion(format.paletteDataVersion),
    );
    this.#removeBlockData(format, x, y, z);
    this.#modified = true;
  }

  /**
   * その座標を指す付随データを取り除く
   *
   * `block_entities` / `block_ticks` / `fluid_ticks`の要素は
   * いずれも`x` `y` `z`を**絶対座標**で持つ
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
   * @throws SpringNbtError 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）
   */
  getBiome(x: number, y: number, z: number): string | undefined {
    this.#requireFormat();
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
   * 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）
   */
  setBiome(x: number, y: number, z: number, biome: string): void {
    this.#requireFormat();
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
   * @throws SpringNbtError 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）
   */
  invalidateLighting(): void {
    this.#requireFormat();
    this.#body().setByte("isLightOn", 0);
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

function checkLocalCoordinates(x: number, z: number): void {
  // チャンク内相対座標は0..15でなければならない
  if (x < 0 || x > 15 || z < 0 || z > 15) {
    throw SpringNbtError.invalidArgument(
      `チャンク内相対座標が範囲外: (${x}, ${z})。X も Z も 0..15 であること`,
    );
  }
}

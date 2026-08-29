/**
 * チャンク 1 つ分。地形の読み書きの入口。
 *
 * **読んだ NBT をそのまま保持し、変更した部分だけを書き戻す。**
 * 未知のキーを落とさないので、将来の追加要素があってもデータを壊さない。
 *
 * 仕様: `docs/spec/30-chunk-format.md`
 */

import { TARGET_DATA_VERSION } from "../index.js";
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
import { PalettedContainer } from "./palettedContainer.js";

/** セクション 1 つに入るブロック数。 */
export const BLOCKS_PER_SECTION = 4096;

/** セクション 1 つに入るバイオームのエントリ数（4×4×4 単位）。 */
export const BIOMES_PER_SECTION = 64;

/** ブロックに紐づく付随データのキー。ブロックを置き換えたら整合が崩れる。 */
const BLOCK_DATA_KEYS = ["block_entities", "block_ticks", "fluid_ticks"] as const;

/** 付随データの要素が、指定の絶対座標を指しているか。 */
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

/** DataVersion が対象と違ったときの動作。 */
export enum VersionMismatchAction {
  /** 警告コールバックを呼んで続行する。既定。 */
  Warn = "warn",
  /** `UNSUPPORTED_DATA_VERSION` の例外にする。 */
  Error = "error",
  /** 何もしない。 */
  Ignore = "ignore",
}

/** チャンク読み込みのオプション。 */
export interface ChunkReadOptions {
  /** DataVersion が対象と違うときの動作。既定は `Warn`。 */
  onVersionMismatch?: VersionMismatchAction;
  /** 警告の通知先。 */
  onWarning?: (message: string) => void;
  /** data の長さが期待値と違うとき、長さからビット幅を逆算して読むか。 */
  lenientBitStorage?: boolean;
}

/** チャンク書き込みのオプション。 */
export interface ChunkWriteOptions {
  /**
   * 対象バージョン以外の DataVersion を持つチャンクの書き戻しを許すか。
   *
   * 既定は false。古いワールドを黙って新形式で上書きし、
   * 利用者が気づかないうちに壊すことを防ぐため（`docs/adr/0003-version-policy.md`）。
   */
  allowForeignDataVersion?: boolean;
}

/**
 * チャンクを Y 方向に 16 ブロックずつ区切った 16×16×16 の立方体。
 *
 * `BlockLight` / `SkyLight` などの解釈していないキーは元の NBT に残り、
 * 書き戻しでそのまま出力される。
 */
export class ChunkSection {
  #blockStates: PalettedContainer | undefined;
  #biomes: PalettedContainer | undefined;

  private constructor(
    readonly raw: NbtCompound,
    readonly y: number,
  ) {}

  /** ブロック状態。持たないセクション（光源専用）では undefined。 */
  get blockStates(): PalettedContainer | undefined {
    return this.#blockStates;
  }

  /** バイオーム。持たないセクションでは undefined。 */
  get biomes(): PalettedContainer | undefined {
    return this.#biomes;
  }

  /** ブロック状態を持つか。 */
  get hasBlockStates(): boolean {
    return this.#blockStates !== undefined;
  }

  /** バイオームを持つか。 */
  get hasBiomes(): boolean {
    return this.#biomes !== undefined;
  }

  /** NBT からセクションを読む。 */
  static fromNbt(nbt: NbtCompound, lenientBitStorage: boolean): ChunkSection {
    const section = new ChunkSection(nbt, nbt.getByte("Y"));
    const blockStates = nbt.optCompound("block_states");

    // 光源専用のセクションは block_states を持たない
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

  /** NBT へ書き戻す。解釈していないキーはそのまま残る。 */
  toNbt(): NbtCompound {
    if (this.#blockStates !== undefined) {
      this.raw.set("block_states", this.#blockStates.toNbt());
    }

    if (this.#biomes !== undefined) {
      this.raw.set("biomes", this.#biomes.toNbt());
    }

    return this.raw;
  }

  /** 使われていないパレット要素を取り除く。 */
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
 * チャンク 1 つ分。地形の読み書きの入口。
 *
 * **読んだ NBT をそのまま保持し、変更した部分だけを書き戻す。**
 * 未知のキーを落とさないので、将来の追加要素があってもデータを壊さない。
 */
export class Chunk {
  readonly #sections = new Map<number, ChunkSection>();

  private constructor(readonly raw: NbtCompound) {}

  /** チャンク構造のバージョン。 */
  get dataVersion(): number {
    return this.raw.getInt("DataVersion");
  }

  /** 絶対チャンクX座標。 */
  get x(): number {
    return this.raw.getInt("xPos");
  }

  /** 絶対チャンクZ座標。 */
  get z(): number {
    return this.raw.getInt("zPos");
  }

  /** 最下段セクションのY位置。オーバーワールドは -4。 */
  get minSectionY(): number {
    return this.raw.getInt("yPos");
  }

  /** 生成段階（`minecraft:full` など）。 */
  get status(): string {
    return this.raw.getString("Status");
  }

  /** 生成が完了しているか。ブロック改変の対象にしてよいのはこれだけ。 */
  get isFullyGenerated(): boolean {
    return this.status === "minecraft:full";
  }

  /** 存在するセクションのY位置。昇順。 */
  get sectionYs(): number[] {
    return [...this.#sections.keys()].sort((left, right) => left - right);
  }

  /** NBT からチャンクを読む。 */
  static fromNbt(nbt: NbtCompound, options?: ChunkReadOptions): Chunk {
    const chunk = new Chunk(nbt);
    chunk.#checkDataVersion(options);

    let lenient = false;

    if (options !== undefined && options.lenientBitStorage === true) {
      lenient = true;
    }

    const sectionList = nbt.optList("sections");

    if (sectionList === undefined) {
      return chunk;
    }

    // 並び順に依存しないよう、Y から索引を作る
    for (const entry of sectionList) {
      if (entry.type !== TagType.Compound) {
        throw SpringNbtError.unexpectedTagType("sections の要素が compound でない");
      }

      const section = ChunkSection.fromNbt(entry as NbtCompound, lenient);
      chunk.#sections.set(section.y, section);
    }

    return chunk;
  }

  /** DataVersion を検査し、オプションに従って警告またはエラーにする。 */
  #checkDataVersion(options?: ChunkReadOptions): void {
    const version = this.dataVersion;

    if (version === TARGET_DATA_VERSION) {
      return;
    }

    let action = VersionMismatchAction.Warn;

    if (options !== undefined && options.onVersionMismatch !== undefined) {
      action = options.onVersionMismatch;
    }

    const message =
      `DataVersion が対象と違う: ${version}（対象は ${TARGET_DATA_VERSION}）`;

    if (action === VersionMismatchAction.Error) {
      throw new SpringNbtError(ErrorCode.UnsupportedDataVersion, message);
    }

    // 警告として扱う設定で、通知先があるときだけ知らせる
    if (action === VersionMismatchAction.Warn && options !== undefined
        && options.onWarning !== undefined) {
      options.onWarning(message);
    }
  }

  /** NBT へ書き戻す。変更したセクションだけを反映し、他のキーはそのまま残す。 */
  toNbt(options?: ChunkWriteOptions): NbtCompound {
    const version = this.dataVersion;
    let allowForeign = false;

    if (options !== undefined && options.allowForeignDataVersion === true) {
      allowForeign = true;
    }

    if (version !== TARGET_DATA_VERSION && !allowForeign) {
      throw new SpringNbtError(
        ErrorCode.UnsupportedDataVersion,
        `DataVersion ${version} のチャンクは書き戻せない（対象は ${TARGET_DATA_VERSION}）。` +
          "許可するなら allowForeignDataVersion を立てること",
      );
    }

    // 常に対象バージョンを書く
    this.raw.set("DataVersion", new NbtInt(TARGET_DATA_VERSION));

    if (this.#sections.size === 0) {
      return this.raw;
    }

    const sectionList = new NbtList(TagType.Compound);

    // Y の昇順で書き出す
    for (const sectionY of this.sectionYs) {
      sectionList.add(this.#sections.get(sectionY)!.toNbt());
    }

    this.raw.set("sections", sectionList);
    return this.raw;
  }

  /** Y位置からセクションを得る。無ければ undefined。 */
  section(sectionY: number): ChunkSection | undefined {
    return this.#sections.get(sectionY);
  }

  /**
   * ブロックを取得する。
   *
   * @param x チャンク内相対X座標 (0..15)
   * @param y 絶対Y座標
   * @param z チャンク内相対Z座標 (0..15)
   */
  getBlock(x: number, y: number, z: number): BlockState | undefined {
    checkLocalCoordinates(x, z);
    const section = this.section(y >> 4);

    if (section === undefined || !section.hasBlockStates) {
      return undefined;
    }

    const entry = section.blockStates!.get(blockIndex(x, y, z));

    if (entry.type !== TagType.Compound) {
      throw SpringNbtError.unexpectedTagType("ブロックのパレット要素が compound でない");
    }

    return BlockState.fromNbt(entry as NbtCompound);
  }

  /** ブロックを設定する。 */
  setBlock(x: number, y: number, z: number, state: BlockState): void {
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

    section.blockStates!.set(blockIndex(x, y, z), state.toNbt());
    this.#removeBlockData(x, y, z);
  }

  /**
   * その座標を指す付随データを取り除く。
   *
   * `block_entities` / `block_ticks` / `fluid_ticks` の要素は
   * いずれも `x` `y` `z` を**絶対座標**で持つ。
   */
  #removeBlockData(x: number, y: number, z: number): void {
    const absoluteX = this.x * 16 + x;
    const absoluteZ = this.z * 16 + z;

    // 3 つのリストは形が同じなので、まとめて同じ処理をかける
    for (const key of BLOCK_DATA_KEYS) {
      const list = this.raw.optList(key);

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

  /** バイオームを取得する。4×4×4 の単位なので、座標は自動的に丸められる。 */
  getBiome(x: number, y: number, z: number): string | undefined {
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

  /** バイオームを設定する。4×4×4 の単位。 */
  setBiome(x: number, y: number, z: number, biome: string): void {
    checkLocalCoordinates(x, z);

    const sectionY = y >> 4;
    const section = this.section(sectionY);

    if (section === undefined || !section.hasBiomes) {
      throw SpringNbtError.invalidArgument(
        `Y=${y} を含むセクション（Y=${sectionY}）が無いか、バイオームを持たない`,
      );
    }

    section.biomes!.set(biomeIndex(x, y, z), new NbtString(biome));
  }

  /**
   * `Heightmaps` を削除し、Minecraft に再計算させる。
   *
   * 本ライブラリは高さマップを再計算しない。ブロックを改変したら呼ぶこと
   * （`docs/adr/0004-defer-heightmap-recalc.md`）。
   */
  clearHeightmaps(): void {
    this.raw.remove("Heightmaps");
  }

  /** `isLightOn` を 0 にし、光源の再計算を促す。 */
  invalidateLighting(): void {
    this.raw.set("isLightOn", new NbtByte(0));
  }

  /** 使われていないパレット要素を全セクションから取り除く。 */
  compact(): void {
    // 全セクションのパレットをまとめて掃除する
    for (const section of this.#sections.values()) {
      section.compact();
    }
  }
}

/**
 * セクション内のブロック添字。
 *
 * `& 15` により負のY座標でも正しく求まる。
 */
export function blockIndex(x: number, y: number, z: number): number {
  return (y & 15) * 256 + (z & 15) * 16 + (x & 15);
}

/** セクション内のバイオーム添字。1 エントリが 4×4×4 ブロック。 */
export function biomeIndex(x: number, y: number, z: number): number {
  return Math.floor((y & 15) / 4) * 16 + Math.floor((z & 15) / 4) * 4 + Math.floor((x & 15) / 4);
}

function checkLocalCoordinates(x: number, z: number): void {
  // チャンク内相対座標は 0..15 でなければならない
  if (x < 0 || x > 15 || z < 0 || z > 15) {
    throw SpringNbtError.invalidArgument(
      `チャンク内相対座標が範囲外: (${x}, ${z})。X も Z も 0..15 であること`,
    );
  }
}

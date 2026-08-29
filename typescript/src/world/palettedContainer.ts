/**
 * パレットとビットストレージの組
 * セクション内のブロック状態やバイオームを格納する
 *
 * パレットの要素は**生の `NbtTag` のまま**持つ
 * こうすると、触っていないブロックについては Minecraft が書き出したときの
 * プロパティの並び順まで含めてそのまま書き戻せる
 *
 * 仕様: `docs/spec/31-paletted-container.md`
 */

import { SpringNbtError } from "../errors.js";
import { NbtCompound, NbtList, NbtLongArray, NbtTag } from "../nbt/index.js";
import { BitStorage } from "./bitStorage.js";

/**
 * パレットとビットストレージの組
 * セクション内のブロック状態やバイオームを格納する
 *
 * パレットの要素は**生の `NbtTag` のまま**持つ
 * こうすると、触っていないブロックの
 * プロパティの並び順まで含めてそのまま書き戻せる
 */
export class PalettedContainer {
  readonly #palette: NbtTag[] = [];
  readonly #entryCount: number;
  readonly #minBits: number;

  #storage: BitStorage | undefined;

  private constructor(entryCount: number, minBits: number) {
    this.#entryCount = entryCount;
    this.#minBits = minBits;
  }

  /** エントリ数
  /** ブロックなら 4096、バイオームなら 64
  /** */
  get entryCount(): number {
    return this.#entryCount;
  }

  /** ビット幅の下限
  /** ブロックなら 4、バイオームなら 1
  /** */
  get minBits(): number {
    return this.#minBits;
  }

  /** パレット
  /** 読み取り専用
  /** */
  get palette(): readonly NbtTag[] {
    return this.#palette;
  }

  /** 現在のビット幅
  /** パレットが 1 要素なら 0（記憶域を持たない）
  /** */
  get bitsPerEntry(): number {
    if (this.#storage === undefined) {
      return 0;
    }

    return this.#storage.bitsPerEntry;
  }

  /** 単一の値で埋めたコンテナを作る
  /** */
  static filled(value: NbtTag, entryCount: number, minBits: number): PalettedContainer {
    const result = new PalettedContainer(entryCount, minBits);
    result.#palette.push(value);
    return result;
  }

  /** NBT から読み込む
  /** */
  static fromNbt(
    nbt: NbtCompound,
    entryCount: number,
    minBits: number,
    lenientBitStorage = false,
  ): PalettedContainer {
    const result = new PalettedContainer(entryCount, minBits);
    const paletteTag = nbt.optList("palette");

    if (paletteTag === undefined || paletteTag.size === 0) {
      throw SpringNbtError.malformed("palette が無いか空");
    }

    // パレットの要素は生の NbtTag のまま持つ
    // 並び順まで元どおりに書き戻すため
    for (const entry of paletteTag) {
      result.#palette.push(entry);
    }

    const data = nbt.optLongArray("data");

    if (data === undefined) {
      // パレットが 1 要素なら data は無くてよい
      if (result.#palette.length !== 1) {
        throw SpringNbtError.malformed(
          `palette が ${result.#palette.length} 要素なのに data が無い`,
        );
      }

      return result;
    }

    const bits = Math.max(minBits, ceilLog2(result.#palette.length));
    result.#storage = BitStorage.fromLongs(data, bits, entryCount, lenientBitStorage);

    // 取り出した添字がパレットの範囲に収まっているか確かめる
    // 黙って 0 番目で代替すると、壊れたデータをそうと分からない形で書き戻してしまう
    for (let index = 0; index < entryCount; index++) {
      const value = result.#storage.get(index);

      if (value >= result.#palette.length) {
        throw SpringNbtError.malformed(
          `添字 ${index} の値 ${value} がパレット（${result.#palette.length} 要素）の範囲外`,
        );
      }
    }

    return result;
  }

  /** NBT へ変換する
  /** */
  toNbt(): NbtCompound {
    const result = new NbtCompound();
    const paletteTag = new NbtList();

    // パレットの要素は読んだときのまま書き出す
    for (const entry of this.#palette) {
      paletteTag.add(entry);
    }

    // パレットが 1 要素なら data は書かない
    // Minecraft と同じ振る舞い
    if (this.#storage !== undefined && this.#palette.length > 1) {
      result.set("data", new NbtLongArray(this.#storage.toLongs()));
    }

    result.set("palette", paletteTag);
    return result;
  }

  /** 添字の値を取り出す
  /** */
  get(index: number): NbtTag {
    this.#checkIndex(index);

    // 記憶域が無いということは、全エントリがパレットの 0 番目
    if (this.#storage === undefined) {
      return this.#palette[0];
    }

    return this.#palette[this.#storage.get(index)];
  }

  /** 添字の値を書き換える
  /** パレットに無ければ追加する
  /** */
  set(index: number, value: NbtTag): void {
    this.#checkIndex(index);
    const paletteIndex = this.#indexOfOrAdd(value);

    // 記憶域が無く、書き込む値も 0 番目なら何もしなくてよい
    if (this.#storage === undefined && paletteIndex === 0) {
      return;
    }

    this.#ensureStorage();
    this.#storage!.set(index, paletteIndex);
  }

  /** 全エントリを 1 つの値で埋める
  /** パレットもその 1 要素だけにする
  /** */
  fill(value: NbtTag): void {
    this.#palette.length = 0;
    this.#palette.push(value);
    this.#storage = undefined;
  }

  /**
   * どのエントリからも参照されていないパレット要素を取り除き、添字を振り直す
   *
   * 大量の `set` を行う用途で遅くならないよう、明示的に呼んだときだけ実行する
   */
  compact(): void {
    if (this.#storage === undefined) {
      return;
    }

    const usedEntries = new Array<boolean>(this.#palette.length).fill(false);

    // どのパレット要素が実際に使われているかを数える
    for (let index = 0; index < this.#entryCount; index++) {
      usedEntries[this.#storage.get(index)] = true;
    }

    const compacted: NbtTag[] = [];
    const remap = new Int32Array(this.#palette.length);

    // 使われている要素だけを詰め直し、新しい添字を割り当てる
    for (let old = 0; old < this.#palette.length; old++) {
      if (!usedEntries[old]) {
        remap[old] = -1;
        continue;
      }

      remap[old] = compacted.length;
      compacted.push(this.#palette[old]);
    }

    if (compacted.length === this.#palette.length) {
      return;
    }

    const newBits = Math.max(this.#minBits, ceilLog2(compacted.length));
    const rebuilt = BitStorage.create(newBits, this.#entryCount);

    // 新しい添字へ置き換えながら詰め直す
    for (let index = 0; index < this.#entryCount; index++) {
      rebuilt.set(index, remap[this.#storage.get(index)]);
    }

    this.#palette.length = 0;
    this.#palette.push(...compacted);

    if (compacted.length === 1) {
      // 1 要素になったら記憶域を捨てる
      this.#storage = undefined;
    } else {
      this.#storage = rebuilt;
    }
  }

  /** パレット内の位置を返す
  /** 無ければ末尾へ追加する
  /** */
  #indexOfOrAdd(value: NbtTag): number {
    // パレットは高々 4096 要素なので線形探索で足りる
    for (let index = 0; index < this.#palette.length; index++) {
      if (nbtEquals(this.#palette[index], value)) {
        return index;
      }
    }

    this.#palette.push(value);
    return this.#palette.length - 1;
  }

  /** 現在のパレット長に合うビット幅の記憶域を用意する
  /** */
  #ensureStorage(): void {
    const required = Math.max(this.#minBits, ceilLog2(this.#palette.length));

    if (this.#storage === undefined) {
      // これまで単一値だったので、全エントリが 0 番目のまま始まる
      this.#storage = BitStorage.create(required, this.#entryCount);
      return;
    }

    if (this.#storage.bitsPerEntry >= required) {
      return;
    }

    // パレットが増えてビット幅が足りなくなったら、全体を詰め直す
    this.#storage = this.#storage.resize(required);
  }

  #checkIndex(index: number): void {
    if (index < 0 || index >= this.#entryCount) {
      throw SpringNbtError.invalidArgument(
        `添字が範囲外: ${index} (0..${this.#entryCount - 1})`,
      );
    }
  }
}

/** `count` 個の値を表すのに必要な最小ビット数
/** 1 なら 0
/** */
export function ceilLog2(count: number): number {
  let bits = 0;

  // 1 を超える分だけシフトして数える
  while (1 << bits < count) {
    bits += 1;
  }

  return bits;
}

/**
 * タグどうしが等しいか
 *
 * NBT 層のクラスは `equals` を持たないので、パレットの重複判定用にここで比べる
 * パレットに入るのは Compound（ブロック）か String（バイオーム）だけ
 */
function nbtEquals(left: NbtTag, right: NbtTag): boolean {
  if (left.type !== right.type) {
    return false;
  }

  if (left instanceof NbtCompound && right instanceof NbtCompound) {
    if (left.size !== right.size) {
      return false;
    }

    const leftEntries = [...left.entries()];
    const rightEntries = [...right.entries()];

    // 挿入順まで含めて一致することを確かめる
    for (let index = 0; index < leftEntries.length; index++) {
      if (leftEntries[index][0] !== rightEntries[index][0]) {
        return false;
      }

      if (!nbtEquals(leftEntries[index][1], rightEntries[index][1])) {
        return false;
      }
    }

    return true;
  }

  // それ以外は値の比較で足りる（パレットに入るのは String まで）
  return String((left as { value?: unknown }).value)
    === String((right as { value?: unknown }).value);
}

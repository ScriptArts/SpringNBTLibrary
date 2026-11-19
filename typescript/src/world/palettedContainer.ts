/**
 * パレットとビットストレージの組
 * セクション内のブロック状態やバイオームを格納する
 *
 * パレットの要素は**生の`NbtTag`のまま**持つ
 * こうすると、触っていないブロックについてはMinecraftが書き出したときの
 * プロパティの並び順まで含めてそのまま書き戻せる
 *
 * 26.3からは、ブロックのパレットに文字列とCompoundが混ざる
 * Minecraftはこうした異種リストをCompoundのリストとして保存し、Compoundでない要素を`{"": <値>}`で包む
 * 読むときにこの包みを外して持ち、書くときに要素の型を見て包み直す
 */

import { SpringNbtError } from "../errors.js";
import { NbtCompound, NbtList, NbtLongArray, NbtTag, TagType } from "../nbt/index.js";
import { BitStorage } from "./bitStorage.js";

/**
 * パレットとビットストレージの組
 * セクション内のブロック状態やバイオームを格納する
 *
 * パレットの要素は**生の`NbtTag`のまま**持つ
 * こうすると、触っていないブロックについてはMinecraftが書き出したときの
 * プロパティの並び順まで含めてそのまま書き戻せる
 */
export class PalettedContainer {
  readonly #palette: NbtTag[] = [];
  readonly #entryCount: number;
  readonly #minBits: number;
  readonly #spanning: boolean;
  readonly #alwaysHasData: boolean;

  #storage: BitStorage | undefined;

  private constructor(
    entryCount: number,
    minBits: number,
    spanning: boolean,
    alwaysHasData: boolean,
  ) {
    this.#entryCount = entryCount;
    this.#minBits = minBits;
    this.#spanning = spanning;
    this.#alwaysHasData = alwaysHasData;
  }

  /**
   * エントリ数
   * ブロックなら4096、バイオームなら64
   */
  get entryCount(): number {
    return this.#entryCount;
  }

  /**
   * ビット幅の下限
   * ブロックなら4、バイオームなら1
   */
  get minBits(): number {
    return this.#minBits;
  }

  /**
   * パレット
   * 読み取り専用
   */
  get palette(): readonly NbtTag[] {
    return this.#palette;
  }

  /**
   * 現在のビット幅
   * パレットが1要素なら0（記憶域を持たない）
   */
  get bitsPerEntry(): number {
    if (this.#storage === undefined) {
      return 0;
    }

    return this.#storage.bitsPerEntry;
  }

  /** 単一の値で埋めたコンテナを作る */
  static filled(value: NbtTag, entryCount: number, minBits: number): PalettedContainer {
    const result = new PalettedContainer(entryCount, minBits, false, false);
    result.#palette.push(value);
    return result;
  }

  /** NBTから読み込む */
  static fromNbt(
    nbt: NbtCompound,
    entryCount: number,
    minBits: number,
    lenientBitStorage = false,
  ): PalettedContainer {
    const paletteTag = nbt.optList("palette");

    if (paletteTag === undefined || paletteTag.size === 0) {
      throw SpringNbtError.malformed("palette が無いか空");
    }

    // パレットの要素は生のNbtTagのまま持つ
    // 並び順まで元どおりに書き戻すため
    // 異種リストの包みだけは外しておき、書くときに包み直す
    const entries: NbtTag[] = [];

    // 包みを外しながら、パレットの要素を順に集める
    for (const entry of paletteTag) {
      entries.push(unwrapListElement(entry));
    }

    return PalettedContainer.fromParts(
      entries,
      nbt.optLongArray("data"),
      entryCount,
      minBits,
      false,
      false,
      lenientBitStorage,
    );
  }

  /**
   * パレットとdataから作る
   * 1.13から1.15までの詰め方や、dataが必ず書かれる形式を読むための入口
   *
   * @param palette パレットの要素（異種リストの包みは外してあること）
   * @param data packedな配列（無ければundefined）
   * @param spanning 64bitの境目をまたいで詰めるか
   * @param alwaysHasData パレットが1要素でもdataを書く形式か
   * @param lenientBitStorage dataの長さが合わないとき、長さからビット幅を逆算して読むか
   * @internal
   */
  static fromParts(
    palette: readonly NbtTag[],
    data: BigInt64Array | undefined,
    entryCount: number,
    minBits: number,
    spanning: boolean,
    alwaysHasData: boolean,
    lenientBitStorage: boolean,
  ): PalettedContainer {
    if (palette.length === 0) {
      throw SpringNbtError.malformed("palette が無いか空");
    }

    const result = new PalettedContainer(entryCount, minBits, spanning, alwaysHasData);
    result.#palette.push(...palette);

    if (data === undefined) {
      // パレットが1要素ならdataは無くてよい
      if (result.#palette.length !== 1) {
        throw SpringNbtError.malformed(
          `palette が ${result.#palette.length} 要素なのに data が無い`,
        );
      }

      return result;
    }

    const bits = Math.max(minBits, ceilLog2(result.#palette.length));
    result.#storage = BitStorage.fromLongsWith(data, bits, entryCount, lenientBitStorage, spanning);

    // 取り出した添字がパレットの範囲に収まっているか確かめる
    // エラーを出さずに0番目で代替すると、おかしくなったデータをそうと分からない形で書き戻してしまう
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

  /**
   * パレットとdataに分けて返す
   * パレットの要素は異種リストの包みを掛けないまま返す
   * dataは、パレットが1要素なら（`alwaysHasData`でない限り）undefined
   *
   * @internal
   */
  toParts(): { palette: NbtTag[]; data: BigInt64Array | undefined } {
    const entries = [...this.#palette];

    // パレットが2要素以上なら、記憶域をそのまま返す
    if (this.#storage !== undefined && this.#palette.length > 1) {
      return { palette: entries, data: this.#storage.toLongs() };
    }

    // 1要素でもdataを書く形式なら、記憶域が無くてもゼロで埋めた配列を作る
    if (this.#alwaysHasData) {
      const bits = Math.max(this.#minBits, ceilLog2(this.#palette.length));
      const zeroed = BitStorage.createWith(bits, this.#entryCount, this.#spanning);
      return { palette: entries, data: zeroed.toLongs() };
    }

    return { palette: entries, data: undefined };
  }

  /** NBTへ変換する */
  toNbt(): NbtCompound {
    const result = new NbtCompound();

    // パレットの要素は読んだときのまま書き出す
    // 型が混ざっていれば、Minecraftと同じく包んでCompoundのリストにする
    const paletteTag = paletteToList(this.#palette);

    // パレットが1要素ならdataは書かない
    // Minecraftと同じ振る舞い
    if (this.#storage !== undefined && this.#palette.length > 1) {
      result.set("data", new NbtLongArray(this.#storage.toLongs()));
    }

    result.set("palette", paletteTag);
    return result;
  }

  /** 添字の値を取り出す */
  get(index: number): NbtTag {
    this.#checkIndex(index);

    // 記憶域が無いということは、全エントリがパレットの0番目
    if (this.#storage === undefined) {
      return this.#palette[0];
    }

    return this.#palette[this.#storage.get(index)];
  }

  /**
   * 添字の値を書き換える
   * パレットに無ければ追加する
   */
  set(index: number, value: NbtTag): void {
    this.#checkIndex(index);
    const paletteIndex = this.#indexOfOrAdd(value);

    // 記憶域が無く、書き込む値も0番目なら何もしなくてよい
    if (this.#storage === undefined && paletteIndex === 0) {
      return;
    }

    this.#ensureStorage();
    this.#storage!.set(index, paletteIndex);
  }

  /**
   * 全エントリを1つの値で埋める
   * パレットもその1要素だけにする
   */
  fill(value: NbtTag): void {
    this.#palette.length = 0;
    this.#palette.push(value);
    this.#storage = undefined;
  }

  /**
   * どのエントリからも参照されていないパレット要素を取り除き、添字を振り直す
   *
   * 大量の`set`を行う用途で遅くならないよう、明示的に呼んだときだけ実行する
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
    const rebuilt = BitStorage.createWith(newBits, this.#entryCount, this.#spanning);

    // 新しい添字へ置き換えながら詰め直す
    for (let index = 0; index < this.#entryCount; index++) {
      rebuilt.set(index, remap[this.#storage.get(index)]);
    }

    this.#palette.length = 0;
    this.#palette.push(...compacted);

    if (compacted.length === 1) {
      // 1要素になったら記憶域を捨てる
      this.#storage = undefined;
    } else {
      this.#storage = rebuilt;
    }
  }

  /**
   * パレット内の位置を返す
   * 無ければ末尾へ追加する
   */
  #indexOfOrAdd(value: NbtTag): number {
    // パレットは高々4096要素なので線形探索で足りる
    for (let index = 0; index < this.#palette.length; index++) {
      if (nbtEquals(this.#palette[index], value)) {
        return index;
      }
    }

    this.#palette.push(value);
    return this.#palette.length - 1;
  }

  /** 現在のパレット長に合うビット幅の記憶域を用意する */
  #ensureStorage(): void {
    const required = Math.max(this.#minBits, ceilLog2(this.#palette.length));

    if (this.#storage === undefined) {
      // これまで単一値だったので、全エントリが0番目のまま始まる
      this.#storage = BitStorage.createWith(required, this.#entryCount, this.#spanning);
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

/**
 * `count`個の値を表すのに必要な最小ビット数
 * 1なら0
 */
export function ceilLog2(count: number): number {
  let bits = 0;

  // 1を超える分だけシフトして数える
  while (1 << bits < count) {
    bits += 1;
  }

  return bits;
}

/**
 * 異種リストの要素を包むCompoundか
 * 空のキー1つだけを持つものがそれに当たる（MinecraftのListTagと同じ判定）
 */
function isListWrapper(tag: NbtTag): boolean {
  if (!(tag instanceof NbtCompound)) {
    return false;
  }

  return tag.size === 1 && tag.containsKey("");
}

/**
 * 異種リストの包みを外す
 * 包みでなければそのまま返す
 */
function unwrapListElement(tag: NbtTag): NbtTag {
  if (isListWrapper(tag)) {
    return (tag as NbtCompound).get("");
  }

  return tag;
}

/**
 * パレットの要素をリストへ詰める
 *
 * 要素の型がすべて同じならその型のリストにする
 * 1つでも違えば、Minecraftと同じくCompoundのリストにして、Compoundでない要素と包みに見える要素を包む
 */
function paletteToList(entries: readonly NbtTag[]): NbtList {
  let elementType = entries[0].type;

  // 先頭と型の違う要素があるか調べる
  for (const entry of entries) {
    // 1つでも違えば、異種リストとしてCompoundのリストにする
    if (entry.type !== elementType) {
      elementType = TagType.Compound;
      break;
    }
  }

  const result = new NbtList(elementType);

  // 要素を順にリストへ入れる
  for (const entry of entries) {
    // Compoundのリストでは、Compoundでない要素と包みに見える要素を包む
    if (elementType === TagType.Compound && (!(entry instanceof NbtCompound) || isListWrapper(entry))) {
      const wrapper = new NbtCompound();
      wrapper.set("", entry);
      result.add(wrapper);
    } else {
      result.add(entry);
    }
  }

  return result;
}

/**
 * タグどうしが等しいか
 *
 * パレットの重複判定に使う
 * パレットに入るのはCompoundかStringだけ
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

  // それ以外は値の比較で足りる（パレットに入るのはStringまで）
  return String((left as { value?: unknown }).value)
    === String((right as { value?: unknown }).value);
}

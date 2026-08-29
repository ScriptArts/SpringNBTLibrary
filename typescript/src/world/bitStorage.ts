/**
 * 添字を 64bit 整数の配列へ詰めた表現。1.16 以降の**跨ぎなし**パッキング。
 *
 * 1 つの `bigint` に入りきらない分は、その値の残りビットを未使用のまま捨て、
 * 次の値の最下位ビットから始める。
 *
 * 仕様: `docs/spec/31-paletted-container.md` 2章
 */

import { SpringNbtError } from "../errors.js";

/**
 * 添字を 64bit 整数の配列へ詰めた表現。1.16 以降の**跨ぎなし**パッキング。
 *
 * 1 つの `bigint` に入りきらない分は、その値の残りビットを未使用のまま捨て、
 * 次の値の最下位ビットから始める。
 */
export class BitStorage {
  readonly #data: BigInt64Array;
  readonly #bitsPerEntry: number;
  readonly #entryCount: number;

  private constructor(data: BigInt64Array, bitsPerEntry: number, entryCount: number) {
    this.#data = data;
    this.#bitsPerEntry = bitsPerEntry;
    this.#entryCount = entryCount;
  }

  /** 1 エントリあたりのビット数。 */
  get bitsPerEntry(): number {
    return this.#bitsPerEntry;
  }

  /** エントリ数。ブロックなら 4096、バイオームなら 64。 */
  get entryCount(): number {
    return this.#entryCount;
  }

  /** 1 つの 64bit 値に入るエントリ数。 */
  get valuesPerLong(): number {
    return Math.floor(64 / this.#bitsPerEntry);
  }

  /** すべてゼロで初期化した記憶域を作る。 */
  static create(bitsPerEntry: number, entryCount: number): BitStorage {
    if (bitsPerEntry < 1 || bitsPerEntry > 32) {
      throw SpringNbtError.invalidArgument(`ビット幅が範囲外: ${bitsPerEntry}`);
    }

    return new BitStorage(
      new BigInt64Array(BitStorage.longCount(bitsPerEntry, entryCount)),
      bitsPerEntry,
      entryCount,
    );
  }

  /**
   * 既存の 64bit 配列から作る。
   *
   * @param lenient true なら配列長からビット幅を逆算して読む（第三者ツール由来の救済）
   */
  static fromLongs(
    data: BigInt64Array,
    bitsPerEntry: number,
    entryCount: number,
    lenient = false,
  ): BitStorage {
    const expected = BitStorage.longCount(bitsPerEntry, entryCount);

    if (data.length === expected) {
      return new BitStorage(data, bitsPerEntry, entryCount);
    }

    if (!lenient) {
      throw SpringNbtError.malformed(
        `bits=${bitsPerEntry} なら data は ${expected} long のはずだが ${data.length} long`,
      );
    }

    // 配列長からビット幅を逆算する。合致する幅が無ければ諦める
    for (let candidate = 1; candidate <= 32; candidate++) {
      if (BitStorage.longCount(candidate, entryCount) === data.length) {
        return new BitStorage(data, candidate, entryCount);
      }
    }

    throw SpringNbtError.malformed(
      `data の長さ ${data.length} long に合うビット幅が無い（エントリ数 ${entryCount}）`,
    );
  }

  /** 必要な 64bit 値の個数を求める。 */
  static longCount(bitsPerEntry: number, entryCount: number): number {
    const valuesPerLong = Math.floor(64 / bitsPerEntry);
    return Math.ceil(entryCount / valuesPerLong);
  }

  /** 添字の値を取り出す。 */
  get(index: number): number {
    this.#checkIndex(index);

    const perLong = this.valuesPerLong;
    const longIndex = Math.floor(index / perLong);
    const bitOffset = BigInt((index % perLong) * this.#bitsPerEntry);
    const mask = (1n << BigInt(this.#bitsPerEntry)) - 1n;

    // 符号付きのままシフトすると上位ビットが伸びるので、符号なしへ直してから動かす
    const unsigned = BigInt.asUintN(64, this.#data[longIndex]);
    return Number((unsigned >> bitOffset) & mask);
  }

  /** 添字の値を書き換える。 */
  set(index: number, value: number): void {
    this.#checkIndex(index);

    const limit = 1 << this.#bitsPerEntry;

    if (value < 0 || value >= limit) {
      throw SpringNbtError.invalidArgument(
        `値がビット幅に収まらない: ${value} (0..${limit - 1})`,
      );
    }

    const perLong = this.valuesPerLong;
    const longIndex = Math.floor(index / perLong);
    const bitOffset = BigInt((index % perLong) * this.#bitsPerEntry);
    const mask = ((1n << BigInt(this.#bitsPerEntry)) - 1n) << bitOffset;

    const current = BigInt.asUintN(64, this.#data[longIndex]);
    const updated = (current & ~mask) | ((BigInt(value) << bitOffset) & mask);
    this.#data[longIndex] = BigInt.asIntN(64, updated);
  }

  /** packed な配列を返す。内部の配列をそのまま返す（コピーしない）。 */
  toLongs(): BigInt64Array {
    return this.#data;
  }

  /** 別のビット幅へ詰め直した新しい記憶域を返す。 */
  resize(newBitsPerEntry: number): BitStorage {
    const result = BitStorage.create(newBitsPerEntry, this.#entryCount);

    // 全エントリを読み直して新しい幅で詰める
    for (let index = 0; index < this.#entryCount; index++) {
      result.set(index, this.get(index));
    }

    return result;
  }

  #checkIndex(index: number): void {
    if (index < 0 || index >= this.#entryCount) {
      throw SpringNbtError.invalidArgument(
        `添字が範囲外: ${index} (0..${this.#entryCount - 1})`,
      );
    }
  }
}

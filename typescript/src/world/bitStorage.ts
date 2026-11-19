/**
 * 添字を64bit整数の配列へ詰めた表現
 * 1.16以降の**跨ぎなし**パッキング
 *
 * 1つの`bigint`に入りきらない分は、その値の残りビットを未使用のまま捨て、
 * 次の値の最下位ビットから始める
 */

import { SpringNbtError } from "../errors.js";

/**
 * 添字を64bit整数の配列へ詰めた表現
 * 1.16以降の**跨ぎなし**パッキング
 *
 * 1つの`bigint`に入りきらない分は、その値の残りビットを未使用のまま捨て、
 * 次の値の最下位ビットから始める
 */
export class BitStorage {
  readonly #data: BigInt64Array;
  readonly #bitsPerEntry: number;
  readonly #entryCount: number;
  readonly #spanning: boolean;

  private constructor(
    data: BigInt64Array,
    bitsPerEntry: number,
    entryCount: number,
    spanning: boolean,
  ) {
    this.#data = data;
    this.#bitsPerEntry = bitsPerEntry;
    this.#entryCount = entryCount;
    this.#spanning = spanning;
  }

  /**
   * 64bitの境目をまたいで詰めるか
   * 1.13から1.15までの形式ならtrue
   *
   * @internal
   */
  get spanning(): boolean {
    return this.#spanning;
  }

  /** 1エントリあたりのビット数 */
  get bitsPerEntry(): number {
    return this.#bitsPerEntry;
  }

  /**
   * エントリ数
   * ブロックなら4096、バイオームなら64
   */
  get entryCount(): number {
    return this.#entryCount;
  }

  /** 1つの64bit値に入るエントリ数 */
  get valuesPerLong(): number {
    return Math.floor(64 / this.#bitsPerEntry);
  }

  /** すべてゼロで初期化した記憶域を作る */
  static create(bitsPerEntry: number, entryCount: number): BitStorage {
    return BitStorage.createWith(bitsPerEntry, entryCount, false);
  }

  /**
   * 詰め方を指定して、すべてゼロで初期化した記憶域を作る
   *
   * @internal
   */
  static createWith(bitsPerEntry: number, entryCount: number, spanning: boolean): BitStorage {
    if (bitsPerEntry < 1 || bitsPerEntry > 32) {
      throw SpringNbtError.invalidArgument(`ビット幅が範囲外: ${bitsPerEntry}`);
    }

    return new BitStorage(
      new BigInt64Array(BitStorage.longCountWith(bitsPerEntry, entryCount, spanning)),
      bitsPerEntry,
      entryCount,
      spanning,
    );
  }

  /**
   * 既存の64bit配列から作る
   *
   * @param lenient trueなら、配列長が期待値と違う場合に配列長からビット幅を逆算して読む
   * 第三者ツールが書いたデータの救済用
   */
  static fromLongs(
    data: BigInt64Array,
    bitsPerEntry: number,
    entryCount: number,
    lenient = false,
  ): BitStorage {
    return BitStorage.fromLongsWith(data, bitsPerEntry, entryCount, lenient, false);
  }

  /**
   * 詰め方を指定して、既存の64bit配列から作る
   *
   * @internal
   */
  static fromLongsWith(
    data: BigInt64Array,
    bitsPerEntry: number,
    entryCount: number,
    lenient: boolean,
    spanning: boolean,
  ): BitStorage {
    const expected = BitStorage.longCountWith(bitsPerEntry, entryCount, spanning);

    if (data.length === expected) {
      return new BitStorage(data, bitsPerEntry, entryCount, spanning);
    }

    if (!lenient) {
      throw SpringNbtError.malformed(
        `bits=${bitsPerEntry} なら data は ${expected} long のはずだが ${data.length} long`,
      );
    }

    // 配列長からビット幅を逆算する
    // 合致する幅が無ければ諦める
    for (let candidate = 1; candidate <= 32; candidate++) {
      if (BitStorage.longCountWith(candidate, entryCount, spanning) === data.length) {
        return new BitStorage(data, candidate, entryCount, spanning);
      }
    }

    throw SpringNbtError.malformed(
      `data の長さ ${data.length} long に合うビット幅が無い（エントリ数 ${entryCount}）`,
    );
  }

  /** 必要な64bit値の個数を求める */
  static longCount(bitsPerEntry: number, entryCount: number): number {
    return BitStorage.longCountWith(bitsPerEntry, entryCount, false);
  }

  /**
   * 詰め方を指定して、必要な64bit値の個数を求める
   *
   * @internal
   */
  static longCountWith(bitsPerEntry: number, entryCount: number, spanning: boolean): number {
    // またぐ詰め方なら、全ビットを隙間なく並べた長さになる
    if (spanning) {
      return Math.ceil((entryCount * bitsPerEntry) / 64);
    }

    const valuesPerLong = Math.floor(64 / bitsPerEntry);
    return Math.ceil(entryCount / valuesPerLong);
  }

  /** 添字の値を取り出す */
  get(index: number): number {
    this.#checkIndex(index);

    const mask = (1n << BigInt(this.#bitsPerEntry)) - 1n;

    // またぐ詰め方なら、隣の64bit値へ続く分を上位ビットとして足す
    if (this.#spanning) {
      const bitIndex = index * this.#bitsPerEntry;
      const spanLongIndex = Math.floor(bitIndex / 64);
      const spanOffset = bitIndex % 64;
      let spanValue = BigInt.asUintN(64, this.#data[spanLongIndex]) >> BigInt(spanOffset);

      // 次の64bit値へ続く場合は、続き分を左へずらして重ねる
      if (spanOffset + this.#bitsPerEntry > 64) {
        const next = BigInt.asUintN(64, this.#data[spanLongIndex + 1]);
        spanValue |= next << BigInt(64 - spanOffset);
      }

      return Number(spanValue & mask);
    }

    const perLong = this.valuesPerLong;
    const longIndex = Math.floor(index / perLong);
    const bitOffset = BigInt((index % perLong) * this.#bitsPerEntry);

    // 符号付きのままシフトすると上位ビットが伸びるので、符号なしへ直してから動かす
    const unsigned = BigInt.asUintN(64, this.#data[longIndex]);
    return Number((unsigned >> bitOffset) & mask);
  }

  /** 添字の値を書き換える */
  set(index: number, value: number): void {
    this.#checkIndex(index);

    const limit = 1 << this.#bitsPerEntry;

    if (value < 0 || value >= limit) {
      throw SpringNbtError.invalidArgument(
        `値がビット幅に収まらない: ${value} (0..${limit - 1})`,
      );
    }

    // またぐ詰め方なら、隣の64bit値へ続く分も書き込む
    if (this.#spanning) {
      const bitIndex = index * this.#bitsPerEntry;
      const spanLongIndex = Math.floor(bitIndex / 64);
      const spanOffset = bitIndex % 64;
      const spanMask = (1n << BigInt(this.#bitsPerEntry)) - 1n;
      const spanValue = BigInt(value);
      const low = BigInt.asUintN(64, this.#data[spanLongIndex]);
      const lowUpdated = (low & ~(spanMask << BigInt(spanOffset))) | (spanValue << BigInt(spanOffset));
      this.#data[spanLongIndex] = BigInt.asIntN(64, lowUpdated);

      // 次の64bit値へ続く場合は、続き分の下位ビットを書き換える
      if (spanOffset + this.#bitsPerEntry > 64) {
        const shift = BigInt(64 - spanOffset);
        const high = BigInt.asUintN(64, this.#data[spanLongIndex + 1]);
        const highUpdated = (high & ~(spanMask >> shift)) | (spanValue >> shift);
        this.#data[spanLongIndex + 1] = BigInt.asIntN(64, highUpdated);
      }

      return;
    }

    const perLong = this.valuesPerLong;
    const longIndex = Math.floor(index / perLong);
    const bitOffset = BigInt((index % perLong) * this.#bitsPerEntry);
    const mask = ((1n << BigInt(this.#bitsPerEntry)) - 1n) << bitOffset;

    const current = BigInt.asUintN(64, this.#data[longIndex]);
    const updated = (current & ~mask) | ((BigInt(value) << bitOffset) & mask);
    this.#data[longIndex] = BigInt.asIntN(64, updated);
  }

  /**
   * packedな配列を返す
   * 内部の配列をそのまま返す（コピーしない）
   */
  toLongs(): BigInt64Array {
    return this.#data;
  }

  /** 別のビット幅へ詰め直した新しい記憶域を返す */
  resize(newBitsPerEntry: number): BitStorage {
    const result = BitStorage.createWith(newBitsPerEntry, this.#entryCount, this.#spanning);

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

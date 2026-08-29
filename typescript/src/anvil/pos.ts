/**
 * チャンクとリージョンの座標。
 *
 * 仕様: `docs/spec/20-anvil-region.md` 1章
 */

/** リージョンの座標。1リージョンは 32×32 チャンクを担当する。 */
export class RegionPos {
  constructor(
    readonly x: number,
    readonly z: number,
  ) {}

  /** このリージョンのファイル名（`r.X.Z.mca`）。 */
  get fileName(): string {
    return `r.${this.x}.${this.z}.mca`;
  }

  /** 座標が等しいか。 */
  equals(other: RegionPos): boolean {
    return other.x === this.x && other.z === this.z;
  }

  /** マップの鍵として使える文字列。 */
  get key(): string {
    return `${this.x},${this.z}`;
  }

  /** `r.X.Z.mca` 形式のファイル名から座標を得る。解釈できなければ undefined。 */
  static fromFileName(fileName: string): RegionPos | undefined {
    const parts = fileName.split(".");

    // "r" "<x>" "<z>" "mca" の 4 つに分かれるはず
    if (parts.length !== 4 || parts[0] !== "r" || parts[3] !== "mca") {
      return undefined;
    }

    // 整数として厳密に読めるものだけを受け付ける
    if (!/^-?\d+$/.test(parts[1]) || !/^-?\d+$/.test(parts[2])) {
      return undefined;
    }

    return new RegionPos(Number.parseInt(parts[1], 10), Number.parseInt(parts[2], 10));
  }
}

/** チャンクの絶対座標。 */
export class ChunkPos {
  constructor(
    readonly x: number,
    readonly z: number,
  ) {}

  /**
   * このチャンクを含むリージョンの座標。
   *
   * 算術右シフトなので負の座標でも正しく求まる。
   */
  get region(): RegionPos {
    return new RegionPos(this.x >> 5, this.z >> 5);
  }

  /** リージョン内でのX位置 (0..31)。 */
  get localX(): number {
    return this.x & 31;
  }

  /** リージョン内でのZ位置 (0..31)。 */
  get localZ(): number {
    return this.z & 31;
  }

  /** ロケーションテーブル内の添字 (0..1023)。 */
  get index(): number {
    return this.localX + this.localZ * 32;
  }

  /** 座標が等しいか。 */
  equals(other: ChunkPos): boolean {
    return other.x === this.x && other.z === this.z;
  }
}

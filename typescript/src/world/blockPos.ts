/**
 * ブロックの絶対座標と、その範囲
 *
 * 仕様: `docs/spec/30-chunk-format.md` 5章
 */

import { ChunkPos } from "../anvil/index.js";

/** ブロックの絶対座標 */
export class BlockPos {
  constructor(
    readonly x: number,
    readonly y: number,
    readonly z: number,
  ) {}

  /**
   * この座標を含むチャンクの座標
   * 算術右シフトなので負の座標でも正しく求まる
   */
  get chunkPos(): ChunkPos {
    return new ChunkPos(this.x >> 4, this.z >> 4);
  }

  /** チャンク内でのX位置 (0..15) */
  get localX(): number {
    return this.x & 15;
  }

  /** チャンク内でのZ位置 (0..15) */
  get localZ(): number {
    return this.z & 15;
  }

  /** 各軸へずらした座標を返す */
  offset(dx: number, dy: number, dz: number): BlockPos {
    return new BlockPos(this.x + dx, this.y + dy, this.z + dz);
  }

  /** 同じ座標か */
  equals(other: unknown): boolean {
    return (
      other instanceof BlockPos && other.x === this.x && other.y === this.y && other.z === this.z
    );
  }

  /** `(x, y, z)` の形の文字列にする */
  toString(): string {
    return `(${this.x}, ${this.y}, ${this.z})`;
  }
}

/**
 * ブロック座標の直方体な範囲
 *
 * 両端を含む
 * `Cuboid.of(0, 0, 0, 0, 0, 0)` は 1 ブロック
 *
 * 範囲内のブロックを順に処理したいときに使う
 */
export class Cuboid {
  readonly minX: number;
  readonly minY: number;
  readonly minZ: number;
  readonly maxX: number;
  readonly maxY: number;
  readonly maxZ: number;

  /**
   * 両端の座標から作る
   * 大小の順序は問わない。内部で小さいほうを最小に揃える
   */
  constructor(first: BlockPos, second: BlockPos) {
    this.minX = Math.min(first.x, second.x);
    this.minY = Math.min(first.y, second.y);
    this.minZ = Math.min(first.z, second.z);
    this.maxX = Math.max(first.x, second.x);
    this.maxY = Math.max(first.y, second.y);
    this.maxZ = Math.max(first.z, second.z);
  }

  /** 両端の座標から作る */
  static of(x1: number, y1: number, z1: number, x2: number, y2: number, z2: number): Cuboid {
    return new Cuboid(new BlockPos(x1, y1, z1), new BlockPos(x2, y2, z2));
  }

  /** X 方向の長さ */
  get sizeX(): number {
    return this.maxX - this.minX + 1;
  }

  /** Y 方向の長さ */
  get sizeY(): number {
    return this.maxY - this.minY + 1;
  }

  /** Z 方向の長さ */
  get sizeZ(): number {
    return this.maxZ - this.minZ + 1;
  }

  /** 含まれるブロックの個数 */
  get volume(): number {
    return this.sizeX * this.sizeY * this.sizeZ;
  }

  /** その座標が範囲に含まれるか */
  contains(x: number, y: number, z: number): boolean {
    return (
      x >= this.minX &&
      x <= this.maxX &&
      y >= this.minY &&
      y <= this.maxY &&
      z >= this.minZ &&
      z <= this.maxZ
    );
  }

  /**
   * 範囲内の座標を順に返す
   * 並びは Y、Z、X の順で、X がいちばん内側で動く
   */
  *positions(): IterableIterator<BlockPos> {
    // 内側から X が動くので、同じチャンクの並びを続けて触れる
    for (let y = this.minY; y <= this.maxY; y++) {
      for (let z = this.minZ; z <= this.maxZ; z++) {
        for (let x = this.minX; x <= this.maxX; x++) {
          yield new BlockPos(x, y, z);
        }
      }
    }
  }

  /** 同じ範囲か */
  equals(other: unknown): boolean {
    return (
      other instanceof Cuboid &&
      other.minX === this.minX &&
      other.minY === this.minY &&
      other.minZ === this.minZ &&
      other.maxX === this.maxX &&
      other.maxY === this.maxY &&
      other.maxZ === this.maxZ
    );
  }

  /** 両端を並べた文字列にする */
  toString(): string {
    return `(${this.minX}, ${this.minY}, ${this.minZ})-(${this.maxX}, ${this.maxY}, ${this.maxZ})`;
  }
}

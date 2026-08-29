/**
 * リージョンファイルが並ぶディレクトリ 1 つ分
 * （`region/`、`entities/`、`poi/` のいずれか）。
 *
 * 開いたリージョンファイルはキャッシュし、`close()` でまとめて閉じる。
 * チャンク座標からリージョンを解決するので、利用側はリージョンの存在を意識しなくてよい。
 *
 * 仕様: `docs/spec/20-anvil-region.md` 5章
 */

import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { ErrorCode, SpringNbtError } from "../errors.js";
import { NbtCompound } from "../nbt/index.js";
import { ChunkPos, RegionPos } from "./pos.js";
import { RegionFile, RegionFileMode } from "./regionFile.js";

export class RegionFolder {
  readonly #cache = new Map<string, RegionFile>();
  readonly #mode: RegionFileMode;
  #closed = false;

  private constructor(
    readonly directory: string,
    mode: RegionFileMode,
  ) {
    this.#mode = mode;
  }

  /** リージョンフォルダを開く。 */
  static open(directory: string, mode: RegionFileMode = RegionFileMode.ReadOnly): RegionFolder {
    if (!existsSync(directory) && mode === RegionFileMode.ReadOnly) {
      throw new SpringNbtError(ErrorCode.Io, `リージョンフォルダが存在しない: ${directory}`);
    }

    return new RegionFolder(directory, mode);
  }

  /** このフォルダに存在するリージョンの座標を返す。 */
  regionPositions(): RegionPos[] {
    this.#ensureOpen();

    if (!existsSync(this.directory)) {
      return [];
    }

    const found: RegionPos[] = [];

    // r.X.Z.mca として解釈できるファイルだけを拾う
    for (const name of readdirSync(this.directory)) {
      const position = RegionPos.fromFileName(name);

      if (position !== undefined) {
        found.push(position);
      }
    }

    // 走査順がファイルシステム依存にならないよう、座標で並べる
    found.sort((left, right) => {
      if (left.z !== right.z) {
        return left.z - right.z;
      }

      return left.x - right.x;
    });

    return found;
  }

  /** リージョンファイルを取得する。読み取り専用で存在しなければ undefined。 */
  region(regionX: number, regionZ: number): RegionFile | undefined {
    this.#ensureOpen();
    const position = new RegionPos(regionX, regionZ);
    const cached = this.#cache.get(position.key);

    if (cached !== undefined) {
      return cached;
    }

    const path = join(this.directory, position.fileName);

    // 読み取り専用では、存在しないリージョンは「チャンクが無い」として undefined を返す
    if (!existsSync(path) && this.#mode === RegionFileMode.ReadOnly) {
      return undefined;
    }

    const opened = RegionFile.open(path, this.#mode);
    this.#cache.set(position.key, opened);
    return opened;
  }

  /** チャンクが存在するか。 */
  hasChunk(chunkX: number, chunkZ: number): boolean {
    const file = this.#regionFor(chunkX, chunkZ);

    if (file === undefined) {
      return false;
    }

    return file.hasChunk(chunkX, chunkZ);
  }

  /** チャンクを NBT として読む。存在しなければ undefined。 */
  readChunk(chunkX: number, chunkZ: number): NbtCompound | undefined {
    const file = this.#regionFor(chunkX, chunkZ);

    if (file === undefined) {
      return undefined;
    }

    return file.readChunk(chunkX, chunkZ);
  }

  /** チャンクを NBT として書き込む。 */
  writeChunk(chunkX: number, chunkZ: number, tag: NbtCompound): void {
    const file = this.#regionFor(chunkX, chunkZ);

    if (file === undefined) {
      throw SpringNbtError.invalidArgument(
        `読み取り専用のフォルダには書き込めない: ${this.directory}`,
      );
    }

    file.writeChunk(chunkX, chunkZ, tag);
  }

  /** チャンクを削除する。削除できたら true。 */
  deleteChunk(chunkX: number, chunkZ: number): boolean {
    const file = this.#regionFor(chunkX, chunkZ);

    if (file === undefined) {
      return false;
    }

    return file.deleteChunk(chunkX, chunkZ);
  }

  /** このフォルダに存在する全チャンクの座標を返す。 */
  chunkPositions(): ChunkPos[] {
    const result: ChunkPos[] = [];

    // リージョンごとに、その中のチャンクを順に集める
    for (const position of this.regionPositions()) {
      const file = this.region(position.x, position.z);

      if (file === undefined) {
        continue;
      }

      result.push(...file.chunkPositions());
    }

    return result;
  }

  /** 開いている全リージョンの変更を書き出す。 */
  flush(): void {
    this.#ensureOpen();

    for (const file of this.#cache.values()) {
      file.flush();
    }
  }

  /** 開いている全リージョンを閉じる。 */
  close(): void {
    if (this.#closed) {
      return;
    }

    for (const file of this.#cache.values()) {
      file.close();
    }

    this.#cache.clear();
    this.#closed = true;
  }

  #regionFor(chunkX: number, chunkZ: number): RegionFile | undefined {
    const position = new ChunkPos(chunkX, chunkZ).region;
    return this.region(position.x, position.z);
  }

  #ensureOpen(): void {
    if (this.#closed) {
      throw SpringNbtError.invalidArgument("既に閉じられたリージョンフォルダ");
    }
  }
}

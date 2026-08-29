/**
 * リージョンファイルが並ぶディレクトリ 1 つ分
 * （`region/`、`entities/`、`poi/` のいずれか）。
 *
 * 開いたリージョンファイルはキャッシュし、`close()` でまとめて閉じる。
 * チャンク座標からリージョンを解決するので、利用側はリージョンの存在を意識しなくてよい。
 *
 * `RegionFile` はファイル全体をメモリへ載せるため、キャッシュには
 * `maxCachedRegions` 件の上限がある。上限を超えると、最も長く使われていない
 * ものから書き出して閉じる。大きなワールドを端から走査してもメモリを使い切らない。
 *
 * このため `region()` が返した参照は、
 * **別のリージョンへアクセスすると閉じられている場合がある**。
 * 参照を保持せず、必要なたびに取得すること。
 *
 * 仕様: `docs/spec/20-anvil-region.md` 5章
 */

import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { ErrorCode, SpringNbtError } from "../errors.js";
import { NbtCompound } from "../nbt/index.js";
import { ChunkPos, RegionPos } from "./pos.js";
import { RegionFile, RegionFileMode } from "./regionFile.js";

/**
 * 同時に開いておくリージョンファイル数の既定の上限。
 *
 * 1 リージョンは最大 255 セクタ × 1024 チャンク＝理論上 1GiB になりうる。
 * 実データでは数 MB から数十 MB 程度。8 件なら通常のワールドで数百 MB に収まる。
 */
export const DEFAULT_MAX_CACHED_REGIONS = 8;

/**
 * リージョンファイルが並ぶディレクトリ 1 つ分
 * （`region/`、`entities/`、`poi/` のいずれか）。
 *
 * チャンク座標からリージョンを解決するので、利用側はリージョンの存在を意識しなくてよい。
 */
export class RegionFolder {
  readonly #cache = new Map<string, RegionFile>();

  /** 最近使った順のリージョンキー。末尾がいちばん新しい。 */
  readonly #recentlyUsed: string[] = [];

  readonly #mode: RegionFileMode;
  #closed = false;

  private constructor(
    readonly directory: string,
    mode: RegionFileMode,
    readonly maxCachedRegions: number,
  ) {
    this.#mode = mode;
  }

  /** いま開いているリージョンファイル数。 */
  get cachedRegionCount(): number {
    return this.#cache.size;
  }

  /** リージョンフォルダを開く。 */
  static open(
    directory: string,
    mode: RegionFileMode = RegionFileMode.ReadOnly,
    maxCachedRegions: number = DEFAULT_MAX_CACHED_REGIONS,
  ): RegionFolder {
    if (maxCachedRegions < 1) {
      throw SpringNbtError.invalidArgument(
        `maxCachedRegions は 1 以上でなければならない: ${maxCachedRegions}`,
      );
    }

    if (!existsSync(directory) && mode === RegionFileMode.ReadOnly) {
      throw new SpringNbtError(ErrorCode.Io, `リージョンフォルダが存在しない: ${directory}`);
    }

    return new RegionFolder(directory, mode, maxCachedRegions);
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
      this.#touch(position.key);
      return cached;
    }

    const path = join(this.directory, position.fileName);

    // 読み取り専用では、存在しないリージョンは「チャンクが無い」として undefined を返す
    if (!existsSync(path) && this.#mode === RegionFileMode.ReadOnly) {
      return undefined;
    }

    // 開く前に空きを作る。開いてからだと一瞬だけ上限を超える
    this.#evictUntilBelowLimit();

    const opened = RegionFile.open(path, this.#mode);
    this.#cache.set(position.key, opened);
    this.#touch(position.key);
    return opened;
  }

  /** 使ったリージョンを、最近使った列の末尾へ移す。 */
  #touch(key: string): void {
    const index = this.#recentlyUsed.indexOf(key);

    if (index >= 0) {
      this.#recentlyUsed.splice(index, 1);
    }

    this.#recentlyUsed.push(key);
  }

  /** 新しく 1 件開けるよう、上限を下回るまで古いものを閉じる。 */
  #evictUntilBelowLimit(): void {
    // 上限に達している間、いちばん長く使っていないものから閉じる
    while (this.#cache.size >= this.maxCachedRegions && this.#recentlyUsed.length > 0) {
      const oldest = this.#recentlyUsed.shift();

      if (oldest === undefined) {
        break;
      }

      const file = this.#cache.get(oldest);

      if (file !== undefined) {
        // 閉じる前に必ず書き出す。捨てると変更が失われる
        file.close();
        this.#cache.delete(oldest);
      }
    }
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
    this.#recentlyUsed.length = 0;
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

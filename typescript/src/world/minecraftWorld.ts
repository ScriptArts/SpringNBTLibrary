/**
 * Minecraft Java版のセーブデータ 1 つ分と、その中の次元
 *
 * 26.x では構成が大きく変わっており、標準の3次元も
 * `dimensions/<名前空間>/<パス>/` の下に並ぶ
 *
 * 仕様: `docs/spec/40-world-layout.md`
 */

import { copyFileSync, existsSync, readdirSync, renameSync, statSync } from "node:fs";
import { basename, join } from "node:path";

import { ChunkPos, RegionFileMode, RegionFolder } from "../anvil/index.js";
import { ErrorCode, SpringNbtError } from "../errors.js";
import { NamedTag, NbtCompound, readFile, writeFile } from "../nbt/index.js";
import { Chunk, ChunkReadOptions, ChunkWriteOptions } from "./chunk.js";
import { BlockState } from "./blockState.js";

/** ワールドを開くときの動作 */
export interface WorldOpenOptions {
  /**
   * 読み書きで開くか
   * 既定は読み取り専用
   */
  writable?: boolean;
  /**
   * `session.lock` の確認を飛ばすか
   *
   * TypeScript 版はこの確認を行わない
   * Node には移植性のある
   * ファイルロックの手段が無いため（`docs/adr/0008-session-lock.md`）
   * 他言語版との API を揃えるためにフィールドだけ用意してある
   *
   * Minecraft が起動中のワールドへ書き込むとデータが壊れるので、
   * 起動していないことは呼び出し側で担保すること
   */
  ignoreSessionLock?: boolean;
  /** チャンク読み込みのオプション */
  chunkRead?: ChunkReadOptions;
  /** チャンク書き込みのオプション */
  chunkWrite?: ChunkWriteOptions;
}

/**
 * `level.dat` の内容
 *
 * 26.x では大幅に軽量化されており、ゲームルールやワールド生成設定は
 * `data/minecraft/` 配下の個別ファイルへ分離されている
 */
export class LevelData {
  readonly raw: NbtCompound;
  readonly data: NbtCompound;
  readonly #rootName: string;

  constructor(named: NamedTag) {
    this.#rootName = named.name;
    this.raw = named.tag;
    this.data = named.tag.getCompound("Data");
  }

  /** チャンク構造のバージョン */
  get dataVersion(): number {
    return this.data.getInt("DataVersion");
  }

  /** ワールド名 */
  get levelName(): string {
    return this.data.getString("LevelName");
  }

  /** ワールドの経過時間（tick） */
  get time(): bigint {
    return this.data.getLong("Time");
  }

  /**
   * ゲームモード
   * 0=サバイバル 1=クリエイティブ 2=アドベンチャー 3=スペクテイター
   */
  get gameType(): number {
    return this.data.getInt("GameType");
  }

  /** スポーン地点の `[x, y, z]` */
  get spawnPos(): Int32Array {
    return this.data.getCompound("spawn").getIntArray("pos");
  }

  /** スポーン地点の次元ID */
  get spawnDimension(): string {
    return this.data.getCompound("spawn").getString("dimension");
  }

  /** 難易度（`normal` など） */
  get difficulty(): string {
    return this.data.getCompound("difficulty_settings").getString("difficulty");
  }

  /** ハードコアか */
  get isHardcore(): boolean {
    return this.data.getCompound("difficulty_settings").getBool("hardcore");
  }

  /** バージョン名（`26.2` など） */
  get versionName(): string {
    return this.data.getCompound("Version").getString("Name");
  }

  /** 書き出し用の `NamedTag` を作る */
  toNamedTag(): NamedTag {
    return new NamedTag(this.#rootName, this.raw);
  }
}

/**
 * ワールド内の次元 1 つ分
 * `region/` `entities/` `poi/` をまとめて扱う
 *
 * ブロックの取得・設定は**絶対ワールド座標**で行い、
 * リージョン・チャンク・セクションの解決は内部で済ませる
 */
export class Dimension {
  readonly #chunkCache = new Map<string, Chunk>();
  readonly #modified = new Set<string>();
  readonly #writable: boolean;
  readonly #chunkRead: ChunkReadOptions | undefined;
  readonly #chunkWrite: ChunkWriteOptions | undefined;

  #regions: RegionFolder | undefined;
  #entities: RegionFolder | undefined;
  #poi: RegionFolder | undefined;
  #closed = false;

  constructor(
    readonly id: string,
    readonly directory: string,
    options: WorldOpenOptions,
  ) {
    this.#writable = options.writable === true;
    this.#chunkRead = options.chunkRead;
    this.#chunkWrite = options.chunkWrite;
  }

  /**
   * 地形のリージョンフォルダ
   * 無ければ undefined
   */
  get regionFolder(): RegionFolder | undefined {
    this.#regions = this.#folder(this.#regions, "region");
    return this.#regions;
  }

  /**
   * エンティティのリージョンフォルダ
   * 無ければ undefined
   */
  get entityFolder(): RegionFolder | undefined {
    this.#entities = this.#folder(this.#entities, "entities");
    return this.#entities;
  }

  /**
   * POI のリージョンフォルダ
   * 無ければ undefined
   */
  get poiFolder(): RegionFolder | undefined {
    this.#poi = this.#folder(this.#poi, "poi");
    return this.#poi;
  }

  /**
   * `data/minecraft/<name>.dat` を読む
   * 存在しなければ undefined
   */
  dataFile(name: string): NbtCompound | undefined {
    this.#ensureOpen();
    const path = join(this.directory, "data", "minecraft", `${name}.dat`);

    if (!existsSync(path)) {
      return undefined;
    }

    return readFile(path).tag;
  }

  /** この次元に存在する全チャンクの座標を返す */
  chunkPositions(): ChunkPos[] {
    this.#ensureOpen();
    const folder = this.regionFolder;

    if (folder === undefined) {
      return [];
    }

    return folder.chunkPositions();
  }

  /**
   * チャンクを読む
   * 読み込んだチャンクはキャッシュされる
   */
  chunk(chunkX: number, chunkZ: number): Chunk | undefined {
    this.#ensureOpen();
    const key = `${chunkX},${chunkZ}`;
    const cached = this.#chunkCache.get(key);

    if (cached !== undefined) {
      return cached;
    }

    const folder = this.regionFolder;

    if (folder === undefined) {
      return undefined;
    }

    const nbt = folder.readChunk(chunkX, chunkZ);

    if (nbt === undefined) {
      return undefined;
    }

    const chunk = Chunk.fromNbt(nbt, this.#chunkRead);
    this.#chunkCache.set(key, chunk);
    return chunk;
  }

  /** チャンクを書き戻す */
  saveChunk(chunk: Chunk): void {
    this.#ensureOpen();
    this.#ensureWritable();
    const folder = this.regionFolder;

    if (folder === undefined) {
      throw SpringNbtError.invalidArgument(`region/ が無い次元には書き込めない: ${this.id}`);
    }

    folder.writeChunk(chunk.x, chunk.z, chunk.toNbt(this.#chunkWrite));
    this.#modified.delete(`${chunk.x},${chunk.z}`);
  }

  /**
   * 絶対座標でブロックを取得する
   * チャンクが無ければ undefined
   */
  getBlock(x: number, y: number, z: number): BlockState | undefined {
    const chunk = this.chunk(x >> 4, z >> 4);

    if (chunk === undefined) {
      return undefined;
    }

    return chunk.getBlock(x & 15, y, z & 15);
  }

  /**
   * 絶対座標でブロックを設定する
   *
   * 変更したチャンクは記録され、`flush()` でまとめて書き戻される
   * 本ライブラリはチャンクを新規生成しないので、存在しない座標はエラーになる
   */
  setBlock(x: number, y: number, z: number, state: BlockState): void {
    this.#ensureWritable();
    const chunkX = x >> 4;
    const chunkZ = z >> 4;
    const chunk = this.chunk(chunkX, chunkZ);

    if (chunk === undefined) {
      throw SpringNbtError.invalidArgument(
        `チャンク (${chunkX}, ${chunkZ}) が存在しない。本ライブラリはチャンクを生成しない`,
      );
    }

    chunk.setBlock(x & 15, y, z & 15, state);
    this.#modified.add(`${chunkX},${chunkZ}`);
  }

  /**
   * 絶対座標でバイオームを取得する
   * 4×4×4 の単位
   */
  getBiome(x: number, y: number, z: number): string | undefined {
    const chunk = this.chunk(x >> 4, z >> 4);

    if (chunk === undefined) {
      return undefined;
    }

    return chunk.getBiome(x & 15, y, z & 15);
  }

  /**
   * 絶対座標でバイオームを設定する
   * 4×4×4 の単位
   */
  setBiome(x: number, y: number, z: number, biome: string): void {
    this.#ensureWritable();
    const chunkX = x >> 4;
    const chunkZ = z >> 4;
    const chunk = this.chunk(chunkX, chunkZ);

    if (chunk === undefined) {
      throw SpringNbtError.invalidArgument(
        `チャンク (${chunkX}, ${chunkZ}) が存在しない。本ライブラリはチャンクを生成しない`,
      );
    }

    chunk.setBiome(x & 15, y, z & 15, biome);
    this.#modified.add(`${chunkX},${chunkZ}`);
  }

  /** 変更したチャンクをすべて書き戻し、リージョンをディスクへ反映する */
  flush(): void {
    this.#ensureOpen();

    if (!this.#writable) {
      return;
    }

    // 変更のあったチャンクだけを書き戻す
    for (const key of this.#modified) {
      const chunk = this.#chunkCache.get(key);

      if (chunk !== undefined) {
        this.regionFolder!.writeChunk(chunk.x, chunk.z, chunk.toNbt(this.#chunkWrite));
      }
    }

    this.#modified.clear();
    this.#flushFolders();
  }

  /** 変更を書き戻してから閉じる */
  close(): void {
    if (this.#closed) {
      return;
    }

    if (this.#writable) {
      this.flush();
    }

    this.#closeFolders();
    this.#chunkCache.clear();
    this.#closed = true;
  }

  /** 開いているフォルダだけを書き出す */
  #flushFolders(): void {
    // 開いているフォルダだけを書き出す
    for (const folder of [this.#regions, this.#entities, this.#poi]) {
      if (folder !== undefined) {
        folder.flush();
      }
    }
  }

  /** 開いているフォルダだけを閉じる */
  #closeFolders(): void {
    // 開いているフォルダだけを閉じる
    for (const folder of [this.#regions, this.#entities, this.#poi]) {
      if (folder !== undefined) {
        folder.close();
      }
    }
  }

  /**
   * フォルダを遅延して開く
   * 存在しなければ undefined のまま
   */
  #folder(slot: RegionFolder | undefined, name: string): RegionFolder | undefined {
    this.#ensureOpen();

    if (slot !== undefined) {
      return slot;
    }

    const path = join(this.directory, name);

    // 生成されていない次元にはディレクトリ自体が無い
    if (!existsSync(path) && !this.#writable) {
      return undefined;
    }

    let mode = RegionFileMode.ReadOnly;

    if (this.#writable) {
      mode = RegionFileMode.ReadWrite;
    }

    return RegionFolder.open(path, mode);
  }

  #ensureWritable(): void {
    if (!this.#writable) {
      throw SpringNbtError.invalidArgument("読み取り専用で開いたワールドには書き込めない");
    }
  }

  #ensureOpen(): void {
    if (this.#closed) {
      throw SpringNbtError.invalidArgument("既に閉じられた次元");
    }
  }
}

/**
 * Minecraft Java版のセーブデータ 1 つ分
 *
 * 26.x では標準の3次元も `dimensions/<名前空間>/<パス>/` の下に並ぶ
 */
export class MinecraftWorld {
  readonly #dimensions = new Map<string, Dimension>();
  readonly #options: WorldOpenOptions;
  #closed = false;

  private constructor(
    readonly directory: string,
    options: WorldOpenOptions,
    readonly level: LevelData,
  ) {
    this.#options = options;
  }

  /** ワールドを開く */
  static open(directory: string, options: WorldOpenOptions = {}): MinecraftWorld {
    if (!existsSync(directory) || !statSync(directory).isDirectory()) {
      throw new SpringNbtError(ErrorCode.Io, `ワールドディレクトリが無い: ${directory}`);
    }

    const levelPath = join(directory, "level.dat");

    if (!existsSync(levelPath)) {
      throw new SpringNbtError(ErrorCode.Io, `level.dat が無い: ${levelPath}`);
    }

    // 書き込むなら、Minecraft が起動中でないことを先に確かめる
    if (options.writable === true && options.ignoreSessionLock !== true) {
      checkSessionLock(directory);
    }

    return new MinecraftWorld(directory, options, new LevelData(readFile(levelPath)));
  }

  /**
   * `data/minecraft/<name>.dat` を読む
   * 存在しなければ undefined
   *
   * 26.x では `game_rules` / `weather` / `world_gen_settings` などが
   * この形で `level.dat` から分離されている
   */
  dataFile(name: string): NbtCompound | undefined {
    this.#ensureOpen();
    const path = join(this.directory, "data", "minecraft", `${name}.dat`);

    if (!existsSync(path)) {
      return undefined;
    }

    return readFile(path).tag;
  }

  /** 存在する次元のIDを返す */
  dimensionIds(): string[] {
    this.#ensureOpen();
    const root = join(this.directory, "dimensions");

    if (!existsSync(root)) {
      return [];
    }

    const found: string[] = [];

    // dimensions/<名前空間>/<パス>/ の 2 段を辿る
    for (const namespaceName of readdirSync(root)) {
      const namespaceDir = join(root, namespaceName);

      if (!statSync(namespaceDir).isDirectory()) {
        continue;
      }

      // 2 段目が次元のパス
      for (const pathName of readdirSync(namespaceDir)) {
        // ディレクトリだけを次元として数える
        if (statSync(join(namespaceDir, pathName)).isDirectory()) {
          found.push(`${namespaceName}:${pathName}`);
        }
      }
    }

    // 走査順がファイルシステム依存にならないよう並べる
    found.sort();
    return found;
  }

  /**
   * 次元を得る
   * ディレクトリが無ければ undefined
   */
  dimension(dimensionId: string): Dimension | undefined {
    this.#ensureOpen();
    const normalized = normalizeDimensionId(dimensionId);
    const cached = this.#dimensions.get(normalized);

    if (cached !== undefined) {
      return cached;
    }

    const colon = normalized.indexOf(":");
    const path = join(
      this.directory,
      "dimensions",
      normalized.slice(0, colon),
      normalized.slice(colon + 1),
    );

    if (!existsSync(path)) {
      return undefined;
    }

    const opened = new Dimension(normalized, path, this.#options);
    this.#dimensions.set(normalized, opened);
    return opened;
  }

  /** プレイヤーのUUID一覧 */
  playerIds(): string[] {
    this.#ensureOpen();
    const path = join(this.directory, "players", "data");

    if (!existsSync(path)) {
      return [];
    }

    const found: string[] = [];

    // <uuid>.dat の名前部分が UUID にあたる
    for (const name of readdirSync(path)) {
      // .dat 以外のファイルは対象外
      if (name.endsWith(".dat")) {
        found.push(basename(name, ".dat"));
      }
    }

    found.sort();
    return found;
  }

  /**
   * プレイヤーデータを読む
   * 存在しなければ undefined
   */
  player(uuid: string): NbtCompound | undefined {
    this.#ensureOpen();
    const path = join(this.directory, "players", "data", `${uuid}.dat`);

    if (!existsSync(path)) {
      return undefined;
    }

    return readFile(path).tag;
  }

  /**
   * `level.dat` を書き戻す
   *
   * 壊れるとワールド全体が開けなくなるため、
   * 一時ファイルへ書いてから `level.dat_old` へ退避し、最後に置き換える
   */
  saveLevel(): void {
    this.#ensureOpen();

    if (this.#options.writable !== true) {
      throw SpringNbtError.invalidArgument("読み取り専用で開いたワールドには書き込めない");
    }

    const path = join(this.directory, "level.dat");
    const temporary = `${path}.tmp`;
    const backup = `${path}_old`;

    writeFile(temporary, this.level.toNamedTag());

    // 既存の level.dat は、置き換える前に level.dat_old へ退避する
    if (existsSync(path)) {
      copyFileSync(path, backup);
    }

    renameSync(temporary, path);
  }

  /** 開いている次元をすべて閉じる */
  close(): void {
    if (this.#closed) {
      return;
    }

    // 開いている次元をすべて閉じる
    for (const dimension of this.#dimensions.values()) {
      dimension.close();
    }

    this.#dimensions.clear();
    this.#closed = true;
  }

  #ensureOpen(): void {
    if (this.#closed) {
      throw SpringNbtError.invalidArgument("既に閉じられたワールド");
    }
  }
}

/**
 * `session.lock` を確認する（TypeScript 版では何もしない）
 *
 * Minecraft は起動中このファイルのロックを保持し続けるので、本来は
 * 「ロックを取れるか」で判定する
 * しかし Node には移植性のある
 * ファイルロックの手段が無く、ファイルの存在自体は起動していなくても残るため、
 * 存在確認だけでは何も判定できない
 *
 * 誤った判定を返すよりは何もしないほうが安全なので、素通しする
 *
 * 仕様: docs/spec/40-world-layout.md 3章 / docs/adr/0008-session-lock.md
 */
function checkSessionLock(directory: string): void {
  void directory;
}

/** 名前空間が省略されていたら `minecraft:` を補う */
function normalizeDimensionId(dimensionId: string): string {
  if (dimensionId.includes(":")) {
    return dimensionId;
  }

  return `minecraft:${dimensionId}`;
}

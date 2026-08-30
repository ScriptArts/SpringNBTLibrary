/**
 * Anvil のリージョンファイル (`r.X.Z.mca`)
 * 32×32 チャンクを格納する
 *
 * ファイル全体をメモリに読み込んで扱う
 * 実データのリージョンは数 MB 程度で、
 * この方が「触っていないチャンクのバイト配置をそのまま保つ」ことを保証しやすい
 * 開いて何も変えずに `flush()` すると、バイト単位で元と同じファイルになる
 *
 * 仕様: `docs/spec/20-anvil-region.md`
 */

import { existsSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { basename, dirname, join } from "node:path";
import { deflateSync, gunzipSync, gzipSync, inflateSync, constants as zlibConstants } from "node:zlib";

import { ErrorCode, SpringNbtError } from "../errors.js";
import {
  Compression,
  NamedTag,
  NbtCompound,
  readBytes,
  writeBytes,
} from "../nbt/index.js";
import {
  ChunkCompression,
  RawChunk,
  chunkCompressionAsString,
  chunkCompressionFromId,
} from "./compression.js";
import { ChunkPos, RegionPos } from "./pos.js";

/** セクタ長 */
export const SECTOR_SIZE = 4096;

/** ロケーションテーブルとタイムスタンプテーブルが占めるセクタ数 */
const HEADER_SECTORS = 2;

/** 1リージョンに入るチャンク数 */
const CHUNK_COUNT = 1024;

/** 1チャンクが確保できるセクタ数の上限（長さフィールドが u8 のため） */
const MAX_SECTORS = 255;

/**
 * リージョン内に収められるペイロードの上限
 * 超えると外部ファイルへ退避する
 */
const MAX_INLINE_PAYLOAD = MAX_SECTORS * SECTOR_SIZE - 5;

/** リージョンファイルを開くときの動作 */
export enum RegionFileMode {
  /**
   * 読み取り専用
   * 書き込み系の操作はエラーになる
   */
  ReadOnly = "read_only",
  /**
   * 読み書き
   * ファイルが無ければ空のリージョンとして扱う
   */
  ReadWrite = "read_write",
}

/**
 * Anvil のリージョンファイル (`r.X.Z.mca`)
 * 32×32 チャンクを格納する
 *
 * ファイル全体をメモリに読み込んで扱うので、開いて何も変えずに `flush()` すると
 * バイト単位で元と同じファイルになる
 */
export class RegionFile {
  readonly #path: string;
  readonly #directory: string;
  readonly #mode: RegionFileMode;
  readonly #offsets = new Int32Array(CHUNK_COUNT);
  readonly #sectorCounts = new Int32Array(CHUNK_COUNT);
  readonly #timestamps = new Int32Array(CHUNK_COUNT);

  #data: Uint8Array;
  #dirty = false;
  #closed = false;

  private constructor(path: string, mode: RegionFileMode, position: RegionPos, data: Uint8Array) {
    this.#path = path;
    this.#directory = dirname(path);
    this.#mode = mode;
    this.#data = data;
    this.regionX = position.x;
    this.regionZ = position.z;
    this.#parseHeader();
  }

  /** このリージョンのX座標 */
  readonly regionX: number;

  /** このリージョンのZ座標 */
  readonly regionZ: number;

  /**
   * リージョンファイルを開く
   *
   * @param path `r.X.Z.mca` という名前のファイル
   * 座標はファイル名から読み取る
   * @param mode 読み取り専用か読み書きか
   */
  static open(path: string, mode: RegionFileMode = RegionFileMode.ReadOnly): RegionFile {
    const position = RegionPos.fromFileName(basename(path));

    if (position === undefined) {
      throw SpringNbtError.invalidArgument(
        `リージョンファイル名として解釈できない: ${basename(path)}`,
      );
    }

    let raw: Uint8Array;

    // 既にあるファイルは読み込み、無ければ空のヘッダだけを組み立てる
    if (existsSync(path)) {
      try {
        raw = new Uint8Array(readFileSync(path));
      } catch (error) {
        throw new SpringNbtError(ErrorCode.Io, `ファイルを読めない: ${path}`, { cause: error });
      }
    } else if (mode === RegionFileMode.ReadWrite) {
      // 読み書きモードなら、存在しないファイルは空のリージョンとして扱う
      raw = new Uint8Array(HEADER_SECTORS * SECTOR_SIZE);
    } else {
      throw new SpringNbtError(ErrorCode.Io, `ファイルが存在しない: ${path}`);
    }

    return new RegionFile(path, mode, position, raw);
  }

  /** ヘッダを解析し、ロケーションとタイムスタンプを取り込む */
  #parseHeader(): void {
    // 空ファイルは「チャンクが 1 つも無いリージョン」として受け入れる
    if (this.#data.length === 0) {
      this.#data = new Uint8Array(HEADER_SECTORS * SECTOR_SIZE);
      return;
    }

    if (this.#data.length < HEADER_SECTORS * SECTOR_SIZE) {
      throw SpringNbtError.malformed(
        `ヘッダが足りない: ${this.#data.length} バイト（最低 ${HEADER_SECTORS * SECTOR_SIZE} バイト必要）`,
      );
    }

    if (this.#data.length % SECTOR_SIZE !== 0) {
      throw SpringNbtError.malformed(
        `ファイル長がセクタ境界に揃っていない: ${this.#data.length} バイト`,
      );
    }

    const totalSectors = this.#data.length / SECTOR_SIZE;
    const sectorOwner = new Map<number, number>();

    // ロケーションテーブルの 1024 エントリを順に取り込む
    for (let index = 0; index < CHUNK_COUNT; index++) {
      const entry = this.#readUnsigned(index * 4, 4);
      const offset = Math.floor(entry / 256);
      const count = entry & 0xff;

      this.#timestamps[index] = this.#readUnsigned(SECTOR_SIZE + index * 4, 4) | 0;

      if (offset === 0 && count === 0) {
        continue;
      }

      if (offset < HEADER_SECTORS) {
        throw SpringNbtError.malformed(
          `チャンク ${index} のオフセットがヘッダ領域を指している: ${offset}`,
        );
      }

      if (count === 0) {
        throw SpringNbtError.malformed(
          `チャンク ${index} のセクタ数が 0 なのにオフセットが設定されている`,
        );
      }

      if (offset + count > totalSectors) {
        throw SpringNbtError.malformed(`チャンク ${index} の割り当てがファイル外へはみ出している`);
      }

      // 同じセクタを 2 つのチャンクが指していたら、どちらかが壊れている
      for (let sector = offset; sector < offset + count; sector++) {
        const owner = sectorOwner.get(sector);

        if (owner !== undefined) {
          throw SpringNbtError.malformed(
            `セクタ ${sector} がチャンク ${owner} とチャンク ${index} で重複している`,
          );
        }

        sectorOwner.set(sector, index);
      }

      this.#offsets[index] = offset;
      this.#sectorCounts[index] = count;
    }
  }

  /** 指定した座標がこのリージョンの担当範囲にあるか確認し、添字を返す */
  #indexOf(chunkX: number, chunkZ: number): number {
    const position = new ChunkPos(chunkX, chunkZ);
    const region = position.region;

    if (region.x !== this.regionX || region.z !== this.regionZ) {
      throw SpringNbtError.invalidArgument(
        `チャンク (${chunkX}, ${chunkZ}) はリージョン (${this.regionX}, ${this.regionZ}) の担当外`,
      );
    }

    return position.index;
  }

  #ensureWritable(): void {
    if (this.#mode === RegionFileMode.ReadOnly) {
      throw SpringNbtError.invalidArgument("読み取り専用で開いたリージョンには書き込めない");
    }
  }

  #ensureOpen(): void {
    if (this.#closed) {
      throw SpringNbtError.invalidArgument("既に閉じられたリージョンファイル");
    }
  }

  /** チャンクが存在するか */
  hasChunk(chunkX: number, chunkZ: number): boolean {
    this.#ensureOpen();
    return this.#sectorCounts[this.#indexOf(chunkX, chunkZ)] > 0;
  }

  /** 存在するチャンクの座標を、ロケーションテーブルの並び順で返す */
  chunkPositions(): ChunkPos[] {
    this.#ensureOpen();
    const result: ChunkPos[] = [];

    // 添字の昇順に走査する（localZ が外、localX が内）
    for (let index = 0; index < CHUNK_COUNT; index++) {
      if (this.#sectorCounts[index] === 0) {
        continue;
      }

      const localX = index % 32;
      const localZ = Math.floor(index / 32);
      result.push(new ChunkPos(this.regionX * 32 + localX, this.regionZ * 32 + localZ));
    }

    return result;
  }

  /**
   * チャンクの最終更新時刻（Unix 秒）
   * 存在しなければ 0
   */
  timestamp(chunkX: number, chunkZ: number): number {
    this.#ensureOpen();
    return this.#timestamps[this.#indexOf(chunkX, chunkZ)];
  }

  /** チャンクの最終更新時刻を設定する */
  setTimestamp(chunkX: number, chunkZ: number, value: number): void {
    this.#ensureOpen();
    this.#ensureWritable();
    this.#timestamps[this.#indexOf(chunkX, chunkZ)] = value;
    this.#dirty = true;
  }

  /**
   * チャンクを圧縮されたまま取り出す
   * 存在しなければ undefined
   */
  readChunkRaw(chunkX: number, chunkZ: number): RawChunk | undefined {
    this.#ensureOpen();
    const index = this.#indexOf(chunkX, chunkZ);

    if (this.#sectorCounts[index] === 0) {
      return undefined;
    }

    const start = this.#offsets[index] * SECTOR_SIZE;
    const length = this.#readUnsigned(start, 4) | 0;
    const schemeByte = this.#data[start + 4];

    if (length < 1) {
      throw SpringNbtError.malformed(
        `チャンク (${chunkX}, ${chunkZ}) の length が不正: ${length}`,
      );
    }

    if (4 + length > this.#sectorCounts[index] * SECTOR_SIZE) {
      throw SpringNbtError.malformed(
        `チャンク (${chunkX}, ${chunkZ}) の length が確保セクタ数を超えている`,
      );
    }

    const external = (schemeByte & 0x80) !== 0;
    const compression = chunkCompressionFromId(schemeByte & 0x7f);

    if (external) {
      // 最上位ビットが立っている場合、本体は c.X.Z.mcc にある
      return new RawChunk(compression, this.#readExternalFile(chunkX, chunkZ), true);
    }

    return new RawChunk(compression, this.#data.slice(start + 5, start + 4 + length), false);
  }

  /**
   * チャンクを NBT として読む
   * 存在しなければ undefined
   */
  readChunk(chunkX: number, chunkZ: number): NbtCompound | undefined {
    const raw = this.readChunkRaw(chunkX, chunkZ);

    if (raw === undefined) {
      return undefined;
    }

    return readBytes(decompressChunk(raw), { compression: Compression.None }).tag;
  }

  /** チャンクを NBT として書き込む */
  writeChunk(
    chunkX: number,
    chunkZ: number,
    tag: NbtCompound,
    compression: ChunkCompression = ChunkCompression.Zlib,
  ): void {
    const plain = writeBytes(new NamedTag("", tag), { compression: Compression.None });
    this.writeChunkRaw(chunkX, chunkZ, new RawChunk(compression, compressChunk(plain, compression)));
  }

  /** 圧縮済みのチャンクをそのまま書き込む */
  writeChunkRaw(chunkX: number, chunkZ: number, raw: RawChunk): void {
    this.#ensureOpen();
    this.#ensureWritable();

    const index = this.#indexOf(chunkX, chunkZ);
    const useExternal = raw.data.length > MAX_INLINE_PAYLOAD;

    let payload: Uint8Array;
    let schemeByte: number;

    if (useExternal) {
      // 1MiB を超えるチャンクは外部ファイルへ退避し、リージョンには目印だけ残す
      this.#writeExternalFile(chunkX, chunkZ, raw.data);
      payload = new Uint8Array(0);
      schemeByte = raw.compression | 0x80;
    } else {
      this.#deleteExternalFile(chunkX, chunkZ);
      payload = raw.data;
      schemeByte = raw.compression;
    }

    const needed = Math.ceil((4 + 1 + payload.length) / SECTOR_SIZE);

    if (needed > MAX_SECTORS) {
      throw SpringNbtError.invalidArgument(
        `チャンクが大きすぎる: ${needed} セクタ（上限 ${MAX_SECTORS}）`,
      );
    }

    const start = this.#allocateSectors(index, needed);

    // 確保した領域をゼロで埋めてから書く（前の内容を残さないため）
    this.#data.fill(0, start * SECTOR_SIZE, (start + needed) * SECTOR_SIZE);

    const position = start * SECTOR_SIZE;
    this.#writeUnsigned(position, 1 + payload.length, 4);
    this.#data[position + 4] = schemeByte;
    this.#data.set(payload, position + 5);

    this.#offsets[index] = start;
    this.#sectorCounts[index] = needed;
    this.#timestamps[index] = Math.floor(Date.now() / 1000);
    this.#dirty = true;
  }

  /**
   * チャンクを削除する
   * 削除できたら true
   */
  deleteChunk(chunkX: number, chunkZ: number): boolean {
    this.#ensureOpen();
    this.#ensureWritable();

    const index = this.#indexOf(chunkX, chunkZ);

    if (this.#sectorCounts[index] === 0) {
      return false;
    }

    this.#deleteExternalFile(chunkX, chunkZ);
    this.#offsets[index] = 0;
    this.#sectorCounts[index] = 0;
    this.#timestamps[index] = 0;
    this.#dirty = true;
    return true;
  }

  /**
   * 必要なセクタ数を確保し、開始セクタ番号を返す
   *
   * 既存の割り当てがちょうど同じ大きさならその場を使い、
   * そうでなければ先頭から空き領域を探し、無ければ末尾へ追加する
   */
  #allocateSectors(index: number, needed: number): number {
    // 大きさが変わらないなら動かさない
    // 触っていないチャンクの配置を保つため
    if (this.#sectorCounts[index] === needed) {
      return this.#offsets[index];
    }

    const used = this.#buildSectorUsage(index);
    const totalSectors = this.#data.length / SECTOR_SIZE;
    let run = 0;

    // 先頭から連続した空き領域を探す
    for (let sector = HEADER_SECTORS; sector < totalSectors; sector++) {
      if (used[sector]) {
        run = 0;
        continue;
      }

      run += 1;

      if (run === needed) {
        return sector - needed + 1;
      }
    }

    // 見つからなければ末尾へ追加する
    // 末尾の空きは再利用できる
    const start = totalSectors - run;
    this.#resize((start + needed) * SECTOR_SIZE);
    return start;
  }

  /**
   * セクタの使用状況を作る
   * `ignoreIndex` のチャンクは空きとして扱う
   */
  #buildSectorUsage(ignoreIndex: number): boolean[] {
    const totalSectors = this.#data.length / SECTOR_SIZE;
    const used = new Array<boolean>(totalSectors).fill(false);

    // ヘッダの 2 セクタは常に使用中
    for (let sector = 0; sector < HEADER_SECTORS && sector < totalSectors; sector++) {
      used[sector] = true;
    }

    // 他のチャンクが占めているセクタに印を付ける
    for (let other = 0; other < CHUNK_COUNT; other++) {
      if (other === ignoreIndex || this.#sectorCounts[other] === 0) {
        continue;
      }

      const from = this.#offsets[other];

      // 他のチャンクが占めるセクタに印を付ける
      for (let sector = from; sector < from + this.#sectorCounts[other]; sector++) {
        if (sector < totalSectors) {
          used[sector] = true;
        }
      }
    }

    return used;
  }

  /**
   * 全チャンクを隙間なく詰め直す
   * 断片化したファイルを縮めたいときに使う
   */
  optimize(): void {
    this.#ensureOpen();
    this.#ensureWritable();

    const collected: Array<{ index: number; raw: RawChunk }> = [];

    // 先に全チャンクを取り出してから、新しい配置で書き直す
    for (let index = 0; index < CHUNK_COUNT; index++) {
      if (this.#sectorCounts[index] === 0) {
        continue;
      }

      const localX = index % 32;
      const localZ = Math.floor(index / 32);
      const raw = this.readChunkRaw(this.regionX * 32 + localX, this.regionZ * 32 + localZ);

      if (raw !== undefined) {
        collected.push({ index, raw });
      }
    }

    const savedTimestamps = this.#timestamps.slice();
    this.#data = new Uint8Array(HEADER_SECTORS * SECTOR_SIZE);
    this.#offsets.fill(0);
    this.#sectorCounts.fill(0);

    let nextSector = HEADER_SECTORS;

    // 添字の昇順に、先頭から詰めて配置する
    for (const { index, raw } of collected) {
      let payload: Uint8Array;
      let schemeByte: number;

      if (raw.external) {
        payload = new Uint8Array(0);
        schemeByte = raw.compression | 0x80;
      } else {
        payload = raw.data;
        schemeByte = raw.compression;
      }

      const needed = Math.ceil((4 + 1 + payload.length) / SECTOR_SIZE);
      this.#resize((nextSector + needed) * SECTOR_SIZE);

      const position = nextSector * SECTOR_SIZE;
      this.#writeUnsigned(position, 1 + payload.length, 4);
      this.#data[position + 4] = schemeByte;
      this.#data.set(payload, position + 5);

      this.#offsets[index] = nextSector;
      this.#sectorCounts[index] = needed;
      nextSector += needed;
    }

    this.#timestamps.set(savedTimestamps);
    this.#dirty = true;
  }

  /** 変更をファイルへ書き出す */
  flush(): void {
    this.#ensureOpen();

    if (this.#mode === RegionFileMode.ReadOnly) {
      return;
    }

    this.#writeHeader();

    try {
      writeFileSync(this.#path, this.#data);
    } catch (error) {
      throw new SpringNbtError(ErrorCode.Io, `ファイルへ書けない: ${this.#path}`, { cause: error });
    }

    this.#dirty = false;
  }

  /**
   * 現在の内容をバイト列として組み立てる
   * ファイルには書かない
   */
  toBytes(): Uint8Array {
    this.#ensureOpen();
    this.#writeHeader();
    return this.#data.slice();
  }

  /** ロケーションテーブルとタイムスタンプテーブルを先頭 2 セクタへ書き戻す */
  #writeHeader(): void {
    // 位置表とタイムスタンプ表を、添字順に組み立て直す
    for (let index = 0; index < CHUNK_COUNT; index++) {
      this.#writeUnsigned(index * 4, this.#offsets[index] * 256 + this.#sectorCounts[index], 4);
      this.#writeUnsigned(SECTOR_SIZE + index * 4, this.#timestamps[index] >>> 0, 4);
    }
  }

  /** 変更があれば書き出してから閉じる */
  close(): void {
    if (this.#closed) {
      return;
    }

    if (this.#dirty && this.#mode === RegionFileMode.ReadWrite) {
      this.flush();
    }

    this.#closed = true;
  }

  // -- バイト操作 ---------------------------------------------------------

  #resize(length: number): void {
    if (this.#data.length >= length) {
      return;
    }

    const grown = new Uint8Array(length);
    grown.set(this.#data);
    this.#data = grown;
  }

  /** 指定位置からビッグエンディアンで読む */
  #readUnsigned(position: number, count: number): number {
    let value = 0;

    // 上位バイトから順に積み上げる
    for (let offset = 0; offset < count; offset++) {
      value = value * 256 + this.#data[position + offset];
    }

    return value;
  }

  /** 指定位置へビッグエンディアンで書く */
  #writeUnsigned(position: number, value: number, count: number): void {
    let remaining = value >>> 0;

    // 下位バイトから詰めていく
    for (let offset = count - 1; offset >= 0; offset--) {
      this.#data[position + offset] = remaining & 0xff;
      remaining = Math.floor(remaining / 256);
    }
  }

  // -- 外部ファイル (.mcc) ------------------------------------------------

  #externalPath(chunkX: number, chunkZ: number): string {
    return join(this.#directory, `c.${chunkX}.${chunkZ}.mcc`);
  }

  #readExternalFile(chunkX: number, chunkZ: number): Uint8Array {
    const external = this.#externalPath(chunkX, chunkZ);

    if (!existsSync(external)) {
      throw new SpringNbtError(ErrorCode.MalformedData, `外部チャンクファイルが無い: ${external}`);
    }

    try {
      return new Uint8Array(readFileSync(external));
    } catch (error) {
      throw new SpringNbtError(ErrorCode.Io, `外部チャンクファイルを読めない: ${external}`, {
        cause: error,
      });
    }
  }

  #writeExternalFile(chunkX: number, chunkZ: number, payload: Uint8Array): void {
    const external = this.#externalPath(chunkX, chunkZ);

    try {
      writeFileSync(external, payload);
    } catch (error) {
      throw new SpringNbtError(ErrorCode.Io, `外部チャンクファイルへ書けない: ${external}`, {
        cause: error,
      });
    }
  }

  #deleteExternalFile(chunkX: number, chunkZ: number): void {
    const external = this.#externalPath(chunkX, chunkZ);

    // 縮んで内部へ戻ったチャンクの残骸を消す
    if (existsSync(external)) {
      try {
        rmSync(external);
      } catch (error) {
        throw new SpringNbtError(
          ErrorCode.Io,
          `外部チャンクファイルを削除できない: ${external}`,
          { cause: error },
        );
      }
    }
  }
}

/** 圧縮済みペイロードを展開する */
function decompressChunk(raw: RawChunk): Uint8Array {
  if (raw.compression === ChunkCompression.None) {
    return raw.data;
  }

  if (raw.compression === ChunkCompression.Gzip || raw.compression === ChunkCompression.Zlib) {
    try {
      if (raw.compression === ChunkCompression.Gzip) {
        return new Uint8Array(gunzipSync(raw.data));
      }

      return new Uint8Array(inflateSync(raw.data));
    } catch (error) {
      throw new SpringNbtError(ErrorCode.MalformedData, "チャンクの圧縮データを展開できない", {
        cause: error,
      });
    }
  }

  throw SpringNbtError.unsupportedFeature(
    `${chunkCompressionAsString(raw.compression)} 圧縮のチャンクは扱えない。` +
      "生バイトAPI (readChunkRaw) を使うこと",
  );
}

/** ペイロードを指定の方式で圧縮する */
function compressChunk(plain: Uint8Array, compression: ChunkCompression): Uint8Array {
  if (compression === ChunkCompression.None) {
    return plain;
  }

  if (compression === ChunkCompression.Gzip) {
    return new Uint8Array(gzipSync(plain, { level: zlibConstants.Z_BEST_COMPRESSION }));
  }

  if (compression === ChunkCompression.Zlib) {
    return new Uint8Array(deflateSync(plain, { level: zlibConstants.Z_BEST_COMPRESSION }));
  }

  throw SpringNbtError.unsupportedFeature(
    `この圧縮方式では書き込めない: ${chunkCompressionAsString(compression)}`,
  );
}

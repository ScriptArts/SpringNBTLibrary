/**
 * NBT のファイル・バイト列からの読み書き。
 *
 * 仕様: `docs/spec/10-nbt-binary.md` 3章〜6章
 */

import { readFileSync, writeFileSync } from "node:fs";
import {
  deflateSync,
  gunzipSync,
  gzipSync,
  inflateSync,
  constants as zlibConstants,
} from "node:zlib";

import { ErrorCode, SpringNbtError } from "../errors.js";
import * as mutf8 from "./mutf8.js";
import {
  NbtByte,
  NbtByteArray,
  NbtCompound,
  NbtDouble,
  NbtFloat,
  NbtInt,
  NbtIntArray,
  NbtList,
  NbtLong,
  NbtLongArray,
  NbtShort,
  NbtString,
  NbtTag,
  TagType,
  tagTypeAsString,
  tagTypeFromId,
} from "./tag.js";

/** NBT のルートタグの並び方。 */
export enum NbtFormat {
  /** ファイル形式。ルートは「タグID + 名前長 + 名前 + ペイロード」の順に並ぶ。 */
  Java = "java",
  /** ネットワーク形式 (1.20.2 以降)。ルートに名前が付かない。 */
  Network = "network",
}

/** 圧縮方式。 */
export enum Compression {
  /** 無圧縮。 */
  None = "none",
  /** GZip (RFC 1952)。 */
  Gzip = "gzip",
  /** Zlib (RFC 1950)。 */
  Zlib = "zlib",
  /** 先頭バイトから自動判定する。読み込み時のみ指定できる。 */
  Auto = "auto",
}

/** ルート名とルートタグの組。 */
export class NamedTag {
  constructor(
    readonly name: string,
    readonly tag: NbtCompound,
  ) {}
}

/** NBT 読み込みのオプション。 */
export interface NbtReadOptions {
  /** ルートタグの並び方。既定は {@link NbtFormat.Java}。 */
  format?: NbtFormat;
  /** 圧縮方式。既定は {@link Compression.Auto}。 */
  compression?: Compression;
  /** ネストの深さ上限。既定は 512。 */
  maxDepth?: number;
  /** 展開後の総バイト数の上限。負値なら無制限。既定は -1。 */
  maxDecompressedSize?: number;
}

/** NBT 書き込みのオプション。 */
export interface NbtWriteOptions {
  /** ルートタグの並び方。既定は {@link NbtFormat.Java}。 */
  format?: NbtFormat;
  /** 圧縮方式。既定は {@link Compression.Gzip}。 */
  compression?: Compression;
}

const DEFAULT_MAX_DEPTH = 512;

// ---------------------------------------------------------------------------
// 読み込み
// ---------------------------------------------------------------------------

/**
 * 展開済みのバイト列から NBT を読み出す。
 *
 * 入力全体をあらかじめメモリに持つ設計にしている。
 * 「宣言された長さが残り入力長を超えていないか」を確保前に検査できるようにするため。
 */
class Reader {
  readonly #data: Uint8Array;
  readonly #view: DataView;
  readonly #maxDepth: number;
  #position = 0;

  constructor(data: Uint8Array, maxDepth: number) {
    this.#data = data;
    this.#view = new DataView(data.buffer, data.byteOffset, data.byteLength);
    this.#maxDepth = maxDepth;
  }

  get #remaining(): number {
    return this.#data.length - this.#position;
  }

  /** ルートタグを 1 つ読む。形式によって名前の有無が変わる。 */
  readRoot(format: NbtFormat): NamedTag {
    const type = tagTypeFromId(this.#readByte());

    // Java版のファイル形式でもネットワーク形式でも、ルートは必ず TAG_Compound
    if (type !== TagType.Compound) {
      throw SpringNbtError.malformed(
        `ルートタグは compound でなければならないが ${tagTypeAsString(type)} だった`,
      );
    }

    let name: string;
    if (format === NbtFormat.Java) {
      // ファイル形式のルートには名前が付く（通常は空文字列）
      name = requireUtf8Representable(this.#readString(), "ルート名");
    } else {
      // ネットワーク形式 (1.20.2+) のルートに名前は無い
      name = "";
    }

    const root = this.#readCompoundPayload(1);

    // 末尾に余分なバイトが残っていたら、読み違えている可能性が高い
    if (this.#remaining !== 0) {
      throw SpringNbtError.malformed(
        `ルートタグの後に ${this.#remaining} バイトの余分な入力がある`,
      );
    }

    return new NamedTag(name, root);
  }

  #readPayload(type: TagType, depth: number): NbtTag {
    // 深さ上限は再帰する型に入る手前で検査する
    if (depth > this.#maxDepth) {
      throw SpringNbtError.limitExceeded(`ネストが深すぎる (上限 ${this.#maxDepth})`);
    }

    switch (type) {
      case TagType.Byte:
        return new NbtByte(this.#take(1, (offset) => this.#view.getInt8(offset)));
      case TagType.Short:
        return new NbtShort(this.#take(2, (offset) => this.#view.getInt16(offset, false)));
      case TagType.Int:
        return new NbtInt(this.#take(4, (offset) => this.#view.getInt32(offset, false)));
      case TagType.Long:
        return new NbtLong(this.#take(8, (offset) => this.#view.getBigInt64(offset, false)));
      case TagType.Float:
        return new NbtFloat(this.#take(4, (offset) => this.#view.getFloat32(offset, false)));
      case TagType.Double:
        return new NbtDouble(this.#take(8, (offset) => this.#view.getFloat64(offset, false)));
      case TagType.ByteArray:
        return new NbtByteArray(this.#readByteArrayPayload());
      case TagType.String:
        return new NbtString(this.#readString());
      case TagType.List:
        return this.#readListPayload(depth);
      case TagType.Compound:
        return this.#readCompoundPayload(depth);
      case TagType.IntArray:
        return new NbtIntArray(this.#readIntArrayPayload());
      case TagType.LongArray:
        return new NbtLongArray(this.#readLongArrayPayload());
      default:
        throw SpringNbtError.malformed("TAG_End のペイロードを読もうとした");
    }
  }

  #readCompoundPayload(depth: number): NbtCompound {
    const compound = new NbtCompound();

    // TAG_End が現れるまで名前付きタグを読み続ける
    for (;;) {
      const type = tagTypeFromId(this.#readByte());

      if (type === TagType.End) {
        return compound;
      }

      const name = requireUtf8Representable(this.#readString(), "Compound のキー");
      compound.set(name, this.#readPayload(type, depth + 1));
    }
  }

  #readListPayload(depth: number): NbtList {
    const elementType = tagTypeFromId(this.#readByte());
    const count = this.#readLength();

    if (elementType === TagType.End) {
      // 要素型 End のリストは空でなければならない
      if (count !== 0) {
        throw SpringNbtError.malformed(`要素型 End のリストに ${count} 個の要素が宣言されている`);
      }

      return new NbtList(TagType.End);
    }

    // 1 要素の最小バイト数から、宣言された個数が入力に収まるかを先に検査する
    this.#ensureAvailable(count * minimumPayloadSize(elementType));

    const list = new NbtList(elementType);

    // 宣言された個数だけペイロードを読む
    for (let index = 0; index < count; index++) {
      list.add(this.#readPayload(elementType, depth + 1));
    }

    return list;
  }

  #readByteArrayPayload(): Int8Array {
    const count = this.#readLength();
    this.#ensureAvailable(count);

    const result = new Int8Array(count);

    // バイト単位でそのまま写す
    for (let index = 0; index < count; index++) {
      result[index] = this.#view.getInt8(this.#position + index);
    }

    this.#position += count;
    return result;
  }

  #readIntArrayPayload(): Int32Array {
    const count = this.#readLength();
    this.#ensureAvailable(count * 4);

    const result = new Int32Array(count);

    // 4 バイトずつビッグエンディアンで読む
    for (let index = 0; index < count; index++) {
      result[index] = this.#view.getInt32(this.#position + index * 4, false);
    }

    this.#position += count * 4;
    return result;
  }

  #readLongArrayPayload(): BigInt64Array {
    const count = this.#readLength();
    this.#ensureAvailable(count * 8);

    const result = new BigInt64Array(count);

    // 8 バイトずつビッグエンディアンで読む
    for (let index = 0; index < count; index++) {
      result[index] = this.#view.getBigInt64(this.#position + index * 8, false);
    }

    this.#position += count * 8;
    return result;
  }

  /** MUTF-8 の文字列（u16 の長さ + 本体）を読む。 */
  #readString(): string {
    const length = this.#take(2, (offset) => this.#view.getUint16(offset, false));
    this.#ensureAvailable(length);

    const text = mutf8.decode(this.#data, this.#position, length);
    this.#position += length;
    return text;
  }

  /** 配列・リストの長さフィールドを読む。負値は不正。 */
  #readLength(): number {
    const length = this.#take(4, (offset) => this.#view.getInt32(offset, false));

    // 長さは i32 だが、負値は仕様上ありえない
    if (length < 0) {
      throw SpringNbtError.malformed(`長さが負値: ${length}`);
    }

    return length;
  }

  #readByte(): number {
    this.#ensureAvailable(1);
    const value = this.#data[this.#position];
    this.#position += 1;
    return value;
  }

  /** 指定バイト数を読み進めて値を取り出す。 */
  #take<T>(count: number, read: (offset: number) => T): T {
    this.#ensureAvailable(count);
    const value = read(this.#position);
    this.#position += count;
    return value;
  }

  /** 残り入力が必要バイト数を満たすか検査する。メモリを確保する前に呼ぶ。 */
  #ensureAvailable(required: number): void {
    if (required > this.#remaining) {
      throw SpringNbtError.malformed(
        `入力が足りない: ${required} バイト必要だが残り ${this.#remaining} バイト`,
      );
    }
  }
}

/** その型のペイロードが最低何バイトになるかを返す。長さの先行検証に使う。 */
function minimumPayloadSize(type: TagType): number {
  switch (type) {
    case TagType.Byte:
      return 1;
    case TagType.Short:
      return 2;
    case TagType.Int:
    case TagType.Float:
      return 4;
    case TagType.Long:
    case TagType.Double:
      return 8;
    // 長さフィールドの 4 バイトは必ずある
    case TagType.ByteArray:
    case TagType.IntArray:
    case TagType.LongArray:
      return 4;
    // 長さフィールドの 2 バイトは必ずある
    case TagType.String:
      return 2;
    // 要素型 1 バイト + 個数 4 バイト
    case TagType.List:
      return 5;
    // 終端の TAG_End 1 バイトは必ずある
    default:
      return 1;
  }
}

/**
 * キーやルート名として使える文字列か検査する。
 *
 * 値と違い、キーには孤立サロゲートを許さない（仕様 10 の 2.2章）。
 * Minecraft が書き出すキーは ASCII の識別子のみで、
 * 孤立サロゲートが現れるのはデータ破損を意味する。
 */
function requireUtf8Representable(text: string, role: string): string {
  // 対にならないサロゲートが含まれていないか調べる
  for (let index = 0; index < text.length; index++) {
    const unit = text.charCodeAt(index);

    if (unit >= 0xd800 && unit <= 0xdbff) {
      let next = 0;

      if (index + 1 < text.length) {
        next = text.charCodeAt(index + 1);
      }

      if (next >= 0xdc00 && next <= 0xdfff) {
        index += 1;
      } else {
        throw SpringNbtError.malformed(`${role}が UTF-8 に写せない（孤立サロゲートを含む）`);
      }
    } else if (unit >= 0xdc00 && unit <= 0xdfff) {
      throw SpringNbtError.malformed(`${role}が UTF-8 に写せない（孤立サロゲートを含む）`);
    }
  }

  return text;
}

// ---------------------------------------------------------------------------
// 書き込み
// ---------------------------------------------------------------------------

/**
 * NBT を展開済みのバイト列へ書き出す。
 *
 * 出力は一意でなければならない（ラウンドトリップ検証が成立するため）。
 * Compound は挿入順のまま、浮動小数点はビットパターンのまま書き出す。
 */
class Writer {
  #chunks: Uint8Array[] = [];
  #scratch = new DataView(new ArrayBuffer(8));

  /** ルートタグを 1 つ書き出す。形式によって名前の有無が変わる。 */
  writeRoot(named: NamedTag, format: NbtFormat): Uint8Array {
    this.#pushByte(TagType.Compound);

    if (format === NbtFormat.Java) {
      // ファイル形式のルートには名前が付く
      this.#writeString(named.name);
    }

    this.#writeCompoundPayload(named.tag);
    return this.#concat();
  }

  #writePayload(tag: NbtTag): void {
    switch (tag.type) {
      case TagType.Byte:
        this.#pushByte(tag.value & 0xff);
        break;
      case TagType.Short:
        this.#writeScalar(2, (view) => view.setInt16(0, tag.value, false));
        break;
      case TagType.Int:
        this.#writeScalar(4, (view) => view.setInt32(0, tag.value, false));
        break;
      case TagType.Long:
        this.#writeScalar(8, (view) => view.setBigInt64(0, tag.value, false));
        break;
      case TagType.Float:
        // NaN や -0.0 を保つため、そのまま書く
        this.#writeScalar(4, (view) => view.setFloat32(0, tag.value, false));
        break;
      case TagType.Double:
        this.#writeScalar(8, (view) => view.setFloat64(0, tag.value, false));
        break;
      case TagType.ByteArray:
        this.#writeScalar(4, (view) => view.setInt32(0, tag.value.length, false));
        this.#chunks.push(new Uint8Array(tag.value.buffer.slice(tag.value.byteOffset, tag.value.byteOffset + tag.value.byteLength)));
        break;
      case TagType.String:
        this.#writeString(tag.value);
        break;
      case TagType.List:
        this.#writeListPayload(tag);
        break;
      case TagType.Compound:
        this.#writeCompoundPayload(tag);
        break;
      case TagType.IntArray:
        this.#writeScalar(4, (view) => view.setInt32(0, tag.value.length, false));

        // 4 バイトずつビッグエンディアンで書く
        for (const value of tag.value) {
          this.#writeScalar(4, (view) => view.setInt32(0, value, false));
        }

        break;
      case TagType.LongArray:
        this.#writeScalar(4, (view) => view.setInt32(0, tag.value.length, false));

        // 8 バイトずつビッグエンディアンで書く
        for (const value of tag.value) {
          this.#writeScalar(8, (view) => view.setBigInt64(0, value, false));
        }

        break;
      default:
        throw SpringNbtError.malformed("書き出せないタグ");
    }
  }

  #writeCompoundPayload(compound: NbtCompound): void {
    // 挿入順のまま「タグID + 名前 + ペイロード」を並べる
    for (const [key, value] of compound.entries()) {
      this.#pushByte(value.type);
      this.#writeString(key);
      this.#writePayload(value);
    }

    this.#pushByte(TagType.End);
  }

  #writeListPayload(list: NbtList): void {
    this.#pushByte(list.elementType);
    this.#writeScalar(4, (view) => view.setInt32(0, list.size, false));

    // 要素型は共通なので、ペイロードだけを並べる
    for (const item of list) {
      this.#writePayload(item);
    }
  }

  #writeString(text: string): void {
    const encoded = mutf8.encode(text);

    // 長さフィールドは u16。キー名は素の string なのでここでも検査する
    if (encoded.length > mutf8.MAX_BYTE_LENGTH) {
      throw SpringNbtError.invalidArgument(
        `文字列が長すぎる: MUTF-8 で ${encoded.length} バイト (上限 ${mutf8.MAX_BYTE_LENGTH})`,
      );
    }

    this.#writeScalar(2, (view) => view.setUint16(0, encoded.length, false));
    this.#chunks.push(encoded);
  }

  #writeScalar(size: number, write: (view: DataView) => void): void {
    write(this.#scratch);
    this.#chunks.push(new Uint8Array(this.#scratch.buffer.slice(0, size)));
  }

  #pushByte(value: number): void {
    this.#chunks.push(Uint8Array.of(value));
  }

  #concat(): Uint8Array {
    let total = 0;

    // 先に全体長を数えてから 1 回で確保する
    for (const chunk of this.#chunks) {
      total += chunk.length;
    }

    const result = new Uint8Array(total);
    let offset = 0;

    for (const chunk of this.#chunks) {
      result.set(chunk, offset);
      offset += chunk.length;
    }

    return result;
  }
}

// ---------------------------------------------------------------------------
// 圧縮
// ---------------------------------------------------------------------------

/**
 * 先頭バイトから圧縮方式を判定する。
 *
 * @throws {SpringNbtError} どの方式とも判定できない場合
 */
export function detectCompression(bytes: Uint8Array): Compression {
  if (bytes.length === 0) {
    throw SpringNbtError.malformed("入力が空で圧縮方式を判定できない");
  }

  // GZip は必ず 1F 8B で始まる
  if (bytes.length >= 2 && bytes[0] === 0x1f && bytes[1] === 0x8b) {
    return Compression.Gzip;
  }

  if (bytes.length >= 2) {
    // zlib ヘッダは「圧縮法が 8 (deflate)」かつ「先頭2バイトが 31 の倍数」
    const isDeflate = (bytes[0] & 0x0f) === 0x08;
    const header = (bytes[0] << 8) | bytes[1];

    if (isDeflate && header % 31 === 0) {
      return Compression.Zlib;
    }
  }

  // 無圧縮なら先頭は TAG_Compound のタグID
  if (bytes[0] === TagType.Compound) {
    return Compression.None;
  }

  throw SpringNbtError.malformed(
    `圧縮方式を判定できない (先頭バイト 0x${bytes[0].toString(16).toUpperCase().padStart(2, "0")})`,
  );
}

function decompress(bytes: Uint8Array, options: Required<NbtReadOptions>): Uint8Array {
  let method: Compression;
  if (options.compression === Compression.Auto) {
    method = detectCompression(bytes);
  } else {
    method = options.compression;
  }

  if (method === Compression.None) {
    return bytes;
  }

  let plain: Uint8Array;
  try {
    if (method === Compression.Gzip) {
      plain = new Uint8Array(gunzipSync(bytes));
    } else if (method === Compression.Zlib) {
      plain = new Uint8Array(inflateSync(bytes));
    } else {
      throw SpringNbtError.invalidArgument(`展開できない圧縮方式: ${method}`);
    }
  } catch (error) {
    if (error instanceof SpringNbtError) {
      throw error;
    }

    throw new SpringNbtError(ErrorCode.MalformedData, "圧縮データを展開できない", { cause: error });
  }

  // 展開後のサイズ上限を確認する
  if (options.maxDecompressedSize >= 0 && plain.length > options.maxDecompressedSize) {
    throw SpringNbtError.limitExceeded(
      `展開後のサイズが上限 ${options.maxDecompressedSize} バイトを超えた`,
    );
  }

  return plain;
}

function compress(plain: Uint8Array, method: Compression): Uint8Array {
  if (method === Compression.None) {
    return plain;
  }

  if (method === Compression.Gzip) {
    return new Uint8Array(gzipSync(plain, { level: zlibConstants.Z_BEST_COMPRESSION }));
  }

  if (method === Compression.Zlib) {
    return new Uint8Array(deflateSync(plain, { level: zlibConstants.Z_BEST_COMPRESSION }));
  }

  throw SpringNbtError.invalidArgument(`圧縮できない方式: ${method}`);
}

// ---------------------------------------------------------------------------
// 公開 API
// ---------------------------------------------------------------------------

/** 省略された項目を既定値で埋める。 */
function fillReadOptions(options?: NbtReadOptions): Required<NbtReadOptions> {
  const filled: Required<NbtReadOptions> = {
    format: NbtFormat.Java,
    compression: Compression.Auto,
    maxDepth: DEFAULT_MAX_DEPTH,
    maxDecompressedSize: -1,
  };

  if (options === undefined) {
    return filled;
  }

  // 指定された項目だけを上書きする
  if (options.format !== undefined) {
    filled.format = options.format;
  }

  if (options.compression !== undefined) {
    filled.compression = options.compression;
  }

  if (options.maxDepth !== undefined) {
    filled.maxDepth = options.maxDepth;
  }

  if (options.maxDecompressedSize !== undefined) {
    filled.maxDecompressedSize = options.maxDecompressedSize;
  }

  return filled;
}

/** 省略された項目を既定値で埋める。 */
function fillWriteOptions(options?: NbtWriteOptions): Required<NbtWriteOptions> {
  const filled: Required<NbtWriteOptions> = {
    format: NbtFormat.Java,
    compression: Compression.Gzip,
  };

  if (options === undefined) {
    return filled;
  }

  // 指定された項目だけを上書きする
  if (options.format !== undefined) {
    filled.format = options.format;
  }

  if (options.compression !== undefined) {
    filled.compression = options.compression;
  }

  return filled;
}

/** バイト列から NBT を読む。 */
export function readBytes(bytes: Uint8Array, options?: NbtReadOptions): NamedTag {
  const effective = fillReadOptions(options);
  const plain = decompress(bytes, effective);
  return new Reader(plain, effective.maxDepth).readRoot(effective.format);
}

/** ファイルから NBT を読む。 */
export function readFile(path: string, options?: NbtReadOptions): NamedTag {
  let raw: Uint8Array;

  try {
    raw = new Uint8Array(readFileSync(path));
  } catch (error) {
    // 下位の入出力エラーは情報を失わないよう原因として保持する
    throw new SpringNbtError(ErrorCode.Io, `ファイルを読めない: ${path}`, { cause: error });
  }

  return readBytes(raw, options);
}

/** NBT をバイト列へ書き出す。 */
export function writeBytes(named: NamedTag, options?: NbtWriteOptions): Uint8Array {
  const effective = fillWriteOptions(options);

  // 書き込み時に Auto は決められない
  if (effective.compression === Compression.Auto) {
    throw SpringNbtError.invalidArgument("書き込みで Compression.Auto は指定できない");
  }

  const plain = new Writer().writeRoot(named, effective.format);
  return compress(plain, effective.compression);
}

/** NBT をファイルへ書き出す。 */
export function writeFile(path: string, named: NamedTag, options?: NbtWriteOptions): void {
  const bytes = writeBytes(named, options);

  try {
    writeFileSync(path, bytes);
  } catch (error) {
    throw new SpringNbtError(ErrorCode.Io, `ファイルへ書けない: ${path}`, { cause: error });
  }
}

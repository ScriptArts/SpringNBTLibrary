/**
 * NBT のタグ型と値モデル。
 *
 * 仕様: `docs/spec/10-nbt-binary.md` 1章・7章
 */

import { SpringNbtError } from "../errors.js";
import * as mutf8 from "./mutf8.js";

/** NBT のタグ型。値は仕様が定めるタグIDと一致する。 */
export enum TagType {
  /** TAG_End (0)。Compound の終端を表す。 */
  End = 0,
  /** TAG_Byte (1)。 */
  Byte = 1,
  /** TAG_Short (2)。 */
  Short = 2,
  /** TAG_Int (3)。 */
  Int = 3,
  /** TAG_Long (4)。 */
  Long = 4,
  /** TAG_Float (5)。 */
  Float = 5,
  /** TAG_Double (6)。 */
  Double = 6,
  /** TAG_Byte_Array (7)。 */
  ByteArray = 7,
  /** TAG_String (8)。 */
  String = 8,
  /** TAG_List (9)。 */
  List = 9,
  /** TAG_Compound (10)。 */
  Compound = 10,
  /** TAG_Int_Array (11)。 */
  IntArray = 11,
  /** TAG_Long_Array (12)。 */
  LongArray = 12,
}

const TAG_TYPE_LABELS: Record<TagType, string> = {
  [TagType.End]: "end",
  [TagType.Byte]: "byte",
  [TagType.Short]: "short",
  [TagType.Int]: "int",
  [TagType.Long]: "long",
  [TagType.Float]: "float",
  [TagType.Double]: "double",
  [TagType.ByteArray]: "byte_array",
  [TagType.String]: "string",
  [TagType.List]: "list",
  [TagType.Compound]: "compound",
  [TagType.IntArray]: "int_array",
  [TagType.LongArray]: "long_array",
};

/** 適合性テストで言語間比較に使う識別子を返す。 */
export function tagTypeAsString(type: TagType): string {
  return TAG_TYPE_LABELS[type];
}

/**
 * タグIDから {@link TagType} を得る。
 *
 * @throws {SpringNbtError} 未知のタグIDの場合
 */
export function tagTypeFromId(id: number): TagType {
  // 0..12 の範囲外はすべて不正なタグID
  if (id < 0 || id > TagType.LongArray) {
    throw SpringNbtError.malformed(`未知のタグID: ${id}`);
  }

  return id as TagType;
}

/**
 * Number 型で保持する整数の範囲を検査する。
 *
 * JavaScript の number は倍精度なので、i32 までは正確に扱えるが幅の情報を持たない。
 * 構築時に検査しておかないと、書き出しで黙って切り詰められる。
 */
function checkRange(value: number, minimum: number, maximum: number, typeName: string): number {
  if (!Number.isInteger(value)) {
    throw SpringNbtError.invalidArgument(`${typeName} には整数を渡すこと: ${value}`);
  }

  if (value < minimum || value > maximum) {
    throw SpringNbtError.invalidArgument(
      `${typeName} の範囲外: ${value} (範囲 ${minimum}..${maximum})`,
    );
  }

  return value;
}

/** TAG_Byte。8bit 符号付き整数。 */
export class NbtByte {
  readonly type = TagType.Byte as const;
  #value: number;

  constructor(value: number) {
    this.#value = checkRange(value, -128, 127, "byte");
  }

  /** 保持している値。 */
  get value(): number {
    return this.#value;
  }

  /** 値を差し替える。範囲外なら INVALID_ARGUMENT。 */
  set value(newValue: number) {
    this.#value = checkRange(newValue, -128, 127, "byte");
  }

  /** このタグの深いコピーを作る。 */
  copy(): NbtByte {
    return new NbtByte(this.#value);
  }
}

/** TAG_Short。16bit 符号付き整数。 */
export class NbtShort {
  readonly type = TagType.Short as const;
  #value: number;

  constructor(value: number) {
    this.#value = checkRange(value, -32768, 32767, "short");
  }

  /** 保持している値。 */
  get value(): number {
    return this.#value;
  }

  /** 値を差し替える。範囲外なら INVALID_ARGUMENT。 */
  set value(newValue: number) {
    this.#value = checkRange(newValue, -32768, 32767, "short");
  }

  /** このタグの深いコピーを作る。 */
  copy(): NbtShort {
    return new NbtShort(this.#value);
  }
}

/** TAG_Int。32bit 符号付き整数。 */
export class NbtInt {
  readonly type = TagType.Int as const;
  #value: number;

  constructor(value: number) {
    this.#value = checkRange(value, -2147483648, 2147483647, "int");
  }

  /** 保持している値。 */
  get value(): number {
    return this.#value;
  }

  /** 値を差し替える。範囲外なら INVALID_ARGUMENT。 */
  set value(newValue: number) {
    this.#value = checkRange(newValue, -2147483648, 2147483647, "int");
  }

  /** このタグの深いコピーを作る。 */
  copy(): NbtInt {
    return new NbtInt(this.#value);
  }
}

const LONG_MIN = -9223372036854775808n;
const LONG_MAX = 9223372036854775807n;

/**
 * TAG_Long。64bit 符号付き整数。
 *
 * 値は `bigint` で保持する。JavaScript の `number` は倍精度なので、
 * 2^53 を超える整数を正確に表せず、そのまま使うとワールドのシード値などが壊れる。
 */
export class NbtLong {
  readonly type = TagType.Long as const;
  #value: bigint;

  constructor(value: bigint) {
    this.#value = NbtLong.#check(value);
  }

  /** 保持している値。 */
  get value(): bigint {
    return this.#value;
  }

  /** 値を差し替える。範囲外なら INVALID_ARGUMENT。 */
  set value(newValue: bigint) {
    this.#value = NbtLong.#check(newValue);
  }

  /** このタグの深いコピーを作る。 */
  copy(): NbtLong {
    return new NbtLong(this.#value);
  }

  static #check(value: bigint): bigint {
    if (typeof value !== "bigint") {
      throw SpringNbtError.invalidArgument(`long には bigint を渡すこと: ${String(value)}`);
    }

    if (value < LONG_MIN || value > LONG_MAX) {
      throw SpringNbtError.invalidArgument(`long の範囲外: ${value}`);
    }

    return value;
  }
}

/** TAG_Float。IEEE 754 binary32。 */
export class NbtFloat {
  readonly type = TagType.Float as const;
  #value: number;

  constructor(value: number) {
    // 他言語と同じ値になるよう、構築時に binary32 へ丸める
    this.#value = Math.fround(value);
  }

  /** 保持している値。 */
  get value(): number {
    return this.#value;
  }

  /** 値を差し替える。範囲外なら INVALID_ARGUMENT。 */
  set value(newValue: number) {
    this.#value = Math.fround(newValue);
  }

  /** このタグの深いコピーを作る。 */
  copy(): NbtFloat {
    return new NbtFloat(this.#value);
  }
}

/** TAG_Double。IEEE 754 binary64。 */
export class NbtDouble {
  readonly type = TagType.Double as const;

  constructor(public value: number) {}

  /** このタグの深いコピーを作る。 */
  copy(): NbtDouble {
    return new NbtDouble(this.value);
  }
}

/** TAG_String。MUTF-8 で符号化される文字列。 */
export class NbtString {
  readonly type = TagType.String as const;
  #value: string;

  constructor(value: string) {
    this.#value = NbtString.#check(value);
  }

  /** 保持している値。 */
  get value(): string {
    return this.#value;
  }

  /** 値を差し替える。範囲外なら INVALID_ARGUMENT。 */
  set value(newValue: string) {
    this.#value = NbtString.#check(newValue);
  }

  /** このタグの深いコピーを作る。 */
  copy(): NbtString {
    return new NbtString(this.#value);
  }

  static #check(value: string): string {
    const length = mutf8.byteLength(value);

    // 長さフィールドは u16。65535 を超えると書き出せない
    if (length > mutf8.MAX_BYTE_LENGTH) {
      throw SpringNbtError.invalidArgument(
        `文字列が長すぎる: MUTF-8 で ${length} バイト (上限 ${mutf8.MAX_BYTE_LENGTH})`,
      );
    }

    return value;
  }
}

/** TAG_Byte_Array。8bit 符号付き整数の配列。 */
export class NbtByteArray {
  readonly type = TagType.ByteArray as const;

  constructor(public value: Int8Array) {}

  /** このタグの深いコピーを作る。 */
  copy(): NbtByteArray {
    return new NbtByteArray(this.value.slice());
  }
}

/** TAG_Int_Array。32bit 符号付き整数の配列。 */
export class NbtIntArray {
  readonly type = TagType.IntArray as const;

  constructor(public value: Int32Array) {}

  /** このタグの深いコピーを作る。 */
  copy(): NbtIntArray {
    return new NbtIntArray(this.value.slice());
  }
}

/** TAG_Long_Array。64bit 符号付き整数の配列。 */
export class NbtLongArray {
  readonly type = TagType.LongArray as const;

  constructor(public value: BigInt64Array) {}

  /** このタグの深いコピーを作る。 */
  copy(): NbtLongArray {
    return new NbtLongArray(this.value.slice());
  }
}

/**
 * TAG_List。要素型が 1 つに固定されたタグの列。
 *
 * 空リストの要素型は {@link TagType.End}。最初の要素を追加した時点で型が確定する。
 * 全要素を削除しても確定済みの要素型は維持される
 * （読み書きの往復で型が消えないようにするため）。
 */
export class NbtList {
  readonly type = TagType.List as const;
  #elementType: TagType;
  #items: NbtTag[] = [];

  constructor(elementType: TagType = TagType.End, elements?: Iterable<NbtTag>) {
    this.#elementType = elementType;

    // 与えられた要素は 1 つずつ型検査しながら追加する
    if (elements !== undefined) {
      for (const element of elements) {
        this.add(element);
      }
    }
  }

  /** 要素の型。空で未確定なら {@link TagType.End}。 */
  get elementType(): TagType {
    return this.#elementType;
  }

  /** 要素数。 */
  get size(): number {
    return this.#items.length;
  }

  /** 位置を指定して取り出す。 */
  get(index: number): NbtTag {
    return this.#items[index];
  }

  /** 位置を指定して置き換える。 */
  set(index: number, item: NbtTag): void {
    this.#ensureElementType(item);
    this.#items[index] = item;
  }

  /** 末尾に追加する。 */
  add(item: NbtTag): void {
    this.#ensureElementType(item);
    this.#items.push(item);
  }

  /** 位置を指定して挿入する。 */
  insert(index: number, item: NbtTag): void {
    this.#ensureElementType(item);
    this.#items.splice(index, 0, item);
  }

  /** 位置を指定して削除する。 */
  removeAt(index: number): void {
    this.#items.splice(index, 1);
  }

  /** 全要素を削除する。確定済みの要素型は維持する。 */
  clear(): void {
    this.#items.length = 0;
  }

  /** このタグの深いコピーを作る。 */
  copy(): NbtList {
    const result = new NbtList(this.#elementType);

    // 要素も深くコピーする
    for (const item of this.#items) {
      result.#items.push(item.copy());
    }

    return result;
  }

  [Symbol.iterator](): Iterator<NbtTag> {
    return this.#items[Symbol.iterator]();
  }

  /**
   * 追加しようとしているタグが要素型と一致するか調べる。
   * リストが未確定なら、そのタグの型で確定させる。
   */
  #ensureElementType(item: NbtTag): void {
    if (this.#elementType === TagType.End) {
      // 未確定のリストは最初の要素で型が決まる
      this.#elementType = item.type;
    } else if (this.#elementType !== item.type) {
      throw SpringNbtError.unexpectedTagType(
        `リストの要素型は ${tagTypeAsString(this.#elementType)} だが ` +
          `${tagTypeAsString(item.type)} を追加しようとした`,
      );
    }
  }
}

/**
 * TAG_Compound。挿入順を保持する、名前付きタグのマップ。
 *
 * 既存キーへの再設定は位置を維持したまま値だけを置き換える
 * （`Map` の既定の振る舞い）。
 */
export class NbtCompound {
  readonly type = TagType.Compound as const;
  #entries = new Map<string, NbtTag>();

  /** 要素数。 */
  get size(): number {
    return this.#entries.size;
  }

  /** 挿入順のキー一覧。 */
  keys(): IterableIterator<string> {
    return this.#entries.keys();
  }

  /** 挿入順の [キー, タグ] の並び。 */
  entries(): IterableIterator<[string, NbtTag]> {
    return this.#entries.entries();
  }

  /** キーが存在するか。 */
  containsKey(key: string): boolean {
    return this.#entries.has(key);
  }

  /** 値を設定する。既存キーなら位置を維持して値だけ置き換える。 */
  set(key: string, value: NbtTag): void {
    this.#entries.set(key, value);
  }

  /** キーに対応するタグを返す。存在しなければ undefined。 */
  opt(key: string): NbtTag | undefined {
    return this.#entries.get(key);
  }

  /** キーに対応するタグを返す。存在しなければ例外。 */
  get(key: string): NbtTag {
    const found = this.#entries.get(key);

    if (found === undefined) {
      throw SpringNbtError.invalidArgument(`キーが存在しない: ${key}`);
    }

    return found;
  }

  /** キーを削除する。削除できたら true。 */
  remove(key: string): boolean {
    return this.#entries.delete(key);
  }

  /** 全要素を削除する。 */
  clear(): void {
    this.#entries.clear();
  }

  /** このタグの深いコピーを作る。 */
  copy(): NbtCompound {
    const result = new NbtCompound();

    // 挿入順のまま深くコピーする
    for (const [key, value] of this.#entries) {
      result.set(key, value.copy());
    }

    return result;
  }

  [Symbol.iterator](): Iterator<[string, NbtTag]> {
    return this.#entries[Symbol.iterator]();
  }

  // -- 型付き取得子 -------------------------------------------------------
  //
  // 「キーが無い」と「型が違う」は区別する。
  // opt* はキーが無ければ undefined を返し、get* は例外を送出する。
  // どちらも型が違えば必ず UNEXPECTED_TAG_TYPE の例外になる。

  /** TAG_Byte を取得する。キーが無ければ undefined。 */
  optByte(key: string): number | undefined {
    return this.#optScalar(key, TagType.Byte) as number | undefined;
  }

  /** TAG_Byte を取得する。キーが無ければ例外。 */
  getByte(key: string): number {
    return this.#require(key, this.optByte(key)) as number;
  }

  /** TAG_Short を取得する。キーが無ければ undefined。 */
  optShort(key: string): number | undefined {
    return this.#optScalar(key, TagType.Short) as number | undefined;
  }

  /** TAG_Short を取得する。キーが無ければ例外。 */
  getShort(key: string): number {
    return this.#require(key, this.optShort(key)) as number;
  }

  /** TAG_Int を取得する。キーが無ければ undefined。 */
  optInt(key: string): number | undefined {
    return this.#optScalar(key, TagType.Int) as number | undefined;
  }

  /** TAG_Int を取得する。キーが無ければ例外。 */
  getInt(key: string): number {
    return this.#require(key, this.optInt(key)) as number;
  }

  /** TAG_Long を取得する。キーが無ければ undefined。 */
  optLong(key: string): bigint | undefined {
    return this.#optScalar(key, TagType.Long) as bigint | undefined;
  }

  /** TAG_Long を取得する。キーが無ければ例外。 */
  getLong(key: string): bigint {
    return this.#require(key, this.optLong(key)) as bigint;
  }

  /** TAG_Float を取得する。キーが無ければ undefined。 */
  optFloat(key: string): number | undefined {
    return this.#optScalar(key, TagType.Float) as number | undefined;
  }

  /** TAG_Float を取得する。キーが無ければ例外。 */
  getFloat(key: string): number {
    return this.#require(key, this.optFloat(key)) as number;
  }

  /** TAG_Double を取得する。キーが無ければ undefined。 */
  optDouble(key: string): number | undefined {
    return this.#optScalar(key, TagType.Double) as number | undefined;
  }

  /** TAG_Double を取得する。キーが無ければ例外。 */
  getDouble(key: string): number {
    return this.#require(key, this.optDouble(key)) as number;
  }

  /** TAG_Byte を真偽値として取得する。0 以外が true。キーが無ければ undefined。 */
  optBool(key: string): boolean | undefined {
    const raw = this.optByte(key);

    if (raw === undefined) {
      return undefined;
    }

    return raw !== 0;
  }

  /** TAG_Byte を真偽値として取得する。0 以外が true。キーが無ければ例外。 */
  getBool(key: string): boolean {
    return this.getByte(key) !== 0;
  }

  /** TAG_String を取得する。キーが無ければ undefined。 */
  optString(key: string): string | undefined {
    return this.#optScalar(key, TagType.String) as string | undefined;
  }

  /** TAG_String を取得する。キーが無ければ例外。 */
  getString(key: string): string {
    return this.#require(key, this.optString(key)) as string;
  }

  /** TAG_Byte_Array を取得する。キーが無ければ undefined。 */
  optByteArray(key: string): Int8Array | undefined {
    return this.#optScalar(key, TagType.ByteArray) as Int8Array | undefined;
  }

  /** TAG_Byte_Array を取得する。キーが無ければ例外。 */
  getByteArray(key: string): Int8Array {
    return this.#require(key, this.optByteArray(key)) as Int8Array;
  }

  /** TAG_Int_Array を取得する。キーが無ければ undefined。 */
  optIntArray(key: string): Int32Array | undefined {
    return this.#optScalar(key, TagType.IntArray) as Int32Array | undefined;
  }

  /** TAG_Int_Array を取得する。キーが無ければ例外。 */
  getIntArray(key: string): Int32Array {
    return this.#require(key, this.optIntArray(key)) as Int32Array;
  }

  /** TAG_Long_Array を取得する。キーが無ければ undefined。 */
  optLongArray(key: string): BigInt64Array | undefined {
    return this.#optScalar(key, TagType.LongArray) as BigInt64Array | undefined;
  }

  /** TAG_Long_Array を取得する。キーが無ければ例外。 */
  getLongArray(key: string): BigInt64Array {
    return this.#require(key, this.optLongArray(key)) as BigInt64Array;
  }

  /** TAG_List を取得する。キーが無ければ undefined。 */
  optList(key: string): NbtList | undefined {
    return this.#castTag(key, TagType.List) as NbtList | undefined;
  }

  /** TAG_List を取得する。キーが無ければ例外。 */
  getList(key: string): NbtList {
    return this.#require(key, this.optList(key)) as NbtList;
  }

  /** TAG_Compound を取得する。キーが無ければ undefined。 */
  optCompound(key: string): NbtCompound | undefined {
    return this.#castTag(key, TagType.Compound) as NbtCompound | undefined;
  }

  /** TAG_Compound を取得する。キーが無ければ例外。 */
  getCompound(key: string): NbtCompound {
    return this.#require(key, this.optCompound(key)) as NbtCompound;
  }

  /** キーに対応するタグを目的の型として取り出す。キーが無ければ undefined、型が違えば例外。 */
  #castTag(key: string, expected: TagType): NbtTag | undefined {
    const tag = this.#entries.get(key);

    if (tag === undefined) {
      return undefined;
    }

    if (tag.type !== expected) {
      throw SpringNbtError.unexpectedTagType(
        `キー "${key}" は ${tagTypeAsString(tag.type)} だが ` +
          `${tagTypeAsString(expected)} として取り出そうとした`,
      );
    }

    return tag;
  }

  /** 値を持つタグから中身を取り出す。 */
  #optScalar(key: string, expected: TagType): unknown {
    const tag = this.#castTag(key, expected);

    if (tag === undefined) {
      return undefined;
    }

    return (tag as { value: unknown }).value;
  }

  #require<T>(key: string, value: T | undefined): T {
    if (value === undefined) {
      throw SpringNbtError.invalidArgument(`キーが存在しない: ${key}`);
    }

    return value;
  }
}

/**
 * NBT のタグ。判別可能な合併型なので、`switch (tag.type)` で網羅的に分岐できる。
 *
 * 仕様: `docs/spec/10-nbt-binary.md` 1章
 */
export type NbtTag =
  | NbtByte
  | NbtShort
  | NbtInt
  | NbtLong
  | NbtFloat
  | NbtDouble
  | NbtByteArray
  | NbtString
  | NbtList
  | NbtCompound
  | NbtIntArray
  | NbtLongArray;

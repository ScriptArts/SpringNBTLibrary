/**
 * SNBT (Stringified NBT) のパースと出力
 *
 * 対応範囲は「バイナリ NBT へ損失なく写せる部分集合」
 * 1.21.5 以降の異種リスト（`[1, "a"]`）は受理しない
 *
 * 仕様: `docs/spec/11-snbt.md` / `docs/adr/0006-snbt-scope.md`
 */

import { ErrorCode, SpringNbtError } from "../errors.js";
import * as canonical from "./canonical.js";
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
} from "./tag.js";

const INDENT_UNIT = "    ";

const WIDTH_SUFFIXES = "bBsSlLfFdD";

const SIMPLE_ESCAPES = new Map<string, string>([
  ["\\", "\\"],
  ['"', '"'],
  ["'", "'"],
  ["b", "\b"],
  ["s", " "],
  ["t", "\t"],
  ["n", "\n"],
  ["f", "\f"],
  ["r", "\r"],
]);

const LONG_MIN = -9223372036854775808n;
const LONG_MAX = 9223372036854775807n;

/** 引用符なしで書ける文字か */
function isBareChar(c: string): boolean {
  if (c >= "a" && c <= "z") {
    return true;
  }

  if (c >= "A" && c <= "Z") {
    return true;
  }

  if (c >= "0" && c <= "9") {
    return true;
  }

  return c === "_" || c === "-" || c === "." || c === "+";
}

function hexDigitValue(c: string): number {
  if (c >= "0" && c <= "9") {
    return c.charCodeAt(0) - 0x30;
  }

  if (c >= "a" && c <= "f") {
    return c.charCodeAt(0) - 0x61 + 10;
  }

  if (c >= "A" && c <= "F") {
    return c.charCodeAt(0) - 0x41 + 10;
  }

  return -1;
}

function isHexBody(body: string): boolean {
  return body.length > 2 && body[0] === "0" && (body[1] === "x" || body[1] === "X");
}

function isBinaryBody(body: string): boolean {
  if (!(body.length > 2 && body[0] === "0" && (body[1] === "b" || body[1] === "B"))) {
    return false;
  }

  // 2進リテラルの本体は 0 と 1 だけ
  for (let index = 2; index < body.length; index++) {
    if (body[index] !== "0" && body[index] !== "1") {
      return false;
    }
  }

  return true;
}

// ---------------------------------------------------------------------------
// パーサ
// ---------------------------------------------------------------------------

class Parser {
  readonly #chars: string[];
  #position = 0;

  constructor(text: string) {
    // サロゲートペアを 2 コード単位のまま扱うため、コードポイント単位に分けない
    this.#chars = text.split("");
  }

  /**
   * 入力全体を 1 つのタグとして読む
   * 末尾に余りがあればエラーにする
   */
  parseWhole(): NbtTag {
    const value = this.#parseValue();
    this.#skipWhitespace();

    // 値の後に余分な文字が残っていたら、書き手の意図と違う解釈をしている
    if (this.#position < this.#chars.length) {
      throw this.#malformed(`値の後に余分な文字がある: '${this.#chars[this.#position]}'`);
    }

    return value;
  }

  #parseValue(): NbtTag {
    this.#skipWhitespace();

    if (this.#position >= this.#chars.length) {
      throw this.#malformed("値が来るべき位置で入力が尽きた");
    }

    const c = this.#chars[this.#position];

    if (c === "{") {
      return this.#parseCompound();
    }

    if (c === "[") {
      return this.#parseListOrArray();
    }

    if (c === '"' || c === "'") {
      return new NbtString(this.#parseQuotedString());
    }

    return this.#parseUnquoted();
  }

  #parseCompound(): NbtCompound {
    this.#expect("{");
    const compound = new NbtCompound();
    this.#skipWhitespace();

    // 空の Compound
    if (this.#peek() === "}") {
      this.#position += 1;
      return compound;
    }

    // 要素を 1 つずつ読む
    for (;;) {
      this.#skipWhitespace();

      // 末尾カンマの直後に閉じ括弧が来る形を許す
      if (this.#peek() === "}") {
        this.#position += 1;
        return compound;
      }

      const key = this.#parseKey();
      this.#skipWhitespace();
      this.#expect(":");
      compound.set(key, this.#parseValue());

      this.#skipWhitespace();
      const next = this.#peek();

      if (next === ",") {
        this.#position += 1;
      } else if (next === "}") {
        this.#position += 1;
        return compound;
      } else {
        throw this.#malformed(`Compound の区切りが不正: '${next}'`);
      }
    }
  }

  #parseListOrArray(): NbtTag {
    this.#expect("[");

    // "[B;" のような型付き配列かどうかを先に判定する
    if (this.#position + 1 < this.#chars.length && this.#chars[this.#position + 1] === ";") {
      const marker = this.#chars[this.#position];

      if (marker === "B" || marker === "I" || marker === "L") {
        this.#position += 2;
        return this.#parseTypedArray(marker);
      }
    }

    return this.#parseList();
  }

  #parseList(): NbtList {
    const list = new NbtList();
    this.#skipWhitespace();

    // 空のリスト
    if (this.#peek() === "]") {
      this.#position += 1;
      return list;
    }

    // 要素を 1 つずつ読む
    for (;;) {
      this.#skipWhitespace();

      // 末尾カンマの直後に閉じ括弧が来る形を許す
      if (this.#peek() === "]") {
        this.#position += 1;
        return list;
      }

      const value = this.#parseValue();

      // 異種リストはバイナリ NBT へ写せないため受理しない (adr/0006)
      if (list.elementType !== TagType.End && list.elementType !== value.type) {
        throw this.#malformed(
          `リストに異なる型が混在している: ${tagTypeAsString(list.elementType)} と ` +
            `${tagTypeAsString(value.type)}`,
        );
      }

      list.add(value);

      this.#skipWhitespace();
      const next = this.#peek();

      if (next === ",") {
        this.#position += 1;
      } else if (next === "]") {
        this.#position += 1;
        return list;
      } else {
        throw this.#malformed(`リストの区切りが不正: '${next}'`);
      }
    }
  }

  #parseTypedArray(marker: string): NbtTag {
    const values: bigint[] = [];
    this.#skipWhitespace();

    // 空でなければ要素を読む
    if (this.#peek() === "]") {
      this.#position += 1;
    } else {
      // 閉じ括弧が来るまで要素を読み続ける
      for (;;) {
        this.#skipWhitespace();

        // 末尾カンマの直後に閉じ括弧が来る形を許す
        if (this.#peek() === "]") {
          this.#position += 1;
          break;
        }

        values.push(this.#toIntegral(this.#parseValue()));

        this.#skipWhitespace();
        const next = this.#peek();

        if (next === ",") {
          this.#position += 1;
        } else if (next === "]") {
          this.#position += 1;
          break;
        } else {
          throw this.#malformed(`配列の区切りが不正: '${next}'`);
        }
      }
    }

    if (marker === "B") {
      const result = new Int8Array(values.length);

      // 各要素が Byte の範囲に収まるか確認しながら詰める
      for (let index = 0; index < values.length; index++) {
        const value = values[index];

        if (value < -128n || value > 127n) {
          throw this.#malformed(`ByteArray の要素が範囲外: ${value}`);
        }

        result[index] = Number(value);
      }

      return new NbtByteArray(result);
    }

    if (marker === "I") {
      const result = new Int32Array(values.length);

      // 各要素が Int の範囲に収まるか確認しながら詰める
      for (let index = 0; index < values.length; index++) {
        const value = values[index];

        if (value < -2147483648n || value > 2147483647n) {
          throw this.#malformed(`IntArray の要素が範囲外: ${value}`);
        }

        result[index] = Number(value);
      }

      return new NbtIntArray(result);
    }

    return new NbtLongArray(BigInt64Array.from(values));
  }

  /**
   * 整数タグから値を取り出す
   * 整数以外なら例外
   */
  #toIntegral(tag: NbtTag): bigint {
    if (tag.type === TagType.Byte || tag.type === TagType.Short || tag.type === TagType.Int) {
      return BigInt(tag.value);
    }

    if (tag.type === TagType.Long) {
      return tag.value;
    }

    throw this.#malformed(`型付き配列の要素が整数でない: ${tagTypeAsString(tag.type)}`);
  }

  #parseKey(): string {
    const c = this.#peek();

    if (c === '"' || c === "'") {
      return this.#parseQuotedString();
    }

    const bare = this.#readBareToken();

    if (bare.length === 0) {
      throw this.#malformed("Compound のキーが空");
    }

    return bare;
  }

  #parseQuotedString(): string {
    const quote = this.#chars[this.#position];
    this.#position += 1;
    let result = "";

    // 閉じ引用符が来るまで読む
    for (;;) {
      if (this.#position >= this.#chars.length) {
        throw this.#malformed("文字列が閉じられていない");
      }

      const c = this.#chars[this.#position];

      if (c === quote) {
        this.#position += 1;
        return result;
      }

      if (c === "\\") {
        this.#position += 1;
        result += this.#readEscape();
      } else {
        result += c;
        this.#position += 1;
      }
    }
  }

  #readEscape(): string {
    if (this.#position >= this.#chars.length) {
      throw this.#malformed("エスケープが途中で切れている");
    }

    const c = this.#chars[this.#position];
    this.#position += 1;

    const simple = SIMPLE_ESCAPES.get(c);

    if (simple !== undefined) {
      return simple;
    }

    if (c === "x") {
      return String.fromCharCode(this.#readHexDigits(2));
    }

    if (c === "u") {
      // \uXXXX は UTF-16 コード単位を直接指定する
      // 孤立サロゲートもここで書ける
      return String.fromCharCode(this.#readHexDigits(4));
    }

    if (c === "U") {
      const codePoint = this.#readHexDigits(8);

      // Unicode のコードポイント範囲を外れていないか確認する
      if (codePoint > 0x10ffff) {
        throw this.#malformed(`コードポイントが範囲外: U+${codePoint.toString(16).toUpperCase()}`);
      }

      return String.fromCodePoint(codePoint);
    }

    if (c === "N") {
      throw this.#readNamedCharacter();
    }

    throw this.#malformed(`未知のエスケープ: '\\${c}'`);
  }

  #readHexDigits(count: number): number {
    if (this.#position + count > this.#chars.length) {
      throw this.#malformed("エスケープの16進数字が足りない");
    }

    let value = 0;

    // 指定桁数ぶん 16進数字を読む
    for (let offset = 0; offset < count; offset++) {
      const c = this.#chars[this.#position + offset];
      const digit = hexDigitValue(c);

      if (digit < 0) {
        throw this.#malformed(`エスケープに16進数字でない文字がある: '${c}'`);
      }

      value = value * 16 + digit;
    }

    this.#position += count;
    return value;
  }

  /** Unicode 文字名によるエスケープ `\N{...}` を読む */
  #readNamedCharacter(): SpringNbtError {
    const start = this.#position;

    // 閉じ波括弧まで読み飛ばす
    while (this.#position < this.#chars.length && this.#chars[this.#position] !== "}") {
      this.#position += 1;
    }

    const name = this.#chars.slice(start, this.#position).join("");

    // 実装間で Unicode 文字名の表が揃わないため対応しない
    return new SpringNbtError(
      ErrorCode.UnsupportedFeature,
      `文字名によるエスケープには対応していない: \\N${name}`,
    );
  }

  #parseUnquoted(): NbtTag {
    const token = this.#readBareToken();

    if (token.length === 0) {
      throw this.#malformed(`値が来るべき位置に解釈できない文字がある: '${this.#peekOrEmpty()}'`);
    }

    // bool(...) / uuid(...) の関数呼び出し
    this.#skipWhitespace();
    if (this.#peekOrEmpty() === "(" && (token === "bool" || token === "uuid")) {
      return this.#parseFunction(token);
    }

    if (token === "true") {
      return new NbtByte(1);
    }

    if (token === "false") {
      return new NbtByte(0);
    }

    const number = this.#tryParseNumber(token);

    if (number !== undefined) {
      return number;
    }

    return new NbtString(token);
  }

  #parseFunction(name: string): NbtTag {
    this.#expect("(");
    const argument = this.#parseValue();
    this.#skipWhitespace();
    this.#expect(")");

    if (name === "bool") {
      // 0 以外を真とする
      if (this.#toIntegral(argument) !== 0n) {
        return new NbtByte(1);
      }

      return new NbtByte(0);
    }

    return this.#uuidToIntArray(argument);
  }

  #uuidToIntArray(argument: NbtTag): NbtIntArray {
    if (argument.type !== TagType.String) {
      throw this.#malformed("uuid() の引数は文字列でなければならない");
    }

    const hex = argument.value.replaceAll("-", "");

    if (hex.length !== 32 || !/^[0-9a-fA-F]+$/.test(hex)) {
      throw this.#malformed(`UUID として解釈できない: ${argument.value}`);
    }

    const result = new Int32Array(4);

    // UUID を上位から 32bit ずつ 4 要素の IntArray へ写す
    for (let index = 0; index < 4; index++) {
      result[index] = Number.parseInt(hex.slice(index * 8, (index + 1) * 8), 16) | 0;
    }

    return new NbtIntArray(result);
  }

  /**
   * 数値トークンを解釈する
   * 数値として読めなければ undefined（文字列として扱われる）
   */
  #tryParseNumber(token: string): NbtTag | undefined {
    let negative = false;
    let start = 0;

    if (token[0] === "+" || token[0] === "-") {
      negative = token[0] === "-";
      start = 1;
    }

    let body = token.slice(start);

    if (body.length === 0) {
      return undefined;
    }

    let widthSuffix = "";
    let unsignedSuffix = false;

    const hexBody = isHexBody(body);
    const last = body[body.length - 1];

    // 幅接尾辞を末尾から剥がす
    // 16進では b/d/f が数字と紛れるため s/l だけを認める
    let suffixAllowed: boolean;
    if (hexBody) {
      suffixAllowed = last === "s" || last === "S" || last === "l" || last === "L";
    } else {
      suffixAllowed = WIDTH_SUFFIXES.includes(last);
    }

    if (suffixAllowed && body.length >= 2) {
      widthSuffix = last.toLowerCase();
      body = body.slice(0, -1);

      // 符号接尾辞 u / s は幅接尾辞の手前に置かれる
      if (body.length >= 2) {
        const signChar = body[body.length - 1];

        if (signChar === "u" || signChar === "U") {
          unsignedSuffix = true;
          body = body.slice(0, -1);
        } else if (signChar === "s" || signChar === "S") {
          body = body.slice(0, -1);
        }
      }
    }

    body = body.replaceAll("_", "");

    if (body.length === 0) {
      return undefined;
    }

    // 特殊な浮動小数点値
    if (body === "Infinity") {
      return this.#makeFloating(Number.POSITIVE_INFINITY, negative, widthSuffix);
    }

    if (body === "NaN") {
      return this.#makeFloating(Number.NaN, negative, widthSuffix);
    }

    if (isHexBody(body)) {
      return this.#parseRadix(body.slice(2), 16, negative, widthSuffix, unsignedSuffix);
    }

    if (isBinaryBody(body)) {
      return this.#parseRadix(body.slice(2), 2, negative, widthSuffix, unsignedSuffix);
    }

    const looksFloating = body.includes(".") || body.includes("e") || body.includes("E");

    if (looksFloating || widthSuffix === "f" || widthSuffix === "d") {
      const parsed = Number(body);

      if (Number.isNaN(parsed) && body !== "NaN") {
        return undefined;
      }

      return this.#makeFloating(parsed, negative, widthSuffix);
    }

    return this.#parseRadix(body, 10, negative, widthSuffix, unsignedSuffix);
  }

  #makeFloating(value: number, negative: boolean, widthSuffix: string): NbtTag {
    let signed = value;

    if (negative) {
      signed = -value;
    }

    if (widthSuffix === "f") {
      return new NbtFloat(signed);
    }

    // 接尾辞なしの小数は Double
    if (widthSuffix === "" || widthSuffix === "d") {
      return new NbtDouble(signed);
    }

    throw this.#malformed(`小数に整数の接尾辞 '${widthSuffix}' は付けられない`);
  }

  #parseRadix(
    digits: string,
    radix: number,
    negative: boolean,
    widthSuffix: string,
    unsignedSuffix: boolean,
  ): NbtTag | undefined {
    if (digits.length === 0) {
      return undefined;
    }

    let magnitude = 0n;
    const radixBig = BigInt(radix);

    // 桁を1つずつ積み上げる
    for (const c of digits) {
      const digit = hexDigitValue(c);

      if (digit < 0 || digit >= radix) {
        return undefined;
      }

      magnitude = magnitude * radixBig + BigInt(digit);

      // 符号なし 64bit を超えたらその場で打ち切る
      if (magnitude > 0xffffffffffffffffn) {
        throw this.#malformed(`整数が大きすぎる: ${digits}`);
      }
    }

    return this.#makeIntegral(magnitude, negative, widthSuffix, unsignedSuffix);
  }

  #makeIntegral(
    magnitude: bigint,
    negative: boolean,
    widthSuffix: string,
    unsignedSuffix: boolean,
  ): NbtTag {
    if (unsignedSuffix) {
      // 符号なし指定は、その幅の符号なし最大値までを受け付けて符号付きへ読み替える
      if (widthSuffix === "b") {
        return new NbtByte(Number(this.#wrapUnsigned(magnitude, 0xffn, 8n)));
      }

      if (widthSuffix === "s") {
        return new NbtShort(Number(this.#wrapUnsigned(magnitude, 0xffffn, 16n)));
      }

      if (widthSuffix === "l") {
        return new NbtLong(BigInt.asIntN(64, magnitude));
      }

      return new NbtInt(Number(this.#wrapUnsigned(magnitude, 0xffffffffn, 32n)));
    }

    let value = magnitude;

    if (negative) {
      value = -magnitude;
    }

    if (value < LONG_MIN || value > LONG_MAX) {
      throw this.#malformed(`整数が 64bit に収まらない: ${value}`);
    }

    if (widthSuffix === "b") {
      return new NbtByte(Number(this.#checkRange(value, -128n, 127n, "byte")));
    }

    if (widthSuffix === "s") {
      return new NbtShort(Number(this.#checkRange(value, -32768n, 32767n, "short")));
    }

    if (widthSuffix === "l") {
      return new NbtLong(value);
    }

    if (widthSuffix === "f") {
      return new NbtFloat(Number(value));
    }

    if (widthSuffix === "d") {
      return new NbtDouble(Number(value));
    }

    // 接尾辞なしの整数は Int
    // 暗黙に Long へ格上げしない
    return new NbtInt(Number(this.#checkRange(value, -2147483648n, 2147483647n, "int")));
  }

  #wrapUnsigned(magnitude: bigint, max: bigint, bits: bigint): bigint {
    if (magnitude > max) {
      throw this.#malformed(`符号なし整数が範囲外: ${magnitude} (上限 ${max})`);
    }

    return BigInt.asIntN(Number(bits), magnitude);
  }

  #checkRange(value: bigint, minimum: bigint, maximum: bigint, typeName: string): bigint {
    if (value < minimum || value > maximum) {
      throw this.#malformed(`${typeName} の範囲外: ${value}`);
    }

    return value;
  }

  #readBareToken(): string {
    const start = this.#position;

    // 引用符なしトークンに使える文字を読み進める
    while (this.#position < this.#chars.length && isBareChar(this.#chars[this.#position])) {
      this.#position += 1;
    }

    return this.#chars.slice(start, this.#position).join("");
  }

  #skipWhitespace(): void {
    // 空白・改行・タブを読み飛ばす
    while (this.#position < this.#chars.length && /\s/.test(this.#chars[this.#position])) {
      this.#position += 1;
    }
  }

  #peek(): string {
    if (this.#position >= this.#chars.length) {
      throw this.#malformed("入力が途中で尽きた");
    }

    return this.#chars[this.#position];
  }

  /**
   * 末尾でも例外にしない先読み
   * 入力が尽きていれば空文字列を返す
   */
  #peekOrEmpty(): string {
    if (this.#position >= this.#chars.length) {
      return "";
    }

    return this.#chars[this.#position];
  }

  #expect(expected: string): void {
    this.#skipWhitespace();

    if (this.#position >= this.#chars.length) {
      throw this.#malformed(`'${expected}' が来るべき位置で入力が尽きた`);
    }

    if (this.#chars[this.#position] !== expected) {
      throw this.#malformed(`'${expected}' を期待したが '${this.#chars[this.#position]}' だった`);
    }

    this.#position += 1;
  }

  #malformed(message: string): SpringNbtError {
    return SpringNbtError.malformed(`SNBT (${this.#position} 文字目): ${message}`);
  }
}

/** SNBT 文字列をタグへ変換する */
export function parse(text: string): NbtTag {
  return new Parser(text).parseWhole();
}

/** SNBT 文字列を Compound へ変換する */
export function parseCompound(text: string): NbtCompound {
  const tag = parse(text);

  if (tag.type === TagType.Compound) {
    return tag;
  }

  throw SpringNbtError.unexpectedTagType(`ルートが compound でない: ${tagTypeAsString(tag.type)}`);
}

// ---------------------------------------------------------------------------
// ライタ
// ---------------------------------------------------------------------------

/** タグを 1 行の SNBT へ変換する */
export function write(tag: NbtTag): string {
  const parts: string[] = [];
  writeTag(parts, tag, -1);
  return parts.join("");
}

/**
 * タグを整形した SNBT へ変換する
 * インデントは空白 4 個
 */
export function writePretty(tag: NbtTag): string {
  const parts: string[] = [];
  writeTag(parts, tag, 0);
  return parts.join("");
}

/**
 * タグを書き出す
 * `depth` が負なら 1 行、0 以上なら整形して出力する
 */
function writeTag(parts: string[], tag: NbtTag, depth: number): void {
  switch (tag.type) {
    case TagType.Byte:
      parts.push(`${tag.value}b`);
      break;
    case TagType.Short:
      parts.push(`${tag.value}s`);
      break;
    case TagType.Int:
      parts.push(`${tag.value}`);
      break;
    case TagType.Long:
      parts.push(`${tag.value}L`);
      break;
    case TagType.Float:
      parts.push(`${canonical.fromFloat(tag.value)}f`);
      break;
    case TagType.Double:
      parts.push(`${canonical.fromDouble(tag.value)}d`);
      break;
    case TagType.String:
      parts.push(quoteString(tag.value));
      break;
    case TagType.ByteArray:
      writeTypedArray(parts, "B", Array.from(tag.value), "B");
      break;
    case TagType.IntArray:
      writeTypedArray(parts, "I", Array.from(tag.value), "");
      break;
    case TagType.LongArray:
      writeTypedArray(parts, "L", Array.from(tag.value), "L");
      break;
    case TagType.List:
      writeList(parts, tag, depth);
      break;
    case TagType.Compound:
      writeCompound(parts, tag, depth);
      break;
    default:
      throw SpringNbtError.unexpectedTagType("SNBT へ書けないタグ");
  }
}

function writeCompound(parts: string[], compound: NbtCompound, depth: number): void {
  if (compound.size === 0) {
    parts.push("{}");
    return;
  }

  parts.push("{");
  let first = true;

  // 挿入順のまま「キー: 値」を並べる
  for (const [key, value] of compound.entries()) {
    if (!first) {
      parts.push(",");
    }

    first = false;
    appendSeparator(parts, nextDepth(depth));
    parts.push(quoteKey(key));
    parts.push(":");

    // 整形時はコロンの後に空白を入れて読みやすくする
    if (depth >= 0) {
      parts.push(" ");
    }

    writeTag(parts, value, nextDepth(depth));
  }

  appendSeparator(parts, depth);
  parts.push("}");
}

function writeList(parts: string[], list: NbtList, depth: number): void {
  if (list.size === 0) {
    parts.push("[]");
    return;
  }

  parts.push("[");
  let first = true;

  // 要素型は共通なので値だけを並べる
  for (const item of list) {
    if (!first) {
      parts.push(",");
    }

    first = false;
    appendSeparator(parts, nextDepth(depth));
    writeTag(parts, item, nextDepth(depth));
  }

  appendSeparator(parts, depth);
  parts.push("]");
}

function writeTypedArray(
  parts: string[],
  marker: string,
  values: Array<number | bigint>,
  elementSuffix: string,
): void {
  parts.push(`[${marker};`);

  // 型付き配列は 1 行に収める
  for (let index = 0; index < values.length; index++) {
    if (index > 0) {
      parts.push(",");
    }

    parts.push(`${values[index]}${elementSuffix}`);
  }

  parts.push("]");
}

/** 整形出力なら改行とインデントを、1 行出力なら何も入れない */
function appendSeparator(parts: string[], depth: number): void {
  if (depth < 0) {
    return;
  }

  parts.push("\n");
  parts.push(INDENT_UNIT.repeat(depth));
}

/** 整形出力のときだけ深さを 1 段進める */
function nextDepth(depth: number): number {
  if (depth < 0) {
    return -1;
  }

  return depth + 1;
}

/**
 * キーを出力する
 * 引用符なしで書ける場合はそのまま出す
 */
function quoteKey(key: string): string {
  if (isBareWritable(key)) {
    return key;
  }

  return quoteString(key);
}

function isBareWritable(text: string): boolean {
  if (text.length === 0) {
    return false;
  }

  // 引用符なしで書ける文字だけで構成されているか調べる
  for (const c of text) {
    if (!isBareChar(c)) {
      return false;
    }
  }

  return true;
}

const QUOTE_ESCAPES = new Map<number, string>([
  [0x22, '\\"'],
  [0x5c, "\\\\"],
  [0x08, "\\b"],
  [0x09, "\\t"],
  [0x0a, "\\n"],
  [0x0c, "\\f"],
  [0x0d, "\\r"],
]);

/**
 * 文字列を二重引用符で囲み、必要な文字だけエスケープする
 *
 * UTF-16 コード単位で処理するのは、正しいサロゲートペアと孤立サロゲートを
 * 区別するため
 * ここを誤ると Python / Rust と出力が食い違う
 */
function quoteString(text: string): string {
  let result = '"';
  let index = 0;

  // 1 コード単位ずつ見てエスケープが要るものだけ置き換える
  while (index < text.length) {
    const unit = text.charCodeAt(index);
    const escaped = QUOTE_ESCAPES.get(unit);

    if (escaped !== undefined) {
      result += escaped;
      index += 1;
      continue;
    }

    // 正しいサロゲートペアはそのまま出す
    if (unit >= 0xd800 && unit <= 0xdbff && index + 1 < text.length) {
      const low = text.charCodeAt(index + 1);

      if (low >= 0xdc00 && low <= 0xdfff) {
        result += text[index] + text[index + 1];
        index += 2;
        continue;
      }
    }

    if (unit < 0x20 || unit === 0x7f || (unit >= 0xd800 && unit <= 0xdfff)) {
      // 制御文字と孤立サロゲートは \uXXXX で表す
      result += `\\u${unit.toString(16).padStart(4, "0")}`;
    } else {
      result += text[index];
    }

    index += 1;
  }

  return `${result}"`;
}

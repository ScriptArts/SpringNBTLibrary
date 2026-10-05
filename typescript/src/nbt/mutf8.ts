/**
 * Modified UTF-8 (MUTF-8)の符号化・復号
 *
 * 標準UTF-8との違いは2点だけ
 *  - `U+0000`を`C0 80`の2バイトで表す
 *  - `U+10000`以上をサロゲートペアへ分解し、3バイト × 2で表す (CESU-8)
 *
 * JavaScriptの`string`はUTF-16コード単位の列なので、サロゲートペアも孤立サロゲートもそのまま保持できる（C# / Javaと同じ性質）
 */

import { SpringNbtError } from "../errors.js";

/** MUTF-8の文字列が取りうる最大バイト長（長さフィールドがu16のため） */
export const MAX_BYTE_LENGTH = 65535;

/**
 * MUTF-8バイト列を文字列へ復号する
 *
 * @throws {SpringNbtError} バイト列がMUTF-8として不正な場合
 */
export function decode(data: Uint8Array, offset = 0, length = data.length - offset): string {
  const units: number[] = [];
  let index = offset;
  const end = offset + length;

  // 先頭から1文字ずつ取り出す
  while (index < end) {
    const b0 = data[index];

    if ((b0 & 0x80) === 0x00) {
      // 1バイト形式: 0xxxxxxx (U+0001..U+007F)
      if (b0 === 0x00) {
        // 素の0x00はMUTF-8では現れてはならない (C0 80を使う)
        throw SpringNbtError.malformed("MUTF-8: 素の 0x00 が現れた (U+0000 は C0 80 で表す)");
      }

      units.push(b0);
      index += 1;
    } else if ((b0 & 0xe0) === 0xc0) {
      // 2バイト形式: 110xxxxx 10xxxxxx
      if (index + 1 >= end) {
        throw SpringNbtError.malformed("MUTF-8: 2バイト形式が途中で切れた");
      }

      const b1 = data[index + 1];

      if ((b1 & 0xc0) !== 0x80) {
        throw SpringNbtError.malformed("MUTF-8: 2バイト形式の継続バイトが不正");
      }

      const value = ((b0 & 0x1f) << 6) | (b1 & 0x3f);

      // C0 80 (U+0000)だけは正当
      // それ以外の0x80未満は冗長符号化
      if (value < 0x80 && !(b0 === 0xc0 && b1 === 0x80)) {
        throw SpringNbtError.malformed("MUTF-8: 冗長な2バイト符号化");
      }

      units.push(value);
      index += 2;
    } else if ((b0 & 0xf0) === 0xe0) {
      // 3バイト形式: 1110xxxx 10xxxxxx 10xxxxxx
      if (index + 2 >= end) {
        throw SpringNbtError.malformed("MUTF-8: 3バイト形式が途中で切れた");
      }

      const b1 = data[index + 1];
      const b2 = data[index + 2];

      if ((b1 & 0xc0) !== 0x80 || (b2 & 0xc0) !== 0x80) {
        throw SpringNbtError.malformed("MUTF-8: 3バイト形式の継続バイトが不正");
      }

      const value = ((b0 & 0x0f) << 12) | ((b1 & 0x3f) << 6) | (b2 & 0x3f);

      // 3バイトで表すべき範囲はU+0800以上
      if (value < 0x800) {
        throw SpringNbtError.malformed("MUTF-8: 冗長な3バイト符号化");
      }

      units.push(value);
      index += 3;
    } else {
      // 4バイト形式 (標準UTF-8)や継続バイト単独はMUTF-8では不正
      throw SpringNbtError.malformed(
        `MUTF-8: 不正な先頭バイト 0x${b0.toString(16).toUpperCase().padStart(2, "0")}`,
      );
    }
  }

  // コード単位が多いとfromCharCodeの引数の上限を超えるため、分割して連結する
  let result = "";
  const chunkSize = 8192;

  // 一度に渡す引数が多すぎるとスタックが溢れるので、小分けにして繋ぐ
  for (let start = 0; start < units.length; start += chunkSize) {
    result += String.fromCharCode(...units.slice(start, start + chunkSize));
  }

  return result;
}

/**
 * 文字列をMUTF-8バイト列へ符号化する
 *
 * サロゲートは対になっているかどうかに関わらず1つずつ3バイトで符号化されるため、孤立サロゲートもそのまま往復できる
 */
export function encode(text: string): Uint8Array {
  const buffer = new Uint8Array(byteLength(text));
  let position = 0;

  // コード単位ごとに1〜3バイトへ展開する
  for (let index = 0; index < text.length; index++) {
    const unit = text.charCodeAt(index);

    if (unit >= 0x0001 && unit <= 0x007f) {
      buffer[position] = unit;
      position += 1;
    } else if (unit === 0x0000 || unit <= 0x07ff) {
      // U+0000もこの経路でC0 80になる
      buffer[position] = 0xc0 | ((unit >> 6) & 0x1f);
      buffer[position + 1] = 0x80 | (unit & 0x3f);
      position += 2;
    } else {
      buffer[position] = 0xe0 | ((unit >> 12) & 0x0f);
      buffer[position + 1] = 0x80 | ((unit >> 6) & 0x3f);
      buffer[position + 2] = 0x80 | (unit & 0x3f);
      position += 3;
    }
  }

  return buffer;
}

/**
 * 文字列をMUTF-8で符号化したときのバイト長を求める
 * 実際に符号化はしない
 */
export function byteLength(text: string): number {
  let length = 0;

  // 各コード単位が何バイトになるかを数える
  for (let index = 0; index < text.length; index++) {
    const unit = text.charCodeAt(index);

    if (unit >= 0x0001 && unit <= 0x007f) {
      length += 1;
    } else if (unit === 0x0000 || unit <= 0x07ff) {
      length += 2;
    } else {
      length += 3;
    }
  }

  return length;
}

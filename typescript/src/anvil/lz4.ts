/**
 * 圧縮方式ID 4 (LZ4) のチャンクを展開する
 *
 * 素の LZ4 ブロックでも LZ4 フレーム形式でもなく、
 * 独自ヘッダを持つブロックの連結である
 *
 * 書き込みには対応しない
 * 書き戻すときは Zlib になる
 *
 * 仕様: `docs/spec/20-anvil-region.md` 3.1.1 / 3.1.2
 */

import { SpringNbtError } from "../errors.js";

/** ブロックの先頭に必ず置かれる 8 バイト */
const MAGIC = new Uint8Array([0x4c, 0x5a, 0x34, 0x42, 0x6c, 0x6f, 0x63, 0x6b]);

/** ブロックヘッダの長さ */
const HEADER_LENGTH = 21;

/** トークン上位 4 ビット: 本体が無圧縮 */
const METHOD_STORED = 0x10;

/** トークン上位 4 ビット: 本体が LZ4 圧縮 */
const METHOD_COMPRESSED = 0x20;

/** マッチの最小長 */
const MIN_MATCH = 4;

/** 読み進めた位置を持ち回るための入れ物 */
interface Cursor {
  position: number;
}

/**
 * LZ4Block の連結を展開する
 *
 * @throws {SpringNbtError} 形式に反する入力 (MALFORMED_DATA)
 */
export function decompressLz4(payload: Uint8Array): Uint8Array {
  const blocks: Uint8Array[] = [];
  let position = 0;
  let total = 0;

  // 入力を使い切るまでブロックを読み続ける
  while (position < payload.length) {
    const block = decompressBlock(payload, position);
    blocks.push(block.data);
    total += block.data.length;
    position = block.next;
  }

  const output = new Uint8Array(total);
  let written = 0;

  // 読んだ順につなぐ
  for (const block of blocks) {
    output.set(block, written);
    written += block.length;
  }

  return output;
}

/** ブロックを 1 つ展開し、中身と次のブロックの開始位置を返す */
function decompressBlock(payload: Uint8Array, position: number): { data: Uint8Array; next: number } {
  if (position + HEADER_LENGTH > payload.length) {
    throw SpringNbtError.malformed(
      `LZ4: ブロックヘッダが足りない（${payload.length - position} バイト）`,
    );
  }

  // マジックが違えばそもそも LZ4Block ではない
  for (let index = 0; index < MAGIC.length; index++) {
    if (payload[position + index] !== MAGIC[index]) {
      throw SpringNbtError.malformed("LZ4: ブロックが LZ4Block で始まっていない");
    }
  }

  const view = new DataView(payload.buffer, payload.byteOffset, payload.byteLength);
  const method = payload[position + 8] & 0xf0;
  const compressedLength = view.getInt32(position + 9, true);
  const originalLength = view.getInt32(position + 13, true);
  const body = position + HEADER_LENGTH;

  validateLengths(compressedLength, originalLength);

  if (body + compressedLength > payload.length) {
    throw SpringNbtError.malformed("LZ4: ブロック本体が入力からはみ出している");
  }

  if (method === METHOD_STORED) {
    // 無圧縮なら 2 つの長さは一致していなければならない
    if (compressedLength !== originalLength) {
      throw SpringNbtError.malformed(
        `LZ4: 無圧縮ブロックの長さが食い違う（${compressedLength} と ${originalLength}）`,
      );
    }

    return { data: payload.slice(body, body + compressedLength), next: body + compressedLength };
  }

  if (method === METHOD_COMPRESSED) {
    const data = decompressRawBlock(
      payload.subarray(body, body + compressedLength),
      originalLength,
    );
    return { data, next: body + compressedLength };
  }

  throw SpringNbtError.malformed(
    `LZ4: 未知の圧縮方式 0x${method.toString(16).toUpperCase().padStart(2, "0")}`,
  );
}

/** ヘッダに書かれた 2 つの長さが妥当か調べる */
function validateLengths(compressedLength: number, originalLength: number): void {
  if (compressedLength < 0 || originalLength < 0) {
    throw SpringNbtError.malformed("LZ4: ブロックの長さが負値");
  }

  // 片方だけが 0 になることはない
  if ((compressedLength === 0) !== (originalLength === 0)) {
    throw SpringNbtError.malformed("LZ4: ブロックの長さが片方だけ 0");
  }
}

/** 素の LZ4 ブロックを展開する */
function decompressRawBlock(source: Uint8Array, originalLength: number): Uint8Array {
  const output = new Uint8Array(originalLength);
  const cursor: Cursor = { position: 0 };
  let written = 0;

  // シーケンスを順に読む
  while (cursor.position < source.length) {
    const token = source[cursor.position];
    cursor.position++;

    let literalLength = token >> 4;

    // 15 なら追加バイトで長さが続く
    if (literalLength === 15) {
      literalLength += readLength(source, cursor);
    }

    written = copyLiterals(source, cursor, output, written, literalLength);

    // リテラルを出し切って入力が尽きたら、そこで終わり
    if (cursor.position >= source.length) {
      break;
    }

    if (cursor.position + 2 > source.length) {
      throw SpringNbtError.malformed("LZ4: オフセットが入力からはみ出している");
    }

    const offset = source[cursor.position] | (source[cursor.position + 1] << 8);
    cursor.position += 2;

    if (offset === 0 || offset > written) {
      throw SpringNbtError.malformed(`LZ4: マッチのオフセットが不正: ${offset}`);
    }

    let matchLength = (token & 0x0f) + MIN_MATCH;

    // 下位 4 ビットが 15 なら追加バイトで長さが続く
    if ((token & 0x0f) === 15) {
      matchLength += readLength(source, cursor);
    }

    written = copyMatch(output, written, offset, matchLength);
  }

  if (written !== originalLength) {
    throw SpringNbtError.malformed(
      `LZ4: 展開後の長さが合わない（${written} と ${originalLength}）`,
    );
  }

  return output;
}

/** 255 が続く形式の追加長さを読む */
function readLength(source: Uint8Array, cursor: Cursor): number {
  let total = 0;

  // 255 未満のバイトが出るまで足し続ける
  while (true) {
    if (cursor.position >= source.length) {
      throw SpringNbtError.malformed("LZ4: 長さの追加バイトが途中で切れた");
    }

    const value = source[cursor.position];
    cursor.position++;
    total += value;

    if (value !== 255) {
      return total;
    }
  }
}

/** リテラルをそのまま出力へ写し、書き込み済みの長さを返す */
function copyLiterals(
  source: Uint8Array,
  cursor: Cursor,
  output: Uint8Array,
  written: number,
  length: number,
): number {
  if (cursor.position + length > source.length) {
    throw SpringNbtError.malformed("LZ4: リテラルが入力からはみ出している");
  }

  if (written + length > output.length) {
    throw SpringNbtError.malformed("LZ4: 展開後の長さを超えた");
  }

  output.set(source.subarray(cursor.position, cursor.position + length), written);
  cursor.position += length;
  return written + length;
}

/** 出力済みのバイト列からマッチを写し、書き込み済みの長さを返す */
function copyMatch(output: Uint8Array, written: number, offset: number, length: number): number {
  if (written + length > output.length) {
    throw SpringNbtError.malformed("LZ4: 展開後の長さを超えた");
  }

  const from = written - offset;

  // コピー元と先は重なりうるので 1 バイトずつ写す
  for (let index = 0; index < length; index++) {
    output[written + index] = output[from + index];
  }

  return written + length;
}

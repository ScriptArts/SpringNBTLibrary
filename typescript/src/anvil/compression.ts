/**
 * リージョンファイル内でチャンクに使われる圧縮方式
 *
 * NBT 層の `Compression` とは別物であることに注意
 * あちらはファイル全体の圧縮を表し、こちらはリージョン内の 1 チャンクに付く 1 バイトのIDを表す
 *
 * 仕様: `docs/spec/20-anvil-region.md` 3.1章
 */

import { SpringNbtError } from "../errors.js";

/** 圧縮方式
/** 値は仕様が定める圧縮方式IDと一致する
/** */
export enum ChunkCompression {
  /** GZip (RFC 1952)
  /** 実データではほぼ使われない
  /** */
  Gzip = 1,
  /** Zlib (RFC 1950)
  /** Minecraft が実際に書き出す方式
  /** */
  Zlib = 2,
  /** 無圧縮
  /** */
  None = 3,
  /** LZ4（ブロック形式）
  /** 任意依存
  /** */
  Lz4 = 4,
  /** サードパーティ製サーバのカスタム方式
  /** 中身は解釈できない
  /** */
  Custom = 127,
}

const LABELS = new Map<ChunkCompression, string>([
  [ChunkCompression.Gzip, "gzip"],
  [ChunkCompression.Zlib, "zlib"],
  [ChunkCompression.None, "none"],
  [ChunkCompression.Lz4, "lz4"],
  [ChunkCompression.Custom, "custom"],
]);

/** 適合性テストで言語間比較に使う識別子を返す
/** */
export function chunkCompressionAsString(compression: ChunkCompression): string {
  const label = LABELS.get(compression);

  if (label === undefined) {
    throw SpringNbtError.malformed(`未知の圧縮方式: ${compression}`);
  }

  return label;
}

/**
 * 圧縮方式IDから {@link ChunkCompression} を得る
 *
 * @throws {SpringNbtError} 未知のIDの場合
 */
export function chunkCompressionFromId(id: number): ChunkCompression {
  // 仕様が定めるのは 1・2・3・4・127 の 5 種類だけ
  if (LABELS.has(id as ChunkCompression)) {
    return id as ChunkCompression;
  }

  throw SpringNbtError.malformed(`未知の圧縮方式ID: ${id}`);
}

/** リージョンファイルに格納されたままの、圧縮済みチャンクデータ
/** */
export class RawChunk {
  constructor(
    readonly compression: ChunkCompression,
    readonly data: Uint8Array,
    readonly external: boolean = false,
  ) {}
}

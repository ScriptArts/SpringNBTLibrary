/**
 * 適合性検証ツール。全言語が同じインターフェースで同じ出力を出す。
 *
 * `spec/run-conformance.sh` がこのツールを言語ぶん起動し、
 * 出力を相互に diff することで「全言語が同一に振る舞う」ことを機械的に確かめる。
 *
 * 仕様: `docs/spec/90-conformance.md` 2.3章
 */

import { existsSync, rmSync, writeFileSync } from "node:fs";
import process from "node:process";

import {
  ChunkCompression,
  RegionFile,
  RegionFileMode,
  chunkCompressionAsString,
} from "./anvil/index.js";
import { BlockState, Chunk, VersionMismatchAction } from "./world/index.js";
import { TARGET_DATA_VERSION } from "./index.js";
import { SpringNbtError } from "./errors.js";
import * as mutf8 from "./nbt/mutf8.js";
import * as snbt from "./nbt/snbt.js";
import {
  Compression,
  NamedTag,
  writeBytes as writeNbtBytes,
  NbtCompound,
  NbtFormat,
  NbtList,
  NbtTag,
  TagType,
  readFile,
  tagTypeAsString,
  writeBytes,
} from "./nbt/index.js";
import { NbtCompound as NbtCompoundClass } from "./nbt/index.js";

const USAGE = `使い方:
  conformance decode  <入力パス> <出力JSONパス> [--format network]
  conformance encode  <入力パス> <出力バイナリパス> [--format network]
  conformance snbt    <入力パス> <出力SNBTパス> [--format network]
  conformance region-list    <入力mcaパス> <出力テキストパス>
  conformance region-rewrite <入力mcaパス> <出力mcaパス>
  conformance chunk-report   <入力チャンクnbt> <出力テキストパス>
  conformance chunk-edit     <入力チャンクnbt> <出力nbtパス>
  conformance version`;

// ---------------------------------------------------------------------------
// 正規化JSON
//
// 浮動小数点をビットパターンで、64bit 整数を10進文字列で表すのが要。
// 10進表記の丸めや JSON 数値の精度は処理系ごとに差が出るため、
// そのまま出すと言語間で出力が一致しない。
//
// 仕様: docs/spec/00-conventions.md 6章
// ---------------------------------------------------------------------------

const JSON_ESCAPES = new Map<number, string>([
  [0x22, '\\"'],
  [0x5c, "\\\\"],
  [0x08, "\\b"],
  [0x0c, "\\f"],
  [0x0a, "\\n"],
  [0x0d, "\\r"],
  [0x09, "\\t"],
]);

/**
 * JSON 文字列を書き出す。非 ASCII は必ず `\uXXXX` へ逃がす。
 *
 * エスケープの単位は UTF-16 コード単位。
 * 言語ごとに既定のエスケープ方針が違うため、ここで一律に固定しないと出力が一致しない。
 */
function jsonString(text: string): string {
  let result = '"';

  // コード単位ごとに、JSON として安全な形へ直す
  for (let index = 0; index < text.length; index++) {
    const unit = text.charCodeAt(index);
    const escaped = JSON_ESCAPES.get(unit);

    if (escaped !== undefined) {
      result += escaped;
      continue;
    }

    // ASCII の印字可能文字だけ生で出し、それ以外は \uXXXX にする
    if (unit >= 0x20 && unit <= 0x7e) {
      result += text[index];
    } else {
      result += `\\u${unit.toString(16).padStart(4, "0")}`;
    }
  }

  return `${result}"`;
}

const scratch = new DataView(new ArrayBuffer(8));

function floatBitsHex(value: number): string {
  scratch.setFloat32(0, value, false);
  return `0x${scratch.getUint32(0, false).toString(16).padStart(8, "0")}`;
}

function doubleBitsHex(value: number): string {
  scratch.setFloat64(0, value, false);
  return `0x${scratch.getBigUint64(0, false).toString(16).padStart(16, "0")}`;
}

function toHex(bytes: Uint8Array): string {
  let result = "";

  // 1 バイトずつ 16 進 2 桁へ直す
  for (const value of bytes) {
    result += value.toString(16).padStart(2, "0");
  }

  return result;
}

function jsonTag(tag: NbtTag): string {
  let result = `{"type":${jsonString(tagTypeAsString(tag.type))}`;

  // list だけは value の前に element_type が入る（仕様が定めるキー順）
  if (tag.type === TagType.List) {
    result += `,"element_type":${jsonString(tagTypeAsString((tag as NbtList).elementType))}`;
  }

  result += ',"value":';

  switch (tag.type) {
    case TagType.Byte:
    case TagType.Short:
    case TagType.Int:
      result += `${tag.value}`;
      break;
    case TagType.Long:
      // 64bit 整数は JSON 数値だと処理系によって精度が落ちるため10進文字列で表す
      result += jsonString(`${tag.value}`);
      break;
    case TagType.Float:
      result += jsonString(floatBitsHex(tag.value));
      break;
    case TagType.Double:
      result += jsonString(doubleBitsHex(tag.value));
      break;
    case TagType.String:
      result += jsonString(tag.value);

      // MUTF-8 のバイト列も併記する。孤立サロゲートなど UTF-8 に写せない値を厳密に比較するため
      result += `,"mutf8":${jsonString(toHex(mutf8.encode(tag.value)))}`;
      break;
    case TagType.ByteArray:
    case TagType.IntArray:
      result += `[${Array.from(tag.value).join(",")}]`;
      break;
    case TagType.LongArray: {
      // 64bit 整数は10進文字列の配列で表す
      const items: string[] = [];

      // 配列の各要素を文字列として並べる
      for (const value of tag.value) {
        items.push(jsonString(`${value}`));
      }

      result += `[${items.join(",")}]`;
      break;
    }
    case TagType.List: {
      const items: string[] = [];

      // リストの各要素を再帰的に写す
      for (const item of tag) {
        items.push(jsonTag(item));
      }

      result += `[${items.join(",")}]`;
      break;
    }
    case TagType.Compound: {
      // JSON オブジェクトだと挿入順の保持が処理系依存になるため、組の配列で表す
      const items: string[] = [];

      // compound はキーと値の組の配列として写す。挿入順を保つため
      for (const [key, value] of (tag as NbtCompound).entries()) {
        items.push(`[${jsonString(key)},${jsonTag(value)}]`);
      }

      result += `[${items.join(",")}]`;
      break;
    }
    default:
      throw SpringNbtError.malformed("JSON へ写せないタグ");
  }

  return `${result}}`;
}

/** ルートを含む全体を JSON 文字列へ変換する。末尾に改行を1つ付ける。 */
function normalizedJson(named: NamedTag, format: NbtFormat): string {
  return (
    `{"format":${jsonString(format)}` +
    `,"root_name":${jsonString(named.name)}` +
    `,"root":${jsonTag(named.tag)}}\n`
  );
}


// ---------------------------------------------------------------------------
// リージョンファイル
//
// 仕様: docs/spec/90-conformance.md 2.3章
// ---------------------------------------------------------------------------

/**
 * 存在するチャンクを 1 行 1 チャンクで書き出す。並びはロケーションテーブルの添字順。
 *
 * 各行は「絶対X 絶対Z タイムスタンプ 圧縮方式 圧縮後バイト数 展開後バイト数 キー数」。
 */
function regionList(region: RegionFile): string {
  const lines: string[] = [`region ${region.regionX} ${region.regionZ}`];
  let total = 0;

  // 存在するチャンクを順に読み、要約を組み立てる
  for (const position of region.chunkPositions()) {
    const raw = region.readChunkRaw(position.x, position.z);

    if (raw === undefined) {
      continue;
    }

    const chunk = region.readChunk(position.x, position.z);
    let keyCount = 0;
    let plainLength = 0;

    if (chunk !== undefined) {
      keyCount = chunk.size;
      plainLength = writeNbtBytes(new NamedTag("", chunk), {
        compression: Compression.None,
      }).length;
    }

    lines.push(
      `${position.x} ${position.z} ${region.timestamp(position.x, position.z)} ` +
        `${chunkCompressionAsString(raw.compression)} ${raw.data.length} ${plainLength} ${keyCount}`,
    );
    total += 1;
  }

  lines.push(`total ${total}`);
  return `${lines.join("\n")}\n`;
}

/**
 * 全チャンクを読み直し、無圧縮で新しいリージョンへ詰め直して書き出す。
 *
 * 無圧縮にするのは、zlib の出力が処理系ごとに違い、
 * 圧縮したままでは言語間でバイトが一致しないため。
 */
function regionRewrite(source: RegionFile, outputPath: string): void {
  // 途中結果が残らないよう、書き出し先は必ず作り直す
  if (existsSync(outputPath)) {
    rmSync(outputPath);
  }

  const destination = RegionFile.open(outputPath, RegionFileMode.ReadWrite);

  // 読み込んだチャンクを、そのまま出力側へ詰め直す
  for (const position of source.chunkPositions()) {
    const chunk = source.readChunk(position.x, position.z);

    if (chunk === undefined) {
      continue;
    }

    destination.writeChunk(position.x, position.z, chunk, ChunkCompression.None);
    destination.setTimestamp(position.x, position.z, source.timestamp(position.x, position.z));
  }

  destination.flush();
  destination.close();
}


// ---------------------------------------------------------------------------
// チャンク（World レイヤ）
//
// 仕様: docs/spec/90-conformance.md 2.3章
// ---------------------------------------------------------------------------

/**
 * チャンクの全ブロック・全バイオームを走査して集計する。
 *
 * パレットとビットストレージを端から端まで通すので、
 * ビット詰めの実装が 1 か所でもずれれば集計値が変わる。
 */
function chunkDescribe(chunk: Chunk): string {
  const lines: string[] = [
    `chunk ${chunk.x} ${chunk.z} ${chunk.minSectionY} ${chunk.status}`,
  ];
  const blocks = new Map<string, number>();
  const biomes = new Map<string, number>();

  // セクションごとにブロックとバイオームを数え上げる
  for (const sectionY of chunk.sectionYs) {
    const section = chunk.section(sectionY)!;
    let blockPalette = 0;
    let biomePalette = 0;
    let blockBits = 0;
    let biomeBits = 0;

    if (section.hasBlockStates) {
      blockPalette = section.blockStates!.palette.length;
      blockBits = section.blockStates!.bitsPerEntry;
    }

    if (section.hasBiomes) {
      biomePalette = section.biomes!.palette.length;
      biomeBits = section.biomes!.bitsPerEntry;
    }

    lines.push(
      `section ${sectionY} ${blockPalette} ${blockBits} ${biomePalette} ${biomeBits}`,
    );

    // 全ブロックを 1 つずつ読んで、状態の文字列表現ごとに数える
    for (let y = 0; y < 16; y++) {
      for (let z = 0; z < 16; z++) {
        for (let x = 0; x < 16; x++) {
          const block = chunk.getBlock(x, sectionY * 16 + y, z);

          if (block === undefined) {
            continue;
          }

          const key = block.toString();
          blocks.set(key, countOf(blocks, key) + 1);
        }
      }
    }

    // バイオームは 4×4×4 単位なので、4 ブロックおきに見る
    for (let y = 0; y < 16; y += 4) {
      for (let z = 0; z < 16; z += 4) {
        for (let x = 0; x < 16; x += 4) {
          const biome = chunk.getBiome(x, sectionY * 16 + y, z);

          if (biome === undefined) {
            continue;
          }

          biomes.set(biome, countOf(biomes, biome) + 1);
        }
      }
    }
  }

  // 名前の昇順で出すので、内部の並びに関係なく同じ出力になる
  for (const key of [...blocks.keys()].sort()) {
    lines.push(`block ${key} ${blocks.get(key)}`);
  }

  // 名前の昇順で出すので、内部の並びに関係なく同じ出力になる
  for (const key of [...biomes.keys()].sort()) {
    lines.push(`biome ${key} ${biomes.get(key)}`);
  }

  return `${lines.join("\n")}\n`;
}

/**
 * 決まった手順でチャンクを編集する。全言語で同じ結果になるはず。
 *
 * パレット拡張・ビット幅の再計算・未使用要素の掃除を一通り通す。
 */
function chunkEdit(chunk: Chunk): void {
  const baseY = chunk.minSectionY * 16;

  // パレットに無いブロックを次々に置き、ビット幅の拡張を起こす
  for (let index = 0; index < 20; index++) {
    const state = BlockState.parse(`minecraft:edited_${index}[step=${index}]`);
    chunk.setBlock(index % 16, baseY + Math.floor(index / 16), index % 16, state);
  }

  // プロパティ付きのブロックを、名前は同じで状態違いで置く
  chunk.setBlock(1, baseY + 2, 1, BlockState.parse("minecraft:oak_stairs[facing=north,half=top]"));
  chunk.setBlock(2, baseY + 2, 2, BlockState.parse("minecraft:oak_stairs[half=top,facing=north]"));
  chunk.setBlock(3, baseY + 2, 3, BlockState.parse("oak_stairs[facing=south]"));

  // バイオームも書き換える
  chunk.setBiome(0, baseY, 0, "minecraft:desert");
  chunk.setBiome(8, baseY + 8, 8, "minecraft:jungle");

  // 使われなくなったパレット要素を掃除する
  chunk.compact();

  // 高さマップと光源は再計算しないので、無効化して Minecraft に任せる
  chunk.clearHeightmaps();
  chunk.invalidateLighting();
}

/** 集計表から現在の件数を取り出す。まだ無ければ 0。 */
function countOf(counts: Map<string, number>, key: string): number {
  const current = counts.get(key);

  if (current === undefined) {
    return 0;
  }

  return current;
}

/** チャンク NBT のファイルを読む。 */
function readChunkFile(path: string): Chunk {
  // 検証では DataVersion の違いを警告にせず、そのまま読む
  return Chunk.fromNbt(readFile(path).tag, {
    onVersionMismatch: VersionMismatchAction.Ignore,
  });
}

// ---------------------------------------------------------------------------
// コマンド
// ---------------------------------------------------------------------------

/** `--format network` が指定されていればネットワーク形式として読む。 */
function parseFormat(args: string[]): NbtFormat {
  // 3 番目以降の引数からオプションを探す
  for (let index = 3; index < args.length - 1; index++) {
    if (args[index] === "--format" && args[index + 1] === "network") {
      return NbtFormat.Network;
    }
  }

  return NbtFormat.Java;
}

/**
 * 改行を変換せず、BOM も付けずに UTF-8 で書く。
 *
 * 孤立サロゲートを含みうるが、標準の UTF-8 エンコーダは置換文字にしてしまうため、
 * 自前で符号化する（WTF-8）。
 */
function writeTextFile(path: string, content: string): void {
  const bytes: number[] = [];

  // コード単位を順に見て、正しいサロゲートペアだけ 1 文字として符号化する
  for (let index = 0; index < content.length; index++) {
    const unit = content.charCodeAt(index);

    if (unit >= 0xd800 && unit <= 0xdbff && index + 1 < content.length) {
      const low = content.charCodeAt(index + 1);

      if (low >= 0xdc00 && low <= 0xdfff) {
        const codePoint = 0x10000 + ((unit - 0xd800) << 10) + (low - 0xdc00);
        bytes.push(0xf0 | (codePoint >> 18));
        bytes.push(0x80 | ((codePoint >> 12) & 0x3f));
        bytes.push(0x80 | ((codePoint >> 6) & 0x3f));
        bytes.push(0x80 | (codePoint & 0x3f));
        index += 1;
        continue;
      }
    }

    if (unit < 0x80) {
      bytes.push(unit);
    } else if (unit < 0x800) {
      bytes.push(0xc0 | (unit >> 6));
      bytes.push(0x80 | (unit & 0x3f));
    } else {
      // 孤立サロゲートもこの経路で 3 バイト形式のまま書く
      bytes.push(0xe0 | (unit >> 12));
      bytes.push(0x80 | ((unit >> 6) & 0x3f));
      bytes.push(0x80 | (unit & 0x3f));
    }
  }

  writeFileSync(path, Uint8Array.from(bytes));
}

function main(argv: string[]): number {
  if (argv.length === 0) {
    process.stderr.write(`${USAGE}\n`);
    return 2;
  }

  const command = argv[0];

  if (command === "version") {
    process.stdout.write(
      `typescript spring-nbt-library 0.1.0 target_data_version=${TARGET_DATA_VERSION}\n`,
    );
    return 0;
  }

  const known = [
    "decode", "encode", "snbt",
    "region-list", "region-rewrite",
    "chunk-report", "chunk-edit",
  ];

  // 知らないコマンドなら使い方を出して終わる
  if (!known.includes(command)) {
    process.stderr.write(`${USAGE}\n`);
    return 2;
  }

  if (argv.length < 3) {
    process.stderr.write(`${USAGE}\n`);
    return 2;
  }

  const format = parseFormat(argv);

  try {
    if (command === "chunk-report") {
      writeTextFile(argv[2], chunkDescribe(readChunkFile(argv[1])));
      return 0;
    }

    if (command === "chunk-edit") {
      const chunk = readChunkFile(argv[1]);
      chunkEdit(chunk);
      writeFileSync(
        argv[2],
        writeNbtBytes(new NamedTag("", chunk.toNbt()), { compression: Compression.None }),
      );
      return 0;
    }

    if (command === "region-list" || command === "region-rewrite") {
      const region = RegionFile.open(argv[1], RegionFileMode.ReadOnly);

      if (command === "region-list") {
        writeTextFile(argv[2], regionList(region));
      } else {
        regionRewrite(region, argv[2]);
      }

      region.close();
      return 0;
    }

    const named = readFile(argv[1], { format });

    if (command === "decode") {
      writeTextFile(argv[2], normalizedJson(named, format));
    } else if (command === "encode") {
      writeFileSync(argv[2], writeBytes(named, { format, compression: Compression.None }));
    } else {
      writeTextFile(argv[2], `${snbt.write(named.tag)}\n`);
    }
  } catch (error) {
    if (error instanceof SpringNbtError) {
      // 言語間で同じ ErrorCode を出すことが検証対象なので、コードを機械可読な形で出す
      process.stderr.write(`ERROR ${error.code} ${error.message}\n`);
      return 1;
    }

    throw error;
  }

  return 0;
}

process.exitCode = main(process.argv.slice(2));

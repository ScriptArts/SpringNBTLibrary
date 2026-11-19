/**
 * World / Blockレイヤ
 *
 * 他言語版と同じ検証項目を持つ
 * 共通テストベクタによる言語間比較はspec/run-conformance.shが担当し、ここではAPIの振る舞いを直接確かめる
 */

import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { MIN_SUPPORTED_DATA_VERSION, TARGET_DATA_VERSION } from "../src/index.js";
import { ErrorCode, SpringNbtError } from "../src/errors.js";
import {
  BitStorage,
  BlockState,
  Chunk,
  MinecraftWorld,
  PalettedContainer,
  VersionMismatchAction,
  ceilLog2,
} from "../src/world/index.js";
import type { ChunkReadOptions } from "../src/world/index.js";
import type { NbtTag } from "../src/nbt/index.js";
import {
  Compression,
  NamedTag,
  NbtByte,
  NbtCompound,
  NbtInt,
  NbtIntArray,
  NbtList,
  NbtLongArray,
  NbtString,
  TagType,
  readFile,
  writeBytes,
  writeFile,
} from "../src/nbt/index.js";
import { RegionFile, RegionFileMode } from "../src/anvil/index.js";

const HERE = fileURLToPath(new URL(".", import.meta.url));
const REPO_ROOT = join(HERE, "..", "..", "..");
const VECTORS = join(REPO_ROOT, "spec", "testdata", "world");

/** 共通テストベクタ（world/*.nbt）のパス */
function vectorPath(name: string): string {
  return join(VECTORS, `${name}.nbt`);
}

/** テストベクタをチャンクとして読む */
function loadChunk(name: string, options?: ChunkReadOptions): Chunk {
  return Chunk.fromNbt(readFile(vectorPath(name)).tag, options);
}

/**
 * プロパティの無いブロックのパレット要素を作る
 * 26.3からはブロックIDだけの文字列で入る
 */
function blockEntry(name: string): NbtString {
  return new NbtString(name);
}

/** 異種リストの要素を包むCompoundを作る */
function wrapped(tag: NbtTag): NbtCompound {
  const wrapper = new NbtCompound();
  wrapper.set("", tag);
  return wrapper;
}

/** 26.2までの形式（Name / Properties）のパレット要素を作る */
function nameProperties(name: string, properties?: [string, string][]): NbtCompound {
  const entry = new NbtCompound();
  entry.setString("Name", name);

  // プロパティがあるときだけPropertiesを足す
  if (properties !== undefined) {
    const propertiesTag = new NbtCompound();

    // 渡された順に入れる
    for (const [key, value] of properties) {
      propertiesTag.setString(key, value);
    }

    entry.set("Properties", propertiesTag);
  }

  return entry;
}

/** 26.3からの形式（id / properties）のパレット要素を作る */
function idProperties(name: string, properties: [string, string][]): NbtCompound {
  const entry = new NbtCompound();
  entry.setString("id", name);
  const propertiesTag = new NbtCompound();

  // 渡された順に入れる
  for (const [key, value] of properties) {
    propertiesTag.setString(key, value);
  }

  entry.set("properties", propertiesTag);
  return entry;
}

/**
 * 扱える形式の下限より古く、1.13より前でもあるDataVersion
 * どの世代でも解釈しない
 */
const PRE_FLATTENING_DATA_VERSION = 1400;

/** 1.13より前のようにLevelに本体を包み、ブロックを数値IDで持つチャンクを作る */
function preFlatteningChunk(): NbtCompound {
  const section = new NbtCompound();
  section.setByte("Y", 0);
  section.setByteArray("Blocks", new Int8Array(4096).fill(1));
  section.setByteArray("Data", new Int8Array(2048));
  const sections = new NbtList(TagType.Compound);
  sections.add(section);

  const level = new NbtCompound();
  level.setInt("xPos", 3);
  level.setInt("zPos", -2);
  level.set("Sections", sections);

  const root = new NbtCompound();
  root.setInt("DataVersion", PRE_FLATTENING_DATA_VERSION);
  root.set("Level", level);
  return root;
}

/** 1.17までのようにLevelに本体を包んだチャンクを作る */
function levelChunk(dataVersion: number): NbtCompound {
  const level = new NbtCompound();
  level.setInt("xPos", 0);
  level.setInt("zPos", 0);
  level.setString("Status", "full");
  level.set("Sections", new NbtList(TagType.Compound));

  const root = new NbtCompound();
  root.setInt("DataVersion", dataVersion);
  root.set("Level", level);
  return root;
}

/** チャンクのNBTを無圧縮のバイト列にする */
function chunkBytes(tag: NbtCompound): Uint8Array {
  return writeBytes(new NamedTag("", tag), { compression: Compression.None });
}

/** 書き出したチャンクの最初のセクションのブロックのパレット */
function firstBlockPalette(written: NbtCompound): NbtList {
  const section = written.getList("sections").get(0) as NbtCompound;
  return section.getCompound("block_states").getList("palette");
}

/** SpringNbtErrorが指定のコードで投げられることを確かめる */
function assertErrorCode(code: ErrorCode, action: () => unknown): void {
  assert.throws(action, (error: unknown) => {
    assert.ok(error instanceof SpringNbtError);
    assert.equal(error.code, code);
    return true;
  });
}

// ---------------------------------------------------------------------------
// BlockState
// ---------------------------------------------------------------------------

test("BlockState: 名前空間を省略すると minecraft が補われる", () => {
  const state = BlockState.parse("stone");
  assert.equal(state.name, "minecraft:stone");
  assert.equal(state.properties.size, 0);
  assert.equal(state.toString(), "minecraft:stone");
});

test("BlockState: プロパティは名前の昇順に並ぶ", () => {
  const state = BlockState.parse("minecraft:oak_stairs[waterlogged=false,facing=north,half=top]");
  assert.equal(state.toString(), "minecraft:oak_stairs[facing=north,half=top,waterlogged=false]");
});

test("BlockState: 並び順が違っても同じブロックとして等しい", () => {
  const first = BlockState.parse("minecraft:oak_stairs[facing=north,half=top]");
  const second = BlockState.parse("minecraft:oak_stairs[half=top,facing=north]");
  assert.ok(first.equals(second));
});

test("BlockState: 名前が同じでもプロパティが違えば等しくない", () => {
  const first = BlockState.parse("minecraft:oak_stairs[facing=north]");
  const second = BlockState.parse("minecraft:oak_stairs[facing=south]");
  assert.ok(!first.equals(second));
});

test("BlockState: with で作り直しても元は変わらない", () => {
  const original = BlockState.parse("minecraft:oak_stairs[facing=north]");
  const changed = original.with("facing", "south");
  assert.equal(original.property("facing"), "north");
  assert.equal(changed.property("facing"), "south");
});

test("BlockState: 存在しないプロパティは undefined", () => {
  assert.equal(BlockState.parse("minecraft:stone").property("facing"), undefined);
});

test("BlockState: NBT との相互変換でプロパティが保たれる", () => {
  const state = BlockState.parse("minecraft:oak_stairs[facing=north,half=top]");
  const nbt = state.toNbt() as NbtCompound;
  assert.deepEqual([...nbt.keys()], ["id", "properties"]);
  assert.equal(nbt.getString("id"), "minecraft:oak_stairs");
  assert.equal(nbt.getCompound("properties").getString("facing"), "north");
  assert.ok(BlockState.fromNbt(nbt).equals(state));
});

test("BlockState: プロパティ無しのブロックは文字列になる", () => {
  assert.ok(BlockState.parse("minecraft:air").toNbt().equals(new NbtString("minecraft:air")));
});

test("BlockState: 文字列のパレット要素を読める", () => {
  const state = BlockState.fromNbt(new NbtString("minecraft:stone"));
  assert.equal(state.name, "minecraft:stone");
  assert.equal(state.properties.size, 0);
});

test("BlockState: 包まれたパレット要素を読める", () => {
  const state = BlockState.fromNbt(wrapped(new NbtString("minecraft:stone")));
  assert.equal(state.toString(), "minecraft:stone");
});

test("BlockState: properties の無い Compound も読める", () => {
  const entry = new NbtCompound();
  entry.set("id", new NbtString("minecraft:stone"));
  assert.equal(BlockState.fromNbt(entry).toString(), "minecraft:stone");
});

test("BlockState: パレット要素が 26.2 までの形式なら MALFORMED_DATA", () => {
  const entry = new NbtCompound();
  entry.set("Name", new NbtString("minecraft:stone"));
  assertErrorCode(ErrorCode.MalformedData, () => BlockState.fromNbt(entry));
});

test("BlockState: 文字列でも Compound でもない要素は UNEXPECTED_TAG_TYPE", () => {
  assertErrorCode(ErrorCode.UnexpectedTagType, () => BlockState.fromNbt(new NbtInt(1)));
});

test("BlockState: DataVersion 2844 では Name / Properties を読む", () => {
  const properties = new NbtCompound();
  properties.set("facing", new NbtString("north"));
  const entry = new NbtCompound();
  entry.set("Name", new NbtString("minecraft:oak_stairs"));
  entry.set("Properties", properties);

  const state = BlockState.fromNbtForDataVersion(entry, 2844);
  assert.equal(state.toString(), "minecraft:oak_stairs[facing=north]");
});

test("BlockState: DataVersion 2844 で id を持つ要素は MALFORMED_DATA", () => {
  const entry = new NbtCompound();
  entry.set("id", new NbtString("minecraft:stone"));
  assertErrorCode(ErrorCode.MalformedData, () => BlockState.fromNbtForDataVersion(entry, 2844));
});

test("BlockState: DataVersion 2844 で文字列の要素は UNEXPECTED_TAG_TYPE", () => {
  assertErrorCode(ErrorCode.UnexpectedTagType, () =>
    BlockState.fromNbtForDataVersion(new NbtString("minecraft:stone"), 2844));
});

test("BlockState: DataVersion 2844 で Properties の値が文字列でなければ UNEXPECTED_TAG_TYPE", () => {
  const properties = new NbtCompound();
  properties.set("facing", new NbtInt(1));
  const entry = new NbtCompound();
  entry.set("Name", new NbtString("minecraft:oak_stairs"));
  entry.set("Properties", properties);
  assertErrorCode(ErrorCode.UnexpectedTagType, () => BlockState.fromNbtForDataVersion(entry, 2844));
});

test("BlockState: DataVersion 2844 では Name / Properties で書く", () => {
  const plain = BlockState.parse("minecraft:stone").toNbtForDataVersion(2844) as NbtCompound;
  const expected = new NbtCompound();
  expected.set("Name", new NbtString("minecraft:stone"));
  assert.ok(plain.equals(expected));
  assert.equal(plain.containsKey("Properties"), false);

  const stairs = BlockState.parse("minecraft:oak_stairs[half=top,facing=north]");
  const nbt = stairs.toNbtForDataVersion(2844) as NbtCompound;
  assert.deepEqual([...nbt.keys()], ["Name", "Properties"]);
  assert.equal(nbt.getString("Name"), "minecraft:oak_stairs");
  assert.deepEqual([...nbt.getCompound("Properties").keys()], ["facing", "half"]);
  assert.ok(BlockState.fromNbtForDataVersion(nbt, 2844).equals(stairs));
});

for (const dataVersion of [5006, 5023]) {
  test(`BlockState: DataVersion ${dataVersion} は fromNbt / toNbt と同じ`, () => {
    const stairs = BlockState.parse("minecraft:oak_stairs[facing=north,half=top]");
    assert.ok(stairs.toNbtForDataVersion(dataVersion).equals(stairs.toNbt()));

    const plain = BlockState.parse("minecraft:stone");
    assert.ok(plain.toNbtForDataVersion(dataVersion).equals(new NbtString("minecraft:stone")));

    assert.ok(BlockState.fromNbtForDataVersion(new NbtString("minecraft:stone"), dataVersion).equals(plain));
    assert.ok(BlockState.fromNbtForDataVersion(stairs.toNbt(), dataVersion).equals(stairs));
    const wrapper = wrapped(new NbtString("minecraft:stone"));
    assert.ok(
      BlockState.fromNbtForDataVersion(wrapper, dataVersion).equals(BlockState.fromNbt(wrapper)),
    );
  });
}

test("BlockState: DataVersion 1519 で境界の形式を扱える", () => {
  const state = BlockState.parse("minecraft:oak_stairs[facing=north]");
  assert.ok(BlockState.fromNbtForDataVersion(state.toNbtForDataVersion(1519), 1519).equals(state));
});

test("BlockState: DataVersion が 1519 未満なら INVALID_ARGUMENT", () => {
  assertErrorCode(ErrorCode.InvalidArgument, () =>
    BlockState.fromNbtForDataVersion(new NbtString("minecraft:stone"), 1518));
  assertErrorCode(ErrorCode.InvalidArgument, () =>
    BlockState.parse("minecraft:stone").toNbtForDataVersion(1518));
});

test("BlockState: 壊れた文字列は INVALID_ARGUMENT", () => {
  const broken = [
    "",
    "minecraft:oak_stairs[facing=north",
    "minecraft:oak_stairs[facing]",
    "minecraft:oak_stairs[facing=north,facing=south]",
    "minecraft:oak_stairs[]extra",
  ];

  // 崩し方ごとに同じエラーコードになることを確かめる
  for (const text of broken) {
    assertErrorCode(ErrorCode.InvalidArgument, () => BlockState.parse(text));
  }
});

// ---------------------------------------------------------------------------
// BitStorage
// ---------------------------------------------------------------------------

test("BitStorage: 必要な long 数は跨ぎなしで求まる", () => {
  assert.equal(BitStorage.longCount(4, 4096), 256);
  assert.equal(BitStorage.longCount(5, 4096), 342);
  assert.equal(BitStorage.longCount(1, 64), 1);
  assert.equal(BitStorage.longCount(6, 64), 7);
});

test("BitStorage: またぐ詰め方で long 数が合う", () => {
  assert.equal(BitStorage.longCountWith(5, 4096, true), 320);
  assert.equal(BitStorage.longCountWith(4, 4096, true), 256);
});

test("BitStorage: またぐ詰め方では値が 64bit の境目をまたいで並ぶ", () => {
  const storage = BitStorage.createWith(5, 4096, true);

  // 添字12はビット60から64までなので、data[0]の上位4bitとdata[1]の最下位bitに分かれる
  storage.set(12, 0b10111);
  const longs = storage.toLongs();

  assert.equal((BigInt.asUintN(64, longs[0]) >> 60n) & 0b1111n, 0b0111n);
  assert.equal(longs[1] & 1n, 1n);
  assert.equal(storage.get(12), 0b10111);
});

test("BitStorage: またぐ詰め方で境目の値を上書きしても隣が壊れない", () => {
  const storage = BitStorage.createWith(5, 4096, true);
  storage.set(11, 0b11111);
  storage.set(13, 0b11111);

  // 添字12は境目をまたぐので、書き込みのたびに両隣が保たれるか確かめる
  for (const value of [0b11111, 0b00000, 0b10101]) {
    storage.set(12, value);
    assert.equal(storage.get(12), value);
    assert.equal(storage.get(11), 0b11111);
    assert.equal(storage.get(13), 0b11111);
  }
});

test("BitStorage: またぐ詰め方で最後の long の末尾まで読み書きできる", () => {
  const storage = BitStorage.createWith(5, 4096, true);
  storage.set(4094, 0b10101);
  storage.set(4095, 0b11011);

  // 添字4095はビット20475から20479で、最後のlongのビット59から63に収まる
  assert.equal(storage.get(4094), 0b10101);
  assert.equal(storage.get(4095), 0b11011);
  assert.equal(BigInt.asUintN(64, storage.toLongs()[319]) >> 59n, 0b11011n);
});

test("BitStorage: 書いた値をそのまま読み出せる", () => {
  const storage = BitStorage.create(5, 4096);

  // 全エントリに位置由来の値を書いて、取りこぼしが無いか確かめる
  for (let index = 0; index < 4096; index++) {
    storage.set(index, index % 32);
  }

  for (let index = 0; index < 4096; index++) {
    assert.equal(storage.get(index), index % 32);
  }
});

test("BitStorage: long 境界を跨がずに詰める", () => {
  const storage = BitStorage.create(5, 4096);

  // bits=5なら1つのlongに12個
  // 添字12は次のlongの最下位から始まる
  storage.set(11, 31);
  storage.set(12, 1);
  const longs = storage.toLongs();

  assert.equal(longs[0], 31n << 55n);
  assert.equal(longs[1], 1n);
});

test("BitStorage: ビット幅を広げても値が保たれる", () => {
  const storage = BitStorage.create(4, 4096);

  for (let index = 0; index < 4096; index++) {
    storage.set(index, index % 16);
  }

  const widened = storage.resize(5);
  assert.equal(widened.bitsPerEntry, 5);
  assert.equal(widened.toLongs().length, 342);

  for (let index = 0; index < 4096; index++) {
    assert.equal(widened.get(index), index % 16);
  }
});

test("BitStorage: ビット幅に対して長さが合わない配列は MALFORMED_DATA", () => {
  assertErrorCode(ErrorCode.MalformedData, () =>
    BitStorage.fromLongs(new BigInt64Array(100), 4, 4096, false),
  );
});

test("BitStorage: 寛容モードなら長さからビット幅を逆算する", () => {
  // 4096エントリを342 longで表せるのはbits=5のときだけ
  const storage = BitStorage.fromLongs(new BigInt64Array(342), 4, 4096, true);
  assert.equal(storage.bitsPerEntry, 5);
});

test("BitStorage: ビット幅に収まらない値は INVALID_ARGUMENT", () => {
  const storage = BitStorage.create(4, 64);
  assertErrorCode(ErrorCode.InvalidArgument, () => storage.set(0, 16));
});

test("BitStorage: 範囲外の添字は INVALID_ARGUMENT", () => {
  const storage = BitStorage.create(4, 64);
  assertErrorCode(ErrorCode.InvalidArgument, () => storage.get(64));
});

// ---------------------------------------------------------------------------
// PalettedContainer
// ---------------------------------------------------------------------------

test("PalettedContainer: 必要ビット数は ceilLog2", () => {
  assert.equal(ceilLog2(1), 0);
  assert.equal(ceilLog2(2), 1);
  assert.equal(ceilLog2(4), 2);
  assert.equal(ceilLog2(5), 3);
  assert.equal(ceilLog2(17), 5);
});

test("PalettedContainer: またぐ詰め方のコンテナは17種類目でビット幅が5になる", () => {
  const palette: NbtTag[] = [];

  for (let index = 0; index < 16; index++) {
    palette.push(blockEntry(`minecraft:block_${index}`));
  }

  const container = PalettedContainer.fromParts(
    palette,
    new BigInt64Array(256),
    4096,
    4,
    true,
    false,
    false,
  );
  assert.equal(container.bitsPerEntry, 4);

  // 全エントリに位置由来の値を書いてから、17種類目を1つ足す
  for (let index = 0; index < 4096; index++) {
    container.set(index, blockEntry(`minecraft:block_${index % 16}`));
  }

  container.set(7, blockEntry("minecraft:block_16"));
  assert.equal(container.bitsPerEntry, 5);
  const grownData = container.toParts().data;
  assert.ok(grownData !== undefined);
  assert.equal(grownData.length, 320);

  for (let index = 0; index < 4096; index++) {
    let expected = `minecraft:block_${index % 16}`;

    if (index === 7) {
      expected = "minecraft:block_16";
    }

    assert.deepEqual(container.get(index), new NbtString(expected));
  }
});

for (const spanning of [false, true]) {
  test(`PalettedContainer: dataが必ず書かれる形式なら1要素のパレットでもビット幅4のdataを返す（spanning=${spanning}）`, () => {
    const container = PalettedContainer.fromParts(
      [blockEntry("minecraft:air")],
      undefined,
      4096,
      4,
      spanning,
      true,
      false,
    );

    const parts = container.toParts();
    assert.equal(parts.palette.length, 1);
    assert.ok(parts.data !== undefined);
    assert.equal(parts.data.length, 256);
  });
}

test("PalettedContainer: 単一値のコンテナは data を持たない", () => {
  const container = PalettedContainer.filled(blockEntry("minecraft:air"), 4096, 4);
  assert.equal(container.bitsPerEntry, 0);

  const nbt = container.toNbt();
  assert.equal(nbt.optLongArray("data"), undefined);
  assert.equal(nbt.getList("palette").size, 1);
});

test("PalettedContainer: 値を足すとパレットとビット幅が広がる", () => {
  const container = PalettedContainer.filled(blockEntry("minecraft:air"), 4096, 4);

  // 17種のブロックを足してパレットを18要素にし、bits=4から5への拡張を起こす
  for (let index = 0; index < 17; index++) {
    container.set(index, blockEntry(`minecraft:block_${index}`));
  }

  assert.equal(container.palette.length, 18);
  assert.equal(container.bitsPerEntry, 5);
  assert.equal(container.toNbt().getLongArray("data").length, 342);
});

test("PalettedContainer: 書き出しは data が先で palette が後", () => {
  // 実データがこの順なので、無変更で書き戻したときにバイト単位で一致する
  const container = PalettedContainer.filled(blockEntry("minecraft:air"), 4096, 4);
  container.set(0, blockEntry("minecraft:stone"));

  assert.deepEqual([...container.toNbt().keys()], ["data", "palette"]);
});

test("PalettedContainer: compact で未使用のパレット要素が消える", () => {
  const container = PalettedContainer.filled(blockEntry("minecraft:air"), 4096, 4);
  container.set(0, blockEntry("minecraft:stone"));
  container.set(0, blockEntry("minecraft:dirt"));
  assert.equal(container.palette.length, 3);

  container.compact();

  // 残るのは実際に使われているairとdirtの2つ
  assert.equal(container.palette.length, 2);
  assert.equal((container.get(0) as NbtString).value, "minecraft:dirt");
});

test("PalettedContainer: fill で単一値に戻る", () => {
  const container = PalettedContainer.filled(blockEntry("minecraft:air"), 4096, 4);
  container.set(0, blockEntry("minecraft:stone"));
  container.fill(blockEntry("minecraft:water"));

  assert.equal(container.palette.length, 1);
  assert.equal(container.bitsPerEntry, 0);
  assert.equal((container.get(4095) as NbtString).value, "minecraft:water");
});

test("PalettedContainer: 文字列だけのパレットは文字列のリストで書く", () => {
  const container = PalettedContainer.filled(blockEntry("minecraft:air"), 4096, 4);
  container.set(0, blockEntry("minecraft:stone"));

  const palette = container.toNbt().getList("palette");
  assert.equal(palette.elementType, TagType.String);
  assert.ok(palette.get(1).equals(new NbtString("minecraft:stone")));
});

test("PalettedContainer: 型が混ざったパレットは文字列を包んで Compound のリストで書く", () => {
  const stairs = BlockState.parse("minecraft:oak_stairs[facing=north]").toNbt();
  const container = PalettedContainer.filled(blockEntry("minecraft:air"), 4096, 4);
  container.set(0, stairs);

  const palette = container.toNbt().getList("palette");
  assert.equal(palette.elementType, TagType.Compound);
  assert.ok(palette.get(0).equals(wrapped(new NbtString("minecraft:air"))));
  assert.ok(palette.get(1).equals(stairs));
});

test("PalettedContainer: 包まれたパレットは包みを外して持ち元どおりに書き戻す", () => {
  const stairs = BlockState.parse("minecraft:oak_stairs[facing=north]").toNbt();
  const palette = new NbtList(TagType.Compound);
  palette.add(wrapped(new NbtString("minecraft:air")));
  palette.add(stairs);

  // パレット2要素ならbits=4で256 long
  const nbt = new NbtCompound();
  nbt.set("data", new NbtLongArray(new BigInt64Array(256)));
  nbt.set("palette", palette);

  const container = PalettedContainer.fromNbt(nbt, 4096, 4);

  // 包みは外れ、要素は文字列とCompoundとして並ぶ
  assert.ok(container.palette[0].equals(new NbtString("minecraft:air")));
  assert.ok(container.palette[1].equals(stairs));

  // 書き戻すと、また包まれて元と同じになる
  assert.ok(container.toNbt().equals(nbt));
});

test("PalettedContainer: compact で Compound が消えると文字列のリストに戻る", () => {
  const stairs = BlockState.parse("minecraft:oak_stairs[facing=north]").toNbt();
  const container = PalettedContainer.filled(blockEntry("minecraft:air"), 4096, 4);
  container.set(0, stairs);
  container.set(0, blockEntry("minecraft:stone"));

  container.compact();

  const palette = container.toNbt().getList("palette");
  assert.equal(palette.elementType, TagType.String);
  assert.equal(palette.size, 2);
});

test("PalettedContainer: 範囲外の添字は INVALID_ARGUMENT", () => {
  const container = PalettedContainer.filled(blockEntry("minecraft:air"), 4096, 4);
  assertErrorCode(ErrorCode.InvalidArgument, () => container.get(4096));
});

// ---------------------------------------------------------------------------
// Chunk
// ---------------------------------------------------------------------------

test("Chunk: パレット 1 要素のチャンクを読める", () => {
  const chunk = loadChunk("palette_1");

  assert.equal(chunk.dataVersion, TARGET_DATA_VERSION);
  assert.equal(chunk.x, 0);
  assert.equal(chunk.z, 0);
  assert.equal(chunk.minSectionY, -4);
  assert.ok(chunk.isFullyGenerated);
  assert.deepEqual(chunk.sectionYs, [-4]);
  assert.equal(chunk.getBlock(0, -64, 0)?.name, "minecraft:air");
  assert.equal(chunk.getBiome(0, -64, 0), "minecraft:plains");
});

test("Chunk: ビット幅 5 のチャンクを端から端まで読める", () => {
  const chunk = loadChunk("palette_17");
  const head = ["minecraft:air", "minecraft:stone"];

  // ベクタの添字は (位置 * 11) % 17
  // パレットの先頭2つだけ名前が違う
  for (let position = 0; position < 4096; position++) {
    const paletteIndex = (position * 11) % 17;
    const block = chunk.getBlock(position & 15, -64 + (position >> 8), (position >> 4) & 15);
    assert.ok(block !== undefined);

    if (paletteIndex < 2) {
      assert.equal(block.toString(), head[paletteIndex]);
    } else {
      assert.equal(block.toString(), `minecraft:stone[variant=v${paletteIndex - 2}]`);
    }
  }
});

test("Chunk: セクションの無い高さは undefined", () => {
  const chunk = loadChunk("palette_1");
  assert.equal(chunk.getBlock(0, 100, 0), undefined);
  assert.equal(chunk.section(0), undefined);
});

test("Chunk: 生成途中のチャンクは full ではない", () => {
  const chunk = loadChunk("proto_chunk");
  assert.equal(chunk.status, "minecraft:structure_starts");
  assert.ok(!chunk.isFullyGenerated);
});

test("Chunk: ブロックを置くとその場所だけ変わる", () => {
  const chunk = loadChunk("palette_1");
  chunk.setBlock(3, -60, 7, BlockState.parse("minecraft:oak_stairs[facing=north,half=top]"));

  assert.equal(chunk.getBlock(3, -60, 7)?.toString(), "minecraft:oak_stairs[facing=north,half=top]");
  assert.equal(chunk.getBlock(3, -60, 6)?.name, "minecraft:air");
  assert.equal(chunk.getBlock(4, -60, 7)?.name, "minecraft:air");
});

test("Chunk: ブロックを文字列でも置ける", () => {
  const chunk = loadChunk("palette_1");
  chunk.setBlock(3, -60, 7, "minecraft:oak_stairs[facing=north,half=top]");

  assert.equal(chunk.getBlock(3, -60, 7)?.toString(), "minecraft:oak_stairs[facing=north,half=top]");
});

test("Chunk: 変更したチャンクには印が付く", () => {
  const chunk = loadChunk("palette_1");
  assert.equal(chunk.isModified, false);

  chunk.setBlock(3, -60, 7, "minecraft:stone");
  assert.equal(chunk.isModified, true);

  // 保存済みとして印を外せる
  chunk.isModified = false;
  assert.equal(chunk.isModified, false);

  // 同じ状態を置き直すだけなら何も起きないので印も付かない
  chunk.setBlock(3, -60, 7, "minecraft:stone");
  assert.equal(chunk.isModified, false);

  chunk.clearHeightmaps();
  assert.equal(chunk.isModified, true);
});

test("Chunk: バイオームは 4 ブロック単位で効く", () => {
  const chunk = loadChunk("palette_1");
  chunk.setBiome(0, -64, 0, "minecraft:desert");

  // 同じ4×4×4の枠内はまとめて変わる
  assert.equal(chunk.getBiome(3, -61, 3), "minecraft:desert");
  assert.equal(chunk.getBiome(4, -64, 0), "minecraft:plains");
});

test("Chunk: compact で未使用のパレット要素が消える", () => {
  const chunk = loadChunk("palette_unused");
  const before = chunk.section(-4)?.toNbt();
  assert.equal(before?.getCompound("block_states").getList("palette").size, 4);

  chunk.compact();

  const after = chunk.section(-4)?.toNbt();
  assert.equal(after?.getCompound("block_states").getList("palette").size, 2);
});

test("Chunk: 無変更で書き戻すと元と同じ NBT になる", () => {
  const named = readFile(vectorPath("multi_section"));
  const before = writeBytes(named, { compression: Compression.None });

  const chunk = Chunk.fromNbt(named.tag);
  const after = writeBytes(new NamedTag(named.name, chunk.toNbt()), {
    compression: Compression.None,
  });

  assert.deepEqual(after, before);
});

test("Chunk: ブロックを置き換えると同じ座標の付随データが消える", () => {
  const chunk = loadChunk("block_entities");
  assert.equal(chunk.raw.getList("block_entities").size, 3);
  assert.equal(chunk.raw.getList("block_ticks").size, 2);
  assert.equal(chunk.raw.getList("fluid_ticks").size, 1);

  // (0,-64,0)にはchestとblock_tick、(1,-64,1)にはfurnaceとfluid_tickがある
  chunk.setBlock(0, -64, 0, BlockState.parse("minecraft:stone"));
  chunk.setBlock(1, -64, 1, BlockState.parse("minecraft:stone"));

  const entities = chunk.raw.getList("block_entities");

  // 触っていない(15,-50,15)のbarrelだけが残る
  assert.equal(entities.size, 1);
  assert.equal((entities.get(0) as NbtCompound).getString("id"), "minecraft:barrel");

  const ticks = chunk.raw.getList("block_ticks");
  assert.equal(ticks.size, 1);
  assert.equal((ticks.get(0) as NbtCompound).getInt("x"), 15);

  assert.equal(chunk.raw.getList("fluid_ticks").size, 0);
});

test("Chunk: 同じブロックを置き直しても付随データは消えない", () => {
  const chunk = loadChunk("block_entities");
  const current = chunk.getBlock(0, -64, 0);
  assert.ok(current !== undefined);

  // 変化が無いなら付随データを触る理由がない
  chunk.setBlock(0, -64, 0, current);

  assert.equal(chunk.raw.getList("block_entities").size, 3);
  assert.equal(chunk.raw.getList("block_ticks").size, 2);
});

test("Chunk: 別のチャンクの同じ相対座標は消さない", () => {
  // 付随データは絶対座標で持つので、チャンク座標を間違えると無関係な要素を消してしまう
  const root = readFile(vectorPath("block_entities")).tag;
  root.set("xPos", new NbtInt(1));
  root.set("zPos", new NbtInt(1));

  const chunk = Chunk.fromNbt(root);
  chunk.setBlock(0, -64, 0, BlockState.parse("minecraft:stone"));

  // このチャンクの(0,-64,0)は絶対座標(16,-64,16)
  // どれとも一致しない
  assert.equal(chunk.raw.getList("block_entities").size, 3);
});

test("Chunk: 高さマップと光源を無効化できる", () => {
  const chunk = loadChunk("palette_1");
  chunk.clearHeightmaps();
  chunk.invalidateLighting();

  const raw = chunk.toNbt();
  assert.equal(raw.optCompound("Heightmaps"), undefined);
  assert.equal(raw.getBool("isLightOn"), false);
});

test("Chunk: 添字が範囲外のチャンクは MALFORMED_DATA", () => {
  assertErrorCode(ErrorCode.MalformedData, () => loadChunk("palette_index_out_of_range"));
});

test("Chunk: data 長が合わないチャンクは MALFORMED_DATA", () => {
  assertErrorCode(ErrorCode.MalformedData, () => loadChunk("bitstorage_wrong_length"));
});

test("Chunk: チャンク内の相対座標が範囲外なら INVALID_ARGUMENT", () => {
  const chunk = loadChunk("palette_1");
  assertErrorCode(ErrorCode.InvalidArgument, () => chunk.getBlock(16, -64, 0));
});

// ---------------------------------------------------------------------------
// DataVersionの扱い
// ---------------------------------------------------------------------------

/** DataVersionだけを、扱える形式の下限より古い値に差し替えたチャンクを作る */
function foreignChunk(): NbtCompound {
  const root = readFile(vectorPath("palette_1")).tag;
  root.set("DataVersion", new NbtInt(PRE_FLATTENING_DATA_VERSION));
  return root;
}

test("DataVersion: 既定では警告として通す", () => {
  const warnings: string[] = [];
  const chunk = Chunk.fromNbt(foreignChunk(), {
    onVersionMismatch: VersionMismatchAction.Warn,
    onWarning: (message: string) => warnings.push(message),
  });

  assert.equal(chunk.dataVersion, PRE_FLATTENING_DATA_VERSION);
  assert.equal(warnings.length, 1);
});

test("DataVersion: 26.2 のチャンクは警告を出さずに読める", () => {
  const warnings: string[] = [];

  // 26.2の形式も扱う形式に含まれる
  loadChunk("palette_old_format", {
    onVersionMismatch: VersionMismatchAction.Warn,
    onWarning: (message: string) => warnings.push(message),
  });

  assert.equal(warnings.length, 0);
});

test("DataVersion: 扱える形式の下限は 1.18", () => {
  assert.equal(MIN_SUPPORTED_DATA_VERSION, 2844);
});

test("DataVersion: Error を指定すると読み込みで弾く", () => {
  assertErrorCode(ErrorCode.UnsupportedDataVersion, () =>
    Chunk.fromNbt(foreignChunk(), { onVersionMismatch: VersionMismatchAction.Error }),
  );
});

test("DataVersion: Ignore なら何も起きない", () => {
  const warnings: string[] = [];
  Chunk.fromNbt(foreignChunk(), {
    onVersionMismatch: VersionMismatchAction.Ignore,
    onWarning: (message: string) => warnings.push(message),
  });

  assert.equal(warnings.length, 0);
});

test("DataVersion: 別バージョン由来のチャンクは既定で書き戻せない", () => {
  const chunk = Chunk.fromNbt(foreignChunk(), {
    onVersionMismatch: VersionMismatchAction.Ignore,
  });

  assertErrorCode(ErrorCode.UnsupportedDataVersion, () => chunk.toNbt());
});

test("DataVersion: 許可すれば古いチャンクも元のバージョンのまま書き戻せる", () => {
  const chunk = Chunk.fromNbt(foreignChunk(), {
    onVersionMismatch: VersionMismatchAction.Ignore,
  });

  // DataVersionは読んだ値のまま残す
  assert.equal(
    chunk.toNbt({ allowForeignDataVersion: true }).getInt("DataVersion"),
    PRE_FLATTENING_DATA_VERSION,
  );
});

/** 対象より新しいDataVersionを持つチャンクを作る */
function newerChunk(): NbtCompound {
  const root = readFile(vectorPath("palette_1")).tag;
  root.setInt("DataVersion", 5100);
  return root;
}

test("DataVersion: 新しいバージョンのチャンクは警告を出さない", () => {
  const warnings: string[] = [];

  // 形式が同じであれば、新しいバージョンでも警告を出さずに読める
  const chunk = Chunk.fromNbt(newerChunk(), {
    onVersionMismatch: VersionMismatchAction.Warn,
    onWarning: (message) => warnings.push(message),
  });

  assert.equal(chunk.dataVersion, 5100);
  assert.deepEqual(warnings, []);
});

test("DataVersion: 新しいバージョンのチャンクはエラー設定でも通る", () => {
  const chunk = Chunk.fromNbt(newerChunk(), {
    onVersionMismatch: VersionMismatchAction.Error,
  });

  assert.equal(chunk.dataVersion, 5100);
});

test("DataVersion: 新しいバージョンのチャンクはそのまま書き戻せる", () => {
  const chunk = Chunk.fromNbt(newerChunk());

  // 許可を出さなくても書き戻せて、DataVersionも変わらない
  assert.equal(chunk.toNbt().getInt("DataVersion"), 5100);
});

test("DataVersion: 対象バージョンのチャンクはそのまま書き戻せる", () => {
  const chunk = loadChunk("palette_1");
  assert.equal(chunk.toNbt().getInt("DataVersion"), TARGET_DATA_VERSION);
});

// ---------------------------------------------------------------------------
// チャンクの形式の世代
// ---------------------------------------------------------------------------

test("ChunkFormat: DataVersion 4903 のチャンクを読み無変更で書き戻すと元と同じになる", () => {
  const tag = readFile(vectorPath("v4903_edit")).tag;
  const before = chunkBytes(tag);
  const chunk = Chunk.fromNbt(tag);

  // ベクタの添字は (位置 * 7) % 5
  assert.equal(chunk.dataVersion, 4903);
  assert.equal(chunk.getBlock(0, -64, 0)!.toString(), "minecraft:air");
  assert.equal(chunk.getBlock(1, -64, 0)!.toString(), "minecraft:dirt");
  assert.equal(chunk.getBlock(2, -64, 0)!.toString(), "minecraft:oak_stairs[facing=west,half=top]");
  assert.equal(chunk.getBlock(3, -64, 0)!.toString(), "minecraft:stone");
  assert.equal(chunk.getBlock(4, -64, 0)!.toString(), "minecraft:oak_stairs[facing=east,half=bottom]");
  assert.equal(chunk.getBiome(0, -64, 0), "minecraft:plains");

  assert.deepEqual(chunkBytes(chunk.toNbt()), before);
});

test("ChunkFormat: DataVersion 4903 のチャンクに置いたブロックは Name / Properties で入る", () => {
  const chunk = loadChunk("v4903_edit");
  chunk.setBlock(5, -64, 5, BlockState.parse("minecraft:oak_stairs[facing=north]"));
  const written = chunk.toNbt();

  // パレットの末尾に26.2の形式で足される
  const palette = firstBlockPalette(written);
  assert.ok(palette.get(palette.size - 1).equals(nameProperties("minecraft:oak_stairs", [["facing", "north"]])));

  // DataVersionは読んだ値のまま
  assert.equal(written.getInt("DataVersion"), 4903);

  // 読み直しても同じ状態が返る
  const reread = Chunk.fromNbt(written);
  assert.equal(reread.getBlock(5, -64, 5)!.toString(), "minecraft:oak_stairs[facing=north]");
});

test("ChunkFormat: 形式の違うチャンクはそれぞれ読んだ形式で書き出す", () => {
  const older = loadChunk("v4903_edit");
  const newer = loadChunk("palette_5");

  // 2つのチャンクに同じ手順で同じブロックを置く
  for (const chunk of [older, newer]) {
    chunk.setBlock(5, -64, 5, BlockState.parse("minecraft:oak_stairs[facing=north]"));
    chunk.setBlock(6, -64, 6, BlockState.parse("minecraft:edited_plain"));
  }

  const olderWritten = older.toNbt();
  const olderPalette = firstBlockPalette(olderWritten);
  assert.ok(
    olderPalette
      .get(olderPalette.size - 2)
      .equals(nameProperties("minecraft:oak_stairs", [["facing", "north"]])),
  );
  assert.ok(olderPalette.get(olderPalette.size - 1).equals(nameProperties("minecraft:edited_plain")));
  assert.equal(olderWritten.getInt("DataVersion"), 4903);

  const newerWritten = newer.toNbt();
  const newerPalette = firstBlockPalette(newerWritten);

  // 型の混ざったパレットはCompoundのリストになり、文字列の要素だけが包まれる
  assert.ok(
    newerPalette
      .get(newerPalette.size - 2)
      .equals(idProperties("minecraft:oak_stairs", [["facing", "north"]])),
  );
  assert.ok(
    newerPalette.get(newerPalette.size - 1).equals(wrapped(new NbtString("minecraft:edited_plain"))),
  );
  assert.equal(newerWritten.getInt("DataVersion"), TARGET_DATA_VERSION);
});

test("ChunkFormat: 指定した世代と Level の有無が食い違えば MALFORMED_DATA", () => {
  // Levelを持つチャンクを、Levelの無い世代で読ませる
  assertErrorCode(ErrorCode.MalformedData, () =>
    Chunk.fromNbt(levelChunk(2586), {
      onVersionMismatch: VersionMismatchAction.Ignore,
      formatDataVersion: 5023,
    }),
  );
});

test("ChunkFormat: 世代を指定しても下限より古いチャンクは書き戻せない", () => {
  const chunk = Chunk.fromNbt(preFlatteningChunk(), {
    onVersionMismatch: VersionMismatchAction.Ignore,
    formatDataVersion: 5023,
  });

  assertErrorCode(ErrorCode.UnsupportedDataVersion, () => chunk.toNbt());
});

test("ChunkFormat: 世代に 1519 未満を指定すると INVALID_ARGUMENT", () => {
  assertErrorCode(ErrorCode.InvalidArgument, () =>
    loadChunk("palette_1", { formatDataVersion: 1518 }),
  );
});

test("ChunkFormat: DataVersion が 1519 未満のチャンクは元の NBT だけを持つ", () => {
  const root = preFlatteningChunk();
  const before = chunkBytes(root);
  const chunk = Chunk.fromNbt(root, { onVersionMismatch: VersionMismatchAction.Ignore });

  // 座標はLevelの中から読み、セクションは解釈しない
  assert.equal(chunk.x, 3);
  assert.equal(chunk.z, -2);
  assert.deepEqual(chunk.sectionYs, []);

  // ブロック・バイオーム・高さマップ・光源の操作はどれも受け付けない
  const operations: (() => unknown)[] = [
    () => chunk.getBlock(0, 0, 0),
    () => chunk.setBlock(0, 0, 0, "minecraft:stone"),
    () => chunk.getBiome(0, 0, 0),
    () => chunk.setBiome(0, 0, 0, "minecraft:plains"),
    () => chunk.clearHeightmaps(),
    () => chunk.invalidateLighting(),
  ];

  // 操作ごとにUNSUPPORTED_DATA_VERSIONになることを確かめる
  for (const operation of operations) {
    assertErrorCode(ErrorCode.UnsupportedDataVersion, operation);
  }

  // 許可すれば、読んだNBTがそのまま返る
  assert.deepEqual(chunkBytes(chunk.toNbt({ allowForeignDataVersion: true })), before);
});

test("ChunkFormat: 世代を選んだ DataVersion を返す", () => {
  const tag = readFile(vectorPath("v4903_edit")).tag;
  assert.equal(Chunk.fromNbt(tag).formatDataVersion, 4903);

  // 指定すれば、チャンク自身のDataVersionではなくその値になる
  const chunk = Chunk.fromNbt(tag, { formatDataVersion: 5023 });
  assert.equal(chunk.formatDataVersion, 5023);
  assert.equal(chunk.dataVersion, 4903);
});

// ---------------------------------------------------------------------------
// MinecraftWorld
// ---------------------------------------------------------------------------

test("MinecraftWorld: 存在しないディレクトリは IO", () => {
  const missing = join(tmpdir(), "springnbt-missing-world");
  assertErrorCode(ErrorCode.Io, () => MinecraftWorld.open(missing));
});

test("MinecraftWorld: level.dat が無いディレクトリは IO", () => {
  const work = mkdtempSync(join(tmpdir(), "springnbt-world-"));

  try {
    assertErrorCode(ErrorCode.Io, () => MinecraftWorld.open(work));
  } finally {
    // テストごとに作った一時ディレクトリを片付ける
    rmSync(work, { recursive: true, force: true });
  }
});

test("MinecraftWorld: 次元経由で読んだチャンクの警告も通知先へ届く", () => {
  const work = mkdtempSync(join(tmpdir(), "springnbt-world-"));

  try {
    const region = join(work, "dimensions", "minecraft", "overworld", "region");
    mkdirSync(region, { recursive: true });

    // DataVersionが扱える形式より古いチャンクを1つだけ持つワールドを作る
    writeLevel(work, { DataVersion: new NbtInt(5023) });

    const file = RegionFile.open(join(region, "r.0.0.mca"), RegionFileMode.ReadWrite);
    file.writeChunk(0, 0, foreignChunk());
    file.close();

    const warnings: string[] = [];
    const world = MinecraftWorld.open(work, { chunkRead: { onWarning: (message) => warnings.push(message) } });
    const overworld = world.dimension("minecraft:overworld");
    assert.ok(overworld !== undefined);
    assert.ok(overworld.chunk(0, 0) !== undefined);
    world.close();

    // ワールドを開くときに渡した通知先が、次元経由の読み込みでも呼ばれる
    assert.equal(warnings.length, 1);
  } finally {
    // テストごとに作った一時ディレクトリを片付ける
    rmSync(work, { recursive: true, force: true });
  }
});

// ---------------------------------------------------------------------------
// ワールドの構成の世代（L1とL2）
// ---------------------------------------------------------------------------

/** `Data`に指定の項目だけを持つlevel.datを書く */
function writeLevel(directory: string, entries: Record<string, NbtTag>): void {
  const data = new NbtCompound();

  for (const [key, tag] of Object.entries(entries)) {
    data.set(key, tag);
  }

  const root = new NbtCompound();
  root.set("Data", data);
  writeFile(join(directory, "level.dat"), new NamedTag("", root));
}

/** 指定の項目を持つ.datを、フォルダごと作って書く */
function writeDat(path: string, entries: Record<string, NbtTag>): void {
  mkdirSync(dirname(path), { recursive: true });
  const root = new NbtCompound();

  for (const [key, tag] of Object.entries(entries)) {
    root.set(key, tag);
  }

  writeFile(path, new NamedTag("", root));
}

/** 一時フォルダを作って渡し、終わったら消す */
function withTempWorld(body: (directory: string) => void): void {
  const work = mkdtempSync(join(tmpdir(), "springnbt-layout-"));

  try {
    body(work);
  } finally {
    // テストごとに作った一時ディレクトリを片付ける
    rmSync(work, { recursive: true, force: true });
  }
}

/** L1の合成ワールドを作る */
function makeL1World(directory: string): void {
  writeLevel(directory, { DataVersion: new NbtInt(3953) });

  for (const folder of ["region", "DIM-1/region", "DIM1/region", "dimensions/mymap/arena/region"]) {
    mkdirSync(join(directory, folder), { recursive: true });
  }
}

test("WorldLayout: world_l1_dimensions", () => {
  withTempWorld((work) => {
    makeL1World(work);
    const world = MinecraftWorld.open(work);

    try {
      assert.deepEqual(world.dimensionIds(), [
        "minecraft:overworld",
        "minecraft:the_nether",
        "minecraft:the_end",
        "mymap:arena",
      ]);
      assert.equal(world.dimension("minecraft:overworld")!.directory, work);
      assert.equal(world.dimension("minecraft:the_nether")!.directory, join(work, "DIM-1"));
      assert.equal(world.dimension("minecraft:the_end")!.directory, join(work, "DIM1"));
      assert.equal(world.dimension("mymap:arena")!.directory, join(work, "dimensions", "mymap", "arena"));

      // 次元が無ければundefined
      assert.equal(world.dimension("mymap:missing"), undefined);
    } finally {
      world.close();
    }
  });
});

test("WorldLayout: L1で存在しない標準の次元は並ばない", () => {
  withTempWorld((work) => {
    writeLevel(work, { DataVersion: new NbtInt(3953) });
    mkdirSync(join(work, "region"));
    const world = MinecraftWorld.open(work);

    try {
      assert.deepEqual(world.dimensionIds(), ["minecraft:overworld"]);
      assert.equal(world.dimension("minecraft:the_nether"), undefined);
    } finally {
      world.close();
    }
  });
});

test("WorldLayout: L1では dimensions の下の標準の次元は並ばない", () => {
  withTempWorld((work) => {
    writeLevel(work, { DataVersion: new NbtInt(3953) });
    mkdirSync(join(work, "dimensions", "minecraft", "the_nether", "region"), { recursive: true });
    const world = MinecraftWorld.open(work);

    try {
      assert.ok(!world.dimensionIds().includes("minecraft:the_nether"));
      assert.equal(world.dimension("minecraft:the_nether"), undefined);
    } finally {
      world.close();
    }
  });
});

test("WorldLayout: world_l1_players", () => {
  withTempWorld((work) => {
    makeL1World(work);
    writeDat(join(work, "playerdata", "b-uuid.dat"), { Health: new NbtInt(20) });
    writeDat(join(work, "playerdata", "a-uuid.dat"), { Health: new NbtInt(7) });
    const world = MinecraftWorld.open(work);

    try {
      assert.deepEqual(world.playerIds(), ["a-uuid", "b-uuid"]);
      assert.equal(world.player("a-uuid")!.getInt("Health"), 7);
      assert.equal(world.player("missing"), undefined);
    } finally {
      world.close();
    }
  });
});

test("WorldLayout: world_l1_data_file", () => {
  withTempWorld((work) => {
    makeL1World(work);
    writeDat(join(work, "data", "scoreboard.dat"), { Value: new NbtInt(1) });
    writeDat(join(work, "DIM-1", "data", "raids_nether.dat"), { Value: new NbtInt(2) });
    const world = MinecraftWorld.open(work);

    try {
      assert.equal(world.dataFile("scoreboard")!.getInt("Value"), 1);
      assert.equal(world.dataFile("missing"), undefined);
      assert.equal(world.dimension("minecraft:the_nether")!.dataFile("raids_nether")!.getInt("Value"), 2);

      // オーバーワールドの次元は、ワールドと同じdata/を読む
      assert.equal(world.dimension("minecraft:overworld")!.dataFile("scoreboard")!.getInt("Value"), 1);
    } finally {
      world.close();
    }
  });
});

test("WorldLayout: level_data_l1_getters", () => {
  withTempWorld((work) => {
    writeLevel(work, {
      DataVersion: new NbtInt(3953),
      SpawnX: new NbtInt(10),
      SpawnY: new NbtInt(64),
      SpawnZ: new NbtInt(-5),
      Difficulty: new NbtByte(2),
      hardcore: new NbtByte(1),
    });
    const world = MinecraftWorld.open(work);

    try {
      assert.deepEqual(Array.from(world.level.spawnPos), [10, 64, -5]);
      assert.equal(world.level.difficulty, "normal");
      assert.equal(world.level.isHardcore, true);
      assertErrorCode(ErrorCode.UnsupportedFeature, () => world.level.spawnDimension);
    } finally {
      world.close();
    }
  });
});

test("WorldLayout: L1の難易度は数値を名前に直す", () => {
  const names = ["peaceful", "easy", "normal", "hard"];

  // 0〜3をそれぞれ名前に直せる
  for (const [number, name] of names.entries()) {
    withTempWorld((work) => {
      writeLevel(work, { DataVersion: new NbtInt(3953), Difficulty: new NbtByte(number) });
      const world = MinecraftWorld.open(work);
      assert.equal(world.level.difficulty, name);
      world.close();
    });
  }
});

test("WorldLayout: L1の難易度が範囲外なら MalformedData", () => {
  // 範囲の外側の両端を確かめる
  for (const number of [-1, 4]) {
    withTempWorld((work) => {
      writeLevel(work, { DataVersion: new NbtInt(3953), Difficulty: new NbtByte(number) });
      const world = MinecraftWorld.open(work);
      assertErrorCode(ErrorCode.MalformedData, () => world.level.difficulty);
      world.close();
    });
  }
});

test("WorldLayout: world_l2_unchanged", () => {
  withTempWorld((work) => {
    const spawn = new NbtCompound();
    spawn.set("pos", new NbtIntArray(Int32Array.of(1, 2, 3)));
    spawn.set("dimension", new NbtString("minecraft:overworld"));
    const settings = new NbtCompound();
    settings.set("difficulty", new NbtString("hard"));
    settings.set("hardcore", new NbtByte(1));
    writeLevel(work, { DataVersion: new NbtInt(5023), spawn, difficulty_settings: settings });

    mkdirSync(join(work, "dimensions", "minecraft", "overworld"), { recursive: true });
    mkdirSync(join(work, "dimensions", "minecraft", "the_end"), { recursive: true });
    writeDat(join(work, "players", "data", "u.dat"), { Health: new NbtInt(3) });
    writeDat(join(work, "data", "minecraft", "weather.dat"), { Value: new NbtInt(4) });
    writeDat(join(work, "dimensions", "minecraft", "the_end", "data", "minecraft", "raids.dat"), {
      Value: new NbtInt(5),
    });
    const world = MinecraftWorld.open(work);

    try {
      assert.deepEqual(Array.from(world.level.spawnPos), [1, 2, 3]);
      assert.equal(world.level.spawnDimension, "minecraft:overworld");
      assert.equal(world.level.difficulty, "hard");
      assert.equal(world.level.isHardcore, true);
      assert.deepEqual(world.dimensionIds(), ["minecraft:overworld", "minecraft:the_end"]);
      assert.deepEqual(world.playerIds(), ["u"]);
      assert.equal(world.dataFile("weather")!.getInt("Value"), 4);
      assert.equal(world.dimension("the_end")!.dataFile("raids")!.getInt("Value"), 5);
    } finally {
      world.close();
    }
  });
});

test("WorldLayout: DataVersion が無い level.dat は L1 として読む", () => {
  withTempWorld((work) => {
    writeLevel(work, {});
    mkdirSync(join(work, "DIM1"));
    const world = MinecraftWorld.open(work);

    try {
      assert.deepEqual(world.dimensionIds(), ["minecraft:the_end"]);
    } finally {
      world.close();
    }
  });
});

test("WorldLayout: world_override_layout", () => {
  withTempWorld((work) => {
    // level.datは26.3を名乗るが、構成はL1
    writeLevel(work, {
      DataVersion: new NbtInt(5023),
      SpawnX: new NbtInt(1),
      SpawnY: new NbtInt(2),
      SpawnZ: new NbtInt(3),
    });
    mkdirSync(join(work, "region"));

    const plain = MinecraftWorld.open(work);
    assert.deepEqual(plain.dimensionIds(), []);
    plain.close();

    const world = MinecraftWorld.open(work, { formatDataVersion: 3953 });

    try {
      assert.deepEqual(world.dimensionIds(), ["minecraft:overworld"]);
      assert.deepEqual(Array.from(world.level.spawnPos), [1, 2, 3]);
    } finally {
      world.close();
    }

    assertErrorCode(ErrorCode.InvalidArgument, () => MinecraftWorld.open(work, { formatDataVersion: 1518 }));
  });
});

test("WorldLayout: ワールドの指定は読むチャンクの世代にも効く", () => {
  withTempWorld((work) => {
    writeLevel(work, { DataVersion: new NbtInt(5023) });
    const region = join(work, "dimensions", "minecraft", "overworld", "region");
    mkdirSync(region, { recursive: true });
    const file = RegionFile.open(join(region, "r.0.0.mca"), RegionFileMode.ReadWrite);
    file.writeChunk(0, 0, readFile(vectorPath("palette_1")).tag);
    file.close();

    // ワールドの指定がchunkReadの指定より優先される
    const readOptions: ChunkReadOptions = { formatDataVersion: 5023 };
    const world = MinecraftWorld.open(work, { chunkRead: readOptions, formatDataVersion: 5006 });

    try {
      const loaded = world.dimension("minecraft:overworld")!.chunk(0, 0)!;
      assert.equal(loaded.formatDataVersion, 5006);
    } finally {
      world.close();
    }

    // 渡したオプションは書き換えない
    assert.equal(readOptions.formatDataVersion, 5023);
  });
});

/**
 * World / Blockレイヤ
 *
 * 他言語版と同じ検証項目を持つ
 * 共通テストベクタによる言語間比較はspec/run-conformance.shが担当し、ここではAPIの振る舞いを直接確かめる
 */

import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { TARGET_DATA_VERSION } from "../src/index.js";
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
import {
  Compression,
  NamedTag,
  NbtCompound,
  NbtInt,
  NbtString,
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

/** ブロックのパレット要素を作る */
function blockEntry(name: string): NbtCompound {
  const entry = new NbtCompound();
  entry.set("Name", new NbtString(name));
  return entry;
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
  const nbt = state.toNbt();
  assert.equal(nbt.getString("Name"), "minecraft:oak_stairs");
  assert.equal(nbt.getCompound("Properties").getString("facing"), "north");
  assert.ok(BlockState.fromNbt(nbt).equals(state));
});

test("BlockState: プロパティ無しの NBT には Properties を書かない", () => {
  assert.equal(BlockState.parse("minecraft:air").toNbt().optCompound("Properties"), undefined);
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
  assert.equal((container.get(0) as NbtCompound).getString("Name"), "minecraft:dirt");
});

test("PalettedContainer: fill で単一値に戻る", () => {
  const container = PalettedContainer.filled(blockEntry("minecraft:air"), 4096, 4);
  container.set(0, blockEntry("minecraft:stone"));
  container.fill(blockEntry("minecraft:water"));

  assert.equal(container.palette.length, 1);
  assert.equal(container.bitsPerEntry, 0);
  assert.equal((container.get(4095) as NbtCompound).getString("Name"), "minecraft:water");
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

/** DataVersionだけを差し替えたチャンクを作る */
function foreignChunk(): NbtCompound {
  const root = readFile(vectorPath("palette_1")).tag;
  root.set("DataVersion", new NbtInt(3953));
  return root;
}

test("DataVersion: 既定では警告として通す", () => {
  const warnings: string[] = [];
  const chunk = Chunk.fromNbt(foreignChunk(), {
    onVersionMismatch: VersionMismatchAction.Warn,
    onWarning: (message: string) => warnings.push(message),
  });

  assert.equal(chunk.dataVersion, 3953);
  assert.equal(warnings.length, 1);
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
  assert.equal(chunk.toNbt({ allowForeignDataVersion: true }).getInt("DataVersion"), 3953);
});

/** 対象より新しいDataVersionを持つチャンクを作る */
function newerChunk(): NbtCompound {
  const root = readFile(vectorPath("palette_1")).tag;
  root.setInt("DataVersion", 5015);
  return root;
}

test("DataVersion: 新しいバージョンのチャンクは警告を出さない", () => {
  const warnings: string[] = [];

  // 形式が同じであれば、新しいバージョンでも警告を出さずに読める
  const chunk = Chunk.fromNbt(newerChunk(), {
    onVersionMismatch: VersionMismatchAction.Warn,
    onWarning: (message) => warnings.push(message),
  });

  assert.equal(chunk.dataVersion, 5015);
  assert.deepEqual(warnings, []);
});

test("DataVersion: 新しいバージョンのチャンクはエラー設定でも通る", () => {
  const chunk = Chunk.fromNbt(newerChunk(), {
    onVersionMismatch: VersionMismatchAction.Error,
  });

  assert.equal(chunk.dataVersion, 5015);
});

test("DataVersion: 新しいバージョンのチャンクはそのまま書き戻せる", () => {
  const chunk = Chunk.fromNbt(newerChunk());

  // 許可を出さなくても書き戻せて、DataVersionも変わらない
  assert.equal(chunk.toNbt().getInt("DataVersion"), 5015);
});

test("DataVersion: 対象バージョンのチャンクはそのまま書き戻せる", () => {
  const chunk = loadChunk("palette_1");
  assert.equal(chunk.toNbt().getInt("DataVersion"), TARGET_DATA_VERSION);
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
    const level = new NbtCompound();
    level.set("Data", new NbtCompound());
    writeFile(join(work, "level.dat"), new NamedTag("", level));

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

/**
 * Anvil リージョンファイルの読み書き。
 *
 * 仕様: docs/spec/20-anvil-region.md
 *
 * 他言語版と同じ検証項目を持つ。
 * 共通テストベクタによる言語間比較は spec/run-conformance.sh が担当し、
 * ここでは API の振る舞いを直接確かめる。
 */

import assert from "node:assert/strict";
import { cpSync, existsSync, mkdtempSync, readFileSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { TARGET_DATA_VERSION } from "../src/index.js";
import { ErrorCode, SpringNbtError } from "../src/errors.js";
import {
  ChunkCompression,
  ChunkPos,
  RegionFile,
  RegionFileMode,
  RegionFolder,
  RegionPos,
  SECTOR_SIZE,
} from "../src/anvil/index.js";
import { NbtByteArray, NbtCompound, NbtInt, NbtString } from "../src/nbt/index.js";

const HERE = fileURLToPath(new URL(".", import.meta.url));
const REPO_ROOT = join(HERE, "..", "..", "..");
const VECTORS = join(REPO_ROOT, "spec", "testdata", "anvil");

/** 共通テストベクタのディレクトリ。 */
function vectorDir(name: string): string {
  const path = join(VECTORS, name);

  if (!existsSync(path)) {
    throw new Error(`テストベクタが見つからない: anvil/${name}`);
  }

  return path;
}

/** テストごとの一時ディレクトリを作る。 */
function makeWorkDir(): string {
  return mkdtempSync(join(tmpdir(), "springnbt-test-"));
}

/** ベクタを一時ディレクトリへ複製し、書き込みテストで原本を汚さないようにする。 */
function copyVector(name: string, work: string): string {
  const destination = join(work, name);
  cpSync(vectorDir(name), destination, { recursive: true });
  return destination;
}

function sampleChunk(x: number, z: number): NbtCompound {
  const chunk = new NbtCompound();
  chunk.set("DataVersion", new NbtInt(TARGET_DATA_VERSION));
  chunk.set("xPos", new NbtInt(x));
  chunk.set("zPos", new NbtInt(z));
  chunk.set("yPos", new NbtInt(-4));
  chunk.set("Status", new NbtString("minecraft:full"));
  return chunk;
}

/** 圧縮しても縮まないバイト列を作る。サイズの制御が効くようにするため。 */
function incompressible(length: number): Int8Array {
  const result = new Int8Array(length);
  let state = 0x12345678;

  // 線形合同法で疑似乱数を作る。テストの再現性を保つため固定の種を使う
  for (let index = 0; index < length; index++) {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    result[index] = (state >>> 24) << 24 >> 24;
  }

  return result;
}

function assertErrorCode(fn: () => unknown, expected: ErrorCode): void {
  try {
    fn();
  } catch (error) {
    assert.ok(error instanceof SpringNbtError, `SpringNbtError ではない: ${String(error)}`);
    assert.equal(error.code, expected);
    return;
  }

  assert.fail(`例外が送出されなかった (期待 ${expected})`);
}

// ---------------------------------------------------------------------------
// 座標計算
// ---------------------------------------------------------------------------

test("チャンク座標は負の値でも正しく求まる", () => {
  const cases: Array<[number, number, number, number, number, number]> = [
    [0, 0, 0, 0, 0, 0],
    [31, 31, 0, 0, 31, 31],
    [32, 32, 1, 1, 0, 0],
    [-1, -1, -1, -1, 31, 31],
    [-32, -32, -1, -1, 0, 0],
    [-33, -33, -2, -2, 31, 31],
  ];

  // 算術右シフトなので負の座標でも正しく求まる
  for (const [chunkX, chunkZ, regionX, regionZ, localX, localZ] of cases) {
    const position = new ChunkPos(chunkX, chunkZ);
    assert.equal(position.region.x, regionX);
    assert.equal(position.region.z, regionZ);
    assert.equal(position.localX, localX);
    assert.equal(position.localZ, localZ);
    assert.equal(position.index, localX + localZ * 32);
  }
});

test("リージョンのファイル名を往復できる", () => {
  assert.equal(new RegionPos(-1, 2).fileName, "r.-1.2.mca");
  assert.ok(RegionPos.fromFileName("r.-1.2.mca")?.equals(new RegionPos(-1, 2)));

  // 形式が違うものは受け付けない
  assert.equal(RegionPos.fromFileName("r.0.0.mcr"), undefined);
  assert.equal(RegionPos.fromFileName("region.mca"), undefined);
  assert.equal(RegionPos.fromFileName("r.a.0.mca"), undefined);
});

// ---------------------------------------------------------------------------
// 読み込み
// ---------------------------------------------------------------------------

test("空のリージョンにはチャンクが無い", () => {
  const region = RegionFile.open(join(vectorDir("empty"), "r.0.0.mca"));
  assert.equal(region.chunkPositions().length, 0);
  assert.equal(region.hasChunk(0, 0), false);
  assert.equal(region.readChunk(0, 0), undefined);
  region.close();
});

test("チャンクが 1 つのリージョンを読める", () => {
  const region = RegionFile.open(join(vectorDir("single_chunk"), "r.0.0.mca"));
  const positions = region.chunkPositions();

  assert.equal(positions.length, 1);
  assert.ok(positions[0].equals(new ChunkPos(0, 0)));
  assert.equal(region.readChunk(0, 0)?.getInt("DataVersion"), TARGET_DATA_VERSION);
  assert.equal(region.readChunk(0, 0)?.getString("Status"), "minecraft:full");
  assert.equal(region.timestamp(0, 0), 1700000000);
  region.close();
});

test("圧縮方式が混在していても読める", () => {
  const region = RegionFile.open(join(vectorDir("mixed_compression"), "r.0.0.mca"));

  assert.equal(region.readChunkRaw(0, 0)?.compression, ChunkCompression.Gzip);
  assert.equal(region.readChunkRaw(1, 0)?.compression, ChunkCompression.Zlib);
  assert.equal(region.readChunkRaw(2, 0)?.compression, ChunkCompression.None);

  // 方式が違っても中身は同じように読める
  for (let x = 0; x < 3; x++) {
    assert.equal(region.readChunk(x, 0)?.getInt("xPos"), x);
  }

  region.close();
});

test("外部ファイルへ退避されたチャンクを読める", () => {
  const region = RegionFile.open(join(vectorDir("external_mcc"), "r.0.0.mca"));
  const raw = region.readChunkRaw(0, 0);

  assert.equal(raw?.external, true);
  assert.equal(raw?.compression, ChunkCompression.Zlib);
  assert.equal(region.readChunk(0, 0)?.getString("Status"), "minecraft:full");
  region.close();
});

test("壊れたヘッダを弾く", () => {
  for (const vector of ["bad_offset", "overlapping_sectors", "unaligned_length", "offset_out_of_file"]) {
    assertErrorCode(
      () => RegionFile.open(join(vectorDir(vector), "r.0.0.mca")),
      ErrorCode.MalformedData,
    );
  }
});

test("担当外のチャンク座標を弾く", () => {
  const region = RegionFile.open(join(vectorDir("empty"), "r.0.0.mca"));

  // r.0.0 が担当するのは 0..31 の範囲だけ
  assertErrorCode(() => region.hasChunk(32, 0), ErrorCode.InvalidArgument);
  region.close();
});

test("読み取り専用では書き込めない", () => {
  const region = RegionFile.open(join(vectorDir("empty"), "r.0.0.mca"));
  assertErrorCode(() => region.writeChunk(0, 0, sampleChunk(0, 0)), ErrorCode.InvalidArgument);
  region.close();
});

// ---------------------------------------------------------------------------
// 書き込み
// ---------------------------------------------------------------------------

test("開いて何も変えずに書き戻すとバイトが変わらない", () => {
  // 触っていないチャンクの配置を保つことが、既存ワールドを壊さない前提になる
  const work = makeWorkDir();

  try {
    const directory = copyVector("fragmented", work);
    const path = join(directory, "r.0.0.mca");
    const original = readFileSync(path);

    const region = RegionFile.open(path, RegionFileMode.ReadWrite);
    region.flush();
    region.close();

    assert.deepEqual(readFileSync(path), original);
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
});

test("チャンクを書いて読み戻せる", () => {
  const work = makeWorkDir();

  try {
    const path = join(work, "r.0.0.mca");
    const region = RegionFile.open(path, RegionFileMode.ReadWrite);
    region.writeChunk(3, 4, sampleChunk(3, 4));
    region.flush();
    region.close();

    const reopened = RegionFile.open(path);
    assert.equal(reopened.hasChunk(3, 4), true);
    assert.equal(reopened.readChunk(3, 4)?.getInt("xPos"), 3);
    reopened.close();

    // 書き出したファイルは必ずセクタ境界に揃う
    assert.equal(statSync(path).size % SECTOR_SIZE, 0);
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
});

test("同じ大きさで書き直すとその場に留まる", () => {
  const work = makeWorkDir();

  try {
    const directory = copyVector("fragmented", work);
    const path = join(directory, "r.0.0.mca");
    const originalLength = statSync(path).size;

    const region = RegionFile.open(path, RegionFileMode.ReadWrite);
    // 同じ内容を書き直すので、必要セクタ数は変わらない
    region.writeChunk(0, 0, region.readChunk(0, 0)!);
    region.flush();
    region.close();

    // その場で上書きされるので、ファイルは伸びない
    assert.equal(statSync(path).size, originalLength);

    const reopened = RegionFile.open(path);
    assert.equal(reopened.chunkPositions().length, 3);
    reopened.close();
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
});

test("大きくなったチャンクは移動し、他を壊さない", () => {
  const work = makeWorkDir();

  try {
    const directory = copyVector("fragmented", work);
    const path = join(directory, "r.0.0.mca");

    // 5 セクタぶんになる大きなチャンクを作る
    const big = sampleChunk(0, 0);
    big.set("filler", new NbtByteArray(incompressible(5 * SECTOR_SIZE)));

    const region = RegionFile.open(path, RegionFileMode.ReadWrite);
    region.writeChunk(0, 0, big);
    region.flush();
    region.close();

    const reopened = RegionFile.open(path);
    // 動かした結果、他の 2 チャンクが壊れていないこと
    assert.equal(reopened.chunkPositions().length, 3);
    assert.equal(reopened.readChunk(5, 3)?.getInt("xPos"), 5);
    assert.equal(reopened.readChunk(31, 31)?.getInt("xPos"), 31);
    assert.equal(reopened.readChunk(0, 0)?.getByteArray("filler").length, 5 * SECTOR_SIZE);
    reopened.close();
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
});

test("削除したチャンクは消え、他は残る", () => {
  const work = makeWorkDir();

  try {
    const directory = copyVector("fragmented", work);
    const path = join(directory, "r.0.0.mca");

    const region = RegionFile.open(path, RegionFileMode.ReadWrite);
    assert.equal(region.deleteChunk(5, 3), true);
    assert.equal(region.deleteChunk(5, 3), false);
    region.flush();
    region.close();

    const reopened = RegionFile.open(path);
    assert.equal(reopened.hasChunk(5, 3), false);
    assert.equal(reopened.timestamp(5, 3), 0);
    assert.equal(reopened.chunkPositions().length, 2);
    reopened.close();
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
});

test("空いたセクタは再利用される", () => {
  const work = makeWorkDir();

  try {
    const directory = copyVector("fragmented", work);
    const path = join(directory, "r.0.0.mca");
    const originalLength = statSync(path).size;

    const region = RegionFile.open(path, RegionFileMode.ReadWrite);
    region.deleteChunk(5, 3);
    region.writeChunk(7, 7, sampleChunk(7, 7));
    region.flush();
    region.close();

    // 空いたセクタへ収まるので、ファイルは伸びない
    assert.equal(statSync(path).size, originalLength);

    const reopened = RegionFile.open(path);
    assert.equal(reopened.readChunk(7, 7)?.getInt("xPos"), 7);
    reopened.close();
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
});

test("optimize でファイルが詰まる", () => {
  const work = makeWorkDir();

  try {
    const directory = copyVector("fragmented", work);
    const path = join(directory, "r.0.0.mca");
    const originalLength = statSync(path).size;

    const region = RegionFile.open(path, RegionFileMode.ReadWrite);
    region.optimize();
    region.flush();
    region.close();

    const optimizedLength = statSync(path).size;

    // 隙間が詰まるぶん小さくなる
    assert.ok(optimizedLength < originalLength, `縮んでいない: ${originalLength} -> ${optimizedLength}`);
    assert.equal(optimizedLength % SECTOR_SIZE, 0);

    const reopened = RegionFile.open(path);
    assert.equal(reopened.chunkPositions().length, 3);
    assert.equal(reopened.timestamp(0, 0), 1700000000);
    assert.equal(reopened.readChunk(31, 31)?.getInt("xPos"), 31);
    reopened.close();
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
});

test("巨大なチャンクは外部ファイルへ退避され、縮めば戻る", () => {
  const work = makeWorkDir();

  try {
    const path = join(work, "r.0.0.mca");

    // 1MiB を超えるよう、圧縮の効かないデータを詰める
    const huge = sampleChunk(1, 2);
    huge.set("filler", new NbtByteArray(incompressible(1200 * 1024)));

    let region = RegionFile.open(path, RegionFileMode.ReadWrite);
    region.writeChunk(1, 2, huge, ChunkCompression.None);
    region.flush();
    region.close();

    const external = join(work, "c.1.2.mcc");
    assert.ok(existsSync(external), "外部ファイルへ退避されていない");

    let reopened = RegionFile.open(path);
    assert.equal(reopened.readChunkRaw(1, 2)?.external, true);
    assert.equal(reopened.readChunk(1, 2)?.getByteArray("filler").length, 1200 * 1024);
    reopened.close();

    // 小さく書き直すと内部へ戻り、外部ファイルは消える
    region = RegionFile.open(path, RegionFileMode.ReadWrite);
    region.writeChunk(1, 2, sampleChunk(1, 2));
    region.flush();
    region.close();

    assert.ok(!existsSync(external), "内部へ戻ったのに外部ファイルが残っている");

    reopened = RegionFile.open(path);
    assert.equal(reopened.readChunkRaw(1, 2)?.external, false);
    reopened.close();
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
});

test("タイムスタンプを明示的に設定できる", () => {
  const work = makeWorkDir();

  try {
    const path = join(work, "r.0.0.mca");
    const region = RegionFile.open(path, RegionFileMode.ReadWrite);
    region.writeChunk(0, 0, sampleChunk(0, 0));
    region.setTimestamp(0, 0, 1234567890);
    region.flush();
    region.close();

    const reopened = RegionFile.open(path);
    assert.equal(reopened.timestamp(0, 0), 1234567890);
    reopened.close();
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
});

// ---------------------------------------------------------------------------
// RegionFolder
// ---------------------------------------------------------------------------

test("フォルダは複数リージョンへチャンクを振り分ける", () => {
  const work = makeWorkDir();

  try {
    const folder = RegionFolder.open(work, RegionFileMode.ReadWrite);
    folder.writeChunk(0, 0, sampleChunk(0, 0));
    folder.writeChunk(-1, -1, sampleChunk(-1, -1));
    folder.writeChunk(40, 40, sampleChunk(40, 40));
    folder.flush();
    folder.close();

    // 3 つの異なるリージョンへ振り分けられる
    for (const name of ["r.0.0.mca", "r.-1.-1.mca", "r.1.1.mca"]) {
      assert.ok(existsSync(join(work, name)), `${name} が作られていない`);
    }

    const reopened = RegionFolder.open(work);
    assert.equal(reopened.regionPositions().length, 3);
    assert.equal(reopened.chunkPositions().length, 3);
    assert.equal(reopened.readChunk(-1, -1)?.getInt("xPos"), -1);
    assert.equal(reopened.readChunk(100, 100), undefined);
    assert.equal(reopened.hasChunk(100, 100), false);
    reopened.close();
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
});

test("RegionFolder: キャッシュ上限を超えると古いリージョンから閉じる", () => {
  const work = mkdtempSync(join(tmpdir(), "springnbt-lru-"));

  try {
    // 上限 2 で 4 リージョンへ書く。古いものは閉じられるが内容は失われない
    const folder = RegionFolder.open(work, RegionFileMode.ReadWrite, 2);

    for (let region = 0; region < 4; region++) {
      folder.writeChunk(region * 32, 0, sampleChunk(region * 32, 0));
      assert.ok(folder.cachedRegionCount <= 2);
    }

    folder.flush();
    folder.close();

    // 追い出されたリージョンも、書き出されてから閉じられている
    const reopened = RegionFolder.open(work);

    try {
      assert.equal(reopened.regionPositions().length, 4);

      for (let region = 0; region < 4; region++) {
        assert.equal(reopened.readChunk(region * 32, 0)?.getInt("xPos"), region * 32);
      }
    } finally {
      reopened.close();
    }
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
});

test("RegionFolder: キャッシュ上限が 0 以下なら INVALID_ARGUMENT", () => {
  const work = mkdtempSync(join(tmpdir(), "springnbt-lru-"));

  try {
    assert.throws(
      () => RegionFolder.open(work, RegionFileMode.ReadOnly, 0),
      (error: unknown) => {
        assert.ok(error instanceof SpringNbtError);
        assert.equal(error.code, ErrorCode.InvalidArgument);
        return true;
      },
    );
  } finally {
    rmSync(work, { recursive: true, force: true });
  }
});

/**
 * ブロック座標と範囲
 *
 * 仕様: `docs/spec/30-chunk-format.md` 5章
 */

import assert from "node:assert/strict";
import test from "node:test";

import { ChunkPos } from "../src/anvil/index.js";
import { BlockPos, Cuboid } from "../src/world/index.js";

test("チャンク座標とチャンク内位置を求められる", () => {
  const pos = new BlockPos(100, 64, -200);

  // 算術右シフトなので負の座標でも正しく求まる
  assert.ok(pos.chunkPos.equals(new ChunkPos(6, -13)));
  assert.equal(pos.localX, 4);
  assert.equal(pos.localZ, 8);
});

test("各軸へずらせる", () => {
  const moved = new BlockPos(1, 2, 3).offset(10, -20, 30);

  assert.ok(moved.equals(new BlockPos(11, -18, 33)));
  assert.ok(!moved.equals(new BlockPos(11, -18, 34)));
});

test("両端の順序は問わない", () => {
  const box = Cuboid.of(10, 20, 30, 0, 5, 15);

  assert.equal(box.minX, 0);
  assert.equal(box.maxX, 10);
  assert.equal(box.sizeX, 11);
  assert.equal(box.sizeY, 16);
  assert.equal(box.sizeZ, 16);
});

test("範囲の内側だけを含む", () => {
  const box = Cuboid.of(0, 0, 0, 1, 1, 1);

  assert.ok(box.contains(0, 0, 0));
  assert.ok(box.contains(1, 1, 1));
  assert.ok(!box.contains(2, 0, 0));
  assert.ok(!box.contains(0, -1, 0));
});

test("範囲内の座標をすべて返す", () => {
  const box = Cuboid.of(0, 0, 0, 1, 2, 3);
  const positions = [...box.positions()];

  assert.equal(positions.length, box.volume);
  assert.equal(positions.length, 2 * 3 * 4);

  // 並びは Y、Z、X の順で、X がいちばん内側で動く
  assert.ok(positions[0].equals(new BlockPos(0, 0, 0)));
  assert.ok(positions[1].equals(new BlockPos(1, 0, 0)));
  assert.ok(positions[2].equals(new BlockPos(0, 0, 1)));
  assert.ok(positions[positions.length - 1].equals(new BlockPos(1, 2, 3)));
});

test("1ブロックの範囲は体積 1", () => {
  const box = Cuboid.of(5, 5, 5, 5, 5, 5);

  assert.equal(box.volume, 1);
  assert.equal([...box.positions()].length, 1);
});

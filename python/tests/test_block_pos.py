"""ブロック座標と範囲の単体テスト。

仕様: docs/spec/30-chunk-format.md 5章
"""

from __future__ import annotations

from spring_nbt_library.anvil import ChunkPos
from spring_nbt_library.world import BlockPos, Cuboid


def test_resolves_chunk_and_local_coordinates():
    pos = BlockPos(100, 64, -200)

    # 算術右シフトなので負の座標でも正しく求まる
    assert pos.chunk_pos == ChunkPos(6, -13)
    assert pos.local_x == 4
    assert pos.local_z == 8


def test_offsets_each_axis():
    moved = BlockPos(1, 2, 3).offset(10, -20, 30)

    assert moved == BlockPos(11, -18, 33)
    assert moved != BlockPos(11, -18, 34)


def test_normalizes_the_order_of_the_two_corners():
    box = Cuboid.of(10, 20, 30, 0, 5, 15)

    assert box.min_x == 0
    assert box.max_x == 10
    assert box.size_x == 11
    assert box.size_y == 16
    assert box.size_z == 16


def test_contains_only_the_positions_inside():
    box = Cuboid.of(0, 0, 0, 1, 1, 1)

    assert box.contains(0, 0, 0)
    assert box.contains(1, 1, 1)
    assert not box.contains(2, 0, 0)
    assert not box.contains(0, -1, 0)


def test_walks_every_position_inside():
    box = Cuboid.of(0, 0, 0, 1, 2, 3)
    positions = list(box.positions())

    assert len(positions) == box.volume
    assert len(positions) == 2 * 3 * 4

    # 並びは Y、Z、X の順で、X がいちばん内側で動く
    assert positions[0] == BlockPos(0, 0, 0)
    assert positions[1] == BlockPos(1, 0, 0)
    assert positions[2] == BlockPos(0, 0, 1)
    assert positions[-1] == BlockPos(1, 2, 3)


def test_one_block_box_has_volume_one():
    box = Cuboid.of(5, 5, 5, 5, 5, 5)

    assert box.volume == 1
    assert len(list(box.positions())) == 1

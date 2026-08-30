"""ブロックの絶対座標と、その範囲

仕様: docs/spec/30-chunk-format.md 5章
"""

from __future__ import annotations

from typing import Iterator

from ..anvil import ChunkPos

__all__ = ["BlockPos", "Cuboid"]


class BlockPos:
    """ブロックの絶対座標"""

    __slots__ = ("x", "y", "z")

    def __init__(self, x: int, y: int, z: int) -> None:
        #: X座標
        self.x = x
        #: Y座標
        self.y = y
        #: Z座標
        self.z = z

    @property
    def chunk_pos(self) -> ChunkPos:
        """この座標を含むチャンクの座標

        算術右シフトなので負の座標でも正しく求まる
        """
        return ChunkPos(self.x >> 4, self.z >> 4)

    @property
    def local_x(self) -> int:
        """チャンク内でのX位置 (0..15)"""
        return self.x & 15

    @property
    def local_z(self) -> int:
        """チャンク内でのZ位置 (0..15)"""
        return self.z & 15

    def offset(self, dx: int, dy: int, dz: int) -> "BlockPos":
        """各軸へずらした座標を返す"""
        return BlockPos(self.x + dx, self.y + dy, self.z + dz)

    def __eq__(self, other) -> bool:
        if not isinstance(other, BlockPos):
            return False

        return other.x == self.x and other.y == self.y and other.z == self.z

    def __hash__(self) -> int:
        return hash((self.x, self.y, self.z))

    def __repr__(self) -> str:
        return "(%d, %d, %d)" % (self.x, self.y, self.z)


class Cuboid:
    """ブロック座標の直方体な範囲

    両端を含む
    ``Cuboid.of(0, 0, 0, 0, 0, 0)`` は 1 ブロック

    範囲内のブロックを順に処理したいときに使う
    """

    __slots__ = ("min_x", "min_y", "min_z", "max_x", "max_y", "max_z")

    def __init__(self, first: BlockPos, second: BlockPos) -> None:
        """両端の座標から作る

        大小の順序は問わない
        内部で小さいほうを最小に揃える
        """
        #: X の最小値
        self.min_x = min(first.x, second.x)
        #: Y の最小値
        self.min_y = min(first.y, second.y)
        #: Z の最小値
        self.min_z = min(first.z, second.z)
        #: X の最大値（含む）
        self.max_x = max(first.x, second.x)
        #: Y の最大値（含む）
        self.max_y = max(first.y, second.y)
        #: Z の最大値（含む）
        self.max_z = max(first.z, second.z)

    @staticmethod
    def of(x1: int, y1: int, z1: int, x2: int, y2: int, z2: int) -> "Cuboid":
        """両端の座標から作る"""
        return Cuboid(BlockPos(x1, y1, z1), BlockPos(x2, y2, z2))

    @property
    def size_x(self) -> int:
        """X 方向の長さ"""
        return self.max_x - self.min_x + 1

    @property
    def size_y(self) -> int:
        """Y 方向の長さ"""
        return self.max_y - self.min_y + 1

    @property
    def size_z(self) -> int:
        """Z 方向の長さ"""
        return self.max_z - self.min_z + 1

    @property
    def volume(self) -> int:
        """含まれるブロックの個数"""
        return self.size_x * self.size_y * self.size_z

    def contains(self, x: int, y: int, z: int) -> bool:
        """その座標が範囲に含まれるか"""
        return (self.min_x <= x <= self.max_x
                and self.min_y <= y <= self.max_y
                and self.min_z <= z <= self.max_z)

    def positions(self) -> Iterator[BlockPos]:
        """範囲内の座標を順に返す

        並びは Y、Z、X の順で、X がいちばん内側で動く
        """
        # 内側から X が動くので、同じチャンクの並びを続けて触れる
        for y in range(self.min_y, self.max_y + 1):
            for z in range(self.min_z, self.max_z + 1):
                for x in range(self.min_x, self.max_x + 1):
                    yield BlockPos(x, y, z)

    def __eq__(self, other) -> bool:
        if not isinstance(other, Cuboid):
            return False

        return (other.min_x == self.min_x and other.min_y == self.min_y
                and other.min_z == self.min_z and other.max_x == self.max_x
                and other.max_y == self.max_y and other.max_z == self.max_z)

    def __hash__(self) -> int:
        return hash((self.min_x, self.min_y, self.min_z,
                     self.max_x, self.max_y, self.max_z))

    def __repr__(self) -> str:
        return "(%d, %d, %d)-(%d, %d, %d)" % (
            self.min_x, self.min_y, self.min_z, self.max_x, self.max_y, self.max_z)

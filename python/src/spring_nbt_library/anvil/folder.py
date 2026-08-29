"""リージョンファイルが並ぶディレクトリ 1 つ分。

``region/``、``entities/``、``poi/`` のいずれかを表す。
開いたリージョンファイルはキャッシュし、:meth:`RegionFolder.close` でまとめて閉じる。
チャンク座標からリージョンを解決するので、利用側はリージョンの存在を意識しなくてよい。

仕様: ``docs/spec/20-anvil-region.md`` 5章
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from ..errors import ErrorCode, SpringNbtError
from ..nbt import NbtCompound
from .region import ChunkPos, RegionFile, RegionFileMode, RegionPos

__all__ = ["RegionFolder"]


class RegionFolder:
    """リージョンフォルダ 1 つ分。"""

    def __init__(self, directory: str, mode: RegionFileMode) -> None:
        self.directory = directory
        self._mode = mode
        self._cache: Dict[RegionPos, RegionFile] = {}
        self._closed = False

    @staticmethod
    def open(directory: str,
             mode: RegionFileMode = RegionFileMode.READ_ONLY) -> "RegionFolder":
        """リージョンフォルダを開く。"""
        if not os.path.isdir(directory) and mode == RegionFileMode.READ_ONLY:
            raise SpringNbtError(
                ErrorCode.IO, "リージョンフォルダが存在しない: %s" % directory)

        return RegionFolder(directory, mode)

    def __enter__(self) -> "RegionFolder":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def region_positions(self) -> List[RegionPos]:
        """このフォルダに存在するリージョンの座標を返す。"""
        self._ensure_open()

        if not os.path.isdir(self.directory):
            return []

        found = []

        # r.X.Z.mca として解釈できるファイルだけを拾う
        for name in os.listdir(self.directory):
            position = RegionPos.from_file_name(name)

            if position is not None:
                found.append(position)

        # 走査順がファイルシステム依存にならないよう、座標で並べる
        found.sort(key=lambda position: (position.z, position.x))
        return found

    def region(self, region_x: int, region_z: int) -> Optional[RegionFile]:
        """リージョンファイルを取得する。読み取り専用で存在しなければ None。"""
        self._ensure_open()
        position = RegionPos(region_x, region_z)
        cached = self._cache.get(position)

        if cached is not None:
            return cached

        path = os.path.join(self.directory, position.file_name())

        # 読み取り専用では、存在しないリージョンは「チャンクが無い」として None を返す
        if not os.path.exists(path) and self._mode == RegionFileMode.READ_ONLY:
            return None

        opened = RegionFile.open(path, self._mode)
        self._cache[position] = opened
        return opened

    def has_chunk(self, chunk_x: int, chunk_z: int) -> bool:
        """チャンクが存在するか。"""
        file = self._region_for(chunk_x, chunk_z)

        if file is None:
            return False

        return file.has_chunk(chunk_x, chunk_z)

    def read_chunk(self, chunk_x: int, chunk_z: int) -> Optional[NbtCompound]:
        """チャンクを NBT として読む。存在しなければ None。"""
        file = self._region_for(chunk_x, chunk_z)

        if file is None:
            return None

        return file.read_chunk(chunk_x, chunk_z)

    def write_chunk(self, chunk_x: int, chunk_z: int, tag: NbtCompound) -> None:
        """チャンクを NBT として書き込む。"""
        file = self._region_for(chunk_x, chunk_z)

        if file is None:
            raise SpringNbtError.invalid_argument(
                "読み取り専用のフォルダには書き込めない: %s" % self.directory)

        file.write_chunk(chunk_x, chunk_z, tag)

    def delete_chunk(self, chunk_x: int, chunk_z: int) -> bool:
        """チャンクを削除する。削除できたら True。"""
        file = self._region_for(chunk_x, chunk_z)

        if file is None:
            return False

        return file.delete_chunk(chunk_x, chunk_z)

    def chunk_positions(self) -> List[ChunkPos]:
        """このフォルダに存在する全チャンクの座標を返す。"""
        result = []

        # リージョンごとに、その中のチャンクを順に集める
        for position in self.region_positions():
            file = self.region(position.x, position.z)

            if file is None:
                continue

            result.extend(file.chunk_positions())

        return result

    def flush(self) -> None:
        """開いている全リージョンの変更を書き出す。"""
        self._ensure_open()

        for file in self._cache.values():
            file.flush()

    def close(self) -> None:
        """開いている全リージョンを閉じる。"""
        if self._closed:
            return

        for file in self._cache.values():
            file.close()

        self._cache.clear()
        self._closed = True

    def _region_for(self, chunk_x: int, chunk_z: int) -> Optional[RegionFile]:
        position = ChunkPos(chunk_x, chunk_z).region()
        return self.region(position.x, position.z)

    def _ensure_open(self) -> None:
        if self._closed:
            raise SpringNbtError.invalid_argument("既に閉じられたリージョンフォルダ")

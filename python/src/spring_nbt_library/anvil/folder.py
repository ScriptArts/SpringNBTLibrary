"""リージョンファイルが並ぶディレクトリ 1 つ分。

``region/``、``entities/``、``poi/`` のいずれかを表す。
開いたリージョンファイルはキャッシュし、:meth:`RegionFolder.close` でまとめて閉じる。
チャンク座標からリージョンを解決するので、利用側はリージョンの存在を意識しなくてよい。

:class:`RegionFile` はファイル全体をメモリへ載せるため、キャッシュには
``max_cached_regions`` 件の上限がある。上限を超えると、最も長く使われていない
ものから書き出して閉じる。大きなワールドを端から走査してもメモリを使い切らない。

このため :meth:`RegionFolder.region` が返した参照は、
**別のリージョンへアクセスすると閉じられている場合がある**。
参照を保持せず、必要なたびに取得すること。

仕様: ``docs/spec/20-anvil-region.md`` 5章
"""

from __future__ import annotations

import os
from collections import OrderedDict
from typing import Dict, List, Optional

from ..errors import ErrorCode, SpringNbtError
from ..nbt import NbtCompound
from .region import ChunkPos, RegionFile, RegionFileMode, RegionPos

__all__ = ["DEFAULT_MAX_CACHED_REGIONS", "RegionFolder"]

#: 同時に開いておくリージョンファイル数の既定の上限。
#:
#: 1 リージョンは最大 255 セクタ × 1024 チャンク＝理論上 1GiB になりうる。
#: 実データでは数 MB から数十 MB 程度。8 件なら通常のワールドで数百 MB に収まる。
DEFAULT_MAX_CACHED_REGIONS = 8


class RegionFolder:
    """リージョンフォルダ 1 つ分。"""

    def __init__(self, directory: str, mode: RegionFileMode,
                 max_cached_regions: int = DEFAULT_MAX_CACHED_REGIONS) -> None:
        self.directory = directory
        #: 同時に開いておくリージョンファイル数の上限。
        self.max_cached_regions = max_cached_regions
        self._mode = mode
        # 最近使った順を保つので、先頭がいちばん長く使っていないもの
        self._cache: "OrderedDict[RegionPos, RegionFile]" = OrderedDict()
        self._closed = False

    @property
    def cached_region_count(self) -> int:
        """いま開いているリージョンファイル数。"""
        return len(self._cache)

    @staticmethod
    def open(directory: str,
             mode: RegionFileMode = RegionFileMode.READ_ONLY,
             max_cached_regions: int = DEFAULT_MAX_CACHED_REGIONS) -> "RegionFolder":
        """リージョンフォルダを開く。"""
        if max_cached_regions < 1:
            raise SpringNbtError.invalid_argument(
                "max_cached_regions は 1 以上でなければならない: %d" % max_cached_regions)

        if not os.path.isdir(directory) and mode == RegionFileMode.READ_ONLY:
            raise SpringNbtError(
                ErrorCode.IO, "リージョンフォルダが存在しない: %s" % directory)

        return RegionFolder(directory, mode, max_cached_regions)

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

            # r.X.Z.mca として解釈できるファイルだけを拾う
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
            # 使ったものを末尾へ move して、最近使った順を保つ
            self._cache.move_to_end(position)
            return cached

        path = os.path.join(self.directory, position.file_name())

        # 読み取り専用では、存在しないリージョンは「チャンクが無い」として None を返す
        if not os.path.exists(path) and self._mode == RegionFileMode.READ_ONLY:
            return None

        # 開く前に空きを作る。開いてからだと一瞬だけ上限を超える
        self._evict_until_below_limit()

        opened = RegionFile.open(path, self._mode)
        self._cache[position] = opened
        return opened

    def _evict_until_below_limit(self) -> None:
        """新しく 1 件開けるよう、上限を下回るまで古いものを閉じる。"""
        # 上限に達している間、いちばん長く使っていないものから閉じる
        while len(self._cache) >= self.max_cached_regions:
            _, oldest = self._cache.popitem(last=False)
            # 閉じる前に必ず書き出す。捨てると変更が失われる
            oldest.close()

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

        # 開いているリージョンをすべて書き出す
        for file in self._cache.values():
            file.flush()

    def close(self) -> None:
        """開いている全リージョンを閉じる。"""
        if self._closed:
            return

        # 開いているリージョンをすべて閉じる
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

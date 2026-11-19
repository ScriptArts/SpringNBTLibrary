"""ワールドの構成の世代
ライブラリの内部だけで使う
公開APIには出さない

世代ごとの違いはこの表に集める
ワールドと``level.dat``の読み書きは表の値に従い、DataVersionによる分岐をほかの場所に書かない
"""

from __future__ import annotations

import os
from typing import List, Optional

from ..errors import SpringNbtError
from ..nbt import NbtCompound
from ._chunk_format import OLDEST_FORMAT_DATA_VERSION

#: L2（26.1以降）が始まるDataVersion
L2_MIN_DATA_VERSION = 4786

#: 標準の次元のIDと、L1でのワールド直下からの相対ディレクトリ
#: 並びがL1の``dimension_ids``の並びになる
_L1_STANDARD_DIMENSIONS = (
    ("minecraft:overworld", ""),
    ("minecraft:the_nether", "DIM-1"),
    ("minecraft:the_end", "DIM1"),
)

#: L1の``Difficulty``の数値と名前
_L1_DIFFICULTIES = ("peaceful", "easy", "normal", "hard")


class WorldLayout:
    """ワールドの構成の世代1つ分"""

    __slots__ = ("min_data_version", "legacy", "player_folder", "data_folder")

    def __init__(self, min_data_version: int, legacy: bool,
                 player_folder: List[str], data_folder: List[str]) -> None:
        #: この世代が始まるDataVersion
        self.min_data_version = min_data_version
        #: 標準の次元が直下と``DIM-1/`` ``DIM1/``に置かれ、``level.dat``にスポーンなどが直に入る構成か
        self.legacy = legacy
        #: ワールド直下からプレイヤーデータのフォルダまでの道
        self.player_folder = player_folder
        #: 次元のフォルダから付随データのフォルダまでの道
        self.data_folder = data_folder

    @staticmethod
    def for_data_version(data_version: int) -> "WorldLayout":
        """DataVersionから世代を引く
        L1より古い値もL1として扱う
        """
        # 境界以上ならL2、それ未満はL1
        if data_version >= L2_MIN_DATA_VERSION:
            return _L2

        return _L1

    @staticmethod
    def detect(data: NbtCompound, override: Optional[int]) -> "WorldLayout":
        """``level.dat``の``Data``と、利用者の指定から世代を決める

        指定があればそれを使い、無ければ``Data.DataVersion``で決める
        ``DataVersion``が無い古いワールドはL1として扱う

        :raises SpringNbtError: 指定が扱える下限より小さい場合
        """
        # 指定は下限より小さいと解釈のしようがない
        if override is not None:
            if override < OLDEST_FORMAT_DATA_VERSION:
                raise SpringNbtError.invalid_argument(
                    "世代を選ぶDataVersionは%d以上でなければならない: %d"
                    % (OLDEST_FORMAT_DATA_VERSION, override))

            return WorldLayout.for_data_version(override)

        found = data.opt_int("DataVersion")

        # DataVersionが無いのは1.9より前のワールドなのでL1
        if found is None:
            return _L1

        return WorldLayout.for_data_version(found)

    def dimension_directory(self, world_directory: str, dimension_id: str) -> str:
        """次元のフォルダのパス
        次元のIDは名前空間つきで渡す
        """
        colon = dimension_id.index(":")
        namespace = dimension_id[:colon]
        path = dimension_id[colon + 1:]

        # L1の標準の次元は、ワールド直下か``DIM-1/`` ``DIM1/``に置かれる
        if self.legacy:
            for standard_id, relative in _L1_STANDARD_DIMENSIONS:
                # 標準の次元ならその専用の場所を返す
                if dimension_id == standard_id:
                    # オーバーワールドはワールドのフォルダそのもの
                    if relative == "":
                        return world_directory

                    return os.path.join(world_directory, relative)

        return os.path.join(world_directory, "dimensions", namespace, path)

    def has_dimension(self, world_directory: str, dimension_id: str) -> bool:
        """次元が存在するか"""
        directory = self.dimension_directory(world_directory, dimension_id)

        # L1のオーバーワールドはワールド直下なので、``region/``の有無で判断する
        if self.legacy and dimension_id == _L1_STANDARD_DIMENSIONS[0][0]:
            return os.path.isdir(os.path.join(directory, "region"))

        return os.path.isdir(directory)

    def dimension_ids(self, world_directory: str) -> List[str]:
        """存在する次元のIDを返す
        L1では標準の3つを固定の順に並べ、そのあとにデータパックの次元をIDの順に並べる
        """
        found = []

        # L1の標準の次元は固定の順で先に並べる
        if self.legacy:
            for standard_id, _ in _L1_STANDARD_DIMENSIONS:
                # 存在する標準の次元だけを数える
                if self.has_dimension(world_directory, standard_id):
                    found.append(standard_id)

        extra = []
        root = os.path.join(world_directory, "dimensions")

        if os.path.isdir(root):
            # dimensions/<名前空間>/<パス>/の2段を辿る
            for namespace_name in os.listdir(root):
                namespace_dir = os.path.join(root, namespace_name)

                # 名前空間はディレクトリだけ
                if not os.path.isdir(namespace_dir):
                    continue

                # 2段目が次元のパス
                for path_name in os.listdir(namespace_dir):
                    dimension_id = "%s:%s" % (namespace_name, path_name)

                    # ディレクトリだけを次元として数える
                    if not os.path.isdir(os.path.join(namespace_dir, path_name)):
                        continue

                    # L1では標準の次元をdimensions/の下からは探さない
                    if self.legacy and dimension_id in found:
                        continue

                    extra.append(dimension_id)

        # 走査順がファイルシステム依存にならないよう並べる
        extra.sort()
        return found + extra

    def player_directory(self, world_directory: str) -> str:
        """プレイヤーデータのフォルダのパス"""
        return os.path.join(world_directory, *self.player_folder)

    def data_file_path(self, dimension_directory: str, name: str) -> str:
        """次元のフォルダの下の付随データのファイルのパス"""
        return os.path.join(dimension_directory, *self.data_folder, name + ".dat")

    def spawn_pos(self, data: NbtCompound) -> List[int]:
        """スポーン地点の``[x, y, z]``"""
        # L1は3つの整数に分かれて入っている
        if self.legacy:
            return [data.get_int("SpawnX"), data.get_int("SpawnY"), data.get_int("SpawnZ")]

        return data.get_compound("spawn").get_int_array("pos")

    def spawn_dimension(self, data: NbtCompound) -> str:
        """スポーン地点の次元ID

        :raises SpringNbtError: この世代の``level.dat``に無い場合（``UNSUPPORTED_FEATURE``）
        """
        # L1にはスポーン地点の次元を持つキーが無い
        if self.legacy:
            raise SpringNbtError.unsupported_feature(
                "26.1より前のlevel.datにはスポーン地点の次元が無い")

        return data.get_compound("spawn").get_string("dimension")

    def difficulty(self, data: NbtCompound) -> str:
        """難易度（``normal``など）

        :raises SpringNbtError: 数値が0〜3の外の場合（``MALFORMED_DATA``）
        """
        # L1は0〜3の数値で入っている
        if self.legacy:
            number = data.get_byte("Difficulty")

            if number < 0 or number >= len(_L1_DIFFICULTIES):
                raise SpringNbtError.malformed("Difficultyが0〜3の外: %d" % number)

            return _L1_DIFFICULTIES[number]

        return data.get_compound("difficulty_settings").get_string("difficulty")

    def is_hardcore(self, data: NbtCompound) -> bool:
        """ハードコアか"""
        # L1は``Data``の直下に入っている
        if self.legacy:
            return data.get_bool("hardcore")

        return data.get_compound("difficulty_settings").get_bool("hardcore")


#: L1: 1.13〜1.21.x
_L1 = WorldLayout(
    min_data_version=OLDEST_FORMAT_DATA_VERSION,
    legacy=True,
    player_folder=["playerdata"],
    data_folder=["data"])

#: L2: 26.1以降
_L2 = WorldLayout(
    min_data_version=L2_MIN_DATA_VERSION,
    legacy=False,
    player_folder=["players", "data"],
    data_folder=["data", "minecraft"])

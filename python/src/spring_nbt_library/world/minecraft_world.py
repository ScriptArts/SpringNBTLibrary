"""Minecraft Java版のセーブデータ 1 つ分と、その中の次元

26.x では構成が大きく変わっており、標準の3次元も
``dimensions/<名前空間>/<パス>/`` の下に並ぶ

仕様: ``docs/spec/40-world-layout.md``
"""

from __future__ import annotations

import os
import shutil
from typing import Dict, List, Optional, Union

try:
    import fcntl
except ImportError:
    # Windows には fcntl が無い
    # その場合 session.lock の確認は行わない
    fcntl = None

from ..anvil import ChunkPos, RegionFileMode, RegionFolder
from ..errors import ErrorCode, SpringNbtError
from ..nbt import NamedTag, NbtCompound, read_file, write_file
from .block_state import BlockState
from .chunk import Chunk, ChunkReadOptions, ChunkWriteOptions

__all__ = ["Dimension", "LevelData", "MinecraftWorld", "WorldOpenOptions"]


class WorldOpenOptions:
    """ワールドを開くときの動作"""

    def __init__(self, writable: bool = False, ignore_session_lock: bool = False,
                 chunk_read: Optional[ChunkReadOptions] = None,
                 chunk_write: Optional[ChunkWriteOptions] = None) -> None:
        #: 読み書きで開くか
        # 既定は読み取り専用
        self.writable = writable

        #: ``session.lock`` の確認を飛ばすか
        #:
        #: Minecraft が起動中のワールドへ書き込むとデータが壊れる
        #: 既定では書き込みモードで開くときに必ず確認する
        # これを立てるのは自己責任
        self.ignore_session_lock = ignore_session_lock

        #: チャンク読み込みのオプション
        if chunk_read is None:
            self.chunk_read = ChunkReadOptions()
        else:
            self.chunk_read = chunk_read

        #: チャンク書き込みのオプション
        if chunk_write is None:
            self.chunk_write = ChunkWriteOptions()
        else:
            self.chunk_write = chunk_write


class LevelData:
    """``level.dat`` の内容

    26.x では大幅に軽量化されており、ゲームルールやワールド生成設定は
    ``data/minecraft/`` 配下の個別ファイルへ分離されている

    仕様: ``docs/spec/40-world-layout.md`` 2章
    """

    __slots__ = ("_root_name", "raw", "data")

    def __init__(self, named: NamedTag) -> None:
        self._root_name = named.name
        self.raw = named.tag
        self.data = named.tag.get_compound("Data")

    @property
    def data_version(self) -> int:
        """チャンク構造のバージョン"""
        return self.data.get_int("DataVersion")

    @property
    def level_name(self) -> str:
        """ワールド名"""
        return self.data.get_string("LevelName")

    @property
    def time(self) -> int:
        """ワールドの経過時間（tick）"""
        return self.data.get_long("Time")

    @property
    def game_type(self) -> int:
        """ゲームモード
        0=サバイバル 1=クリエイティブ 2=アドベンチャー 3=スペクテイター
        """
        return self.data.get_int("GameType")

    @property
    def spawn_pos(self) -> List[int]:
        """スポーン地点の ``[x, y, z]``"""
        return self.data.get_compound("spawn").get_int_array("pos")

    @property
    def spawn_dimension(self) -> str:
        """スポーン地点の次元ID"""
        return self.data.get_compound("spawn").get_string("dimension")

    @property
    def difficulty(self) -> str:
        """難易度（``normal`` など）"""
        return self.data.get_compound("difficulty_settings").get_string("difficulty")

    @property
    def is_hardcore(self) -> bool:
        """ハードコアか"""
        return self.data.get_compound("difficulty_settings").get_bool("hardcore")

    @property
    def version_name(self) -> str:
        """バージョン名（``26.2`` など）"""
        return self.data.get_compound("Version").get_string("Name")

    def to_named_tag(self) -> NamedTag:
        """書き出し用の :class:`NamedTag` を作る"""
        return NamedTag(self._root_name, self.raw)


class Dimension:
    """ワールド内の次元 1 つ分
    ``region/`` ``entities/`` ``poi/`` をまとめて扱う

    ブロックの取得・設定は**絶対ワールド座標**で行い、
    リージョン・チャンク・セクションの解決は内部で済ませる

    仕様: ``docs/spec/40-world-layout.md`` 4章
    """

    #: オーバーワールドの次元ID
    OVERWORLD = "minecraft:overworld"

    #: ネザーの次元ID
    THE_NETHER = "minecraft:the_nether"

    #: エンドの次元ID
    THE_END = "minecraft:the_end"

    def __init__(self, dimension_id: str, directory: str, options: WorldOpenOptions) -> None:
        self.id = dimension_id
        self.directory = directory
        self._options = options
        self._chunk_cache: Dict[str, Chunk] = {}
        self._regions: Optional[RegionFolder] = None
        self._entities: Optional[RegionFolder] = None
        self._poi: Optional[RegionFolder] = None
        self._closed = False

    def __enter__(self) -> "Dimension":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def region_folder(self) -> Optional[RegionFolder]:
        """地形のリージョンフォルダ
        無ければ None
        """
        self._regions = self._folder(self._regions, "region")
        return self._regions

    def entity_folder(self) -> Optional[RegionFolder]:
        """エンティティのリージョンフォルダ
        無ければ None
        """
        self._entities = self._folder(self._entities, "entities")
        return self._entities

    def poi_folder(self) -> Optional[RegionFolder]:
        """POI のリージョンフォルダ
        無ければ None
        """
        self._poi = self._folder(self._poi, "poi")
        return self._poi

    def data_file(self, name: str) -> Optional[NbtCompound]:
        """``data/minecraft/<name>.dat`` を読む
        存在しなければ None
        """
        self._ensure_open()
        path = os.path.join(self.directory, "data", "minecraft", name + ".dat")

        if not os.path.exists(path):
            return None

        return read_file(path).tag

    def chunk_positions(self) -> List[ChunkPos]:
        """この次元に存在する全チャンクの座標を返す"""
        self._ensure_open()
        folder = self.region_folder()

        if folder is None:
            return []

        return folder.chunk_positions()

    def chunk(self, chunk_x: int, chunk_z: int) -> Optional[Chunk]:
        """チャンクを読む
        読み込んだチャンクはキャッシュされる
        """
        self._ensure_open()
        key = "%d,%d" % (chunk_x, chunk_z)
        cached = self._chunk_cache.get(key)

        if cached is not None:
            return cached

        folder = self.region_folder()

        if folder is None:
            return None

        nbt = folder.read_chunk(chunk_x, chunk_z)

        if nbt is None:
            return None

        chunk = Chunk.from_nbt(nbt, self._options.chunk_read)
        self._chunk_cache[key] = chunk
        return chunk

    def save_chunk(self, chunk: Chunk) -> None:
        """チャンクを書き戻す"""
        self._ensure_open()
        self._ensure_writable()
        folder = self.region_folder()

        if folder is None:
            raise SpringNbtError.invalid_argument(
                "region/ が無い次元には書き込めない: %s" % self.id)

        folder.write_chunk(chunk.x, chunk.z, chunk.to_nbt(self._options.chunk_write))
        chunk.is_modified = False

    def get_block(self, x: int, y: int, z: int) -> Optional[BlockState]:
        """絶対座標でブロックを取得する
        チャンクが無ければ None
        """
        chunk = self.chunk(x >> 4, z >> 4)

        if chunk is None:
            return None

        return chunk.get_block(x & 15, y, z & 15)

    def set_block(self, x: int, y: int, z: int, state: Union[BlockState, str]) -> None:
        """絶対座標でブロックを設定する

        ``minecraft:oak_stairs[facing=north]`` の形の文字列でも指定できる

        変更したチャンクには印が付き、:meth:`flush` でまとめて書き戻される
        本ライブラリはチャンクを新規生成しないので、存在しない座標はエラーになる
        """
        self._ensure_writable()
        chunk_x = x >> 4
        chunk_z = z >> 4
        chunk = self.chunk(chunk_x, chunk_z)

        if chunk is None:
            raise SpringNbtError.invalid_argument(
                "チャンク (%d, %d) が存在しない。本ライブラリはチャンクを生成しない"
                % (chunk_x, chunk_z))

        chunk.set_block(x & 15, y, z & 15, state)

    def get_biome(self, x: int, y: int, z: int) -> Optional[str]:
        """絶対座標でバイオームを取得する
        4×4×4 の単位
        """
        chunk = self.chunk(x >> 4, z >> 4)

        if chunk is None:
            return None

        return chunk.get_biome(x & 15, y, z & 15)

    def set_biome(self, x: int, y: int, z: int, biome: str) -> None:
        """絶対座標でバイオームを設定する
        4×4×4 の単位
        """
        self._ensure_writable()
        chunk_x = x >> 4
        chunk_z = z >> 4
        chunk = self.chunk(chunk_x, chunk_z)

        if chunk is None:
            raise SpringNbtError.invalid_argument(
                "チャンク (%d, %d) が存在しない。本ライブラリはチャンクを生成しない"
                % (chunk_x, chunk_z))

        chunk.set_biome(x & 15, y, z & 15, biome)

    def flush(self) -> None:
        """変更したチャンクをすべて書き戻し、リージョンをディスクへ反映する"""
        self._ensure_open()

        if not self._options.writable:
            return

        # 印の立っているチャンクだけを書き戻す
        for chunk in self._chunk_cache.values():
            # 触っていないチャンクは書き戻さない
            if chunk.is_modified:
                self.region_folder().write_chunk(
                    chunk.x, chunk.z, chunk.to_nbt(self._options.chunk_write))
                chunk.is_modified = False

        # 開いているフォルダだけを書き出す
        for folder in (self._regions, self._entities, self._poi):
            # 開いていないフォルダは触らない
            if folder is not None:
                folder.flush()

    def close(self) -> None:
        """変更を書き戻してから閉じる"""
        if self._closed:
            return

        # 書き込みモードなら、閉じる前に変更を反映する
        if self._options.writable:
            self.flush()

        # 開いているフォルダだけを閉じる
        for folder in (self._regions, self._entities, self._poi):
            # 開いていないフォルダは触らない
            if folder is not None:
                folder.close()

        self._chunk_cache.clear()
        self._closed = True

    def _folder(self, slot: Optional[RegionFolder], name: str) -> Optional[RegionFolder]:
        """フォルダを遅延して開く
        存在しなければ None のまま
        """
        self._ensure_open()

        if slot is not None:
            return slot

        path = os.path.join(self.directory, name)

        # 生成されていない次元にはディレクトリ自体が無い
        if not os.path.isdir(path) and not self._options.writable:
            return None

        # ワールドを開いたモードに合わせる
        if self._options.writable:
            mode = RegionFileMode.READ_WRITE
        else:
            mode = RegionFileMode.READ_ONLY

        return RegionFolder.open(path, mode)

    def _ensure_writable(self) -> None:
        if not self._options.writable:
            raise SpringNbtError.invalid_argument("読み取り専用で開いたワールドには書き込めない")

    def _ensure_open(self) -> None:
        if self._closed:
            raise SpringNbtError.invalid_argument("既に閉じられた次元")


class MinecraftWorld:
    """Minecraft Java版のセーブデータ 1 つ分"""

    def __init__(self, directory: str, options: WorldOpenOptions, level: NamedTag) -> None:
        self.directory = directory
        self._options = options
        self.level = LevelData(level)
        self._dimensions: Dict[str, Dimension] = {}
        self._closed = False

    @staticmethod
    def open(directory: str,
             options: Optional[WorldOpenOptions] = None) -> "MinecraftWorld":
        """ワールドを開く

        :raises SpringNbtError: ディレクトリや ``level.dat`` が無い場合
        """
        if options is None:
            effective = WorldOpenOptions()
        else:
            effective = options

        if not os.path.isdir(directory):
            raise SpringNbtError(ErrorCode.IO, "ワールドディレクトリが無い: %s" % directory)

        level_path = os.path.join(directory, "level.dat")

        if not os.path.exists(level_path):
            raise SpringNbtError(ErrorCode.IO, "level.dat が無い: %s" % level_path)

        # 書き込みで開くときだけ、Minecraft が起動中でないかを確かめる
        if effective.writable and not effective.ignore_session_lock:
            _check_session_lock(directory)

        return MinecraftWorld(directory, effective, read_file(level_path))

    def __enter__(self) -> "MinecraftWorld":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def data_file(self, name: str) -> Optional[NbtCompound]:
        """``data/minecraft/<name>.dat`` を読む
        存在しなければ None

        26.x では ``game_rules`` / ``weather`` / ``world_gen_settings`` などが
        この形で ``level.dat`` から分離されている
        """
        self._ensure_open()
        path = os.path.join(self.directory, "data", "minecraft", name + ".dat")

        if not os.path.exists(path):
            return None

        return read_file(path).tag

    def dimension_ids(self) -> List[str]:
        """存在する次元のIDを返す"""
        self._ensure_open()
        root = os.path.join(self.directory, "dimensions")

        if not os.path.isdir(root):
            return []

        found = []

        # dimensions/<名前空間>/<パス>/ の 2 段を辿る
        for namespace_name in os.listdir(root):
            namespace_dir = os.path.join(root, namespace_name)

            if not os.path.isdir(namespace_dir):
                continue

            # 2 段目が次元のパス
            for path_name in os.listdir(namespace_dir):
                # ディレクトリだけを次元として数える
                if os.path.isdir(os.path.join(namespace_dir, path_name)):
                    found.append("%s:%s" % (namespace_name, path_name))

        # 走査順がファイルシステム依存にならないよう並べる
        found.sort()
        return found

    def dimension(self, dimension_id: str) -> Optional[Dimension]:
        """次元を得る
        ディレクトリが無ければ None
        """
        self._ensure_open()
        normalized = _normalize_dimension_id(dimension_id)
        cached = self._dimensions.get(normalized)

        if cached is not None:
            return cached

        colon = normalized.index(":")
        path = os.path.join(self.directory, "dimensions",
                            normalized[:colon], normalized[colon + 1:])

        if not os.path.isdir(path):
            return None

        opened = Dimension(normalized, path, self._options)
        self._dimensions[normalized] = opened
        return opened

    def player_ids(self) -> List[str]:
        """プレイヤーのUUID一覧"""
        self._ensure_open()
        path = os.path.join(self.directory, "players", "data")

        if not os.path.isdir(path):
            return []

        found = [name[:-4] for name in os.listdir(path) if name.endswith(".dat")]
        found.sort()
        return found

    def player(self, uuid: str) -> Optional[NbtCompound]:
        """プレイヤーデータを読む
        存在しなければ None
        """
        self._ensure_open()
        path = os.path.join(self.directory, "players", "data", uuid + ".dat")

        if not os.path.exists(path):
            return None

        return read_file(path).tag

    def save_level(self) -> None:
        """``level.dat`` を書き戻す

        壊れるとワールド全体が開けなくなるため、
        一時ファイルへ書いてから ``level.dat_old`` へ退避し、最後に置き換える
        """
        self._ensure_open()

        if not self._options.writable:
            raise SpringNbtError.invalid_argument("読み取り専用で開いたワールドには書き込めない")

        path = os.path.join(self.directory, "level.dat")
        temporary = path + ".tmp"
        backup = path + "_old"

        write_file(temporary, self.level.to_named_tag())

        # 既存の level.dat は、置き換える前に level.dat_old へ退避する
        if os.path.exists(path):
            shutil.copyfile(path, backup)

        os.replace(temporary, path)

    def close(self) -> None:
        """開いている次元をすべて閉じる"""
        if self._closed:
            return

        # 開いている次元をすべて閉じる
        for dimension in self._dimensions.values():
            dimension.close()

        self._dimensions.clear()
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise SpringNbtError.invalid_argument("既に閉じられたワールド")


def _check_session_lock(directory: str) -> None:
    """``session.lock`` を排他で開けるか確かめる

    Minecraft は起動中このファイルのロックを保持し続ける
    ファイルの存在自体は起動していなくても残るので、
    ロックが取れるかどうかで判定する

    仕様: ``docs/spec/40-world-layout.md`` 3章
    """
    lock_path = os.path.join(directory, "session.lock")

    if not os.path.exists(lock_path):
        return

    # ロックの手段が無い環境では確認できないので素通しする
    if fcntl is None:
        return

    handle = open(lock_path, "r+b")

    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise SpringNbtError(
                ErrorCode.IO,
                "session.lock を排他で開けない。Minecraft が起動中の可能性がある。"
                "無視するなら WorldOpenOptions(ignore_session_lock=True)") from error

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def _normalize_dimension_id(dimension_id: str) -> str:
    """名前空間が省略されていたら ``minecraft:`` を補う"""
    if ":" in dimension_id:
        return dimension_id

    return "minecraft:" + dimension_id

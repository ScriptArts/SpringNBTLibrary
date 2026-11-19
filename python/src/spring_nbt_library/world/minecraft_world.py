"""Minecraft Java版のセーブデータ1つ分と、その中の次元

26.1以降は構成が大きく変わっており、標準の3次元も``dimensions/<名前空間>/<パス>/``の下に並ぶ
それより前の構成も、``level.dat``のDataVersionで見分けて読み書きできる
"""

from __future__ import annotations

import os
import shutil
from typing import Dict, List, Optional, Union

try:
    import fcntl
except ImportError:
    # Windowsにはfcntlが無い
    # その場合session.lockの確認は行わない
    fcntl = None

from ..anvil import ChunkPos, RegionFileMode, RegionFolder
from ..errors import ErrorCode, SpringNbtError
from ..nbt import NamedTag, NbtCompound, read_file, write_bytes
from .block_state import BlockState
from ._world_layout import WorldLayout
from .chunk import Chunk, ChunkReadOptions, ChunkWriteOptions

__all__ = ["Dimension", "LevelData", "MinecraftWorld", "WorldOpenOptions"]


class WorldOpenOptions:
    """ワールドを開くときの動作"""

    def __init__(self, writable: bool = False, ignore_session_lock: bool = False,
                 chunk_read: Optional[ChunkReadOptions] = None,
                 chunk_write: Optional[ChunkWriteOptions] = None,
                 format_data_version: Optional[int] = None) -> None:
        #: 読み書きで開くか
        #: 既定は読み取り専用
        self.writable = writable

        #: ``session.lock``の確認を飛ばすか
        #:
        #: Minecraftが起動中のワールドへ書き込むとデータがおかしくなる
        #: 既定では書き込みモードで開くときに必ず確認する
        #: これを立てるのは自己責任
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

        #: ワールドの構成の世代を選ぶDataVersion
        #:
        #: Noneなら、``level.dat``のDataVersionで選ぶ
        #: 1519以上でなければならない
        #: そのワールドから読むすべてのチャンクの世代にも効き、``chunk_read.format_data_version``より優先する
        self.format_data_version = format_data_version


class LevelData:
    """``level.dat``の内容

    26.1以降は大幅に軽量化されており、ゲームルールやワールド生成設定は``data/minecraft/``配下の個別ファイルへ分離されている
    それより前は、``level.dat``の中に入っている

    スポーン地点・難易度・ハードコアの取得子は、構成の世代ごとのキーを読む
    """

    __slots__ = ("_root_name", "raw", "data", "_layout")

    def __init__(self, named: NamedTag, format_data_version: Optional[int] = None) -> None:
        self._root_name = named.name
        self.raw = named.tag
        self.data = named.tag.get_compound("Data")
        self._layout = WorldLayout.detect(self.data, format_data_version)

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
        """スポーン地点の``[x, y, z]``"""
        return self._layout.spawn_pos(self.data)

    @property
    def spawn_dimension(self) -> str:
        """スポーン地点の次元ID

        26.1より前の``level.dat``には無いので、``UNSUPPORTED_FEATURE``になる
        """
        return self._layout.spawn_dimension(self.data)

    @property
    def difficulty(self) -> str:
        """難易度（``normal``など）

        26.1より前の数値は、0 ``peaceful`` 1 ``easy`` 2 ``normal`` 3 ``hard``に直す
        """
        return self._layout.difficulty(self.data)

    @property
    def is_hardcore(self) -> bool:
        """ハードコアか"""
        return self._layout.is_hardcore(self.data)

    @property
    def version_name(self) -> str:
        """バージョン名（``26.3``など）"""
        return self.data.get_compound("Version").get_string("Name")

    def to_named_tag(self) -> NamedTag:
        """書き出し用の:class:`NamedTag`を作る"""
        return NamedTag(self._root_name, self.raw)


class Dimension:
    """ワールド内の次元1つ分
    ``region/`` ``entities/`` ``poi/``をまとめて扱う

    ブロックの取得・設定は**絶対ワールド座標**で行い、リージョン・チャンク・セクションの解決は内部で済ませる
    """

    #: オーバーワールドの次元ID
    OVERWORLD = "minecraft:overworld"

    #: ネザーの次元ID
    THE_NETHER = "minecraft:the_nether"

    #: エンドの次元ID
    THE_END = "minecraft:the_end"

    def __init__(self, dimension_id: str, directory: str, options: WorldOpenOptions,
                 layout: WorldLayout) -> None:
        self.id = dimension_id
        self.directory = directory
        self._options = options
        self._layout = layout
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
        無ければNone
        """
        self._regions = self._folder(self._regions, "region")
        return self._regions

    def entity_folder(self) -> Optional[RegionFolder]:
        """エンティティのリージョンフォルダ
        無ければNone
        """
        self._entities = self._folder(self._entities, "entities")
        return self._entities

    def poi_folder(self) -> Optional[RegionFolder]:
        """POIのリージョンフォルダ
        無ければNone
        """
        self._poi = self._folder(self._poi, "poi")
        return self._poi

    def data_file(self, name: str) -> Optional[NbtCompound]:
        """``data/minecraft/<name>.dat``を読む
        存在しなければNone

        次元ごとの``world_border`` / ``raids`` / ``chunk_tickets``などが入る
        26.1より前は``data/<name>.dat``を読む
        """
        self._ensure_open()
        path = self._layout.data_file_path(self.directory, name)

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
        読み込んだチャンクはキャッシュされ、次回は同じインスタンスが返る
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
        チャンクが無ければNone
        """
        chunk = self.chunk(x >> 4, z >> 4)

        if chunk is None:
            return None

        return chunk.get_block(x & 15, y, z & 15)

    def set_block(self, x: int, y: int, z: int, state: Union[BlockState, str]) -> None:
        """絶対座標でブロックを設定する

        ``minecraft:oak_stairs[facing=north]``の形の文字列でも指定できる

        変更したチャンクには印が付き、:meth:`flush`でまとめて書き戻される
        本ライブラリはチャンクを新規生成しないので、チャンクが存在しない座標はエラーになる
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
        4×4×4の単位
        """
        chunk = self.chunk(x >> 4, z >> 4)

        if chunk is None:
            return None

        return chunk.get_biome(x & 15, y, z & 15)

    def set_biome(self, x: int, y: int, z: int, biome: str) -> None:
        """絶対座標でバイオームを設定する
        4×4×4の単位
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
        存在しなければNoneのまま
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
    """Minecraft Java版のセーブデータ1つ分"""

    def __init__(self, directory: str, options: WorldOpenOptions, level: NamedTag) -> None:
        self.directory = directory
        self.level = LevelData(level, options.format_data_version)
        self._layout = self.level._layout
        self._options = _with_format_data_version(options)
        self._dimensions: Dict[str, Dimension] = {}
        self._closed = False

    @staticmethod
    def open(directory: str,
             options: Optional[WorldOpenOptions] = None) -> "MinecraftWorld":
        """ワールドを開く

        :raises SpringNbtError: ディレクトリや``level.dat``が無い場合、
            または書き込みモードで``session.lock``を取得できない場合（``fcntl``が使える環境のみ確かめる）、
            または``format_data_version``が1519未満の場合
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

        # 書き込むなら、Minecraftが起動中でないことを先に確かめる
        if effective.writable and not effective.ignore_session_lock:
            _check_session_lock(directory)

        return MinecraftWorld(directory, effective, read_file(level_path))

    def __enter__(self) -> "MinecraftWorld":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def data_file(self, name: str) -> Optional[NbtCompound]:
        """``data/minecraft/<name>.dat``を読む
        存在しなければNone

        26.1以降は``game_rules`` / ``weather`` / ``world_gen_settings``などがこの形で``level.dat``から分離されている
        26.1より前は``data/<name>.dat``を読む
        """
        self._ensure_open()
        path = self._layout.data_file_path(self.directory, name)

        if not os.path.exists(path):
            return None

        return read_file(path).tag

    def dimension_ids(self) -> List[str]:
        """存在する次元のIDを返す
        26.1より前は標準の3次元を固定の順で先に並べ、データパックの次元を``dimensions/``から探す
        """
        self._ensure_open()
        return self._layout.dimension_ids(self.directory)

    def dimension(self, dimension_id: str) -> Optional[Dimension]:
        """次元を得る
        ディレクトリが無ければNone
        """
        self._ensure_open()
        normalized = _normalize_dimension_id(dimension_id)
        cached = self._dimensions.get(normalized)

        if cached is not None:
            return cached

        # 存在しない次元はNoneのまま
        if not self._layout.has_dimension(self.directory, normalized):
            return None

        path = self._layout.dimension_directory(self.directory, normalized)
        opened = Dimension(normalized, path, self._options, self._layout)
        self._dimensions[normalized] = opened
        return opened

    def player_ids(self) -> List[str]:
        """プレイヤーのUUID一覧"""
        self._ensure_open()
        path = self._layout.player_directory(self.directory)

        if not os.path.isdir(path):
            return []

        found = [name[:-4] for name in os.listdir(path) if name.endswith(".dat")]
        found.sort()
        return found

    def player(self, uuid: str) -> Optional[NbtCompound]:
        """プレイヤーデータを読む
        存在しなければNone
        """
        self._ensure_open()
        path = os.path.join(self._layout.player_directory(self.directory), uuid + ".dat")

        if not os.path.exists(path):
            return None

        return read_file(path).tag

    def save_level(self) -> None:
        """``level.dat``を書き戻す

        ``level.dat``がおかしくなるとワールド全体が開けなくなるため、
        一時ファイルへ書いて内容をディスクへ確実に書き出してから、既存の``level.dat``を``level.dat_old``へ退避し、最後に置き換える
        """
        self._ensure_open()

        if not self._options.writable:
            raise SpringNbtError.invalid_argument("読み取り専用で開いたワールドには書き込めない")

        path = os.path.join(self.directory, "level.dat")
        temporary = path + ".tmp"
        backup = path + "_old"

        encoded = write_bytes(self.level.to_named_tag())

        try:
            # 一時ファイルへ書き、置き換える前に内容をディスクへ確実に書き出す
            with open(temporary, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())

            # 既存のlevel.datは、置き換える前にlevel.dat_oldへ退避する
            if os.path.exists(path):
                shutil.copyfile(path, backup)

            os.replace(temporary, path)
        except OSError as error:
            raise SpringNbtError(ErrorCode.IO, "level.dat を書けない: %s" % path) from error

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
    """``session.lock``を排他で開けるか確かめる

    Minecraftは起動中このファイルのロックを保持し続ける
    ファイルの存在自体は起動していなくても残るので、
    ロックが取れるかどうかで判定する
    """
    lock_path = os.path.join(directory, "session.lock")

    if not os.path.exists(lock_path):
        return

    # ロックの手段が無い環境では確認できないので、確認せずに進める
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


def _with_format_data_version(options: WorldOpenOptions) -> WorldOpenOptions:
    """ワールドで世代を指定されていれば、チャンクの読み込みにも同じ指定を入れた複製を返す
    渡されたオプションは書き換えない
    """
    # 指定が無ければ、チャンクごとの指定やチャンク自身のDataVersionに任せる
    if options.format_data_version is None:
        return options

    source = options.chunk_read
    chunk_read = ChunkReadOptions(
        on_version_mismatch=source.on_version_mismatch,
        on_warning=source.on_warning,
        lenient_bit_storage=source.lenient_bit_storage,
        format_data_version=options.format_data_version)

    return WorldOpenOptions(
        writable=options.writable,
        ignore_session_lock=options.ignore_session_lock,
        chunk_read=chunk_read,
        chunk_write=options.chunk_write,
        format_data_version=options.format_data_version)


def _normalize_dimension_id(dimension_id: str) -> str:
    """名前空間が省略されていたら``minecraft:``を補う"""
    if ":" in dimension_id:
        return dimension_id

    return "minecraft:" + dimension_id

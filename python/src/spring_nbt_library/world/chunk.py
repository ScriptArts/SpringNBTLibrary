"""チャンク1つ分
地形の読み書きはここから行う

**読んだNBTをそのまま保持し、書き戻すときに作り直すのはセクションだけにする**
未知のキーを落とさないので、将来の追加要素があってもデータをおかしくしない
"""

from __future__ import annotations

import enum
from typing import Callable, Dict, List, Optional, Union

from .. import MIN_SUPPORTED_DATA_VERSION, TARGET_DATA_VERSION
from ..errors import ErrorCode, SpringNbtError
from ..nbt import NbtCompound, NbtInt, NbtIntArray, NbtList, NbtString, NbtTag, TagType
from ._chunk_format import (
    FULL_STATUSES,
    OLDEST_FORMAT_DATA_VERSION,
    BiomeStorage,
    BlockStorage,
    ChunkFormat,
)
from .block_state import BlockState
from .paletted_container import PalettedContainer

__all__ = [
    "BIOMES_PER_SECTION",
    "BLOCKS_PER_SECTION",
    "Chunk",
    "ChunkReadOptions",
    "ChunkSection",
    "ChunkWriteOptions",
    "VersionMismatchAction",
    "biome_index",
    "block_index",
]

#: セクション1つに入るブロック数
BLOCKS_PER_SECTION = 4096

#: セクション1つに入るバイオームのエントリ数（4×4×4単位）
BIOMES_PER_SECTION = 64

#: 1.15から1.17までの形式で、チャンクの``Biomes``が持つ数値のバイオームIDの数（4×4×4単位で高さ256まで）
_BIOME_IDS_3D_LENGTH = 1024

#: 1.14までの形式で、チャンクの``Biomes``が持つ数値のバイオームIDの数（列ごと）
_BIOME_IDS_2D_LENGTH = 256

#: DataVersionの無いチャンクで、世代の指定も無いときの:attr:`Chunk.format_data_version`
_MISSING_DATA_VERSION = -1

#: 1.17までの形式で、バイオームIDを持つ最も高いY座標
_BIOME_IDS_MAX_Y = 255

#: 生成段階の名前空間
_MINECRAFT_NAMESPACE = "minecraft:"


def _write_container(section: NbtCompound, key: str, written: NbtCompound,
                     read_keys: Optional[List[str]]) -> None:
    """パレット付きコンテナを、読んだときのキーの並びを保ってセクションへ書き戻す

    読んだときにあったキーはその並びで置き、要らなくなった``data``は落とす
    読んだときに無かった``data``を足すときだけ、ライブラリの並び（``data``、``palette``の順）を先に置く
    どちらの場合も、読んだときにあったほかのキーは残す
    並びは読んだときのキーで決めるので、何度書き戻しても同じ結果になる
    """
    current = section.opt_compound(key)

    # 読んだときにコンテナが無ければ、書き出した形をそのまま置く
    if current is None or read_keys is None:
        section.set(key, written)
        return

    order: List[str] = []
    # 読んだときに無かったdataを足すときだけ、ライブラリの並びを先に置く
    if "data" in written and "data" not in read_keys:
        order.extend(written.keys())

    # 読んだときの並びで、残すキーを後ろに続ける
    for name in read_keys:
        # 先に並べたキーは二度入れない
        if name in order:
            continue

        # 要らなくなったdataは落とす
        if name == "data" and "data" not in written:
            continue

        order.append(name)

    result = NbtCompound()

    # 書き出した形にあるキーはその値で、ほかのキーは元の値で並べる
    for name in order:
        # コンテナの中身は書き出した形の値にする
        if name in written:
            result.set(name, written.get(name))
        else:
            result.set(name, current.get(name))

    section.set(key, result)


def _matches_position(entry: NbtCompound, x: int, y: int, z: int) -> bool:
    """付随データの要素が、指定の絶対座標を指しているか"""
    entry_x = entry.opt_int("x")
    entry_y = entry.opt_int("y")
    entry_z = entry.opt_int("z")

    # 座標を持たない要素は、対象かどうか判断できないので触らない
    if entry_x is None or entry_y is None or entry_z is None:
        return False

    return entry_x == x and entry_y == y and entry_z == z


def _describe_chunk(data_version: Optional[int]) -> str:
    """エラーや警告の文で、チャンクをDataVersionで言い表す"""
    # 1.9より前のチャンクはDataVersionを持たない
    if data_version is None:
        return "DataVersionの無いチャンク"

    return "DataVersion %dのチャンク" % data_version


def _palette_entry_for(container: PalettedContainer, state: BlockState,
                       data_version: int) -> NbtTag:
    """ブロック状態を置くときに使うパレット要素を決める

    同じ状態の要素がパレットにあれば、キーやプロパティの並びが違ってもそれを使う
    無ければ世代の形式で作る
    """
    # 実データの{Properties, Name}の並びの要素も、状態として比べて使い回す
    for entry in container.palette:
        # 状態が同じ要素が見つかれば、パレットを増やさずにそれを置く
        if BlockState.from_nbt_for_data_version(entry, data_version) == state:
            return entry

    return state.to_nbt_for_data_version(data_version)


class VersionMismatchAction(enum.Enum):
    """DataVersionが扱える形式より古いときの動作"""

    #: 警告コールバックを呼んで続行する
    #: 既定
    WARN = "warn"

    #: ``UNSUPPORTED_DATA_VERSION``の例外にする
    ERROR = "error"

    #: 何もしない
    IGNORE = "ignore"


class ChunkReadOptions:
    """チャンク読み込みのオプション
    """

    def __init__(self,
                 on_version_mismatch: VersionMismatchAction = VersionMismatchAction.WARN,
                 on_warning: Optional[Callable[[str], None]] = None,
                 lenient_bit_storage: bool = False,
                 format_data_version: Optional[int] = None) -> None:
        #: DataVersionが扱える形式より古いときの動作
        self.on_version_mismatch = on_version_mismatch
        #: 警告の通知先
        #: Noneなら何もしない
        self.on_warning = on_warning
        #: dataの長さが期待値と違うとき、長さからビット幅を逆算して読むか
        self.lenient_bit_storage = lenient_bit_storage
        #: チャンクの形式の世代を選ぶDataVersion
        #:
        #: Noneなら、チャンク自身のDataVersionで選ぶ
        #: 1519以上でなければならない
        #: 扱える形式の下限との比較には使わず、常にチャンク自身のDataVersionで比べる
        self.format_data_version = format_data_version


class ChunkWriteOptions:
    """チャンク書き込みのオプション"""

    def __init__(self, allow_foreign_data_version: bool = False) -> None:
        #: 扱える形式より古いDataVersionを持つチャンクの書き戻しを許すか
        #:
        #: 既定はFalse
        #: エラーを出さずに古いワールドを新形式で上書きし、
        #: 利用者が気づかないうちに使えなくすることを防ぐため
        self.allow_foreign_data_version = allow_foreign_data_version


_DEFAULT_READ = ChunkReadOptions()
_DEFAULT_WRITE = ChunkWriteOptions()


class ChunkSection:
    """チャンクをY方向に16ブロックずつ区切った16×16×16の立方体

    ``BlockLight`` / ``SkyLight``などの解釈していないキーは元のNBTに残り、
    書き戻しでそのまま出力される
    """

    __slots__ = ("raw", "y", "block_states", "biomes", "_block_storage", "_container_keys")

    def __init__(self, raw: NbtCompound, y: int) -> None:
        self.raw = raw
        self.y = y
        self.block_states: Optional[PalettedContainer] = None
        self.biomes: Optional[PalettedContainer] = None
        # 書き戻すときに読んだときと同じキーへ書くため、ブロックの持ち方を覚えておく
        self._block_storage = BlockStorage.CONTAINER
        # パレット付きコンテナを読んだときのキーの並び
        # 書き戻しで同じ並びにするため、コンテナのキーごとに覚えておく
        self._container_keys: Dict[str, List[str]] = {}

    @property
    def has_block_states(self) -> bool:
        """ブロック状態を持つか"""
        return self.block_states is not None

    @property
    def has_biomes(self) -> bool:
        """バイオームを持つか"""
        return self.biomes is not None

    @staticmethod
    def from_nbt(nbt: NbtCompound, options: ChunkReadOptions) -> "ChunkSection":
        """NBTからセクションを読む
        1.18以降の形式（``block_states`` / ``biomes``）として読む
        """
        section = ChunkSection(nbt, nbt.get_byte("Y"))
        block_states = nbt.opt_compound("block_states")

        # 光源専用のセクションはblock_statesを持たない
        if block_states is not None:
            section.block_states = PalettedContainer.from_nbt(
                block_states, BLOCKS_PER_SECTION, 4, options.lenient_bit_storage)
            section._container_keys["block_states"] = list(block_states.keys())

        biomes = nbt.opt_compound("biomes")

        # 光源だけを持つセクションにはバイオームが無い
        if biomes is not None:
            section.biomes = PalettedContainer.from_nbt(
                biomes, BIOMES_PER_SECTION, 1, options.lenient_bit_storage)
            section._container_keys["biomes"] = list(biomes.keys())

        return section

    @staticmethod
    def _from_nbt_for_format(nbt: NbtCompound, options: ChunkReadOptions,
                             chunk_format: ChunkFormat) -> "ChunkSection":
        """世代の持ち方に従ってNBTからセクションを読む（内部用）"""
        # 1.18以降の形式は公開の読み込みと同じ
        if chunk_format.block_storage == BlockStorage.CONTAINER:
            return ChunkSection.from_nbt(nbt, options)

        section = ChunkSection(nbt, nbt.get_byte("Y"))
        section._block_storage = chunk_format.block_storage
        palette = nbt.opt_list("Palette")
        block_states = nbt.opt_long_array("BlockStates")

        # Minecraftも両方がそろったセクションだけを読むので、
        # 片方しか無いセクション（光源だけを持つものなど）はブロックを持たない
        if palette is None or block_states is None:
            return section

        # 書き戻すときにCompoundのリストとして書くので、要素の型をここで確かめる
        for entry in palette:
            # Compound以外の要素は1.17までの形式に無い
            if not isinstance(entry, NbtCompound):
                raise SpringNbtError.unexpected_tag_type(
                    "Palette の要素が compound でない: %s" % entry.type.as_string())

        # BlockStatesはパレットが1要素でも必ず書かれる
        section.block_states = PalettedContainer._from_parts(
            list(palette), block_states, BLOCKS_PER_SECTION, 4,
            chunk_format.spanning_bit_storage, True, options.lenient_bit_storage)
        return section

    def to_nbt(self) -> NbtCompound:
        """NBTへ書き戻す
        解釈していないキーはそのまま残る
        """
        # 1.17までの形式は、セクションの直下のPaletteとBlockStatesへ書き戻す
        if self.block_states is not None \
                and self._block_storage == BlockStorage.SECTION_PALETTE:
            palette, data = self.block_states._to_parts()
            palette_tag = NbtList(TagType.COMPOUND)

            # 要素は読んだときのまま並べる
            for entry in palette:
                palette_tag.append(entry)

            # 既存のキーへ書くので、キーの並びは読んだときのまま残る
            self.raw.set_long_array("BlockStates", data)
            self.raw.set("Palette", palette_tag)
            return self.raw

        # 解釈したコンテナだけを書き戻す
        # 持たないキーは元のまま残す
        if self.block_states is not None:
            _write_container(self.raw, "block_states", self.block_states.to_nbt(),
                             self._container_keys.get("block_states"))

        # 解釈したコンテナだけを書き戻す
        # 持たないキーは元のまま残す
        if self.biomes is not None:
            _write_container(self.raw, "biomes", self.biomes.to_nbt(),
                             self._container_keys.get("biomes"))

        return self.raw

    def compact(self) -> None:
        """使われていないパレット要素を取り除く"""
        if self.block_states is not None:
            self.block_states.compact()

        # 持っているコンテナだけを掃除する
        if self.biomes is not None:
            self.biomes.compact()


class Chunk:
    """チャンク1つ分"""

    __slots__ = ("raw", "_sections", "_modified", "_format", "_format_data_version")

    def __init__(self, raw: NbtCompound) -> None:
        self.raw = raw
        # 書き戻しで読んだときと同じ並びにするため、Yを読んだ順に持つ
        self._sections: Dict[int, ChunkSection] = {}
        self._modified = False
        # 世代を引けなかったチャンクはNoneのままで、元のNBTだけを持つ
        self._format: Optional[ChunkFormat] = None
        self._format_data_version = 0

    @property
    def data_version(self) -> int:
        """チャンク構造のバージョン

        :raises SpringNbtError: ``DataVersion``の無いチャンク（1.9より前）の場合
        """
        return self.raw.get_int("DataVersion")

    @property
    def format_data_version(self) -> int:
        """チャンクの形式の世代を選ぶのに使ったDataVersion

        読み込みのオプションで指定していればその値、指定が無ければ:attr:`data_version`
        :attr:`data_version`が1519未満のチャンクでは、世代を選ばずに指定の値をそのまま返す
        ``DataVersion``の無いチャンクで指定も無ければ-1
        """
        return self._format_data_version

    @property
    def x(self) -> int:
        """絶対チャンクX座標"""
        return self._body().get_int("xPos")

    @property
    def z(self) -> int:
        """絶対チャンクZ座標"""
        return self._body().get_int("zPos")

    @property
    def min_section_y(self) -> int:
        """最下段セクションのY位置
        オーバーワールドは-4
        1.17までの形式では0

        :raises SpringNbtError: 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）
        """
        chunk_format = self._require_format()

        # 1.17までの形式はyPosを持たず、セクションは0段目から始まる
        if not chunk_format.has_y_pos:
            return 0

        return self.raw.get_int("yPos")

    @property
    def status(self) -> str:
        """生成段階（``minecraft:full``など）
        1.19までは名前空間の無い``full``などで入る
        """
        return self._body().get_string("Status")

    @property
    def is_fully_generated(self) -> bool:
        """生成が完了しているか
        ブロック改変の対象にしてよいのはこれだけ

        1.14までの形式では、1.13の``postprocessed``と``fullchunk``も生成済みとみなす
        ``Status``が無いか文字列でないチャンク（1.13より前のものなど）は生成済みとみなさない
        """
        # 1.13より前のチャンクなど、Statusを文字列として読めないものは生成済みとみなさない
        try:
            status = self.status
        except SpringNbtError:
            return False

        # 名前空間の有無はバージョンで違うので、外してから比べる
        if status.startswith(_MINECRAFT_NAMESPACE):
            status = status[len(_MINECRAFT_NAMESPACE):]

        full_statuses = FULL_STATUSES

        # 生成済みとみなす値は世代で違う
        if self._format is not None:
            full_statuses = self._format.full_statuses

        return status in full_statuses

    @property
    def is_modified(self) -> bool:
        """このチャンクに変更が加わったか

        ブロックやバイオームを書き換えると立つ
        :meth:`Dimension.flush`はこれが立っているチャンクだけを書き戻す

        ``raw``を直接いじった場合は立たないので、自分でTrueにすること
        """
        return self._modified

    @is_modified.setter
    def is_modified(self, value: bool) -> None:
        """変更の印を付け外しする"""
        self._modified = value

    @property
    def section_ys(self) -> List[int]:
        """存在するセクションのY位置
        昇順
        """
        return sorted(self._sections)

    @staticmethod
    def from_nbt(nbt: NbtCompound, options: Optional[ChunkReadOptions] = None) -> "Chunk":
        """NBTからチャンクを読む

        形式の世代は、オプションで指定したDataVersionか、チャンク自身のDataVersionで選ぶ
        DataVersionが1519未満のチャンクは、指定があってもどの世代でも解釈せず、元のNBTだけを持つ

        :raises SpringNbtError: 世代を選ぶDataVersionが1519未満の場合（INVALID_ARGUMENT）、
            選んだ世代とチャンクの構造が合わない場合（MALFORMED_DATA）、
            必須のキーが無い、または構造が想定と違う場合
        """
        if options is None:
            effective = _DEFAULT_READ
        else:
            effective = options

        override = effective.format_data_version

        # 1.13より前の形式は、どの世代の部品でも読めない
        if override is not None and override < OLDEST_FORMAT_DATA_VERSION:
            raise SpringNbtError.invalid_argument(
                "世代を選ぶDataVersionは%d以上でなければならない: %d"
                % (OLDEST_FORMAT_DATA_VERSION, override))

        chunk = Chunk(nbt)
        chunk._check_data_version(effective)
        data_version = chunk._own_data_version()
        chunk._format_data_version = _MISSING_DATA_VERSION

        # DataVersionを持つチャンクは、指定が無ければそれで世代を選ぶ
        if data_version is not None:
            chunk._format_data_version = data_version

        # 指定があれば、チャンク自身のDataVersionの代わりにその値で世代を選ぶ
        if override is not None:
            chunk._format_data_version = override

        # 1.13より前のチャンクはブロックが数値IDで、どの世代で読んでも誤った値になる
        # DataVersionの無いチャンクは1.9より前のものなので、同じく解釈しない
        if data_version is None or data_version < OLDEST_FORMAT_DATA_VERSION:
            return chunk

        chunk._format = ChunkFormat.for_data_version(chunk._format_data_version)

        # 表に無い世代のチャンクは、解釈せずに元のNBTだけを持つ
        if chunk._format is None:
            return chunk

        has_level = nbt.opt_compound("Level") is not None

        # 選んだ世代と本体の包み方が食い違うなら、空のチャンクとして読み進めずにエラーにする
        if has_level != chunk._format.wrapped_in_level:
            raise SpringNbtError.malformed(
                "DataVersion %dで選んだ形式と、ルートのLevelの有無が合わない"
                % chunk._format_data_version)

        section_list = chunk._body().opt_list(chunk._format.sections_key)

        if section_list is None:
            return chunk

        # 並び順に依存しないよう、Yから索引を作る
        for entry in section_list:
            if not isinstance(entry, NbtCompound):
                raise SpringNbtError.unexpected_tag_type(
                    "sections の要素が compound でない: %s" % entry.type.as_string())

            # セクションのブロックの持ち方は世代で違う
            section = ChunkSection._from_nbt_for_format(entry, effective, chunk._format)
            chunk._sections[section.y] = section

        return chunk

    def _own_data_version(self) -> Optional[int]:
        """チャンク自身のDataVersion
        無ければNone
        """
        return self.raw.opt_int("DataVersion")

    def _check_data_version(self, options: ChunkReadOptions) -> None:
        """DataVersionを検査し、オプションに従って警告またはエラーにする"""
        version = self._own_data_version()

        # 形式が同じであれば、新しいバージョンでもそのまま読める
        if version is not None and version >= MIN_SUPPORTED_DATA_VERSION:
            return

        message = ("%sはこのライブラリが扱う形式より古い（%d以降が対象）"
                   % (_describe_chunk(version), MIN_SUPPORTED_DATA_VERSION))

        if options.on_version_mismatch == VersionMismatchAction.ERROR:
            raise SpringNbtError(ErrorCode.UNSUPPORTED_DATA_VERSION, message)

        # 警告として扱う設定で、通知先があるときだけ知らせる
        if options.on_version_mismatch == VersionMismatchAction.WARN \
                and options.on_warning is not None:
            options.on_warning(message)

    def to_nbt(self, options: Optional[ChunkWriteOptions] = None) -> NbtCompound:
        """NBTへ書き戻す
        全セクションを読んだときの世代の形式で、読んだときの並びのまま書き戻し、他のキーはそのまま残す

        :raises SpringNbtError: DataVersionが扱える形式より古く、かつ書き戻しが許可されていない場合
        """
        if options is None:
            effective = _DEFAULT_WRITE
        else:
            effective = options

        version = self._own_data_version()
        supported = version is not None and version >= MIN_SUPPORTED_DATA_VERSION

        # 形式の違う古いチャンクは、書き戻すと使えなくなりかねない
        if not supported and not effective.allow_foreign_data_version:
            raise SpringNbtError(
                ErrorCode.UNSUPPORTED_DATA_VERSION,
                "%sは書き戻せない（%d以降が対象）。"
                "許可するなら ChunkWriteOptions(allow_foreign_data_version=True)"
                % (_describe_chunk(version), MIN_SUPPORTED_DATA_VERSION))

        # DataVersionは読んだ値のまま残す
        # 書き換えると、そのワールドを開くゲーム側の判断を誤らせる

        # 元のNBTだけを持つチャンクは、セクションも読んでいないのでそのまま返す
        if self._format is None or len(self._sections) == 0:
            return self.raw

        section_list = NbtList(TagType.COMPOUND)

        # 読んだときの並びで書き出す
        for section in self._sections.values():
            section_list.append(section.to_nbt())

        self._body().set(self._format.sections_key, section_list)
        return self.raw

    def _body(self) -> NbtCompound:
        """チャンクの本体
        1.17までの形式では``Level``の中、1.18以降はルート
        """
        level = self.raw.opt_compound("Level")

        # 世代とLevelの有無は読み込みで突き合わせてあるので、Levelがあればその中が本体
        if level is not None:
            return level

        return self.raw

    def _require_format(self) -> ChunkFormat:
        """チャンクの形式の世代を返す

        :raises SpringNbtError: 世代を引けず、元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）
        """
        # 世代を引けなかったチャンクは、ブロックなどの場所が分からない
        if self._format is None:
            raise SpringNbtError(
                ErrorCode.UNSUPPORTED_DATA_VERSION,
                "%sは形式を解釈せず元のNBTだけを持つので、この操作はできない"
                % _describe_chunk(self._own_data_version()))

        return self._format

    def _require_named_biomes(self) -> ChunkFormat:
        """バイオームを名前で読み書きできる世代を返す

        :raises SpringNbtError: 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）、
            バイオームを数値のIDで持つ世代の場合（UNSUPPORTED_FEATURE）
        """
        chunk_format = self._require_format()

        # 1.17まではバイオームを数値のIDで持ち、名前では読み書きできない
        if chunk_format.biome_storage != BiomeStorage.PALETTED:
            raise SpringNbtError.unsupported_feature(
                "DataVersion %dのチャンクはバイオームを数値のIDで持つ。"
                "get_biome_id / set_biome_idを使うこと" % self._format_data_version)

        return chunk_format

    def _require_biome_ids(self) -> ChunkFormat:
        """バイオームを数値のIDで読み書きできる世代を返す

        :raises SpringNbtError: 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）、
            バイオームを名前で持つ世代の場合（UNSUPPORTED_FEATURE）
        """
        chunk_format = self._require_format()

        # 1.18以降はバイオームを名前で持ち、数値のIDでは読み書きできない
        if chunk_format.biome_storage == BiomeStorage.PALETTED:
            raise SpringNbtError.unsupported_feature(
                "DataVersion %dのチャンクはバイオームを名前で持つ。"
                "get_biome / set_biomeを使うこと" % self._format_data_version)

        return chunk_format

    def _biome_ids(self, chunk_format: ChunkFormat) -> Optional[NbtIntArray]:
        """本体の``Biomes``を返す
        無い、IntArrayでない、長さが世代と合わない場合はNone
        """
        biomes = self._body().opt("Biomes")

        # 生成途中のチャンクなどは、Biomesを持たないか別の形で持つ
        if not isinstance(biomes, NbtIntArray) \
                or len(biomes.value) != _biome_ids_length(chunk_format):
            return None

        return biomes

    def section(self, section_y: int) -> Optional[ChunkSection]:
        """Y位置からセクションを得る
        無ければNone
        """
        return self._sections.get(section_y)

    def get_block(self, x: int, y: int, z: int) -> Optional[BlockState]:
        """ブロックを取得する

        :param x: チャンク内相対X座標 (0..15)
        :param y: 絶対Y座標
        :param z: チャンク内相対Z座標 (0..15)
        :return: ブロック
        セクションが無い、またはblock_statesを持たない場合はNone
        :raises SpringNbtError: 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）
        """
        chunk_format = self._require_format()
        _check_local_coordinates(x, z)
        section = self.section(y >> 4)

        if section is None or not section.has_block_states:
            return None

        # パレットの要素の形は世代で違うので、世代ごとに決めたDataVersionで読む
        return BlockState.from_nbt_for_data_version(
            section.block_states.get(block_index(x, y, z)), chunk_format.palette_data_version)

    def set_block(self, x: int, y: int, z: int, state: Union[BlockState, str]) -> None:
        """ブロックを設定する

        ``minecraft:oak_stairs[facing=north]``の形の文字列でも指定できる

        置き換えによって不整合になる付随データ（``block_entities`` /
        ``block_ticks`` / ``fluid_ticks``のうち、その座標を指すもの）は同時に取り除く
        1.17までの形式では、``Level``の中の``TileEntities`` / ``TileTicks`` / ``LiquidTicks``から取り除く
        残すとブロックと中身が食い違い、Minecraft側で予期しない挙動になるため

        パレットには、チャンクを読んだときの世代の形式で入れる

        :raises SpringNbtError: 対象のセクションが無い、またはblock_statesを持たない場合、
            元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）
        """
        # 文字列で渡されたらBlockStateへ直してから進む
        if isinstance(state, str):
            state = BlockState.parse(state)

        chunk_format = self._require_format()
        _check_local_coordinates(x, z)
        section_y = y >> 4
        section = self.section(section_y)

        if section is None or not section.has_block_states:
            raise SpringNbtError.invalid_argument(
                "Y=%d を含むセクション（Y=%d）が無いか、ブロックを持たない。"
                "本ライブラリはセクションを新規生成しない" % (y, section_y))

        # 同じ状態を置き直すだけなら、付随データを触る理由がない
        # プロパティの並び順に左右されないよう、NBTではなくBlockStateとして比べる
        current = self.get_block(x, y, z)

        if current is not None and current == state:
            return

        # 書き戻すときに読んだときと同じ形式になるよう、世代ごとに決めたDataVersionで読み書きする
        entry = _palette_entry_for(section.block_states, state, chunk_format.palette_data_version)
        section.block_states.set(block_index(x, y, z), entry)
        self._remove_block_data(chunk_format, x, y, z)
        self._modified = True

    def _remove_block_data(self, chunk_format: ChunkFormat, x: int, y: int, z: int) -> None:
        """その座標を指す付随データを取り除く

        ``block_entities`` / ``block_ticks`` / ``fluid_ticks``の要素は
        いずれも``x`` ``y`` ``z``を**絶対座標**で持つ
        1.17までの形式の``TileEntities`` / ``TileTicks`` / ``LiquidTicks``も同じ
        """
        absolute_x = (self.x * 16) + x
        absolute_z = (self.z * 16) + z
        body = self._body()

        # 3つのリストは形が同じなので、まとめて同じ処理をかける
        for key in chunk_format.block_data_keys:
            values = body.opt_list(key)

            if values is None or len(values) == 0:
                continue

            # 後ろから削ると、削除しても残りの添字がずれない
            for position in range(len(values) - 1, -1, -1):
                entry = values[position]

                # 座標を持つ要素のうち、指定の位置を指すものだけを取り除く
                if isinstance(entry, NbtCompound) and _matches_position(
                        entry, absolute_x, y, absolute_z):
                    del values[position]

    def get_biome(self, x: int, y: int, z: int) -> Optional[str]:
        """バイオームを取得する
        4×4×4の単位なので、座標は自動的に丸められる

        :raises SpringNbtError: 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）、
            バイオームを数値のIDで持つ1.17までの形式の場合（UNSUPPORTED_FEATURE）
        """
        self._require_named_biomes()
        _check_local_coordinates(x, z)
        section = self.section(y >> 4)

        if section is None or not section.has_biomes:
            return None

        entry = section.biomes.get(biome_index(x, y, z))

        if not isinstance(entry, NbtString):
            raise SpringNbtError.unexpected_tag_type(
                "バイオームのパレット要素が string でない: %s" % entry.type.as_string())

        return entry.value

    def set_biome(self, x: int, y: int, z: int, biome: str) -> None:
        """バイオームを設定する
        4×4×4の単位

        :raises SpringNbtError: 対象のセクションが無い、またはバイオームを持たない場合、
            元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）、
            バイオームを数値のIDで持つ1.17までの形式の場合（UNSUPPORTED_FEATURE）
        """
        self._require_named_biomes()
        _check_local_coordinates(x, z)
        section_y = y >> 4
        section = self.section(section_y)

        if section is None or not section.has_biomes:
            raise SpringNbtError.invalid_argument(
                "Y=%d を含むセクション（Y=%d）が無いか、バイオームを持たない" % (y, section_y))

        section.biomes.set(biome_index(x, y, z), NbtString(biome))
        self._modified = True

    def get_biome_id(self, x: int, y: int, z: int) -> Optional[int]:
        """数値のバイオームIDを取得する（1.17までの形式）
        1.15以降の形式は4×4×4の単位なので、座標は自動的に丸められる
        1.14までの形式は列ごとに持つので、Yは見ない

        IDは名前に直さない
        1.16.2以降はデータパックで独自のバイオームを足せるので、固定の表では正しく引けないため

        :param x: チャンク内相対X座標 (0..15)
        :param y: 絶対Y座標
        :param z: チャンク内相対Z座標 (0..15)
        :return: バイオームID
        1.15以降の形式でYが0..255の外の場合と、``Biomes``が無いか形が違う場合はNone
        :raises SpringNbtError: 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）、
            バイオームを名前で持つ1.18以降の形式の場合（UNSUPPORTED_FEATURE）
        """
        chunk_format = self._require_biome_ids()
        _check_local_coordinates(x, z)
        biomes = self._biome_ids(chunk_format)

        # Biomesを読めないチャンクは値を持たない
        if biomes is None:
            return None

        # 列ごとに持つ形式は高さを見ない
        if chunk_format.biome_storage == BiomeStorage.IDS_2D:
            return biomes.value[_biome_id_2d_index(x, z)]

        # 高さの範囲外は値を持たない
        if y < 0 or y > _BIOME_IDS_MAX_Y:
            return None

        return biomes.value[_biome_id_index(x, y, z)]

    def set_biome_id(self, x: int, y: int, z: int, biome_id: int) -> None:
        """数値のバイオームIDを設定する（1.17までの形式）
        1.15以降の形式は4×4×4の単位
        1.14までの形式は列ごとに持つので、Yは見ない

        :raises SpringNbtError: 1.15以降の形式でYが0..255の外の場合、
            ``Biomes``が無いか形が違う場合（INVALID_ARGUMENT）、
            元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）、
            バイオームを名前で持つ1.18以降の形式の場合（UNSUPPORTED_FEATURE）
        """
        chunk_format = self._require_biome_ids()
        _check_local_coordinates(x, z)
        index = _biome_id_2d_index(x, z)

        # 4×4×4ごとに持つ形式は、高さ0..255の分だけある
        if chunk_format.biome_storage == BiomeStorage.IDS_3D:
            # 範囲外の高さはどの値にも当たらない
            if y < 0 or y > _BIOME_IDS_MAX_Y:
                raise SpringNbtError.invalid_argument(
                    "Y=%d はバイオームIDを持つ高さ（0..%d）の外" % (y, _BIOME_IDS_MAX_Y))

            index = _biome_id_index(x, y, z)

        biomes = self._biome_ids(chunk_format)

        # 読めないBiomesを作り直すと元のデータを失うので、書き込まない
        if biomes is None:
            raise SpringNbtError.invalid_argument(
                "Biomes が無いか、int[%d] でない" % _biome_ids_length(chunk_format))

        # 配列へ直接入れると範囲の検査を通らないので、intの範囲を先に確かめる
        biomes.value[index] = NbtInt(biome_id).value
        self._modified = True

    def clear_heightmaps(self) -> None:
        """``Heightmaps``を削除し、Minecraftに再計算させる

        本ライブラリは高さマップを再計算しない
        ブロックを改変したら呼ぶこと

        :raises SpringNbtError: 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）
        """
        self._require_format()
        self._body().remove("Heightmaps")
        self._modified = True

    def invalidate_lighting(self) -> None:
        """``isLightOn``を0にし、光源の再計算を促す

        :raises SpringNbtError: 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）、
            ``isLightOn``の無い1.17までの形式のチャンクの場合（UNSUPPORTED_FEATURE）
        """
        chunk_format = self._require_format()
        body = self._body()

        # 書き足さない世代では、isLightOnの無いチャンクは光源の印を持たない
        if not chunk_format.adds_light_flag and "isLightOn" not in body:
            raise SpringNbtError.unsupported_feature(
                "DataVersion %dのチャンクは isLightOn を持たない" % self._format_data_version)

        body.set_byte("isLightOn", 0)
        self._modified = True

    def compact(self) -> None:
        """使われていないパレット要素を全セクションから取り除く"""
        for section in self._sections.values():
            section.compact()


def block_index(x: int, y: int, z: int) -> int:
    """セクション内のブロック添字

    ``& 15``により負のY座標でも正しく求まる
    """
    return ((y & 15) * 256) + ((z & 15) * 16) + (x & 15)


def biome_index(x: int, y: int, z: int) -> int:
    """セクション内のバイオーム添字
    1エントリが4×4×4ブロック
    """
    return (((y & 15) // 4) * 16) + (((z & 15) // 4) * 4) + ((x & 15) // 4)


def _biome_id_index(x: int, y: int, z: int) -> int:
    """1.15から1.17までの形式の``Biomes``の添字
    1エントリが4×4×4ブロック
    """
    return (((y >> 2) & 63) * 16) + ((z >> 2) * 4) + (x >> 2)


def _biome_id_2d_index(x: int, z: int) -> int:
    """1.14までの形式の``Biomes``の添字
    1エントリが1列
    """
    return (z * 16) + x


def _biome_ids_length(chunk_format: ChunkFormat) -> int:
    """世代の``Biomes``が持つ数値のバイオームIDの数"""
    # 列ごとに持つ形式は256個
    if chunk_format.biome_storage == BiomeStorage.IDS_2D:
        return _BIOME_IDS_2D_LENGTH

    return _BIOME_IDS_3D_LENGTH


def _check_local_coordinates(x: int, z: int) -> None:
    # チャンク内相対座標は0..15でなければならない
    if x < 0 or x > 15 or z < 0 or z > 15:
        raise SpringNbtError.invalid_argument(
            "チャンク内相対座標が範囲外: (%d, %d)。X も Z も 0..15 であること" % (x, z))

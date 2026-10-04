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
from ..nbt import NbtByte, NbtCompound, NbtInt, NbtList, NbtString, TagType
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

#: ブロックに紐づく付随データのキー
#: ブロックを置き換えたら整合が崩れる
_BLOCK_DATA_KEYS = ("block_entities", "block_ticks", "fluid_ticks")


def _matches_position(entry: NbtCompound, x: int, y: int, z: int) -> bool:
    """付随データの要素が、指定の絶対座標を指しているか"""
    entry_x = entry.opt_int("x")
    entry_y = entry.opt_int("y")
    entry_z = entry.opt_int("z")

    # 座標を持たない要素は、対象かどうか判断できないので触らない
    if entry_x is None or entry_y is None or entry_z is None:
        return False

    return entry_x == x and entry_y == y and entry_z == z


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
                 lenient_bit_storage: bool = False) -> None:
        #: DataVersionが扱える形式より古いときの動作
        self.on_version_mismatch = on_version_mismatch
        #: 警告の通知先
        #: Noneなら何もしない
        self.on_warning = on_warning
        #: dataの長さが期待値と違うとき、長さからビット幅を逆算して読むか
        self.lenient_bit_storage = lenient_bit_storage


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

    __slots__ = ("raw", "y", "block_states", "biomes")

    def __init__(self, raw: NbtCompound, y: int) -> None:
        self.raw = raw
        self.y = y
        self.block_states: Optional[PalettedContainer] = None
        self.biomes: Optional[PalettedContainer] = None

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
        """NBTからセクションを読む"""
        section = ChunkSection(nbt, nbt.get_byte("Y"))
        block_states = nbt.opt_compound("block_states")

        # 光源専用のセクションはblock_statesを持たない
        if block_states is not None:
            section.block_states = PalettedContainer.from_nbt(
                block_states, BLOCKS_PER_SECTION, 4, options.lenient_bit_storage)

        biomes = nbt.opt_compound("biomes")

        # 光源だけを持つセクションにはバイオームが無い
        if biomes is not None:
            section.biomes = PalettedContainer.from_nbt(
                biomes, BIOMES_PER_SECTION, 1, options.lenient_bit_storage)

        return section

    def to_nbt(self) -> NbtCompound:
        """NBTへ書き戻す
        解釈していないキーはそのまま残る
        """
        if self.block_states is not None:
            self.raw.set("block_states", self.block_states.to_nbt())

        # 解釈したコンテナだけを書き戻す
        # 持たないキーは元のまま残す
        if self.biomes is not None:
            self.raw.set("biomes", self.biomes.to_nbt())

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

    __slots__ = ("raw", "_sections", "_modified")

    def __init__(self, raw: NbtCompound) -> None:
        self.raw = raw
        self._sections: Dict[int, ChunkSection] = {}
        self._modified = False

    @property
    def data_version(self) -> int:
        """チャンク構造のバージョン"""
        return self.raw.get_int("DataVersion")

    @property
    def x(self) -> int:
        """絶対チャンクX座標"""
        return self.raw.get_int("xPos")

    @property
    def z(self) -> int:
        """絶対チャンクZ座標"""
        return self.raw.get_int("zPos")

    @property
    def min_section_y(self) -> int:
        """最下段セクションのY位置
        オーバーワールドは-4
        """
        return self.raw.get_int("yPos")

    @property
    def status(self) -> str:
        """生成段階（``minecraft:full``など）"""
        return self.raw.get_string("Status")

    @property
    def is_fully_generated(self) -> bool:
        """生成が完了しているか
        ブロック改変の対象にしてよいのはこれだけ
        """
        return self.status == "minecraft:full"

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

        :raises SpringNbtError: 必須のキーが無い、または構造が想定と違う場合
        """
        if options is None:
            effective = _DEFAULT_READ
        else:
            effective = options

        chunk = Chunk(nbt)
        chunk._check_data_version(effective)
        section_list = nbt.opt_list("sections")

        if section_list is None:
            return chunk

        # 並び順に依存しないよう、Yから索引を作る
        for entry in section_list:
            if not isinstance(entry, NbtCompound):
                raise SpringNbtError.unexpected_tag_type(
                    "sections の要素が compound でない: %s" % entry.type.as_string())

            section = ChunkSection.from_nbt(entry, effective)
            chunk._sections[section.y] = section

        return chunk

    def _check_data_version(self, options: ChunkReadOptions) -> None:
        """DataVersionを検査し、オプションに従って警告またはエラーにする"""
        version = self.data_version

        # 形式が同じであれば、新しいバージョンでもそのまま読める
        if version >= MIN_SUPPORTED_DATA_VERSION:
            return

        message = ("DataVersion %d はこのライブラリが扱う形式より古い（%d 以降が対象）"
                   % (version, MIN_SUPPORTED_DATA_VERSION))

        if options.on_version_mismatch == VersionMismatchAction.ERROR:
            raise SpringNbtError(ErrorCode.UNSUPPORTED_DATA_VERSION, message)

        # 警告として扱う設定で、通知先があるときだけ知らせる
        if options.on_version_mismatch == VersionMismatchAction.WARN \
                and options.on_warning is not None:
            options.on_warning(message)

    def to_nbt(self, options: Optional[ChunkWriteOptions] = None) -> NbtCompound:
        """NBTへ書き戻す
        全セクションを書き戻し、他のキーはそのまま残す

        :raises SpringNbtError: DataVersionが扱える形式より古く、かつ書き戻しが許可されていない場合
        """
        if options is None:
            effective = _DEFAULT_WRITE
        else:
            effective = options

        version = self.data_version

        # 形式の違う古いチャンクは、書き戻すと使えなくなりかねない
        if version < MIN_SUPPORTED_DATA_VERSION and not effective.allow_foreign_data_version:
            raise SpringNbtError(
                ErrorCode.UNSUPPORTED_DATA_VERSION,
                "DataVersion %d のチャンクは書き戻せない（%d 以降が対象）。"
                "許可するなら ChunkWriteOptions(allow_foreign_data_version=True)"
                % (version, MIN_SUPPORTED_DATA_VERSION))

        # DataVersionは読んだ値のまま残す
        # 書き換えると、そのワールドを開くゲーム側の判断を誤らせる

        if len(self._sections) == 0:
            return self.raw

        section_list = NbtList(TagType.COMPOUND)

        # Yの昇順で書き出す
        for section_y in self.section_ys:
            section_list.append(self._sections[section_y].to_nbt())

        self.raw.set("sections", section_list)
        return self.raw

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
        """
        _check_local_coordinates(x, z)
        section = self.section(y >> 4)

        if section is None or not section.has_block_states:
            return None

        entry = section.block_states.get(block_index(x, y, z))

        if not isinstance(entry, NbtCompound):
            raise SpringNbtError.unexpected_tag_type(
                "ブロックのパレット要素が compound でない: %s" % entry.type.as_string())

        return BlockState.from_nbt(entry)

    def set_block(self, x: int, y: int, z: int, state: Union[BlockState, str]) -> None:
        """ブロックを設定する

        ``minecraft:oak_stairs[facing=north]``の形の文字列でも指定できる

        置き換えによって不整合になる付随データ（``block_entities`` /
        ``block_ticks`` / ``fluid_ticks``のうち、その座標を指すもの）は同時に取り除く
        残すとブロックと中身が食い違い、Minecraft側で予期しない挙動になるため

        :raises SpringNbtError: 対象のセクションが無い、またはblock_statesを持たない場合
        """
        # 文字列で渡されたらBlockStateへ直してから進む
        if isinstance(state, str):
            state = BlockState.parse(state)

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

        section.block_states.set(block_index(x, y, z), state.to_nbt())
        self._remove_block_data(x, y, z)
        self._modified = True

    def _remove_block_data(self, x: int, y: int, z: int) -> None:
        """その座標を指す付随データを取り除く

        ``block_entities`` / ``block_ticks`` / ``fluid_ticks``の要素は
        いずれも``x`` ``y`` ``z``を**絶対座標**で持つ
        """
        absolute_x = (self.x * 16) + x
        absolute_z = (self.z * 16) + z

        # 3つのリストは形が同じなので、まとめて同じ処理をかける
        for key in _BLOCK_DATA_KEYS:
            values = self.raw.opt_list(key)

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
        """
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
        """
        _check_local_coordinates(x, z)
        section_y = y >> 4
        section = self.section(section_y)

        if section is None or not section.has_biomes:
            raise SpringNbtError.invalid_argument(
                "Y=%d を含むセクション（Y=%d）が無いか、バイオームを持たない" % (y, section_y))

        section.biomes.set(biome_index(x, y, z), NbtString(biome))
        self._modified = True

    def clear_heightmaps(self) -> None:
        """``Heightmaps``を削除し、Minecraftに再計算させる

        本ライブラリは高さマップを再計算しない
        ブロックを改変したら呼ぶこと
        """
        self.raw.remove("Heightmaps")
        self._modified = True

    def invalidate_lighting(self) -> None:
        """``isLightOn``を0にし、光源の再計算を促す"""
        self.raw.set_byte("isLightOn", 0)
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


def _check_local_coordinates(x: int, z: int) -> None:
    # チャンク内相対座標は0..15でなければならない
    if x < 0 or x > 15 or z < 0 or z > 15:
        raise SpringNbtError.invalid_argument(
            "チャンク内相対座標が範囲外: (%d, %d)。X も Z も 0..15 であること" % (x, z))

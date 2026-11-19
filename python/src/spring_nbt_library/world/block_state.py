"""ブロックの状態
名前と、任意のプロパティの組

プロパティは**常に名前の昇順で保持する**
こうしておくと文字列表現が一意になり、全言語で同じ出力になる
Minecraftが書き出した並び順は、:class:`PalettedContainer`がパレットを生のNBTのまま持つことで守られる
そのため、触っていないブロックの並びが崩れることはない
"""

from __future__ import annotations

from typing import Dict, Mapping, Optional

from .. import TARGET_DATA_VERSION
from ..errors import SpringNbtError
from ..nbt import NbtCompound, NbtString, NbtTag
from ._chunk_format import OLDEST_FORMAT_DATA_VERSION, PALETTE_ID_FORMAT_DATA_VERSION
from .paletted_container import _unwrap_list_element

__all__ = ["BlockState"]


class BlockState:
    """ブロックの状態"""

    __slots__ = ("name", "_properties")

    def __init__(self, name: str, properties: Optional[Mapping[str, str]] = None) -> None:
        self.name = _normalize(name)
        self._properties: Dict[str, str] = {}

        if properties is not None:
            # 名前の昇順で取り込む
            for key in sorted(properties):
                self._properties[key] = properties[key]

    @property
    def properties(self) -> Mapping[str, str]:
        """プロパティ
        名前の昇順
        """
        return self._properties

    def property(self, key: str) -> Optional[str]:
        """プロパティを取得する
        無ければNone
        """
        return self._properties.get(key)

    def with_property(self, key: str, value: str) -> "BlockState":
        """プロパティを1つ差し替えた新しい状態を返す"""
        merged = dict(self._properties)
        merged[key] = value
        return BlockState(self.name, merged)

    @staticmethod
    def parse(text: str) -> "BlockState":
        """``minecraft:oak_stairs[facing=north,half=top]``形式の文字列から作る

        :raises SpringNbtError: 形式が不正な場合
        """
        bracket = text.find("[")

        # 角括弧が無ければプロパティ無しのブロック名
        if bracket < 0:
            if len(text) == 0:
                raise SpringNbtError.invalid_argument("ブロック名が空")

            return BlockState(text)

        if not text.endswith("]"):
            raise SpringNbtError.invalid_argument("角括弧が閉じられていない: %s" % text)

        body = text[bracket + 1:-1]
        properties = {}

        if len(body) > 0:
            # "key=value"をカンマ区切りで読む
            for pair in body.split(","):
                equals = pair.find("=")

                if equals < 0:
                    raise SpringNbtError.invalid_argument("プロパティに '=' が無い: %s" % pair)

                key = pair[:equals].strip()

                if len(key) == 0:
                    raise SpringNbtError.invalid_argument("プロパティ名が空: %s" % pair)

                # どちらが採用されたか分からないまま書き込まれるのを避けるため、重複は弾く
                if key in properties:
                    raise SpringNbtError.invalid_argument("プロパティ名が重複している: %s" % key)

                properties[key] = pair[equals + 1:].strip()

        return BlockState(text[:bracket], properties)

    @staticmethod
    def from_nbt(nbt: NbtTag) -> "BlockState":
        """パレット要素のNBTから作る

        ``TARGET_DATA_VERSION``の形式で読む
        DataVersionを指定するときは:meth:`from_nbt_for_data_version`を使う

        :raises SpringNbtError: 文字列でもCompoundでもない、``id``が無い、または``properties``の値が文字列でない場合
        """
        return BlockState.from_nbt_for_data_version(nbt, TARGET_DATA_VERSION)

    @staticmethod
    def from_nbt_for_data_version(nbt: NbtTag, data_version: int) -> "BlockState":
        """DataVersionを指定して、パレット要素のNBTから作る

        26.3（DataVersion 5006）以降は、既定の状態がブロックIDだけの文字列で、それ以外は``id``と``properties``を持つCompoundで入っている
        異種リストの要素を包む``{"": <値>}``は外してから読む
        1519以上5006未満は、``Name``と``Properties``を持つCompoundを読む
        文字列は受け付けない

        :param data_version: パレット要素を含むチャンクのDataVersion（1519以上）
        :raises SpringNbtError: ``data_version``が1519未満の場合（INVALID_ARGUMENT）、
            要素が形式に合うタグでない場合、``id`` / ``Name``が無い場合、またはプロパティの値が文字列でない場合
        """
        _check_data_version(data_version)

        # 26.3より前は、Name / Propertiesの形式で入っている
        if data_version < PALETTE_ID_FORMAT_DATA_VERSION:
            return _from_name_properties(nbt)

        return _from_palette_id(nbt)

    def to_nbt(self) -> NbtTag:
        """パレット要素のNBTへ変換する

        ``TARGET_DATA_VERSION``の形式で書く
        DataVersionを指定するときは:meth:`to_nbt_for_data_version`を使う
        """
        return self.to_nbt_for_data_version(TARGET_DATA_VERSION)

    def to_nbt_for_data_version(self, data_version: int) -> NbtTag:
        """DataVersionを指定して、パレット要素のNBTへ変換する

        26.3（DataVersion 5006）以降は、プロパティが空ならブロックIDだけの文字列にし、それ以外は``id``と``properties``を持つCompoundにする
        1519以上5006未満は、``Name``を持つCompoundにし、プロパティが空なら``Properties``キー自体を出力しない
        いずれもMinecraftと同じ振る舞い

        :param data_version: 書き込み先のチャンクのDataVersion（1519以上）
        :raises SpringNbtError: ``data_version``が1519未満の場合（INVALID_ARGUMENT）
        """
        _check_data_version(data_version)

        # 26.3より前は、Name / Propertiesの形式で書く
        if data_version < PALETTE_ID_FORMAT_DATA_VERSION:
            return self._to_name_properties()

        return self._to_palette_id()

    def _to_palette_id(self) -> NbtTag:
        # プロパティが無ければ、Minecraftが既定の状態を書くときと同じく文字列にする
        if len(self._properties) == 0:
            return NbtString(self.name)

        result = NbtCompound()
        result.set("id", NbtString(self.name))
        properties_tag = NbtCompound()

        # 名前の昇順で並ぶ
        for key, value in self._properties.items():
            properties_tag.set(key, NbtString(value))

        result.set("properties", properties_tag)
        return result

    def _to_name_properties(self) -> NbtCompound:
        """``Name`` / ``Properties``の形式へ変換する"""
        result = NbtCompound()
        result.set("Name", NbtString(self.name))

        # プロパティが無ければ、Propertiesキー自体を出力しない
        if len(self._properties) == 0:
            return result

        properties_tag = NbtCompound()

        # 名前の昇順で並ぶ
        for key, value in self._properties.items():
            properties_tag.set(key, NbtString(value))

        result.set("Properties", properties_tag)
        return result

    def __eq__(self, other) -> bool:
        if not isinstance(other, BlockState):
            return False

        return other.name == self.name and other._properties == self._properties

    def __hash__(self) -> int:
        return hash((self.name, tuple(sorted(self._properties.items()))))

    def __str__(self) -> str:
        """``minecraft:oak_stairs[facing=north,half=top]``形式の文字列を返す"""
        if len(self._properties) == 0:
            return self.name

        # 名前の昇順で並べるので、同じ状態なら必ず同じ文字列になる
        body = ",".join("%s=%s" % (key, value) for key, value in self._properties.items())
        return "%s[%s]" % (self.name, body)

    def __repr__(self) -> str:
        return "BlockState(%r)" % str(self)


def _normalize(name: str) -> str:
    """名前空間が省略されていたら``minecraft:``を補う"""
    if ":" in name:
        return name

    return "minecraft:" + name


def _check_data_version(data_version: int) -> None:
    """指定されたDataVersionが、読み書きできる下限以上であることを確かめる"""
    if data_version < OLDEST_FORMAT_DATA_VERSION:
        raise SpringNbtError.invalid_argument(
            "DataVersionは%d以上でなければならない: %d" % (OLDEST_FORMAT_DATA_VERSION, data_version))


def _from_palette_id(nbt: NbtTag) -> BlockState:
    """26.3以降の``id`` / ``properties``の形式から読む"""
    entry = _unwrap_list_element(nbt)

    # 既定の状態は、ブロックIDだけの文字列で入っている
    if isinstance(entry, NbtString):
        return BlockState(entry.value)

    if not isinstance(entry, NbtCompound):
        raise SpringNbtError.unexpected_tag_type(
            "ブロックのパレット要素が string でも compound でもない: %s"
            % entry.type.as_string())

    name = entry.opt_string("id")

    if name is None:
        # Name / Propertiesは26.2までの形式で、読み替えると誤った状態を返しかねない
        if "Name" in entry:
            raise SpringNbtError.malformed(
                "ブロックのパレット要素にidが無い。NameはDataVersion 5006より前の形式なので、5006未満のDataVersionで読むこと")

        raise SpringNbtError.malformed("ブロックのパレット要素に id が無い")

    properties_tag = entry.opt_compound("properties")
    properties = {}

    if properties_tag is not None:
        # propertiesの値はすべて文字列（数値や真偽値も文字列で入る）
        for key, value in properties_tag.items():
            if not isinstance(value, NbtString):
                raise SpringNbtError.unexpected_tag_type(
                    'properties の "%s" が文字列でない: %s' % (key, value.type.as_string()))

            properties[key] = value.value

    return BlockState(name, properties)


def _from_name_properties(nbt: NbtTag) -> BlockState:
    """26.2までの``Name`` / ``Properties``の形式から読む"""
    # 26.2までは文字列のパレット要素も、異種リストの包みも無い
    if not isinstance(nbt, NbtCompound):
        raise SpringNbtError.unexpected_tag_type(
            "ブロックのパレット要素が compound でない: %s" % nbt.type.as_string())

    name = nbt.opt_string("Name")

    if name is None:
        raise SpringNbtError.malformed("ブロックのパレット要素に Name が無い")

    properties_tag = nbt.opt_compound("Properties")
    properties = {}

    if properties_tag is not None:
        # Propertiesの値はすべて文字列（数値や真偽値も文字列で入る）
        for key, value in properties_tag.items():
            if not isinstance(value, NbtString):
                raise SpringNbtError.unexpected_tag_type(
                    'Properties の "%s" が文字列でない: %s' % (key, value.type.as_string()))

            properties[key] = value.value

    return BlockState(name, properties)

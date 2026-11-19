"""ブロックの状態
名前と、任意のプロパティの組

プロパティは**常に名前の昇順で保持する**
こうしておくと文字列表現が一意になり、全言語で同じ出力になる
Minecraftが書き出した並び順は、:class:`PalettedContainer`がパレットを生のNBTのまま持つことで守られる
そのため、触っていないブロックの並びが崩れることはない
"""

from __future__ import annotations

from typing import Dict, Mapping, Optional

from ..errors import SpringNbtError
from ..nbt import NbtCompound, NbtString, NbtTag
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

        26.3で入った形式を読む
        既定の状態はブロックIDだけの文字列で、それ以外は``id``と``properties``を持つCompoundで入っている
        異種リストの要素を包む``{"": <値>}``は外してから読む

        :raises SpringNbtError: 文字列でもCompoundでもない、``id``が無い、または``properties``の値が文字列でない場合
        """
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
                    "ブロックのパレット要素に id が無い。Name は26.2までの形式で、本ライブラリでは扱わない")

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

    def to_nbt(self) -> NbtTag:
        """パレット要素のNBTへ変換する

        プロパティが空ならブロックIDだけの文字列にし、それ以外は``id``と``properties``を持つCompoundにする
        Minecraftと同じ振る舞い
        """
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

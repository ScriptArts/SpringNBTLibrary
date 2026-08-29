"""ブロックの状態。名前と、任意のプロパティの組。

プロパティは**常に名前の昇順で保持する**。こうしておくと文字列表現が一意になり、
全言語で同じ出力になる。Minecraft が書き出した並び順は
:class:`PalettedContainer` がパレットを生の NBT のまま持つことで守られるので、
触っていないブロックの並びが崩れることはない。

仕様: ``docs/spec/30-chunk-format.md`` 2.1章
"""

from __future__ import annotations

from typing import Dict, Mapping, Optional

from ..errors import SpringNbtError
from ..nbt import NbtCompound, NbtString

__all__ = ["BlockState"]


class BlockState:
    """ブロックの状態。"""

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
        """プロパティ。名前の昇順。"""
        return self._properties

    def property(self, key: str) -> Optional[str]:
        """プロパティを取得する。無ければ None。"""
        return self._properties.get(key)

    def with_property(self, key: str, value: str) -> "BlockState":
        """プロパティを 1 つ差し替えた新しい状態を返す。"""
        merged = dict(self._properties)
        merged[key] = value
        return BlockState(self.name, merged)

    @staticmethod
    def parse(text: str) -> "BlockState":
        """``minecraft:oak_stairs[facing=north,half=top]`` 形式の文字列から作る。

        :raises SpringNbtError: 形式が不正な場合。
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
            # "key=value" をカンマ区切りで読む
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
    def from_nbt(nbt: NbtCompound) -> "BlockState":
        """パレット要素の NBT から作る。

        :raises SpringNbtError: ``Name`` が無い、または ``Properties`` の値が文字列でない場合。
        """
        properties_tag = nbt.opt_compound("Properties")
        properties = {}

        if properties_tag is not None:
            # Properties の値はすべて文字列（数値や真偽値も文字列で入る）
            for key, value in properties_tag.items():
                if not isinstance(value, NbtString):
                    raise SpringNbtError.unexpected_tag_type(
                        'Properties の "%s" が文字列でない: %s' % (key, value.type.as_string()))

                properties[key] = value.value

        return BlockState(nbt.get_string("Name"), properties)

    def to_nbt(self) -> NbtCompound:
        """パレット要素の NBT へ変換する。

        プロパティが空なら ``Properties`` キー自体を出力しない。Minecraft と同じ振る舞い。
        """
        result = NbtCompound()
        result.set("Name", NbtString(self.name))

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
        """``minecraft:oak_stairs[facing=north,half=top]`` 形式の文字列を返す。"""
        if len(self._properties) == 0:
            return self.name

        # 名前の昇順で並べるので、同じ状態なら必ず同じ文字列になる
        body = ",".join("%s=%s" % (key, value) for key, value in self._properties.items())
        return "%s[%s]" % (self.name, body)

    def __repr__(self) -> str:
        return "BlockState(%r)" % str(self)


def _normalize(name: str) -> str:
    """名前空間が省略されていたら ``minecraft:`` を補う。"""
    if ":" in name:
        return name

    return "minecraft:" + name

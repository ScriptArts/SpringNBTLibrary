"""NBT のタグ型と値モデル。

仕様: ``docs/spec/10-nbt-binary.md`` 1章・7章
"""

from __future__ import annotations

import enum
import struct
from typing import Dict, Iterator, List, Optional, Tuple

from ..errors import SpringNbtError
from . import mutf8

__all__ = [
    "TagType",
    "NbtTag",
    "NbtByte",
    "NbtShort",
    "NbtInt",
    "NbtLong",
    "NbtFloat",
    "NbtDouble",
    "NbtByteArray",
    "NbtString",
    "NbtList",
    "NbtCompound",
    "NbtIntArray",
    "NbtLongArray",
]


class TagType(enum.Enum):
    """NBT のタグ型。値は仕様が定めるタグIDと一致する。"""

    END = 0
    BYTE = 1
    SHORT = 2
    INT = 3
    LONG = 4
    FLOAT = 5
    DOUBLE = 6
    BYTE_ARRAY = 7
    STRING = 8
    LIST = 9
    COMPOUND = 10
    INT_ARRAY = 11
    LONG_ARRAY = 12

    def as_string(self) -> str:
        """適合性テストで言語間比較に使う識別子。"""
        return _TYPE_NAMES[self]

    @staticmethod
    def from_id(tag_id: int) -> "TagType":
        """タグIDから :class:`TagType` を得る。

        :raises SpringNbtError: 未知のタグIDの場合。
        """
        # 0..12 の範囲外はすべて不正なタグID
        if tag_id < 0 or tag_id > TagType.LONG_ARRAY.value:
            raise SpringNbtError.malformed("未知のタグID: %d" % tag_id)

        return TagType(tag_id)


_TYPE_NAMES = {
    TagType.END: "end",
    TagType.BYTE: "byte",
    TagType.SHORT: "short",
    TagType.INT: "int",
    TagType.LONG: "long",
    TagType.FLOAT: "float",
    TagType.DOUBLE: "double",
    TagType.BYTE_ARRAY: "byte_array",
    TagType.STRING: "string",
    TagType.LIST: "list",
    TagType.COMPOUND: "compound",
    TagType.INT_ARRAY: "int_array",
    TagType.LONG_ARRAY: "long_array",
}


def _check_range(value: int, minimum: int, maximum: int, type_name: str) -> int:
    """Python の int には幅が無いため、構築時に範囲を検査する。"""
    if not isinstance(value, int) or isinstance(value, bool):
        raise SpringNbtError.invalid_argument("%s には整数を渡すこと: %r" % (type_name, value))

    if value < minimum or value > maximum:
        raise SpringNbtError.invalid_argument(
            "%s の範囲外: %d (範囲 %d..%d)" % (type_name, value, minimum, maximum))

    return value


class NbtTag:
    """NBT のタグ。具象型は :class:`NbtByte` などの派生クラス。"""

    #: このタグの型。派生クラスが上書きする。
    type: TagType = TagType.END

    def clone(self) -> "NbtTag":
        """このタグの深いコピーを作る。"""
        raise NotImplementedError


class _ScalarTag(NbtTag):
    """単一の値を持つタグの共通部分。"""

    __slots__ = ("_value",)

    def __init__(self, value) -> None:
        self._value = self._validate(value)

    @property
    def value(self):
        """保持している値。"""
        return self._value

    @value.setter
    def value(self, new_value) -> None:
        self._value = self._validate(new_value)

    def _validate(self, value):
        raise NotImplementedError

    def clone(self) -> "NbtTag":
        return type(self)(self._value)

    def __eq__(self, other) -> bool:
        if type(other) is not type(self):
            return False

        return other._value == self._value

    def __hash__(self) -> int:
        return hash((self.type, self._value))

    def __repr__(self) -> str:
        return "%s(%r)" % (type(self).__name__, self._value)


class NbtByte(_ScalarTag):
    """TAG_Byte。8bit 符号付き整数。"""

    type = TagType.BYTE

    def _validate(self, value):
        return _check_range(value, -128, 127, "byte")


class NbtShort(_ScalarTag):
    """TAG_Short。16bit 符号付き整数。"""

    type = TagType.SHORT

    def _validate(self, value):
        return _check_range(value, -32768, 32767, "short")


class NbtInt(_ScalarTag):
    """TAG_Int。32bit 符号付き整数。"""

    type = TagType.INT

    def _validate(self, value):
        return _check_range(value, -2147483648, 2147483647, "int")


class NbtLong(_ScalarTag):
    """TAG_Long。64bit 符号付き整数。"""

    type = TagType.LONG

    def _validate(self, value):
        return _check_range(value, -9223372036854775808, 9223372036854775807, "long")


class NbtFloat(_ScalarTag):
    """TAG_Float。IEEE 754 binary32。"""

    type = TagType.FLOAT

    def _validate(self, value):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise SpringNbtError.invalid_argument("float には数値を渡すこと: %r" % (value,))

        # Python の float は binary64 なので、構築時に binary32 へ丸めて他言語と揃える
        return struct.unpack(">f", struct.pack(">f", float(value)))[0]

    def __eq__(self, other) -> bool:
        if type(other) is not type(self):
            return False

        # NaN や -0.0 を区別するため、値ではなくビットパターンで比較する
        return struct.pack(">f", other._value) == struct.pack(">f", self._value)

    def __hash__(self) -> int:
        return hash((self.type, struct.pack(">f", self._value)))


class NbtDouble(_ScalarTag):
    """TAG_Double。IEEE 754 binary64。"""

    type = TagType.DOUBLE

    def _validate(self, value):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise SpringNbtError.invalid_argument("double には数値を渡すこと: %r" % (value,))

        return float(value)

    def __eq__(self, other) -> bool:
        if type(other) is not type(self):
            return False

        # NaN や -0.0 を区別するため、値ではなくビットパターンで比較する
        return struct.pack(">d", other._value) == struct.pack(">d", self._value)

    def __hash__(self) -> int:
        return hash((self.type, struct.pack(">d", self._value)))


class NbtString(_ScalarTag):
    """TAG_String。MUTF-8 で符号化される文字列。"""

    type = TagType.STRING

    def _validate(self, value):
        if not isinstance(value, str):
            raise SpringNbtError.invalid_argument("string には str を渡すこと: %r" % (value,))

        length = mutf8.byte_length(value)

        # 長さフィールドは u16。65535 を超えると書き出せない
        if length > mutf8.MAX_BYTE_LENGTH:
            raise SpringNbtError.invalid_argument(
                "文字列が長すぎる: MUTF-8 で %d バイト (上限 %d)" % (length, mutf8.MAX_BYTE_LENGTH))

        return value


class _ArrayTag(NbtTag):
    """整数配列を持つタグの共通部分。"""

    __slots__ = ("_value",)

    #: 要素が取りうる範囲。派生クラスが上書きする。
    _minimum = 0
    _maximum = 0
    _element_name = ""

    def __init__(self, value) -> None:
        self._value = self._validate(value)

    @property
    def value(self) -> List[int]:
        """保持している配列。"""
        return self._value

    @value.setter
    def value(self, new_value) -> None:
        self._value = self._validate(new_value)

    def _validate(self, value) -> List[int]:
        result = list(value)

        # 各要素が対象の幅に収まるか確認する
        for element in result:
            _check_range(element, self._minimum, self._maximum, self._element_name)

        return result

    def clone(self) -> "NbtTag":
        return type(self)(list(self._value))

    def __eq__(self, other) -> bool:
        if type(other) is not type(self):
            return False

        return other._value == self._value

    def __hash__(self) -> int:
        return hash((self.type, tuple(self._value)))

    def __repr__(self) -> str:
        return "%s(%d 要素)" % (type(self).__name__, len(self._value))


class NbtByteArray(_ArrayTag):
    """TAG_Byte_Array。8bit 符号付き整数の配列。"""

    type = TagType.BYTE_ARRAY
    _minimum = -128
    _maximum = 127
    _element_name = "byte"


class NbtIntArray(_ArrayTag):
    """TAG_Int_Array。32bit 符号付き整数の配列。"""

    type = TagType.INT_ARRAY
    _minimum = -2147483648
    _maximum = 2147483647
    _element_name = "int"


class NbtLongArray(_ArrayTag):
    """TAG_Long_Array。64bit 符号付き整数の配列。"""

    type = TagType.LONG_ARRAY
    _minimum = -9223372036854775808
    _maximum = 9223372036854775807
    _element_name = "long"


class NbtList(NbtTag):
    """TAG_List。要素型が 1 つに固定されたタグの列。

    空リストの要素型は :attr:`TagType.END`。最初の要素を追加した時点で型が確定する。
    全要素を削除しても確定済みの要素型は維持される。
    """

    type = TagType.LIST

    def __init__(self, element_type: TagType = TagType.END, elements=None) -> None:
        self._element_type = element_type
        self._items: List[NbtTag] = []

        # 与えられた要素は 1 つずつ型検査しながら追加する
        if elements is not None:
            for element in elements:
                self.append(element)

    @property
    def element_type(self) -> TagType:
        """要素の型。空で未確定なら :attr:`TagType.END`。"""
        return self._element_type

    def append(self, item: NbtTag) -> None:
        """末尾に追加する。

        :raises SpringNbtError: 要素型と一致しない場合。
        """
        self._ensure_element_type(item)
        self._items.append(item)

    def insert(self, index: int, item: NbtTag) -> None:
        """指定位置に挿入する。"""
        self._ensure_element_type(item)
        self._items.insert(index, item)

    def clear(self) -> None:
        """全要素を削除する。確定済みの要素型は維持する。"""
        self._items.clear()

    def clone(self) -> "NbtTag":
        copy = NbtList(self._element_type)

        # 要素も深くコピーする
        for item in self._items:
            copy._items.append(item.clone())

        return copy

    def _ensure_element_type(self, item: NbtTag) -> None:
        """追加しようとしているタグが要素型と一致するか調べる。"""
        # TAG_End はリストの要素になれない
        if item.type == TagType.END:
            raise SpringNbtError.unexpected_tag_type("TAG_End はリストの要素にできない")

        if self._element_type == TagType.END:
            # 未確定のリストは最初の要素で型が決まる
            self._element_type = item.type
        elif self._element_type != item.type:
            raise SpringNbtError.unexpected_tag_type(
                "リストの要素型は %s だが %s を追加しようとした"
                % (self._element_type.as_string(), item.type.as_string()))

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, index: int) -> NbtTag:
        return self._items[index]

    def __setitem__(self, index: int, item: NbtTag) -> None:
        self._ensure_element_type(item)
        self._items[index] = item

    def __delitem__(self, index: int) -> None:
        del self._items[index]

    def __iter__(self) -> Iterator[NbtTag]:
        return iter(self._items)

    def __eq__(self, other) -> bool:
        if not isinstance(other, NbtList):
            return False

        return other._element_type == self._element_type and other._items == self._items

    def __hash__(self) -> int:
        return hash((self.type, self._element_type, len(self._items)))

    def __repr__(self) -> str:
        return "NbtList(%s, %d 要素)" % (self._element_type.as_string(), len(self._items))


class NbtCompound(NbtTag):
    """TAG_Compound。挿入順を保持する、名前付きタグのマップ。

    既存キーへの再設定は位置を維持したまま値だけを置き換える。
    """

    type = TagType.COMPOUND

    def __init__(self, entries=None) -> None:
        # Python の dict は 3.7 以降で挿入順を保つ
        self._entries: Dict[str, NbtTag] = {}

        if entries is not None:
            for key, value in entries:
                self.set(key, value)

    def set(self, key: str, value: NbtTag) -> None:
        """値を設定する。既存キーなら位置を維持して値だけ置き換える。"""
        if not isinstance(key, str):
            raise SpringNbtError.invalid_argument("キーには str を渡すこと: %r" % (key,))

        # TAG_End は Compound の終端マーカーなので値として持てない
        if value.type == TagType.END:
            raise SpringNbtError.unexpected_tag_type("TAG_End は Compound の値にできない")

        self._entries[key] = value

    def opt(self, key: str) -> Optional[NbtTag]:
        """キーに対応するタグを返す。存在しなければ None。"""
        return self._entries.get(key)

    def get(self, key: str) -> NbtTag:
        """キーに対応するタグを返す。存在しなければ例外。"""
        found = self._entries.get(key)

        if found is None:
            raise SpringNbtError.invalid_argument("キーが存在しない: %s" % key)

        return found

    def remove(self, key: str) -> bool:
        """キーを削除する。削除できたら True。"""
        if key in self._entries:
            del self._entries[key]
            return True

        return False

    def clear(self) -> None:
        """全要素を削除する。"""
        self._entries.clear()

    def contains_key(self, key: str) -> bool:
        """キーが存在するか。"""
        return key in self._entries

    def keys(self):
        """挿入順のキー一覧。"""
        return self._entries.keys()

    def items(self) -> Iterator[Tuple[str, NbtTag]]:
        """挿入順の (キー, タグ) の並び。"""
        return iter(self._entries.items())

    def clone(self) -> "NbtTag":
        copy = NbtCompound()

        # 挿入順のまま深くコピーする
        for key, value in self._entries.items():
            copy.set(key, value.clone())

        return copy

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, key: str) -> bool:
        return key in self._entries

    def __getitem__(self, key: str) -> NbtTag:
        return self.get(key)

    def __setitem__(self, key: str, value: NbtTag) -> None:
        self.set(key, value)

    def __delitem__(self, key: str) -> None:
        del self._entries[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._entries)

    def __eq__(self, other) -> bool:
        if not isinstance(other, NbtCompound):
            return False

        # 順序も含めて一致することを確認する
        return list(other._entries.items()) == list(self._entries.items())

    def __hash__(self) -> int:
        return hash((self.type, len(self._entries)))

    def __repr__(self) -> str:
        return "NbtCompound(%d 要素)" % len(self._entries)

    # -- 型付き取得子 -------------------------------------------------------
    #
    # 「キーが無い」と「型が違う」は区別する。
    # opt_* はキーが無ければ None を返し、get_* は例外を送出する。
    # どちらも型が違えば必ず UNEXPECTED_TAG_TYPE の例外になる。

    def _cast(self, key: str, expected):
        """キーに対応するタグを目的の型として取り出す。キーが無ければ None。"""
        tag = self._entries.get(key)

        if tag is None:
            return None

        if isinstance(tag, expected):
            return tag

        raise SpringNbtError.unexpected_tag_type(
            'キー "%s" は %s だが %s として取り出そうとした'
            % (key, tag.type.as_string(), expected.__name__))

    def _require(self, key: str, expected):
        """キーに対応するタグを目的の型として取り出す。キーが無くても例外。"""
        tag = self._cast(key, expected)

        if tag is None:
            raise SpringNbtError.invalid_argument("キーが存在しない: %s" % key)

        return tag

    def opt_byte(self, key: str) -> Optional[int]:
        """TAG_Byte を取得する。キーが無ければ None。"""
        tag = self._cast(key, NbtByte)

        if tag is None:
            return None

        return tag.value

    def get_byte(self, key: str) -> int:
        """TAG_Byte を取得する。キーが無ければ例外。"""
        return self._require(key, NbtByte).value

    def opt_short(self, key: str) -> Optional[int]:
        """TAG_Short を取得する。キーが無ければ None。"""
        tag = self._cast(key, NbtShort)

        if tag is None:
            return None

        return tag.value

    def get_short(self, key: str) -> int:
        """TAG_Short を取得する。キーが無ければ例外。"""
        return self._require(key, NbtShort).value

    def opt_int(self, key: str) -> Optional[int]:
        """TAG_Int を取得する。キーが無ければ None。"""
        tag = self._cast(key, NbtInt)

        if tag is None:
            return None

        return tag.value

    def get_int(self, key: str) -> int:
        """TAG_Int を取得する。キーが無ければ例外。"""
        return self._require(key, NbtInt).value

    def opt_long(self, key: str) -> Optional[int]:
        """TAG_Long を取得する。キーが無ければ None。"""
        tag = self._cast(key, NbtLong)

        if tag is None:
            return None

        return tag.value

    def get_long(self, key: str) -> int:
        """TAG_Long を取得する。キーが無ければ例外。"""
        return self._require(key, NbtLong).value

    def opt_float(self, key: str) -> Optional[float]:
        """TAG_Float を取得する。キーが無ければ None。"""
        tag = self._cast(key, NbtFloat)

        if tag is None:
            return None

        return tag.value

    def get_float(self, key: str) -> float:
        """TAG_Float を取得する。キーが無ければ例外。"""
        return self._require(key, NbtFloat).value

    def opt_double(self, key: str) -> Optional[float]:
        """TAG_Double を取得する。キーが無ければ None。"""
        tag = self._cast(key, NbtDouble)

        if tag is None:
            return None

        return tag.value

    def get_double(self, key: str) -> float:
        """TAG_Double を取得する。キーが無ければ例外。"""
        return self._require(key, NbtDouble).value

    def opt_bool(self, key: str) -> Optional[bool]:
        """TAG_Byte を真偽値として取得する。0 以外が True。キーが無ければ None。"""
        raw = self.opt_byte(key)

        if raw is None:
            return None

        return raw != 0

    def get_bool(self, key: str) -> bool:
        """TAG_Byte を真偽値として取得する。0 以外が True。キーが無ければ例外。"""
        return self.get_byte(key) != 0

    def opt_string(self, key: str) -> Optional[str]:
        """TAG_String を取得する。キーが無ければ None。"""
        tag = self._cast(key, NbtString)

        if tag is None:
            return None

        return tag.value

    def get_string(self, key: str) -> str:
        """TAG_String を取得する。キーが無ければ例外。"""
        return self._require(key, NbtString).value

    def opt_byte_array(self, key: str) -> Optional[List[int]]:
        """TAG_Byte_Array を取得する。キーが無ければ None。"""
        tag = self._cast(key, NbtByteArray)

        if tag is None:
            return None

        return tag.value

    def get_byte_array(self, key: str) -> List[int]:
        """TAG_Byte_Array を取得する。キーが無ければ例外。"""
        return self._require(key, NbtByteArray).value

    def opt_int_array(self, key: str) -> Optional[List[int]]:
        """TAG_Int_Array を取得する。キーが無ければ None。"""
        tag = self._cast(key, NbtIntArray)

        if tag is None:
            return None

        return tag.value

    def get_int_array(self, key: str) -> List[int]:
        """TAG_Int_Array を取得する。キーが無ければ例外。"""
        return self._require(key, NbtIntArray).value

    def opt_long_array(self, key: str) -> Optional[List[int]]:
        """TAG_Long_Array を取得する。キーが無ければ None。"""
        tag = self._cast(key, NbtLongArray)

        if tag is None:
            return None

        return tag.value

    def get_long_array(self, key: str) -> List[int]:
        """TAG_Long_Array を取得する。キーが無ければ例外。"""
        return self._require(key, NbtLongArray).value

    def opt_list(self, key: str) -> Optional[NbtList]:
        """TAG_List を取得する。キーが無ければ None。"""
        return self._cast(key, NbtList)

    def get_list(self, key: str) -> NbtList:
        """TAG_List を取得する。キーが無ければ例外。"""
        return self._require(key, NbtList)

    def opt_compound(self, key: str) -> Optional["NbtCompound"]:
        """TAG_Compound を取得する。キーが無ければ None。"""
        return self._cast(key, NbtCompound)

    def get_compound(self, key: str) -> "NbtCompound":
        """TAG_Compound を取得する。キーが無ければ例外。"""
        return self._require(key, NbtCompound)

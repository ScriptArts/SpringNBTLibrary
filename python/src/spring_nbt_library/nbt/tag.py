"""NBTのタグ型と値モデル
"""

from __future__ import annotations

import enum
import math
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
    """NBTのタグ型
    値は仕様が定めるタグIDと一致する
    """

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
        """適合性テストで言語間比較に使う識別子"""
        return _TYPE_NAMES[self]

    @staticmethod
    def from_id(tag_id: int) -> "TagType":
        """タグIDから:class:`TagType`を得る

        :raises SpringNbtError: 未知のタグIDの場合
        """
        # 0..12の範囲外はすべて不正なタグID
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


def _join_surrogate_pairs(text: str) -> str:
    """UTF-16で対になるサロゲートを1文字へまとめる

    他言語は文字列をUTF-16で持つので、対になったサロゲートと補助文字は同じ文字列になる
    Pythonでも同じ文字列として比べられるよう、対になったものだけを合成し、孤立したものは残す
    """
    # サロゲートを含む文字列だけを組み直す
    for character in text:
        if 0xD800 <= ord(character) <= 0xDFFF:
            return mutf8._from_utf16_units(mutf8._to_utf16_units(text))

    return text


def _has_lone_surrogate(text: str) -> bool:
    """孤立サロゲートを含むか
    対になったサロゲートは:func:`_join_surrogate_pairs`で合成してある前提で、残ったものを探す
    """
    # 合成したあとに残っているサロゲートは、どれも対になっていない
    for character in text:
        if 0xD800 <= ord(character) <= 0xDFFF:
            return True

    return False


def _check_range(value: int, minimum: int, maximum: int, type_name: str) -> int:
    """Pythonのintには幅が無いため、構築時に範囲を検査する"""
    if not isinstance(value, int) or isinstance(value, bool):
        raise SpringNbtError.invalid_argument("%s には整数を渡すこと: %r" % (type_name, value))

    if value < minimum or value > maximum:
        raise SpringNbtError.invalid_argument(
            "%s の範囲外: %d (範囲 %d..%d)" % (type_name, value, minimum, maximum))

    return value


class NbtTag:
    """NBTのタグ
    具象型は:class:`NbtByte`などの派生クラス
    """

    #: このタグの型
    #: 派生クラスが上書きする
    type: TagType = TagType.END

    def copy(self) -> "NbtTag":
        """このタグの深いコピーを作る"""
        raise NotImplementedError


class _ScalarTag(NbtTag):
    """単一の値を持つタグの共通部分"""

    __slots__ = ("_value",)

    def __init__(self, value) -> None:
        self._value = self._validate(value)

    @property
    def value(self):
        """保持している値"""
        return self._value

    @value.setter
    def value(self, new_value) -> None:
        """値を差し替える
        構築時と同じ検査と変換をかける
        整数型の範囲外、文字列の長さ超過、型違いはINVALID_ARGUMENT
        """
        self._value = self._validate(new_value)

    def _validate(self, value):
        raise NotImplementedError

    def copy(self) -> "NbtTag":
        """このタグの深いコピーを作る"""
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
    """TAG_Byte
    8bit符号付き整数
    """

    type = TagType.BYTE

    def _validate(self, value):
        return _check_range(value, -128, 127, "byte")


class NbtShort(_ScalarTag):
    """TAG_Short
    16bit符号付き整数
    """

    type = TagType.SHORT

    def _validate(self, value):
        return _check_range(value, -32768, 32767, "short")


class NbtInt(_ScalarTag):
    """TAG_Int
    32bit符号付き整数
    """

    type = TagType.INT

    def _validate(self, value):
        return _check_range(value, -2147483648, 2147483647, "int")


class NbtLong(_ScalarTag):
    """TAG_Long
    64bit符号付き整数
    """

    type = TagType.LONG

    def _validate(self, value):
        return _check_range(value, -9223372036854775808, 9223372036854775807, "long")


def _round_to_float32(value) -> float:
    """数値をbinary32へ最近接丸めする
    binary32で表せない大きさの値は、他言語と同じく符号付きの無限大にする
    """
    try:
        return struct.unpack(">f", struct.pack(">f", float(value)))[0]
    except OverflowError:
        # 無限大へ丸まる値だけがここへ来る（floatに収まらない巨大な整数も含む）
        if value > 0:
            return math.inf

        return -math.inf


class NbtFloat(_ScalarTag):
    """TAG_Float
    IEEE 754 binary32

    Pythonのfloatはbinary64なので、シグナリングNaNはbinary32との変換で静かなNaNへ変わってしまう
    読み込んだときのビットパターンを覚えておき、値を変えていなければそのまま書き戻す
    """

    __slots__ = ("_bits",)

    type = TagType.FLOAT

    def __init__(self, value) -> None:
        super().__init__(value)
        self._bits = struct.pack(">f", self._value)

    @property
    def value(self):
        """保持している値"""
        return self._value

    @value.setter
    def value(self, new_value) -> None:
        """値を差し替える
        構築時と同じくbinary32へ丸める
        """
        self._value = self._validate(new_value)

        # 値を変えたら、読み込んだときのビットパターンはもう使わない
        self._bits = struct.pack(">f", self._value)

    @classmethod
    def _from_bits(cls, raw: bytes) -> "NbtFloat":
        """binary32のビットパターンからタグを作る
        読んだビットを覚えておき、書き戻すときにそのまま使う
        """
        tag = cls(struct.unpack(">f", raw)[0])
        tag._bits = bytes(raw)
        return tag

    def _to_bits(self) -> bytes:
        """書き出すbinary32のビットパターン"""
        return self._bits

    def _validate(self, value):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise SpringNbtError.invalid_argument("float には数値を渡すこと: %r" % (value,))

        # Pythonのfloatはbinary64なので、構築時にbinary32へ丸めて他言語と揃える
        return _round_to_float32(value)

    def copy(self) -> "NbtTag":
        """このタグの深いコピーを作る"""
        result = NbtFloat(self._value)
        result._bits = self._bits
        return result

    def __eq__(self, other) -> bool:
        if type(other) is not type(self):
            return False

        # NaNや-0.0を区別するため、値ではなくビットパターンで比較する
        return other._bits == self._bits

    def __hash__(self) -> int:
        return hash((self.type, self._bits))


class NbtDouble(_ScalarTag):
    """TAG_Double
    IEEE 754 binary64
    """

    type = TagType.DOUBLE

    def _validate(self, value):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise SpringNbtError.invalid_argument("double には数値を渡すこと: %r" % (value,))

        return float(value)

    def __eq__(self, other) -> bool:
        if type(other) is not type(self):
            return False

        # NaNや-0.0を区別するため、値ではなくビットパターンで比較する
        return struct.pack(">d", other._value) == struct.pack(">d", self._value)

    def __hash__(self) -> int:
        return hash((self.type, struct.pack(">d", self._value)))


class NbtString(_ScalarTag):
    """TAG_String
    MUTF-8で符号化される文字列
    """

    type = TagType.STRING

    def _validate(self, value):
        if not isinstance(value, str):
            raise SpringNbtError.invalid_argument("string には str を渡すこと: %r" % (value,))

        # 対になったサロゲートは、他言語と同じく補助文字1文字として持つ
        value = _join_surrogate_pairs(value)
        length = mutf8.byte_length(value)

        # 長さフィールドはu16
        # 65535を超えると書き出せない
        if length > mutf8.MAX_BYTE_LENGTH:
            raise SpringNbtError.invalid_argument(
                "文字列が長すぎる: MUTF-8 で %d バイト (上限 %d)" % (length, mutf8.MAX_BYTE_LENGTH))

        return value


class _ArrayTag(NbtTag):
    """整数配列を持つタグの共通部分"""

    __slots__ = ("_value",)

    #: 要素が取りうる範囲
    #: 派生クラスが上書きする
    _minimum = 0
    _maximum = 0
    _element_name = ""

    def __init__(self, value) -> None:
        self._value = self._validate(value)

    @property
    def value(self) -> List[int]:
        """保持している配列"""
        return self._value

    @value.setter
    def value(self, new_value) -> None:
        """値を差し替える
        範囲外ならINVALID_ARGUMENT
        """
        self._value = self._validate(new_value)

    def _validate(self, value) -> List[int]:
        result = list(value)

        # 各要素が対象の幅に収まるか確認する
        for element in result:
            _check_range(element, self._minimum, self._maximum, self._element_name)

        return result

    def copy(self) -> "NbtTag":
        """このタグの深いコピーを作る"""
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
    """TAG_Byte_Array
    8bit符号付き整数の配列
    """

    type = TagType.BYTE_ARRAY
    _minimum = -128
    _maximum = 127
    _element_name = "byte"


class NbtIntArray(_ArrayTag):
    """TAG_Int_Array
    32bit符号付き整数の配列
    """

    type = TagType.INT_ARRAY
    _minimum = -2147483648
    _maximum = 2147483647
    _element_name = "int"


class NbtLongArray(_ArrayTag):
    """TAG_Long_Array
    64bit符号付き整数の配列
    """

    type = TagType.LONG_ARRAY
    _minimum = -9223372036854775808
    _maximum = 9223372036854775807
    _element_name = "long"


class NbtList(NbtTag):
    """TAG_List
    要素型が1つに固定されたタグの列

    空リストの要素型は:attr:`TagType.END`
    最初の要素を追加した時点で型が確定する
    全要素を削除しても確定済みの要素型は維持される
    """

    type = TagType.LIST

    def __init__(self, element_type: TagType = TagType.END, elements=None) -> None:
        self._element_type = element_type
        self._items: List[NbtTag] = []

        # 与えられた要素は1つずつ型検査しながら追加する
        if elements is not None:
            # appendを通すことで、要素型の検査も一緒にかかる
            for element in elements:
                self.append(element)

    @property
    def element_type(self) -> TagType:
        """要素の型
        空で未確定なら:attr:`TagType.END`
        """
        return self._element_type

    def append(self, item: NbtTag) -> None:
        """末尾に追加する

        :raises SpringNbtError: 要素型と一致しない場合
        """
        self._ensure_element_type(item)
        self._items.append(item)

    def insert(self, index: int, item: NbtTag) -> None:
        """位置を指定して挿入する"""
        self._ensure_element_type(item)
        self._items.insert(index, item)

    def clear(self) -> None:
        """全要素を削除する
        確定済みの要素型は維持する
        """
        self._items.clear()

    def copy(self) -> "NbtTag":
        """このタグの深いコピーを作る"""
        copy = NbtList(self._element_type)

        # 要素も深くコピーする
        for item in self._items:
            copy._items.append(item.copy())

        return copy

    def _ensure_element_type(self, item: NbtTag) -> None:
        """追加しようとしているタグが要素型と一致するか調べる"""
        # TAG_Endはリストの要素になれない
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
        # 要素型を確定させる前に位置を確かめ、失敗したときに状態を変えない
        if index < -len(self._items) or index >= len(self._items):
            raise IndexError("位置が範囲外: %d" % index)

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
    """TAG_Compound
    挿入順を保持する、名前付きタグのマップ

    既存キーへの再設定は位置を維持したまま値だけを置き換える
    """

    type = TagType.COMPOUND

    def __init__(self, entries=None) -> None:
        # Pythonのdictは3.7以降で挿入順を保つ
        self._entries: Dict[str, NbtTag] = {}

        # 初期値が与えられたら、そのまま順に入れる
        if entries is not None:
            # setを通すことで、挿入順が保たれる
            for key, value in entries:
                self.set(key, value)

    # -- 型付き設定子 -------------------------------------------------------
    #
    # set(key, NbtInt(42))と書かずに済むようにするための糖衣
    # 取得子のget_intと対になる

    def set_byte(self, key: str, value: int) -> None:
        """TAG_Byteとして設定する"""
        self.set(key, NbtByte(value))

    def set_short(self, key: str, value: int) -> None:
        """TAG_Shortとして設定する"""
        self.set(key, NbtShort(value))

    def set_int(self, key: str, value: int) -> None:
        """TAG_Intとして設定する"""
        self.set(key, NbtInt(value))

    def set_long(self, key: str, value: int) -> None:
        """TAG_Longとして設定する"""
        self.set(key, NbtLong(value))

    def set_float(self, key: str, value: float) -> None:
        """TAG_Floatとして設定する"""
        self.set(key, NbtFloat(value))

    def set_double(self, key: str, value: float) -> None:
        """TAG_Doubleとして設定する"""
        self.set(key, NbtDouble(value))

    def set_bool(self, key: str, value: bool) -> None:
        """TAG_Byteとして設定する
        Trueは1、Falseは0
        """
        # NBTに真偽値の専用型は無いので、TAG_Byteの0 / 1で表す
        if value:
            self.set_byte(key, 1)
        else:
            self.set_byte(key, 0)

    def set_string(self, key: str, value: str) -> None:
        """TAG_Stringとして設定する

        :raises SpringNbtError: MUTF-8で65535バイトを超える場合
        """
        self.set(key, NbtString(value))

    def set_byte_array(self, key: str, value: List[int]) -> None:
        """TAG_Byte_Arrayとして設定する"""
        self.set(key, NbtByteArray(value))

    def set_int_array(self, key: str, value: List[int]) -> None:
        """TAG_Int_Arrayとして設定する"""
        self.set(key, NbtIntArray(value))

    def set_long_array(self, key: str, value: List[int]) -> None:
        """TAG_Long_Arrayとして設定する"""
        self.set(key, NbtLongArray(value))

    def set(self, key: str, value: NbtTag) -> None:
        """値を設定する
        既存キーなら位置を維持して値だけ置き換える
        """
        if not isinstance(key, str):
            raise SpringNbtError.invalid_argument("キーには str を渡すこと: %r" % (key,))

        key = _join_surrogate_pairs(key)

        # 孤立サロゲートを含むキーは書き出すと読み戻せないので、ここで止める
        if _has_lone_surrogate(key):
            raise SpringNbtError.invalid_argument("キーに孤立サロゲートは使えない")

        # TAG_EndはCompoundの終端マーカーなので値として持てない
        if value.type == TagType.END:
            raise SpringNbtError.unexpected_tag_type("TAG_End は Compound の値にできない")

        self._entries[key] = value

    def opt(self, key: str) -> Optional[NbtTag]:
        """キーに対応するタグを返す
        存在しなければNone
        """
        return self._entries.get(_join_surrogate_pairs(key))

    def get(self, key: str) -> NbtTag:
        """キーに対応するタグを返す
        存在しなければ例外
        """
        found = self._entries.get(_join_surrogate_pairs(key))

        if found is None:
            raise SpringNbtError.invalid_argument("キーが存在しない: %s" % key)

        return found

    def remove(self, key: str) -> bool:
        """キーを削除する
        削除できたらTrue
        """
        key = _join_surrogate_pairs(key)

        # 存在するキーだけを削除する
        if key in self._entries:
            del self._entries[key]
            return True

        return False

    def clear(self) -> None:
        """全要素を削除する"""
        self._entries.clear()

    def contains_key(self, key: str) -> bool:
        """キーが存在するか"""
        return _join_surrogate_pairs(key) in self._entries

    def keys(self):
        """挿入順のキー一覧"""
        return self._entries.keys()

    def items(self) -> Iterator[Tuple[str, NbtTag]]:
        """挿入順の (キー, タグ) の並び"""
        return iter(self._entries.items())

    def copy(self) -> "NbtTag":
        """このタグの深いコピーを作る"""
        copy = NbtCompound()

        # 挿入順のまま深くコピーする
        for key, value in self._entries.items():
            copy.set(key, value.copy())

        return copy

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, key: str) -> bool:
        return _join_surrogate_pairs(key) in self._entries

    def __getitem__(self, key: str) -> NbtTag:
        return self.get(key)

    def __setitem__(self, key: str, value: NbtTag) -> None:
        self.set(key, value)

    def __delitem__(self, key: str) -> None:
        del self._entries[_join_surrogate_pairs(key)]

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
    # 「キーが無い」と「型が違う」は区別する
    # opt_*はキーが無ければNoneを返し、get_*は例外を送出する
    # どちらも型が違えば必ずUNEXPECTED_TAG_TYPEの例外になる

    def _cast(self, key: str, expected):
        """キーに対応するタグを目的の型として取り出す
        キーが無ければNone、型が違えば例外
        """
        tag = self._entries.get(key)

        if tag is None:
            return None

        if isinstance(tag, expected):
            return tag

        raise SpringNbtError.unexpected_tag_type(
            'キー "%s" は %s だが %s として取り出そうとした'
            % (key, tag.type.as_string(), expected.__name__))

    def _require(self, key: str, expected):
        """キーに対応するタグを目的の型として取り出す
        キーが無くても型が違っても例外
        """
        tag = self._cast(key, expected)

        if tag is None:
            raise SpringNbtError.invalid_argument("キーが存在しない: %s" % key)

        return tag

    def opt_byte(self, key: str) -> Optional[int]:
        """TAG_Byteを取得する
        キーが無ければNone
        """
        tag = self._cast(key, NbtByte)

        if tag is None:
            return None

        return tag.value

    def get_byte(self, key: str) -> int:
        """TAG_Byteを取得する
        キーが無ければ例外
        """
        return self._require(key, NbtByte).value

    def opt_short(self, key: str) -> Optional[int]:
        """TAG_Shortを取得する
        キーが無ければNone
        """
        tag = self._cast(key, NbtShort)

        if tag is None:
            return None

        return tag.value

    def get_short(self, key: str) -> int:
        """TAG_Shortを取得する
        キーが無ければ例外
        """
        return self._require(key, NbtShort).value

    def opt_int(self, key: str) -> Optional[int]:
        """TAG_Intを取得する
        キーが無ければNone
        """
        tag = self._cast(key, NbtInt)

        if tag is None:
            return None

        return tag.value

    def get_int(self, key: str) -> int:
        """TAG_Intを取得する
        キーが無ければ例外
        """
        return self._require(key, NbtInt).value

    def opt_long(self, key: str) -> Optional[int]:
        """TAG_Longを取得する
        キーが無ければNone
        """
        tag = self._cast(key, NbtLong)

        if tag is None:
            return None

        return tag.value

    def get_long(self, key: str) -> int:
        """TAG_Longを取得する
        キーが無ければ例外
        """
        return self._require(key, NbtLong).value

    def opt_float(self, key: str) -> Optional[float]:
        """TAG_Floatを取得する
        キーが無ければNone
        """
        tag = self._cast(key, NbtFloat)

        if tag is None:
            return None

        return tag.value

    def get_float(self, key: str) -> float:
        """TAG_Floatを取得する
        キーが無ければ例外
        """
        return self._require(key, NbtFloat).value

    def opt_double(self, key: str) -> Optional[float]:
        """TAG_Doubleを取得する
        キーが無ければNone
        """
        tag = self._cast(key, NbtDouble)

        if tag is None:
            return None

        return tag.value

    def get_double(self, key: str) -> float:
        """TAG_Doubleを取得する
        キーが無ければ例外
        """
        return self._require(key, NbtDouble).value

    def opt_bool(self, key: str) -> Optional[bool]:
        """TAG_Byteを真偽値として取得する
        0以外がTrue
        キーが無ければNone
        """
        raw = self.opt_byte(key)

        if raw is None:
            return None

        return raw != 0

    def get_bool(self, key: str) -> bool:
        """TAG_Byteを真偽値として取得する
        0以外がTrue
        キーが無ければ例外
        """
        return self.get_byte(key) != 0

    def opt_string(self, key: str) -> Optional[str]:
        """TAG_Stringを取得する
        キーが無ければNone
        """
        tag = self._cast(key, NbtString)

        if tag is None:
            return None

        return tag.value

    def get_string(self, key: str) -> str:
        """TAG_Stringを取得する
        キーが無ければ例外
        """
        return self._require(key, NbtString).value

    def opt_byte_array(self, key: str) -> Optional[List[int]]:
        """TAG_Byte_Arrayを取得する
        キーが無ければNone
        """
        tag = self._cast(key, NbtByteArray)

        if tag is None:
            return None

        return tag.value

    def get_byte_array(self, key: str) -> List[int]:
        """TAG_Byte_Arrayを取得する
        キーが無ければ例外
        """
        return self._require(key, NbtByteArray).value

    def opt_int_array(self, key: str) -> Optional[List[int]]:
        """TAG_Int_Arrayを取得する
        キーが無ければNone
        """
        tag = self._cast(key, NbtIntArray)

        if tag is None:
            return None

        return tag.value

    def get_int_array(self, key: str) -> List[int]:
        """TAG_Int_Arrayを取得する
        キーが無ければ例外
        """
        return self._require(key, NbtIntArray).value

    def opt_long_array(self, key: str) -> Optional[List[int]]:
        """TAG_Long_Arrayを取得する
        キーが無ければNone
        """
        tag = self._cast(key, NbtLongArray)

        if tag is None:
            return None

        return tag.value

    def get_long_array(self, key: str) -> List[int]:
        """TAG_Long_Arrayを取得する
        キーが無ければ例外
        """
        return self._require(key, NbtLongArray).value

    def opt_list(self, key: str) -> Optional[NbtList]:
        """TAG_Listを取得する
        キーが無ければNone
        """
        return self._cast(key, NbtList)

    def get_list(self, key: str) -> NbtList:
        """TAG_Listを取得する
        キーが無ければ例外
        """
        return self._require(key, NbtList)

    def opt_compound(self, key: str) -> Optional["NbtCompound"]:
        """TAG_Compoundを取得する
        キーが無ければNone
        """
        return self._cast(key, NbtCompound)

    def get_compound(self, key: str) -> "NbtCompound":
        """TAG_Compoundを取得する
        キーが無ければ例外
        """
        return self._require(key, NbtCompound)

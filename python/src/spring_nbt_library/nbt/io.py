"""NBT のファイル・バイト列・ストリームからの読み書き。

仕様: ``docs/spec/10-nbt-binary.md`` 3章〜6章
"""

from __future__ import annotations

import enum
import gzip
import struct
import zlib
from typing import Optional

from ..errors import ErrorCode, SpringNbtError
from . import _recursion, mutf8
from .tag import (
    NbtByte,
    NbtByteArray,
    NbtCompound,
    NbtDouble,
    NbtFloat,
    NbtInt,
    NbtIntArray,
    NbtList,
    NbtLong,
    NbtLongArray,
    NbtShort,
    NbtString,
    NbtTag,
    TagType,
)

__all__ = [
    "NbtFormat",
    "Compression",
    "NamedTag",
    "NbtReadOptions",
    "NbtWriteOptions",
    "read_file",
    "read_bytes",
    "read_stream",
    "write_file",
    "write_bytes",
    "write_stream",
    "detect_compression",
]


class NbtFormat(enum.Enum):
    """NBT のルートタグの並び方。"""

    #: ファイル形式。ルートは「タグID + 名前長 + 名前 + ペイロード」の順。
    JAVA = "java"

    #: ネットワーク形式 (1.20.2 以降)。ルートに名前が付かない。
    NETWORK = "network"


class Compression(enum.Enum):
    """圧縮方式。"""

    NONE = "none"
    GZIP = "gzip"
    ZLIB = "zlib"

    #: 先頭バイトから自動判定する。読み込み時のみ指定できる。
    AUTO = "auto"


class NamedTag:
    """ルート名とルートタグの組。"""

    __slots__ = ("name", "tag")

    def __init__(self, name: str, tag: NbtCompound) -> None:
        self.name = name
        self.tag = tag

    def __repr__(self) -> str:
        return "NamedTag(%r, %r)" % (self.name, self.tag)


class NbtReadOptions:
    """NBT 読み込みのオプション。"""

    def __init__(self, fmt: NbtFormat = NbtFormat.JAVA,
                 compression: Compression = Compression.AUTO,
                 max_depth: int = _recursion.DEFAULT_MAX_DEPTH,
                 max_decompressed_size: int = -1) -> None:
        #: ルートタグの並び方。
        self.format = fmt
        #: 圧縮方式。既定は自動判定。
        self.compression = compression
        #: ネストの深さ上限。
        self.max_depth = max_depth
        #: 展開後の総バイト数の上限。負値なら無制限。
        self.max_decompressed_size = max_decompressed_size


class NbtWriteOptions:
    """NBT 書き込みのオプション。"""

    def __init__(self, fmt: NbtFormat = NbtFormat.JAVA,
                 compression: Compression = Compression.GZIP) -> None:
        #: ルートタグの並び方。
        self.format = fmt
        #: 圧縮方式。既定は GZip。
        self.compression = compression


_DEFAULT_READ = NbtReadOptions()
_DEFAULT_WRITE = NbtWriteOptions()



# ---------------------------------------------------------------------------
# 読み込み
# ---------------------------------------------------------------------------


class _Reader:
    """展開済みのバイト列から NBT を読み出す。

    入力全体をあらかじめメモリに持つ設計にしている。
    「宣言された長さが残り入力長を超えていないか」を確保前に検査できるようにするため。
    """

    def __init__(self, data: bytes, max_depth: int) -> None:
        self._data = data
        self._max_depth = max_depth
        self._position = 0

    @property
    def _remaining(self) -> int:
        return len(self._data) - self._position

    def read_root(self, fmt: NbtFormat) -> NamedTag:
        """ルートタグを 1 つ読む。形式によって名前の有無が変わる。"""
        tag_type = TagType.from_id(self._read_byte())

        # Java版のファイル形式でもネットワーク形式でも、ルートは必ず TAG_Compound
        if tag_type != TagType.COMPOUND:
            raise SpringNbtError.malformed(
                "ルートタグは compound でなければならないが %s だった" % tag_type.as_string())

        if fmt == NbtFormat.JAVA:
            # ファイル形式のルートには名前が付く（通常は空文字列）
            name = _require_utf8_representable(self._read_string(), "ルート名")
        else:
            # ネットワーク形式 (1.20.2+) のルートに名前は無い
            name = ""

        root = self._read_compound_payload(1)

        # 末尾に余分なバイトが残っていたら、読み違えている可能性が高い
        if self._remaining != 0:
            raise SpringNbtError.malformed("ルートタグの後に %d バイトの余分な入力がある" % self._remaining)

        return NamedTag(name, root)

    def _read_payload(self, tag_type: TagType, depth: int) -> NbtTag:
        # 深さ上限は再帰する型に入る手前で検査する
        if depth > self._max_depth:
            raise SpringNbtError.limit_exceeded("ネストが深すぎる (上限 %d)" % self._max_depth)

        if tag_type == TagType.BYTE:
            return NbtByte(struct.unpack(">b", self._take(1))[0])

        if tag_type == TagType.SHORT:
            return NbtShort(struct.unpack(">h", self._take(2))[0])

        if tag_type == TagType.INT:
            return NbtInt(struct.unpack(">i", self._take(4))[0])

        if tag_type == TagType.LONG:
            return NbtLong(struct.unpack(">q", self._take(8))[0])

        if tag_type == TagType.FLOAT:
            return NbtFloat(struct.unpack(">f", self._take(4))[0])

        if tag_type == TagType.DOUBLE:
            return NbtDouble(struct.unpack(">d", self._take(8))[0])

        if tag_type == TagType.BYTE_ARRAY:
            return NbtByteArray(self._read_number_array(1, ">b"))

        if tag_type == TagType.STRING:
            return NbtString(self._read_string())

        if tag_type == TagType.LIST:
            return self._read_list_payload(depth)

        if tag_type == TagType.COMPOUND:
            return self._read_compound_payload(depth)

        if tag_type == TagType.INT_ARRAY:
            return NbtIntArray(self._read_number_array(4, ">i"))

        if tag_type == TagType.LONG_ARRAY:
            return NbtLongArray(self._read_number_array(8, ">q"))

        raise SpringNbtError.malformed("TAG_End のペイロードを読もうとした")

    def _read_compound_payload(self, depth: int) -> NbtCompound:
        compound = NbtCompound()

        # TAG_End が現れるまで名前付きタグを読み続ける
        while True:
            tag_type = TagType.from_id(self._read_byte())

            if tag_type == TagType.END:
                return compound

            name = _require_utf8_representable(self._read_string(), "Compound のキー")
            compound.set(name, self._read_payload(tag_type, depth + 1))

    def _read_list_payload(self, depth: int) -> NbtList:
        element_type = TagType.from_id(self._read_byte())
        count = self._read_length()

        if element_type == TagType.END:
            # 要素型 End のリストは空でなければならない
            if count != 0:
                raise SpringNbtError.malformed("要素型 End のリストに %d 個の要素が宣言されている" % count)

            return NbtList(TagType.END)

        # 1 要素の最小バイト数から、宣言された個数が入力に収まるかを先に検査する
        self._ensure_available(count * _minimum_payload_size(element_type))

        elements = []

        # 宣言された個数だけペイロードを読む
        for _ in range(count):
            elements.append(self._read_payload(element_type, depth + 1))

        return NbtList(element_type, elements)

    def _read_number_array(self, element_size: int, fmt: str):
        count = self._read_length()
        self._ensure_available(count * element_size)

        values = []

        # 要素サイズごとに切り出して読む
        for index in range(count):
            offset = self._position + (index * element_size)
            values.append(struct.unpack(fmt, self._data[offset:offset + element_size])[0])

        self._position += count * element_size
        return values

    def _read_string(self) -> str:
        length = struct.unpack(">H", self._take(2))[0]
        self._ensure_available(length)
        text = mutf8.decode(self._data[self._position:self._position + length])
        self._position += length
        return text

    def _read_length(self) -> int:
        length = struct.unpack(">i", self._take(4))[0]

        # 長さは i32 だが、負値は仕様上ありえない
        if length < 0:
            raise SpringNbtError.malformed("長さが負値: %d" % length)

        return length

    def _read_byte(self) -> int:
        self._ensure_available(1)
        value = self._data[self._position]
        self._position += 1
        return value

    def _take(self, count: int) -> bytes:
        self._ensure_available(count)
        chunk = self._data[self._position:self._position + count]
        self._position += count
        return chunk

    def _ensure_available(self, required: int) -> None:
        """残り入力が必要バイト数を満たすか検査する。メモリを確保する前に呼ぶ。"""
        if required > self._remaining:
            raise SpringNbtError.malformed(
                "入力が足りない: %d バイト必要だが残り %d バイト" % (required, self._remaining))


def _require_utf8_representable(text: str, role: str) -> str:
    """キーやルート名として使える文字列か検査する。

    値と違い、キーには孤立サロゲートを許さない（仕様 10 の 2.2章）。
    Minecraft が書き出すキーは ASCII の識別子のみで、
    孤立サロゲートが現れるのはデータ破損を意味する。
    """
    # 対にならないサロゲートが含まれていないか調べる
    index = 0
    # コード単位を 1 つずつ見て、サロゲート対をまとめる
    while index < len(text):
        code = ord(text[index])

        # 上位サロゲートは、対になる下位サロゲートとまとめて 1 文字を成す
        if 0xD800 <= code <= 0xDBFF:
            # 対が揃っていれば 2 コード単位を消費する。揃わなければ孤立サロゲート
            if index + 1 < len(text) and 0xDC00 <= ord(text[index + 1]) <= 0xDFFF:
                index += 2
                continue

            raise SpringNbtError.malformed("%sが UTF-8 に写せない（孤立サロゲートを含む）" % role)

        if 0xDC00 <= code <= 0xDFFF:
            raise SpringNbtError.malformed("%sが UTF-8 に写せない（孤立サロゲートを含む）" % role)

        index += 1

    return text


def _minimum_payload_size(tag_type: TagType) -> int:
    """その型のペイロードが最低何バイトになるかを返す。長さの先行検証に使う。"""
    return _MINIMUM_PAYLOAD_SIZE.get(tag_type, 1)


_MINIMUM_PAYLOAD_SIZE = {
    TagType.BYTE: 1,
    TagType.SHORT: 2,
    TagType.INT: 4,
    TagType.FLOAT: 4,
    TagType.LONG: 8,
    TagType.DOUBLE: 8,
    # 長さフィールドの 4 バイトは必ずある
    TagType.BYTE_ARRAY: 4,
    TagType.INT_ARRAY: 4,
    TagType.LONG_ARRAY: 4,
    # 長さフィールドの 2 バイトは必ずある
    TagType.STRING: 2,
    # 要素型 1 バイト + 個数 4 バイト
    TagType.LIST: 5,
    # 終端の TAG_End 1 バイトは必ずある
    TagType.COMPOUND: 1,
}


# ---------------------------------------------------------------------------
# 書き込み
# ---------------------------------------------------------------------------


class _Writer:
    """NBT を展開済みのバイト列へ書き出す。

    出力は一意でなければならない（ラウンドトリップ検証が成立するため）。
    Compound は挿入順のまま、浮動小数点はビットパターンのまま書き出す。
    """

    def __init__(self) -> None:
        self._buffer = bytearray()

    def write_root(self, named: NamedTag, fmt: NbtFormat) -> bytes:
        """ルートタグを 1 つ書き出す。形式によって名前の有無が変わる。"""
        self._buffer.append(TagType.COMPOUND.value)

        if fmt == NbtFormat.JAVA:
            # ファイル形式のルートには名前が付く
            self._write_string(named.name)

        self._write_compound_payload(named.tag)
        return bytes(self._buffer)

    def _write_payload(self, tag: NbtTag) -> None:
        # タグの型ごとに、決まったバイト表現で書き出す
        if isinstance(tag, NbtByte):
            self._buffer += struct.pack(">b", tag.value)
        elif isinstance(tag, NbtShort):
            self._buffer += struct.pack(">h", tag.value)
        elif isinstance(tag, NbtInt):
            self._buffer += struct.pack(">i", tag.value)
        elif isinstance(tag, NbtLong):
            self._buffer += struct.pack(">q", tag.value)
        elif isinstance(tag, NbtFloat):
            self._buffer += struct.pack(">f", tag.value)
        elif isinstance(tag, NbtDouble):
            self._buffer += struct.pack(">d", tag.value)
        elif isinstance(tag, NbtByteArray):
            self._write_number_array(tag.value, ">b")
        elif isinstance(tag, NbtString):
            self._write_string(tag.value)
        elif isinstance(tag, NbtList):
            self._write_list_payload(tag)
        elif isinstance(tag, NbtCompound):
            self._write_compound_payload(tag)
        elif isinstance(tag, NbtIntArray):
            self._write_number_array(tag.value, ">i")
        elif isinstance(tag, NbtLongArray):
            self._write_number_array(tag.value, ">q")
        else:
            raise SpringNbtError.malformed("書き出せないタグ: %s" % tag.type.as_string())

    def _write_compound_payload(self, compound: NbtCompound) -> None:
        # 挿入順のまま「タグID + 名前 + ペイロード」を並べる
        for key, value in compound.items():
            self._buffer.append(value.type.value)
            self._write_string(key)
            self._write_payload(value)

        self._buffer.append(TagType.END.value)

    def _write_list_payload(self, tag: NbtList) -> None:
        self._buffer.append(tag.element_type.value)
        self._buffer += struct.pack(">i", len(tag))

        # 要素型は共通なので、ペイロードだけを並べる
        for item in tag:
            self._write_payload(item)

    def _write_number_array(self, values, fmt: str) -> None:
        self._buffer += struct.pack(">i", len(values))

        # 要素を1つずつ同じ書式で並べる
        for value in values:
            self._buffer += struct.pack(fmt, value)

    def _write_string(self, text: str) -> None:
        encoded = mutf8.encode(text)

        # 長さフィールドは u16。キー名は素の str なのでここでも検査する
        if len(encoded) > mutf8.MAX_BYTE_LENGTH:
            raise SpringNbtError.invalid_argument(
                "文字列が長すぎる: MUTF-8 で %d バイト (上限 %d)"
                % (len(encoded), mutf8.MAX_BYTE_LENGTH))

        self._buffer += struct.pack(">H", len(encoded))
        self._buffer += encoded


# ---------------------------------------------------------------------------
# 圧縮
# ---------------------------------------------------------------------------


def detect_compression(data: bytes) -> Compression:
    """先頭バイトから圧縮方式を判定する。

    :raises SpringNbtError: どの方式とも判定できない場合。
    """
    if len(data) == 0:
        raise SpringNbtError.malformed("入力が空で圧縮方式を判定できない")

    # GZip は必ず 1F 8B で始まる
    if len(data) >= 2 and data[0] == 0x1F and data[1] == 0x8B:
        return Compression.GZIP

    if len(data) >= 2:
        # zlib ヘッダは「圧縮法が 8 (deflate)」かつ「先頭2バイトが 31 の倍数」
        is_deflate = (data[0] & 0x0F) == 0x08
        header = (data[0] << 8) | data[1]

        if is_deflate and header % 31 == 0:
            return Compression.ZLIB

    # 無圧縮なら先頭は TAG_Compound のタグID
    if data[0] == TagType.COMPOUND.value:
        return Compression.NONE

    raise SpringNbtError.malformed("圧縮方式を判定できない (先頭バイト 0x%02X)" % data[0])


def _decompress(data: bytes, options: NbtReadOptions) -> bytes:
    # AUTO なら先頭バイトから圧縮方式を見分ける
    if options.compression == Compression.AUTO:
        method = detect_compression(data)
    else:
        method = options.compression

    # 方式ごとに圧縮する
    if method == Compression.NONE:
        plain = data
    elif method == Compression.GZIP:
        try:
            plain = gzip.decompress(data)
        except OSError as error:
            raise SpringNbtError(ErrorCode.MALFORMED_DATA, "GZip データを展開できない") from error
    elif method == Compression.ZLIB:
        try:
            plain = zlib.decompress(data)
        except zlib.error as error:
            raise SpringNbtError(ErrorCode.MALFORMED_DATA, "Zlib データを展開できない") from error
    else:
        raise SpringNbtError.invalid_argument("展開できない圧縮方式: %s" % method)

    # 展開後のサイズ上限を確認する
    if options.max_decompressed_size >= 0 and len(plain) > options.max_decompressed_size:
        raise SpringNbtError.limit_exceeded(
            "展開後のサイズが上限 %d バイトを超えた" % options.max_decompressed_size)

    return plain


def _compress(plain: bytes, method: Compression) -> bytes:
    if method == Compression.NONE:
        return plain

    if method == Compression.GZIP:
        # mtime を 0 に固定して、同じ入力から同じバイト列が出るようにする
        return gzip.compress(plain, mtime=0)

    if method == Compression.ZLIB:
        return zlib.compress(plain, 6)

    raise SpringNbtError.invalid_argument("圧縮できない方式: %s" % method)


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------


def read_bytes(data: bytes, options: Optional[NbtReadOptions] = None) -> NamedTag:
    """バイト列から NBT を読む。"""
    if options is None:
        effective = _DEFAULT_READ
    else:
        effective = options

    reader = _Reader(_decompress(data, effective), effective.max_depth)

    # Python は既定の再帰上限が仕様の深さ上限に届かないため、ここで引き上げる
    with _recursion.guard(effective.max_depth, "ネストが深すぎて読み込めない"):
        return reader.read_root(effective.format)


def read_file(path: str, options: Optional[NbtReadOptions] = None) -> NamedTag:
    """ファイルから NBT を読む。"""
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as error:
        raise SpringNbtError(ErrorCode.IO, "ファイルを読めない: %s" % path) from error

    return read_bytes(data, options)


def read_stream(stream, options: Optional[NbtReadOptions] = None) -> NamedTag:
    """ストリームから NBT を読む。ストリームは最後まで読み切る。"""
    try:
        data = stream.read()
    except OSError as error:
        raise SpringNbtError(ErrorCode.IO, "ストリームを読めない") from error

    return read_bytes(data, options)


def write_bytes(named: NamedTag, options: Optional[NbtWriteOptions] = None) -> bytes:
    """NBT をバイト列へ書き出す。"""
    if options is None:
        effective = _DEFAULT_WRITE
    else:
        effective = options

    # 書き込み時に Auto は決められない
    if effective.compression == Compression.AUTO:
        raise SpringNbtError.invalid_argument("書き込みで Compression.AUTO は指定できない")

    writer = _Writer()

    # 書き出しも同じ深さだけ再帰するため、読み込みと同じ余白を確保する
    with _recursion.guard(_recursion.DEFAULT_MAX_DEPTH, "ネストが深すぎて書き出せない"):
        plain = writer.write_root(named, effective.format)

    return _compress(plain, effective.compression)


def write_file(path: str, named: NamedTag, options: Optional[NbtWriteOptions] = None) -> None:
    """NBT をファイルへ書き出す。"""
    data = write_bytes(named, options)

    try:
        with open(path, "wb") as handle:
            handle.write(data)
    except OSError as error:
        raise SpringNbtError(ErrorCode.IO, "ファイルへ書けない: %s" % path) from error


def write_stream(stream, named: NamedTag, options: Optional[NbtWriteOptions] = None) -> None:
    """NBT をストリームへ書き出す。"""
    data = write_bytes(named, options)

    try:
        stream.write(data)
    except OSError as error:
        raise SpringNbtError(ErrorCode.IO, "ストリームへ書けない") from error

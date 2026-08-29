"""Modified UTF-8 (MUTF-8) の符号化・復号。

標準 UTF-8 との違いは 2 点だけ。

* ``U+0000`` を ``C0 80`` の 2 バイトで表す
* ``U+10000`` 以上をサロゲートペアへ分解し、3 バイト × 2 で表す (CESU-8)

Python の :class:`str` はコードポイント単位だが、
``surrogatepass`` 相当の扱いで孤立サロゲートも保持できるため、
C# / Java と同じく文字列としてそのまま往復できる。

仕様: ``docs/spec/10-nbt-binary.md`` 2章
"""

from __future__ import annotations

from ..errors import SpringNbtError

__all__ = ["MAX_BYTE_LENGTH", "decode", "encode", "byte_length"]

#: MUTF-8 の文字列が取りうる最大バイト長（長さフィールドが u16 のため）。
MAX_BYTE_LENGTH = 65535


def _to_utf16_units(text: str):
    """文字列を UTF-16 コード単位の列へ落とす。"""
    units = []

    # コードポイントごとに、補助文字ならサロゲートペアへ分解する
    for character in text:
        code = ord(character)

        # BMP 外の文字は、UTF-16 のサロゲート対へ分解して持つ
        if code >= 0x10000:
            code -= 0x10000
            units.append(0xD800 + (code >> 10))
            units.append(0xDC00 + (code & 0x3FF))
        else:
            units.append(code)

    return units


def _from_utf16_units(units) -> str:
    """UTF-16 コード単位の列を文字列へ戻す。孤立サロゲートはそのまま保持する。"""
    result = []
    index = 0

    # サロゲートペアになっているものだけを1文字へ合成する
    while index < len(units):
        unit = units[index]

        # サロゲート対が揃っていれば 1 つのコードポイントへ戻す
        if 0xD800 <= unit <= 0xDBFF and index + 1 < len(units) and 0xDC00 <= units[index + 1] <= 0xDFFF:
            low = units[index + 1]
            code = 0x10000 + ((unit - 0xD800) << 10) + (low - 0xDC00)
            result.append(chr(code))
            index += 2
        else:
            result.append(chr(unit))
            index += 1

    return "".join(result)


def decode(data: bytes) -> str:
    """MUTF-8 バイト列を文字列へ復号する。

    :raises SpringNbtError: バイト列が MUTF-8 として不正な場合。
    """
    units = []
    index = 0

    # 先頭から 1 文字ずつ取り出す
    while index < len(data):
        b0 = data[index]

        if b0 & 0x80 == 0x00:
            # 1 バイト形式: 0xxxxxxx (U+0001..U+007F)
            if b0 == 0x00:
                # 素の 0x00 は MUTF-8 では現れてはならない (C0 80 を使う)
                raise SpringNbtError.malformed("MUTF-8: 素の 0x00 が現れた (U+0000 は C0 80 で表す)")

            units.append(b0)
            index += 1
        elif b0 & 0xE0 == 0xC0:
            # 2 バイト形式: 110xxxxx 10xxxxxx
            if index + 1 >= len(data):
                raise SpringNbtError.malformed("MUTF-8: 2バイト形式が途中で切れた")

            b1 = data[index + 1]

            if b1 & 0xC0 != 0x80:
                raise SpringNbtError.malformed("MUTF-8: 2バイト形式の継続バイトが不正")

            value = ((b0 & 0x1F) << 6) | (b1 & 0x3F)

            # C0 80 (U+0000) だけは正当。それ以外の 0x80 未満は冗長符号化
            if value < 0x80 and not (b0 == 0xC0 and b1 == 0x80):
                raise SpringNbtError.malformed("MUTF-8: 冗長な2バイト符号化")

            units.append(value)
            index += 2
        elif b0 & 0xF0 == 0xE0:
            # 3 バイト形式: 1110xxxx 10xxxxxx 10xxxxxx
            if index + 2 >= len(data):
                raise SpringNbtError.malformed("MUTF-8: 3バイト形式が途中で切れた")

            b1 = data[index + 1]
            b2 = data[index + 2]

            if b1 & 0xC0 != 0x80 or b2 & 0xC0 != 0x80:
                raise SpringNbtError.malformed("MUTF-8: 3バイト形式の継続バイトが不正")

            value = ((b0 & 0x0F) << 12) | ((b1 & 0x3F) << 6) | (b2 & 0x3F)

            # 3 バイトで表すべき範囲は U+0800 以上
            if value < 0x800:
                raise SpringNbtError.malformed("MUTF-8: 冗長な3バイト符号化")

            units.append(value)
            index += 3
        else:
            # 4 バイト形式 (標準 UTF-8) や継続バイト単独は MUTF-8 では不正
            raise SpringNbtError.malformed("MUTF-8: 不正な先頭バイト 0x%02X" % b0)

    return _from_utf16_units(units)


def encode(text: str) -> bytes:
    """文字列を MUTF-8 バイト列へ符号化する。

    サロゲートは対になっているかどうかに関わらず 1 つずつ 3 バイトで符号化されるため、
    孤立サロゲートもそのまま往復できる。
    """
    out = bytearray()

    # コード単位ごとに 1〜3 バイトへ展開する
    for unit in _to_utf16_units(text):
        # U+0001..U+007F だけが 1 バイト。U+0000 は 2 バイトになる
        if 0x0001 <= unit <= 0x007F:
            out.append(unit)
        elif unit == 0x0000 or unit <= 0x07FF:
            # U+0000 もこの経路で C0 80 になる
            out.append(0xC0 | ((unit >> 6) & 0x1F))
            out.append(0x80 | (unit & 0x3F))
        else:
            out.append(0xE0 | ((unit >> 12) & 0x0F))
            out.append(0x80 | ((unit >> 6) & 0x3F))
            out.append(0x80 | (unit & 0x3F))

    return bytes(out)


def byte_length(text: str) -> int:
    """文字列を MUTF-8 で符号化したときのバイト長を求める。実際に符号化はしない。"""
    length = 0

    # 各コード単位が何バイトになるかを数える
    for unit in _to_utf16_units(text):
        # U+0001..U+007F だけが 1 バイト。U+0000 は 2 バイトになる
        if 0x0001 <= unit <= 0x007F:
            length += 1
        elif unit == 0x0000 or unit <= 0x07FF:
            length += 2
        else:
            length += 3

    return length

"""Modified UTF-8 (MUTF-8)の符号化・復号

標準UTF-8との違いは2点だけ

* ``U+0000``を``C0 80``の2バイトで表す
* ``U+10000``以上をサロゲートペアへ分解し、3バイト × 2で表す (CESU-8)

Pythonの:class:`str`はコードポイント単位だが、``surrogatepass``相当の扱いで孤立サロゲートも保持できる
そのため、C# / Javaと同じく、MUTF-8のバイト列を文字列へ復号しても同じバイト列へ戻せる
"""

from __future__ import annotations

from ..errors import SpringNbtError

__all__ = ["MAX_BYTE_LENGTH", "decode", "encode", "byte_length"]

#: MUTF-8の文字列が取りうる最大バイト長（長さフィールドがu16のため）
MAX_BYTE_LENGTH = 65535


def _to_utf16_units(text: str):
    """文字列をUTF-16コード単位の列へ落とす"""
    units = []

    # コードポイントごとに、補助文字ならサロゲートペアへ分解する
    for character in text:
        code = ord(character)

        # BMP外の文字は、UTF-16のサロゲート対へ分解して持つ
        if code >= 0x10000:
            code -= 0x10000
            units.append(0xD800 + (code >> 10))
            units.append(0xDC00 + (code & 0x3FF))
        else:
            units.append(code)

    return units


def _from_utf16_units(units) -> str:
    """UTF-16コード単位の列を文字列へ戻す
    孤立サロゲートはそのまま保持する
    """
    result = []
    index = 0

    # サロゲートペアになっているものだけを1文字へ合成する
    while index < len(units):
        unit = units[index]

        # サロゲート対が揃っていれば1つのコードポイントへ戻す
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
    """MUTF-8バイト列を文字列へ復号する

    :raises SpringNbtError: バイト列がMUTF-8として不正な場合
    """
    units = []
    index = 0

    # 先頭から1文字ずつ取り出す
    while index < len(data):
        b0 = data[index]

        if b0 & 0x80 == 0x00:
            # 1バイト形式: 0xxxxxxx (U+0001..U+007F)
            if b0 == 0x00:
                # 素の0x00はMUTF-8では現れてはならない (C0 80を使う)
                raise SpringNbtError.malformed("MUTF-8: 素の 0x00 が現れた (U+0000 は C0 80 で表す)")

            units.append(b0)
            index += 1
        elif b0 & 0xE0 == 0xC0:
            # 2バイト形式: 110xxxxx 10xxxxxx
            if index + 1 >= len(data):
                raise SpringNbtError.malformed("MUTF-8: 2バイト形式が途中で切れた")

            b1 = data[index + 1]

            if b1 & 0xC0 != 0x80:
                raise SpringNbtError.malformed("MUTF-8: 2バイト形式の継続バイトが不正")

            value = ((b0 & 0x1F) << 6) | (b1 & 0x3F)

            # C0 80 (U+0000)だけは正当
            # それ以外の0x80未満は冗長符号化
            if value < 0x80 and not (b0 == 0xC0 and b1 == 0x80):
                raise SpringNbtError.malformed("MUTF-8: 冗長な2バイト符号化")

            units.append(value)
            index += 2
        elif b0 & 0xF0 == 0xE0:
            # 3バイト形式: 1110xxxx 10xxxxxx 10xxxxxx
            if index + 2 >= len(data):
                raise SpringNbtError.malformed("MUTF-8: 3バイト形式が途中で切れた")

            b1 = data[index + 1]
            b2 = data[index + 2]

            if b1 & 0xC0 != 0x80 or b2 & 0xC0 != 0x80:
                raise SpringNbtError.malformed("MUTF-8: 3バイト形式の継続バイトが不正")

            value = ((b0 & 0x0F) << 12) | ((b1 & 0x3F) << 6) | (b2 & 0x3F)

            # 3バイトで表すべき範囲はU+0800以上
            if value < 0x800:
                raise SpringNbtError.malformed("MUTF-8: 冗長な3バイト符号化")

            units.append(value)
            index += 3
        else:
            # 4バイト形式 (標準UTF-8)や継続バイト単独はMUTF-8では不正
            raise SpringNbtError.malformed("MUTF-8: 不正な先頭バイト 0x%02X" % b0)

    return _from_utf16_units(units)


def encode(text: str) -> bytes:
    """文字列をMUTF-8バイト列へ符号化する

    サロゲートは対になっているかどうかに関わらず1つずつ3バイトで符号化されるため、孤立サロゲートもそのまま往復できる
    """
    out = bytearray()

    # コード単位ごとに1〜3バイトへ展開する
    for unit in _to_utf16_units(text):
        # U+0001..U+007Fだけが1バイト
        # U+0000は2バイトになる
        if 0x0001 <= unit <= 0x007F:
            out.append(unit)
        elif unit == 0x0000 or unit <= 0x07FF:
            # U+0000もこの経路でC0 80になる
            out.append(0xC0 | ((unit >> 6) & 0x1F))
            out.append(0x80 | (unit & 0x3F))
        else:
            out.append(0xE0 | ((unit >> 12) & 0x0F))
            out.append(0x80 | ((unit >> 6) & 0x3F))
            out.append(0x80 | (unit & 0x3F))

    return bytes(out)


def byte_length(text: str) -> int:
    """文字列をMUTF-8で符号化したときのバイト長を求める
    実際に符号化はしない
    """
    length = 0

    # 各コード単位が何バイトになるかを数える
    for unit in _to_utf16_units(text):
        # U+0001..U+007Fだけが1バイト
        # U+0000は2バイトになる
        if 0x0001 <= unit <= 0x007F:
            length += 1
        elif unit == 0x0000 or unit <= 0x07FF:
            length += 2
        else:
            length += 3

    return length

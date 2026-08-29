"""浮動小数点の正準10進表記。

各言語の標準の数値書式（C# の ``"R"``、Java の ``Float.toString``、
Python の ``repr``、Rust の ``{}``）は互いに一致しない。
指数表記へ切り替わる閾値も、指数部の桁数も、``E`` の大文字小文字も処理系ごとに違う。
そのままでは SNBT 出力の言語間一致が成立しないため、書式をここで固定する。

仕様: ``docs/spec/11-snbt.md`` 5.1章
"""

from __future__ import annotations

import math
import struct

__all__ = ["from_float", "from_double"]

#: 固定小数点表記を使う10進指数の下限。
_MIN_FIXED_EXPONENT = -4

#: 固定小数点表記を使う10進指数の上限。
_MAX_FIXED_EXPONENT = 16


def _special(value: float):
    """特殊値なら文字列を、そうでなければ None を返す。"""
    if math.isnan(value):
        return "NaN"

    if math.isinf(value):
        if value > 0:
            return "Infinity"

        return "-Infinity"

    return None


def from_float(value: float) -> str:
    """binary32 を正準10進表記へ変換する。"""
    special = _special(value)

    if special is not None:
        return special

    target = struct.pack(">f", value)

    # 有効数字を 1 桁ずつ増やし、読み戻してビット一致する最短の表記を探す
    for precision in range(1, 10):
        candidate = "%.*e" % (precision - 1, value)

        if struct.pack(">f", float(candidate)) == target:
            return _format(candidate)

    # 9 桁あれば binary32 は必ず往復するので、ここへは来ない
    return _format("%.8e" % value)


def from_double(value: float) -> str:
    """binary64 を正準10進表記へ変換する。"""
    special = _special(value)

    if special is not None:
        return special

    target = struct.pack(">d", value)

    # 有効数字を 1 桁ずつ増やし、読み戻してビット一致する最短の表記を探す
    for precision in range(1, 18):
        candidate = "%.*e" % (precision - 1, value)

        if struct.pack(">d", float(candidate)) == target:
            return _format(candidate)

    # 17 桁あれば binary64 は必ず往復するので、ここへは来ない
    return _format("%.16e" % value)


def _format(exponential: str) -> str:
    """指数表記の文字列（例 ``"7.5e-01"``）から、仕様が定める正準表記を組み立てる。"""
    negative = False
    index = 0

    if exponential[0] in "+-":
        negative = exponential[0] == "-"
        index = 1

    digits_chars = []

    # 仮数部の数字だけを集める
    while index < len(exponential) and exponential[index] not in "eE":
        character = exponential[index]

        if character.isdigit():
            digits_chars.append(character)

        index += 1

    exponent = int(exponential[index + 1:])
    digits = _trim_trailing_zeros("".join(digits_chars))

    return _compose(negative, digits, exponent)


def _trim_trailing_zeros(digits: str) -> str:
    """末尾のゼロを取り除く。すべてゼロなら "0" を残す。"""
    end = len(digits)

    # 末尾から連続するゼロを削る
    while end > 1 and digits[end - 1] == "0":
        end -= 1

    return digits[:end]


def _compose(negative: bool, digits: str, exponent: int) -> str:
    """数字列と10進指数から最終的な文字列を組み立てる。"""
    if negative:
        sign = "-"
    else:
        sign = ""

    # 値が 0 のときは指数に関わらず 0.0 と書く
    if digits == "0":
        return sign + "0.0"

    if exponent < _MIN_FIXED_EXPONENT or exponent > _MAX_FIXED_EXPONENT:
        # 指数表記
        if len(digits) > 1:
            fraction = digits[1:]
        else:
            fraction = "0"

        return "%s%s.%sE%d" % (sign, digits[0], fraction, exponent)

    if exponent >= 0:
        # 整数部は先頭 (exponent + 1) 桁。足りなければゼロで右詰めする
        integer_digits = exponent + 1

        if len(digits) >= integer_digits:
            integer_part = digits[:integer_digits]
        else:
            integer_part = digits + ("0" * (integer_digits - len(digits)))

        if len(digits) > integer_digits:
            fraction = digits[integer_digits:]
        else:
            fraction = "0"

        return "%s%s.%s" % (sign, integer_part, fraction)

    # 指数が負なら "0." に続けてゼロを詰めてから数字を置く
    return "%s0.%s%s" % (sign, "0" * ((-exponent) - 1), digits)

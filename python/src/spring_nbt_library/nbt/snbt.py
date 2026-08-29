"""SNBT (Stringified NBT) のパースと出力。

対応範囲は「バイナリ NBT へ損失なく写せる部分集合」。
1.21.5 以降の異種リスト（``[1, "a"]``）は受理しない。

仕様: ``docs/spec/11-snbt.md`` / ``docs/adr/0006-snbt-scope.md``
"""

from __future__ import annotations

import uuid as uuid_module
from typing import Optional

from ..errors import ErrorCode, SpringNbtError
from . import _recursion, canonical
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

__all__ = ["parse", "parse_compound", "write", "write_pretty"]

_INDENT_UNIT = "    "

_BARE_EXTRA = "_-.+"

_WIDTH_SUFFIXES = "bBsSlLfFdD"

_ESCAPES = {
    "\\": "\\",
    '"': '"',
    "'": "'",
    "b": "\b",
    "s": " ",
    "t": "\t",
    "n": "\n",
    "f": "\f",
    "r": "\r",
}


def is_bare_char(character: str) -> bool:
    """引用符なしで書ける文字か。"""
    if "a" <= character <= "z":
        return True

    if "A" <= character <= "Z":
        return True

    if "0" <= character <= "9":
        return True

    return character in _BARE_EXTRA


# ---------------------------------------------------------------------------
# パーサ
# ---------------------------------------------------------------------------


class _Parser:
    def __init__(self, text: str) -> None:
        self._text = text
        self._position = 0

    def parse_whole(self) -> NbtTag:
        """入力全体を 1 つのタグとして読む。末尾に余りがあればエラーにする。"""
        value = self._parse_value()
        self._skip_whitespace()

        # 値の後に余分な文字が残っていたら、書き手の意図と違う解釈をしている
        if self._position < len(self._text):
            raise self._malformed("値の後に余分な文字がある: '%s'" % self._text[self._position])

        return value

    def _parse_value(self) -> NbtTag:
        self._skip_whitespace()

        if self._position >= len(self._text):
            raise self._malformed("値が来るべき位置で入力が尽きた")

        character = self._text[self._position]

        if character == "{":
            return self._parse_compound()

        if character == "[":
            return self._parse_list_or_array()

        if character in "\"'":
            return NbtString(self._parse_quoted_string())

        return self._parse_unquoted()

    def _parse_compound(self) -> NbtCompound:
        self._expect("{")
        compound = NbtCompound()
        self._skip_whitespace()

        # 空の Compound
        if self._peek() == "}":
            self._position += 1
            return compound

        # 要素を 1 つずつ読む
        while True:
            self._skip_whitespace()

            # 末尾カンマの直後に閉じ括弧が来る形を許す
            if self._peek() == "}":
                self._position += 1
                return compound

            key = self._parse_key()
            self._skip_whitespace()
            self._expect(":")
            compound.set(key, self._parse_value())

            self._skip_whitespace()
            following = self._peek()

            if following == ",":
                self._position += 1
            elif following == "}":
                self._position += 1
                return compound
            else:
                raise self._malformed("Compound の区切りが不正: '%s'" % following)

    def _parse_list_or_array(self) -> NbtTag:
        self._expect("[")

        # "[B;" のような型付き配列かどうかを先に判定する
        if self._position + 1 < len(self._text) and self._text[self._position + 1] == ";":
            marker = self._text[self._position]

            if marker in "BIL":
                self._position += 2
                return self._parse_typed_array(marker)

        return self._parse_list()

    def _parse_list(self) -> NbtList:
        result = NbtList()
        self._skip_whitespace()

        # 空のリスト
        if self._peek() == "]":
            self._position += 1
            return result

        # 要素を 1 つずつ読む
        while True:
            self._skip_whitespace()

            # 末尾カンマの直後に閉じ括弧が来る形を許す
            if self._peek() == "]":
                self._position += 1
                return result

            value = self._parse_value()

            # 異種リストはバイナリ NBT へ写せないため受理しない (adr/0006)
            if result.element_type != TagType.END and result.element_type != value.type:
                raise self._malformed(
                    "リストに異なる型が混在している: %s と %s"
                    % (result.element_type.as_string(), value.type.as_string()))

            result.append(value)

            self._skip_whitespace()
            following = self._peek()

            if following == ",":
                self._position += 1
            elif following == "]":
                self._position += 1
                return result
            else:
                raise self._malformed("リストの区切りが不正: '%s'" % following)

    def _parse_typed_array(self, marker: str) -> NbtTag:
        values = []
        self._skip_whitespace()

        # 空でなければ要素を読む
        if self._peek() == "]":
            self._position += 1
        else:
            while True:
                self._skip_whitespace()

                # 末尾カンマの直後に閉じ括弧が来る形を許す
                if self._peek() == "]":
                    self._position += 1
                    break

                values.append(self._to_integral(self._parse_value()))

                self._skip_whitespace()
                following = self._peek()

                if following == ",":
                    self._position += 1
                elif following == "]":
                    self._position += 1
                    break
                else:
                    raise self._malformed("配列の区切りが不正: '%s'" % following)

        # 各要素が対象の幅に収まるか確認しながら詰める
        if marker == "B":
            self._check_elements(values, -128, 127, "ByteArray")
            return NbtByteArray(values)

        if marker == "I":
            self._check_elements(values, -2147483648, 2147483647, "IntArray")
            return NbtIntArray(values)

        self._check_elements(values, -9223372036854775808, 9223372036854775807, "LongArray")
        return NbtLongArray(values)

    def _check_elements(self, values, minimum: int, maximum: int, name: str) -> None:
        for value in values:
            if value < minimum or value > maximum:
                raise self._malformed("%s の要素が範囲外: %d" % (name, value))

    def _to_integral(self, tag: NbtTag) -> int:
        """整数タグから値を取り出す。整数以外なら例外。"""
        if isinstance(tag, (NbtByte, NbtShort, NbtInt, NbtLong)):
            return tag.value

        raise self._malformed("型付き配列の要素が整数でない: %s" % tag.type.as_string())

    def _parse_key(self) -> str:
        character = self._peek()

        if character in "\"'":
            return self._parse_quoted_string()

        bare = self._read_bare_token()

        if len(bare) == 0:
            raise self._malformed("Compound のキーが空")

        return bare

    def _parse_quoted_string(self) -> str:
        quote = self._text[self._position]
        self._position += 1
        parts = []

        # 閉じ引用符が来るまで読む
        while True:
            if self._position >= len(self._text):
                raise self._malformed("文字列が閉じられていない")

            character = self._text[self._position]

            if character == quote:
                self._position += 1
                return "".join(parts)

            if character == "\\":
                self._position += 1
                parts.append(self._read_escape())
            else:
                parts.append(character)
                self._position += 1

    def _read_escape(self) -> str:
        if self._position >= len(self._text):
            raise self._malformed("エスケープが途中で切れている")

        character = self._text[self._position]
        self._position += 1

        if character in _ESCAPES:
            return _ESCAPES[character]

        if character == "x":
            return chr(self._read_hex_digits(2))

        if character == "u":
            return chr(self._read_hex_digits(4))

        if character == "U":
            code_point = self._read_hex_digits(8)

            # Unicode のコードポイント範囲を外れていないか確認する
            if code_point > 0x10FFFF:
                raise self._malformed("コードポイントが範囲外: U+%X" % code_point)

            return chr(code_point)

        if character == "N":
            return self._read_named_character()

        raise self._malformed("未知のエスケープ: '\\%s'" % character)

    def _read_hex_digits(self, count: int) -> int:
        if self._position + count > len(self._text):
            raise self._malformed("エスケープの16進数字が足りない")

        chunk = self._text[self._position:self._position + count]

        # 16進数字以外が混じっていないか確認する
        for character in chunk:
            if _hex_digit_value(character) < 0:
                raise self._malformed("エスケープに16進数字でない文字がある: '%s'" % character)

        self._position += count
        return int(chunk, 16)

    def _read_named_character(self) -> str:
        """Unicode 文字名によるエスケープ ``\\N{...}`` を読む。"""
        self._expect("{")
        start = self._position

        # 閉じ波括弧まで名前を読む
        while self._position < len(self._text) and self._text[self._position] != "}":
            self._position += 1

        if self._position >= len(self._text):
            raise self._malformed("文字名エスケープが閉じられていない")

        name = self._text[start:self._position]
        self._position += 1

        # 実装間で Unicode 文字名の表が揃わないため対応しない（C# / Rust には表が無い）
        raise SpringNbtError(
            ErrorCode.UNSUPPORTED_FEATURE,
            "文字名によるエスケープには対応していない: \\N{%s}" % name)

    def _parse_unquoted(self) -> NbtTag:
        token = self._read_bare_token()

        if len(token) == 0:
            raise self._malformed("値が来るべき位置に解釈できない文字がある: '%s'" % self._peek_or_empty())

        # bool(...) / uuid(...) の関数呼び出し
        self._skip_whitespace()
        if self._peek_or_empty() == "(" and token in ("bool", "uuid"):
            return self._parse_function(token)

        if token == "true":
            return NbtByte(1)

        if token == "false":
            return NbtByte(0)

        number = self._try_parse_number(token)

        if number is not None:
            return number

        return NbtString(token)

    def _parse_function(self, name: str) -> NbtTag:
        self._expect("(")
        argument = self._parse_value()
        self._skip_whitespace()
        self._expect(")")

        if name == "bool":
            # 0 以外を真とする
            if self._to_integral(argument) != 0:
                return NbtByte(1)

            return NbtByte(0)

        return self._uuid_to_int_array(argument)

    def _uuid_to_int_array(self, argument: NbtTag) -> NbtIntArray:
        if not isinstance(argument, NbtString):
            raise self._malformed("uuid() の引数は文字列でなければならない")

        try:
            parsed = uuid_module.UUID(argument.value)
        except ValueError as error:
            raise self._malformed("UUID として解釈できない: %s" % argument.value) from error

        # UUID を上位から 32bit ずつ 4 要素の IntArray へ写す
        raw = parsed.bytes
        values = []

        for index in range(4):
            chunk = int.from_bytes(raw[index * 4:(index * 4) + 4], "big", signed=True)
            values.append(chunk)

        return NbtIntArray(values)

    def _try_parse_number(self, token: str) -> Optional[NbtTag]:
        """数値トークンを解釈する。数値として読めなければ None（文字列として扱われる）。"""
        negative = False
        start = 0

        if token[0] in "+-":
            negative = token[0] == "-"
            start = 1

        body = token[start:]

        if len(body) == 0:
            return None

        width_suffix = ""
        unsigned_suffix = False

        is_hex = _is_hex_body(body)

        # 幅接尾辞を末尾から剥がす。16進では b/d/f が数字と紛れるため s/l だけを認める
        last = body[-1]

        if is_hex:
            suffix_allowed = last in "sSlL"
        else:
            suffix_allowed = last in _WIDTH_SUFFIXES

        if suffix_allowed and len(body) >= 2:
            width_suffix = last.lower()
            body = body[:-1]

            # 符号接尾辞 u / s は幅接尾辞の手前に置かれる
            if len(body) >= 2:
                sign_char = body[-1]

                if sign_char in "uU":
                    unsigned_suffix = True
                    body = body[:-1]
                elif sign_char in "sS":
                    body = body[:-1]

        body = body.replace("_", "")

        if len(body) == 0:
            return None

        # 特殊な浮動小数点値
        if body == "Infinity":
            return self._make_floating(float("inf"), negative, width_suffix)

        if body == "NaN":
            return self._make_floating(float("nan"), negative, width_suffix)

        if _is_hex_body(body):
            return self._parse_radix(body[2:], 16, negative, width_suffix, unsigned_suffix)

        if _is_binary_body(body):
            return self._parse_radix(body[2:], 2, negative, width_suffix, unsigned_suffix)

        looks_floating = "." in body or "e" in body or "E" in body

        if looks_floating or width_suffix in ("f", "d"):
            try:
                parsed = float(body)
            except ValueError:
                return None

            return self._make_floating(parsed, negative, width_suffix)

        return self._parse_radix(body, 10, negative, width_suffix, unsigned_suffix)

    def _make_floating(self, value: float, negative: bool, width_suffix: str) -> NbtTag:
        if negative:
            signed = -value
        else:
            signed = value

        if width_suffix == "f":
            return NbtFloat(signed)

        # 接尾辞なしの小数は Double
        if width_suffix in ("", "d"):
            return NbtDouble(signed)

        raise self._malformed("小数に整数の接尾辞 '%s' は付けられない" % width_suffix)

    def _parse_radix(self, digits: str, radix: int, negative: bool,
                     width_suffix: str, unsigned_suffix: bool) -> Optional[NbtTag]:
        if len(digits) == 0:
            return None

        magnitude = 0

        # 桁を1つずつ積み上げる
        for character in digits:
            digit = _hex_digit_value(character)

            if digit < 0 or digit >= radix:
                return None

            magnitude = (magnitude * radix) + digit

        return self._make_integral(magnitude, negative, width_suffix, unsigned_suffix)

    def _make_integral(self, magnitude: int, negative: bool,
                       width_suffix: str, unsigned_suffix: bool) -> NbtTag:
        if unsigned_suffix:
            # 符号なし指定は、その幅の符号なし最大値までを受け付けて符号付きへ読み替える
            if width_suffix == "b":
                return NbtByte(_wrap_unsigned(self._check_unsigned(magnitude, 0xFF), 8))

            if width_suffix == "s":
                return NbtShort(_wrap_unsigned(self._check_unsigned(magnitude, 0xFFFF), 16))

            if width_suffix == "l":
                return NbtLong(_wrap_unsigned(
                    self._check_unsigned(magnitude, 0xFFFFFFFFFFFFFFFF), 64))

            return NbtInt(_wrap_unsigned(self._check_unsigned(magnitude, 0xFFFFFFFF), 32))

        if negative:
            value = -magnitude
        else:
            value = magnitude

        if value < -9223372036854775808 or value > 9223372036854775807:
            raise self._malformed("整数が 64bit に収まらない: %d" % value)

        if width_suffix == "b":
            return NbtByte(self._check_range(value, -128, 127, "byte"))

        if width_suffix == "s":
            return NbtShort(self._check_range(value, -32768, 32767, "short"))

        if width_suffix == "l":
            return NbtLong(value)

        if width_suffix == "f":
            return NbtFloat(float(value))

        if width_suffix == "d":
            return NbtDouble(float(value))

        # 接尾辞なしの整数は Int。暗黙に Long へ格上げしない
        return NbtInt(self._check_range(value, -2147483648, 2147483647, "int"))

    def _check_unsigned(self, magnitude: int, maximum: int) -> int:
        if magnitude > maximum:
            raise self._malformed("符号なし整数が範囲外: %d (上限 %d)" % (magnitude, maximum))

        return magnitude

    def _check_range(self, value: int, minimum: int, maximum: int, type_name: str) -> int:
        if value < minimum or value > maximum:
            raise self._malformed("%s の範囲外: %d" % (type_name, value))

        return value

    def _read_bare_token(self) -> str:
        start = self._position

        # 引用符なしトークンに使える文字を読み進める
        while self._position < len(self._text) and is_bare_char(self._text[self._position]):
            self._position += 1

        return self._text[start:self._position]

    def _skip_whitespace(self) -> None:
        # 空白・改行・タブを読み飛ばす
        while self._position < len(self._text) and self._text[self._position].isspace():
            self._position += 1

    def _peek(self) -> str:
        if self._position >= len(self._text):
            raise self._malformed("入力が途中で尽きた")

        return self._text[self._position]

    def _peek_or_empty(self) -> str:
        """末尾でも例外にしない先読み。入力が尽きていれば空文字列を返す。"""
        if self._position >= len(self._text):
            return ""

        return self._text[self._position]

    def _expect(self, expected: str) -> None:
        self._skip_whitespace()

        if self._position >= len(self._text):
            raise self._malformed("'%s' が来るべき位置で入力が尽きた" % expected)

        if self._text[self._position] != expected:
            raise self._malformed(
                "'%s' を期待したが '%s' だった" % (expected, self._text[self._position]))

        self._position += 1

    def _malformed(self, message: str) -> SpringNbtError:
        return SpringNbtError.malformed("SNBT (%d 文字目): %s" % (self._position, message))


def _is_hex_body(body: str) -> bool:
    return len(body) > 2 and body[0] == "0" and body[1] in "xX"


def _is_binary_body(body: str) -> bool:
    if not (len(body) > 2 and body[0] == "0" and body[1] in "bB"):
        return False

    # 2進リテラルの本体は 0 と 1 だけ
    for character in body[2:]:
        if character not in "01":
            return False

    return True


def _hex_digit_value(character: str) -> int:
    if "0" <= character <= "9":
        return ord(character) - ord("0")

    if "a" <= character <= "f":
        return ord(character) - ord("a") + 10

    if "A" <= character <= "F":
        return ord(character) - ord("A") + 10

    return -1


def _wrap_unsigned(magnitude: int, bits: int) -> int:
    """符号なしの値を、同じビットパターンの符号付きの値へ読み替える。"""
    limit = 1 << (bits - 1)

    if magnitude >= limit:
        return magnitude - (1 << bits)

    return magnitude


# ---------------------------------------------------------------------------
# ライタ
# ---------------------------------------------------------------------------


def parse(text: str) -> NbtTag:
    """SNBT 文字列をタグへ変換する。"""
    # Python は既定の再帰上限が仕様の深さ上限に届かないため、ここで引き上げる
    with _recursion.guard(_recursion.DEFAULT_MAX_DEPTH, "SNBT のネストが深すぎる"):
        return _Parser(text).parse_whole()


def parse_compound(text: str) -> NbtCompound:
    """SNBT 文字列を Compound へ変換する。"""
    tag = parse(text)

    if isinstance(tag, NbtCompound):
        return tag

    raise SpringNbtError.unexpected_tag_type("ルートが compound でない: %s" % tag.type.as_string())


def write(tag: NbtTag) -> str:
    """タグを 1 行の SNBT へ変換する。"""
    parts = []

    with _recursion.guard(_recursion.DEFAULT_MAX_DEPTH, "SNBT のネストが深すぎる"):
        _write_tag(parts, tag, -1)

    return "".join(parts)


def write_pretty(tag: NbtTag) -> str:
    """タグを整形した SNBT へ変換する。インデントは空白 4 個。"""
    parts = []

    with _recursion.guard(_recursion.DEFAULT_MAX_DEPTH, "SNBT のネストが深すぎる"):
        _write_tag(parts, tag, 0)

    return "".join(parts)


def _write_tag(parts, tag: NbtTag, depth: int) -> None:
    """タグを書き出す。``depth`` が負なら 1 行、0 以上なら整形して出力する。"""
    if isinstance(tag, NbtByte):
        parts.append("%db" % tag.value)
    elif isinstance(tag, NbtShort):
        parts.append("%ds" % tag.value)
    elif isinstance(tag, NbtInt):
        parts.append("%d" % tag.value)
    elif isinstance(tag, NbtLong):
        parts.append("%dL" % tag.value)
    elif isinstance(tag, NbtFloat):
        parts.append(canonical.from_float(tag.value) + "f")
    elif isinstance(tag, NbtDouble):
        parts.append(canonical.from_double(tag.value) + "d")
    elif isinstance(tag, NbtString):
        parts.append(_quote_string(tag.value))
    elif isinstance(tag, NbtByteArray):
        _write_typed_array(parts, "B", tag.value, "B")
    elif isinstance(tag, NbtIntArray):
        _write_typed_array(parts, "I", tag.value, "")
    elif isinstance(tag, NbtLongArray):
        _write_typed_array(parts, "L", tag.value, "L")
    elif isinstance(tag, NbtList):
        _write_list(parts, tag, depth)
    elif isinstance(tag, NbtCompound):
        _write_compound(parts, tag, depth)
    else:
        raise SpringNbtError.unexpected_tag_type("SNBT へ書けないタグ: %s" % tag.type.as_string())


def _write_compound(parts, compound: NbtCompound, depth: int) -> None:
    if len(compound) == 0:
        parts.append("{}")
        return

    parts.append("{")
    first = True

    # 挿入順のまま「キー: 値」を並べる
    for key, value in compound.items():
        if not first:
            parts.append(",")

        first = False
        _append_separator(parts, _next_depth(depth))
        parts.append(_quote_key(key))
        parts.append(":")

        # 整形時はコロンの後に空白を入れて読みやすくする
        if depth >= 0:
            parts.append(" ")

        _write_tag(parts, value, _next_depth(depth))

    _append_separator(parts, depth)
    parts.append("}")


def _write_list(parts, value: NbtList, depth: int) -> None:
    if len(value) == 0:
        parts.append("[]")
        return

    parts.append("[")
    first = True

    # 要素型は共通なので値だけを並べる
    for item in value:
        if not first:
            parts.append(",")

        first = False
        _append_separator(parts, _next_depth(depth))
        _write_tag(parts, item, _next_depth(depth))

    _append_separator(parts, depth)
    parts.append("]")


def _write_typed_array(parts, marker: str, values, element_suffix: str) -> None:
    parts.append("[%s;" % marker)

    # 型付き配列は 1 行に収める
    for index, value in enumerate(values):
        if index > 0:
            parts.append(",")

        parts.append("%d%s" % (value, element_suffix))

    parts.append("]")


def _append_separator(parts, depth: int) -> None:
    """整形出力なら改行とインデントを、1 行出力なら何も入れない。"""
    if depth < 0:
        return

    parts.append("\n")
    parts.append(_INDENT_UNIT * depth)


def _next_depth(depth: int) -> int:
    """整形出力のときだけ深さを 1 段進める。"""
    if depth < 0:
        return -1

    return depth + 1


def _quote_key(key: str) -> str:
    """キーを出力する。引用符なしで書ける場合はそのまま出す。"""
    if _is_bare_writable(key):
        return key

    return _quote_string(key)


def _is_bare_writable(text: str) -> bool:
    if len(text) == 0:
        return False

    # 引用符なしで書ける文字だけで構成されているか調べる
    for character in text:
        if not is_bare_char(character):
            return False

    return True


_QUOTE_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\f": "\\f",
    "\r": "\\r",
}


def _quote_string(text: str) -> str:
    """文字列を二重引用符で囲み、必要な文字だけエスケープする。"""
    parts = ['"']

    # 1 文字ずつ見てエスケープが要るものだけ置き換える
    for character in text:
        if character in _QUOTE_ESCAPES:
            parts.append(_QUOTE_ESCAPES[character])
            continue

        code = ord(character)

        # 制御文字とサロゲートは \uXXXX で表す
        if code < 0x20 or code == 0x7F or 0xD800 <= code <= 0xDFFF:
            parts.append("\\u%04x" % code)
        else:
            parts.append(character)

    parts.append('"')
    return "".join(parts)

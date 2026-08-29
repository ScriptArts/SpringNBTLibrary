"""NBT レイヤの単体テスト。

C# 版 (csharp/tests/SpringNBTLibrary.Tests/) と同じ検証項目を持つ。
共通テストベクタによる言語間比較は spec/run-conformance.sh が担当し、
ここでは API の振る舞いを直接確かめる。
"""

from __future__ import annotations

import struct

import pytest

from spring_nbt_library import ErrorCode, SpringNbtError
from spring_nbt_library.nbt import (
    Compression,
    NamedTag,
    NbtByte,
    NbtByteArray,
    NbtCompound,
    NbtDouble,
    NbtFloat,
    NbtFormat,
    NbtInt,
    NbtIntArray,
    NbtList,
    NbtLong,
    NbtLongArray,
    NbtReadOptions,
    NbtShort,
    NbtString,
    NbtWriteOptions,
    TagType,
    detect_compression,
    mutf8,
    read_bytes,
    snbt,
    write_bytes,
)


def uncompressed_read() -> NbtReadOptions:
    return NbtReadOptions(compression=Compression.NONE)


def uncompressed_write() -> NbtWriteOptions:
    return NbtWriteOptions(compression=Compression.NONE)


def hello_world_bytes() -> bytes:
    """仕様書どおりに組んだ最小の NBT。"""
    parts = []

    # ルート: TAG_Compound、名前 "hello world"
    parts.append(bytes([0x0A]))
    parts.append(bytes([0x00, 0x0B]))
    parts.append(b"hello world")

    # 子: TAG_String、名前 "name"、値 "Bananrama"
    parts.append(bytes([0x08]))
    parts.append(bytes([0x00, 0x04]))
    parts.append(b"name")
    parts.append(bytes([0x00, 0x09]))
    parts.append(b"Bananrama")

    # ルートの終端
    parts.append(bytes([0x00]))

    return b"".join(parts)


# ---------------------------------------------------------------------------
# MUTF-8
# ---------------------------------------------------------------------------


class TestMutf8:
    def test_ascii_roundtrip(self):
        assert mutf8.encode("Bananrama") == b"Bananrama"
        assert mutf8.decode(b"Bananrama") == "Bananrama"

    def test_nul_is_two_bytes(self):
        sample = "a\u0000b"
        assert mutf8.encode(sample) == bytes([0x61, 0xC0, 0x80, 0x62])
        assert mutf8.decode(bytes([0x61, 0xC0, 0x80, 0x62])) == sample

    def test_supplementary_char_is_cesu8(self):
        sample = "\U0001F600"
        assert mutf8.encode(sample) == bytes([0xED, 0xA0, 0xBD, 0xED, 0xB8, 0x80])
        assert mutf8.decode(bytes([0xED, 0xA0, 0xBD, 0xED, 0xB8, 0x80])) == sample

    def test_lone_surrogate_survives_roundtrip(self):
        lone = "\ud83d"
        assert mutf8.encode(lone) == bytes([0xED, 0xA0, 0xBD])
        assert mutf8.decode(bytes([0xED, 0xA0, 0xBD])) == lone

    @pytest.mark.parametrize("data", [
        bytes([0x00]),
        bytes([0xC1, 0x81]),
        bytes([0xF0, 0x9F, 0x98, 0x80]),
        bytes([0xE3, 0x81]),
    ])
    def test_invalid_input_is_rejected(self, data):
        with pytest.raises(SpringNbtError) as info:
            mutf8.decode(data)

        assert info.value.code == ErrorCode.MALFORMED_DATA

    def test_byte_length_matches_encoded_length(self):
        sample = "abcあ\U0001F600"
        assert mutf8.byte_length(sample) == len(mutf8.encode(sample))


# ---------------------------------------------------------------------------
# バイナリ読み書き
# ---------------------------------------------------------------------------


class TestNbtIo:
    def test_reads_hand_built_hello_world(self):
        named = read_bytes(hello_world_bytes(), uncompressed_read())

        assert named.name == "hello world"
        assert len(named.tag) == 1
        assert named.tag.get_string("name") == "Bananrama"

    def test_writes_back_the_same_bytes(self):
        original = hello_world_bytes()
        named = read_bytes(original, uncompressed_read())

        assert write_bytes(named, uncompressed_write()) == original

    def test_all_tag_types_roundtrip(self):
        root = build_all_tags()
        encoded = write_bytes(NamedTag("", root), uncompressed_write())
        decoded = read_bytes(encoded, uncompressed_read())

        assert decoded.tag == root
        assert write_bytes(decoded, uncompressed_write()) == encoded

    def test_float_specials_keep_their_bit_pattern(self):
        root = NbtCompound()
        root.set("negative_zero", NbtDouble(-0.0))
        root.set("nan", NbtFloat(float("nan")))
        root.set("infinity", NbtDouble(float("inf")))

        encoded = write_bytes(NamedTag("", root), uncompressed_write())
        decoded = read_bytes(encoded, uncompressed_read()).tag

        # -0.0 と +0.0 は == では区別できないので、ビットパターンで比較する
        assert struct.pack(">d", decoded.get_double("negative_zero")) == struct.pack(">d", -0.0)
        assert decoded.get_float("nan") != decoded.get_float("nan")
        assert decoded.get_double("infinity") == float("inf")

    def test_compound_keeps_insertion_order(self):
        root = NbtCompound()
        root.set("zebra", NbtInt(1))
        root.set("apple", NbtInt(2))
        root.set("mango", NbtInt(3))

        # 既存キーへの再設定は位置を変えない
        root.set("zebra", NbtInt(9))

        assert list(root.keys()) == ["zebra", "apple", "mango"]

        encoded = write_bytes(NamedTag("", root), uncompressed_write())
        decoded = read_bytes(encoded, uncompressed_read()).tag

        assert list(decoded.keys()) == ["zebra", "apple", "mango"]

    def test_empty_list_keeps_element_type_end(self):
        root = NbtCompound()
        root.set("empty", NbtList())

        encoded = write_bytes(NamedTag("", root), uncompressed_write())
        decoded = read_bytes(encoded, uncompressed_read()).tag

        assert decoded.get_list("empty").element_type == TagType.END

    def test_list_rejects_mixed_types(self):
        values = NbtList()
        values.append(NbtInt(1))

        with pytest.raises(SpringNbtError) as info:
            values.append(NbtString("x"))

        assert info.value.code == ErrorCode.UNEXPECTED_TAG_TYPE

    def test_typed_getter_distinguishes_missing_key_from_wrong_type(self):
        root = NbtCompound()
        root.set("value", NbtString("text"))

        # キーが無い場合は None
        assert root.opt_int("missing") is None

        # 型が違う場合はキーの有無に関わらず例外
        with pytest.raises(SpringNbtError) as wrong_type:
            root.opt_int("value")
        assert wrong_type.value.code == ErrorCode.UNEXPECTED_TAG_TYPE

        with pytest.raises(SpringNbtError) as missing:
            root.get_int("missing")
        assert missing.value.code == ErrorCode.INVALID_ARGUMENT

    @pytest.mark.parametrize("method", [Compression.GZIP, Compression.ZLIB, Compression.NONE])
    def test_compression_is_detected_automatically(self, method):
        named = read_bytes(hello_world_bytes(), uncompressed_read())
        encoded = write_bytes(named, NbtWriteOptions(compression=method))

        assert detect_compression(encoded) == method

        # 既定の ReadOptions は AUTO なので、方式を指定しなくても読める
        assert read_bytes(encoded).tag.get_string("name") == "Bananrama"

    def test_network_format_has_no_root_name(self):
        root = NbtCompound()
        root.set("x", NbtInt(1))

        encoded = write_bytes(
            NamedTag("ignored", root),
            NbtWriteOptions(fmt=NbtFormat.NETWORK, compression=Compression.NONE))

        # タグID + ペイロード のみで、名前長の 2 バイトが無い
        assert encoded[0] == 0x0A
        assert encoded[1] == 0x03

        decoded = read_bytes(
            encoded, NbtReadOptions(fmt=NbtFormat.NETWORK, compression=Compression.NONE))

        assert decoded.name == ""
        assert decoded.tag.get_int("x") == 1

    def test_truncated_input_is_rejected(self):
        with pytest.raises(SpringNbtError) as info:
            read_bytes(hello_world_bytes()[:-3], uncompressed_read())

        assert info.value.code == ErrorCode.MALFORMED_DATA

    def test_huge_declared_length_is_rejected_before_allocating(self):
        # ルート直下に「長さ 0x7FFFFFFF の ByteArray」を宣言するだけの入力
        data = (bytes([0x0A]) + bytes([0x00, 0x00])
                + bytes([0x07]) + bytes([0x00, 0x01]) + b"a"
                + bytes([0x7F, 0xFF, 0xFF, 0xFF]))

        with pytest.raises(SpringNbtError) as info:
            read_bytes(data, uncompressed_read())

        assert info.value.code == ErrorCode.MALFORMED_DATA

    def test_unknown_tag_id_is_rejected(self):
        data = bytes([0x0A]) + bytes([0x00, 0x00]) + bytes([0x0D])

        with pytest.raises(SpringNbtError) as info:
            read_bytes(data, uncompressed_read())

        assert info.value.code == ErrorCode.MALFORMED_DATA

    def test_excessive_nesting_is_rejected(self):
        encoded = build_nested_compound(600)

        with pytest.raises(SpringNbtError) as info:
            read_bytes(encoded, uncompressed_read())
        assert info.value.code == ErrorCode.LIMIT_EXCEEDED

        # 上限を上げれば読める
        read_bytes(encoded, NbtReadOptions(compression=Compression.NONE, max_depth=1000))

    def test_trailing_bytes_after_root_are_rejected(self):
        with pytest.raises(SpringNbtError) as info:
            read_bytes(hello_world_bytes() + bytes([0xFF]), uncompressed_read())

        assert info.value.code == ErrorCode.MALFORMED_DATA

    def test_write_rejects_auto_compression(self):
        named = NamedTag("", NbtCompound())

        with pytest.raises(SpringNbtError) as info:
            write_bytes(named, NbtWriteOptions(compression=Compression.AUTO))

        assert info.value.code == ErrorCode.INVALID_ARGUMENT

    @pytest.mark.parametrize("factory,value", [
        (NbtByte, 128),
        (NbtByte, -129),
        (NbtShort, 32768),
        (NbtInt, 2147483648),
        (NbtLong, 9223372036854775808),
    ])
    def test_integer_range_is_checked_on_construction(self, factory, value):
        # Python の int には幅が無いため、構築時に範囲を検査する
        with pytest.raises(SpringNbtError) as info:
            factory(value)

        assert info.value.code == ErrorCode.INVALID_ARGUMENT

    def test_float_is_rounded_to_binary32_on_construction(self):
        # 他言語と同じ値になるよう、構築時に binary32 へ丸める
        value = NbtFloat(0.1).value
        assert struct.pack(">f", value) == struct.pack(">f", 0.1)
        assert value != 0.1


def build_all_tags() -> NbtCompound:
    """全13タグ型を含む Compound を作る。"""
    root = NbtCompound()
    root.set("byte", NbtByte(-128))
    root.set("short", NbtShort(32767))
    root.set("int", NbtInt(-2147483648))
    root.set("long", NbtLong(9223372036854775807))
    root.set("float", NbtFloat(0.49823147))
    root.set("double", NbtDouble(0.4931287132182315))
    root.set("byte_array", NbtByteArray([-128, 0, 127]))
    root.set("string", NbtString("あいう"))
    root.set("int_array", NbtIntArray([-2147483648, 0, 2147483647]))
    root.set("long_array", NbtLongArray([-9223372036854775808, 0, 9223372036854775807]))

    values = NbtList(TagType.LONG)
    values.append(NbtLong(11))
    values.append(NbtLong(12))
    root.set("list", values)

    nested = NbtCompound()
    nested.set("name", NbtString("Hampus"))
    nested.set("value", NbtFloat(0.75))
    root.set("compound", nested)

    return root


def build_nested_compound(depth: int) -> bytes:
    """指定した深さまで Compound を入れ子にしたバイト列を作る。"""
    parts = [bytes([0x0A]), bytes([0x00, 0x00])]

    # ルート + (depth - 1) 段の入れ子
    for _ in range(depth - 1):
        parts.append(bytes([0x0A]))
        parts.append(bytes([0x00, 0x01]))
        parts.append(b"c")

    # 内側から順に終端する
    for _ in range(depth):
        parts.append(bytes([0x00]))

    return b"".join(parts)


# ---------------------------------------------------------------------------
# SNBT
# ---------------------------------------------------------------------------


class TestSnbt:
    @pytest.mark.parametrize("source,expected", [
        ("1b", TagType.BYTE),
        ("1s", TagType.SHORT),
        ("1", TagType.INT),
        ("1L", TagType.LONG),
        ("1.0f", TagType.FLOAT),
        ("1.0", TagType.DOUBLE),
        ("1.0d", TagType.DOUBLE),
        ("true", TagType.BYTE),
        ("false", TagType.BYTE),
        ("hello", TagType.STRING),
        ('"hello"', TagType.STRING),
    ])
    def test_suffix_decides_type(self, source, expected):
        assert snbt.parse(source).type == expected

    @pytest.mark.parametrize("source,expected", [
        ("0x10", 16),
        ("0b1001", 9),
        ("123_456", 123456),
        ("+7", 7),
        ("-7", -7),
    ])
    def test_extended_integer_literals(self, source, expected):
        assert snbt.parse(source) == NbtInt(expected)

    def test_hex_suffix_rule_is_fixed(self):
        # 仕様 11 の 2.1: 16進では b/d/f を数字として読む。幅接尾辞は s/l のみ
        assert snbt.parse("0xFF") == NbtInt(255)
        assert snbt.parse("0xFFb") == NbtInt(4091)
        assert snbt.parse("0xFFl") == NbtLong(255)
        assert snbt.parse("0xFFs") == NbtShort(255)

    def test_zero_byte_literal_is_not_binary(self):
        # 0b は「10進の 0 に Byte 接尾辞」。真偽値の false として広く使われる形
        assert snbt.parse("0b") == NbtByte(0)
        assert snbt.parse("0b1") == NbtInt(1)
        assert snbt.parse("0b1001b") == NbtByte(9)

    def test_unsigned_suffix_wraps_to_signed(self):
        assert snbt.parse("255ub") == NbtByte(-1)
        assert snbt.parse("65535us") == NbtShort(-1)

    def test_unsigned_overflow_is_rejected(self):
        with pytest.raises(SpringNbtError) as info:
            snbt.parse("256ub")

        assert info.value.code == ErrorCode.MALFORMED_DATA

    def test_suffixless_integer_is_not_promoted_to_long(self):
        with pytest.raises(SpringNbtError) as info:
            snbt.parse("2147483648")
        assert info.value.code == ErrorCode.MALFORMED_DATA

        assert snbt.parse("2147483648L") == NbtLong(2147483648)

    def test_typed_arrays(self):
        assert snbt.parse("[B; 1b, 2b]") == NbtByteArray([1, 2])
        assert snbt.parse("[I; 1, 2]") == NbtIntArray([1, 2])
        assert snbt.parse("[L; 1L, 2L]") == NbtLongArray([1, 2])

        # 接尾辞なしでも範囲内なら受理する（Minecraft 自身がそう書き出すため）
        assert snbt.parse("[B; 1, 2]") == NbtByteArray([1, 2])

    def test_typed_array_range_is_checked(self):
        with pytest.raises(SpringNbtError) as info:
            snbt.parse("[B; 200]")

        assert info.value.code == ErrorCode.MALFORMED_DATA

    def test_trailing_commas_are_allowed(self):
        assert len(snbt.parse_compound("{a:1,b:2,}")) == 2
        assert len(snbt.parse("[1,2,]")) == 2

    def test_heterogeneous_list_is_rejected(self):
        # 異種リストはバイナリ NBT へ写せないため受理しない (adr/0006)
        with pytest.raises(SpringNbtError) as info:
            snbt.parse('[1, "a"]')

        assert info.value.code == ErrorCode.MALFORMED_DATA

    def test_escape_sequences(self):
        assert snbt.parse('"\\n"') == NbtString("\n")
        assert snbt.parse('"\\x42"') == NbtString("B")
        assert snbt.parse('"\\u0048"') == NbtString("H")
        assert snbt.parse('"\\s"') == NbtString(" ")
        assert snbt.parse('"\\U0001F600"') == NbtString("\U0001F600")

    def test_named_character_escape_is_unsupported(self):
        with pytest.raises(SpringNbtError) as info:
            snbt.parse('"\\N{SNOWMAN}"')

        assert info.value.code == ErrorCode.UNSUPPORTED_FEATURE

    def test_single_quoted_strings_work(self):
        assert snbt.parse("'say \"hi\"'") == NbtString('say "hi"')

    def test_bool_function(self):
        assert snbt.parse("bool(5)") == NbtByte(1)
        assert snbt.parse("bool(0)") == NbtByte(0)

    def test_uuid_function(self):
        parsed = snbt.parse('uuid("00112233-4455-6677-8899-aabbccddeeff")')
        assert parsed == NbtIntArray([0x00112233, 0x44556677, -0x77665545, -0x33221101])

    def test_snbt_to_nbt_to_snbt_to_nbt_is_stable(self):
        source = ("{ name : 'Bananrama' , list : [ 1L , 2L ] , nested : { flag : true } , "
                  "bytes : [B; 1b, -2b] , ratio : 0.5f }")

        first = snbt.parse(source)
        assert snbt.parse(snbt.write(first)) == first
        assert snbt.parse(snbt.write_pretty(first)) == first

    def test_write_uses_bare_keys_when_possible(self):
        compound = NbtCompound()
        compound.set("plain", NbtInt(1))
        compound.set("needs quote", NbtInt(2))

        assert snbt.write(compound) == '{plain:1,"needs quote":2}'

    def test_write_pretty_indents_with_four_spaces(self):
        nested = NbtCompound()
        nested.set("x", NbtInt(1))
        compound = NbtCompound()
        compound.set("inner", nested)

        assert snbt.write_pretty(compound) == "{\n    inner: {\n        x: 1\n    }\n}"

    def test_trailing_garbage_is_rejected(self):
        with pytest.raises(SpringNbtError) as info:
            snbt.parse("{a:1} junk")

        assert info.value.code == ErrorCode.MALFORMED_DATA

    def test_parse_compound_rejects_non_compound_root(self):
        with pytest.raises(SpringNbtError) as info:
            snbt.parse_compound("42")

        assert info.value.code == ErrorCode.UNEXPECTED_TAG_TYPE


# ---------------------------------------------------------------------------
# 浮動小数点の正準10進表記
# ---------------------------------------------------------------------------


class TestCanonicalDecimal:
    """仕様: docs/spec/11-snbt.md 5.1章

    ここが言語ごとにずれると SNBT 出力の言語間一致が崩れるため、
    期待値は仕様の記述から手で書き下している。
    """

    @pytest.mark.parametrize("value,expected", [
        (1.0, "1.0f"),
        (-1.0, "-1.0f"),
        (0.0, "0.0f"),
        (0.75, "0.75f"),
        (0.49823147, "0.49823147f"),
        (2000.0, "2000.0f"),
        (1e20, "1.0E20f"),
        (1e-30, "1.0E-30f"),
        (0.5, "0.5f"),
        (123.456, "123.456f"),
    ])
    def test_float_formatting(self, value, expected):
        assert snbt.write(NbtFloat(value)) == expected

    @pytest.mark.parametrize("value,expected", [
        (1.0, "1.0d"),
        (0.015, "0.015d"),
        (2000.0, "2000.0d"),
        (0.4931287132182315, "0.4931287132182315d"),
        (3.141592653589793, "3.141592653589793d"),
        (1e20, "1.0E20d"),
        (1e17, "1.0E17d"),
        (1e16, "10000000000000000.0d"),
        (1e-4, "0.0001d"),
        (1e-5, "1.0E-5d"),
    ])
    def test_double_formatting(self, value, expected):
        assert snbt.write(NbtDouble(value)) == expected

    def test_negative_zero_keeps_its_sign(self):
        assert snbt.write(NbtDouble(-0.0)) == "-0.0d"
        assert snbt.write(NbtFloat(-0.0)) == "-0.0f"

    def test_special_values(self):
        assert snbt.write(NbtDouble(float("nan"))) == "NaNd"
        assert snbt.write(NbtDouble(float("inf"))) == "Infinityd"
        assert snbt.write(NbtDouble(float("-inf"))) == "-Infinityd"
        assert snbt.write(NbtFloat(float("nan"))) == "NaNf"

    def test_every_formatted_value_parses_back_to_the_same_bits(self):
        doubles = [0.0, -0.0, 1.0, -1.0, 0.1, 1.0 / 3.0, 1e300, 1e-300, 4903.0]

        # 出力した文字列を読み戻して、ビットパターンが変わらないことを確かめる
        for value in doubles:
            parsed = snbt.parse(snbt.write(NbtDouble(value)))
            assert struct.pack(">d", parsed.value) == struct.pack(">d", value)

        floats = [0.0, -0.0, 1.0, -1.0, 0.1, 1.0 / 3.0, 1e30, 1e-30, 4903.0]

        for value in floats:
            source = NbtFloat(value)
            parsed = snbt.parse(snbt.write(source))
            assert struct.pack(">f", parsed.value) == struct.pack(">f", source.value)

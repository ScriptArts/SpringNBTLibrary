#!/usr/bin/env python3
"""共通テストベクタを生成する。

仕様: docs/spec/90-conformance.md 4章

重要な設計方針:
    このスクリプトは **ライブラリ本体を一切使わない**。
    仕様書の記述だけを根拠に、独立した最小の NBT ライタを内蔵してバイト列を組み立てる。
    ライブラリでベクタを作ると、ライブラリのバグをそのまま期待値にしてしまうため。

使い方:
    python3 spec/tools/build_testdata.py
"""

from __future__ import annotations

import gzip
import json
import os
import struct
import zlib

# ---------------------------------------------------------------------------
# 独立した最小の NBT ライタ（仕様書の記述だけを根拠に実装する）
# ---------------------------------------------------------------------------

TAG_END = 0
TAG_BYTE = 1
TAG_SHORT = 2
TAG_INT = 3
TAG_LONG = 4
TAG_FLOAT = 5
TAG_DOUBLE = 6
TAG_BYTE_ARRAY = 7
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10
TAG_INT_ARRAY = 11
TAG_LONG_ARRAY = 12


def mutf8_encode(text: str) -> bytes:
    """文字列を MUTF-8 へ符号化する。

    標準 UTF-8 との違いは U+0000 が C0 80 になることと、
    補助文字がサロゲートペアへ分解されて 3 バイト × 2 になること。
    """
    out = bytearray()

    # Python の str はコードポイント単位なので、まず UTF-16 コード単位へ落とす
    units = []
    for ch in text:
        code = ord(ch)
        if code >= 0x10000:
            # 補助文字はサロゲートペアへ分解する
            code -= 0x10000
            units.append(0xD800 + (code >> 10))
            units.append(0xDC00 + (code & 0x3FF))
        else:
            units.append(code)

    # コード単位ごとに 1〜3 バイトへ展開する
    for unit in units:
        if 0x0001 <= unit <= 0x007F:
            out.append(unit)
        elif unit == 0x0000 or unit <= 0x07FF:
            out.append(0xC0 | ((unit >> 6) & 0x1F))
            out.append(0x80 | (unit & 0x3F))
        else:
            out.append(0xE0 | ((unit >> 12) & 0x0F))
            out.append(0x80 | ((unit >> 6) & 0x3F))
            out.append(0x80 | (unit & 0x3F))

    return bytes(out)


def write_string(text: str) -> bytes:
    """u16 のバイト長を前置した MUTF-8 文字列。"""
    encoded = mutf8_encode(text)
    if len(encoded) > 65535:
        raise ValueError("文字列が長すぎる: %d バイト" % len(encoded))
    return struct.pack(">H", len(encoded)) + encoded


class Tag:
    """タグID とペイロードの組。"""

    def __init__(self, tag_id: int, payload: bytes) -> None:
        self.tag_id = tag_id
        self.payload = payload


def t_byte(value: int) -> Tag:
    return Tag(TAG_BYTE, struct.pack(">b", value))


def t_short(value: int) -> Tag:
    return Tag(TAG_SHORT, struct.pack(">h", value))


def t_int(value: int) -> Tag:
    return Tag(TAG_INT, struct.pack(">i", value))


def t_long(value: int) -> Tag:
    return Tag(TAG_LONG, struct.pack(">q", value))


def t_float(value: float) -> Tag:
    return Tag(TAG_FLOAT, struct.pack(">f", value))


def t_float_bits(bits: int) -> Tag:
    """ビットパターンを直接指定する。NaN の表現を固定したい場合に使う。"""
    return Tag(TAG_FLOAT, struct.pack(">I", bits))


def t_double(value: float) -> Tag:
    return Tag(TAG_DOUBLE, struct.pack(">d", value))


def t_double_bits(bits: int) -> Tag:
    return Tag(TAG_DOUBLE, struct.pack(">Q", bits))


def t_byte_array(values: list) -> Tag:
    payload = struct.pack(">i", len(values))
    for value in values:
        payload += struct.pack(">b", value)
    return Tag(TAG_BYTE_ARRAY, payload)


def t_string(text: str) -> Tag:
    return Tag(TAG_STRING, write_string(text))


def t_string_raw(raw: bytes) -> Tag:
    """MUTF-8 のバイト列を直接指定する。孤立サロゲートを書くために使う。"""
    return Tag(TAG_STRING, struct.pack(">H", len(raw)) + raw)


def t_list(element_id: int, elements: list) -> Tag:
    payload = struct.pack(">Bi", element_id, len(elements))
    for element in elements:
        payload += element.payload
    return Tag(TAG_LIST, payload)


def t_compound(entries: list) -> Tag:
    """entries は (名前, Tag) の並び。挿入順がそのまま出力順になる。"""
    payload = b""
    for name, tag in entries:
        payload += struct.pack(">B", tag.tag_id)
        payload += write_string(name)
        payload += tag.payload
    payload += struct.pack(">B", TAG_END)
    return Tag(TAG_COMPOUND, payload)


def t_int_array(values: list) -> Tag:
    payload = struct.pack(">i", len(values))
    for value in values:
        payload += struct.pack(">i", value)
    return Tag(TAG_INT_ARRAY, payload)


def t_long_array(values: list) -> Tag:
    payload = struct.pack(">i", len(values))
    for value in values:
        payload += struct.pack(">q", value)
    return Tag(TAG_LONG_ARRAY, payload)


def to_java_file(name: str, root: Tag) -> bytes:
    """ファイル形式（名前付きルート）のバイト列にする。"""
    return struct.pack(">B", root.tag_id) + write_string(name) + root.payload


def to_network(root: Tag) -> bytes:
    """ネットワーク形式（無名ルート、1.20.2+）のバイト列にする。"""
    return struct.pack(">B", root.tag_id) + root.payload


# ---------------------------------------------------------------------------
# ベクタ定義
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TESTDATA = os.path.join(REPO_ROOT, "spec", "testdata")

VECTORS = []


def write_if_changed(path, data):
    """内容が変わるときだけ書き出す。

    Gzip / Zlib の出力バイト列は zlib の実装とバージョンで変わる。
    毎回書き出すと、同じ内容なのに環境ごとに差分が出てしまい、
    「テストベクタが生成器から再現できる」ことを CI で確かめられなくなる。

    そこで**展開後の中身が同じなら書き換えない**。
    圧縮方式そのものを変えたときはバイト列も中身も変わるので、ちゃんと更新される。
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)

    if os.path.exists(path):
        with open(path, "rb") as handle:
            existing = handle.read()

        # 中身が同じなら触らない
        if existing == data:
            return

        if same_after_decompression(existing, data):
            return

    with open(path, "wb") as handle:
        handle.write(data)


def same_after_decompression(existing, data):
    """2 つのバイト列が、展開すると同じ内容になるか。

    どちらかが展開できない形式なら「違う」とみなす。
    """
    try:
        return decompress_for_compare(existing) == decompress_for_compare(data)
    except Exception:
        # 展開できない以上、同じとは言い切れない
        return False


def decompress_for_compare(data):
    """先頭バイトから方式を判定して展開する。判定できなければそのまま返す。"""
    if len(data) >= 2 and data[0] == 0x1F and data[1] == 0x8B:
        return gzip.decompress(data)

    if len(data) >= 2 and (data[0] & 0x0F) == 0x08 and (((data[0] << 8) | data[1]) % 31) == 0:
        return zlib.decompress(data)

    # リージョンファイルは中に複数のチャンクを抱えるので、構造を解いて比べる
    if looks_like_region(data):
        return region_contents(data)

    return data


def looks_like_region(data):
    """リージョンファイルらしい形をしているか。"""
    return len(data) >= 2 * SECTOR and len(data) % SECTOR == 0


def region_contents(data):
    """リージョンファイルを、圧縮に依存しない「論理的な中身」へ均す。

    位置表・タイムスタンプ表と、各チャンクの (圧縮方式ID, 展開後のバイト列) を並べる。
    圧縮結果そのものは zlib の実装で変わるため、比較には使わない。
    """
    parts = [data[:2 * SECTOR]]

    # 位置表の 1024 エントリを順に見て、存在するチャンクを取り出す
    for index in range(1024):
        offset, sectors = struct.unpack_from(">I", data, index * 4)[0] >> 8, data[index * 4 + 3]

        if offset == 0 or sectors == 0:
            continue

        start = offset * SECTOR

        if start + 5 > len(data):
            raise ValueError("位置表がファイルの外を指している")

        length = struct.unpack_from(">i", data, start)[0]
        scheme = data[start + 4]
        payload = data[start + 5:start + 4 + length]

        # 外部ファイルへ退避されている場合、本体はここに無い
        if (scheme & 0x80) != 0:
            parts.append(bytes([index & 0xFF, scheme]))
            continue

        if scheme == 1:
            plain = gzip.decompress(payload)
        elif scheme == 2:
            plain = zlib.decompress(payload)
        else:
            plain = payload

        parts.append(bytes([index & 0xFF, scheme]) + plain)

    return b"\x00".join(parts)


def add_vector(vector_id, filename, data, description,
               fmt="java", compression="none", roundtrip=True, expect_error=None):
    """ベクタを 1 件登録し、ファイルへ書き出す。"""
    write_if_changed(os.path.join(TESTDATA, filename), data)

    entry = {
        "id": vector_id,
        "kind": vector_id.split("/")[0],
        "input": filename,
        "format": fmt,
        "compression": compression,
        "description": description,
    }

    if expect_error is None:
        entry["expect"] = "expect/%s.json" % vector_id
        entry["roundtrip"] = roundtrip
    else:
        # 読み込みが失敗すること自体が期待値になるベクタ
        entry["expect_error"] = expect_error
        entry["roundtrip"] = False

    VECTORS.append(entry)


def hello_world_tag():
    """最小の NBT。ルート名 "hello world" の Compound に文字列がひとつ。"""
    return t_compound([("name", t_string("Bananrama"))])


def all_tags_tag():
    """全13タグを1つずつ含む Compound。"""
    return t_compound([
        ("byte", t_byte(-128)),
        ("short", t_short(32767)),
        ("int", t_int(-2147483648)),
        ("long", t_long(9223372036854775807)),
        ("float", t_float(0.49823147)),
        ("double", t_double(0.4931287132182315)),
        ("byte_array", t_byte_array([-128, 0, 127])),
        ("string", t_string("Bananrama")),
        ("list", t_list(TAG_LONG, [t_long(11), t_long(12), t_long(13)])),
        ("compound", t_compound([
            ("name", t_string("Hampus")),
            ("value", t_float(0.75)),
        ])),
        ("int_array", t_int_array([-2147483648, 0, 2147483647])),
        ("long_array", t_long_array([-9223372036854775808, 0, 9223372036854775807])),
    ])


def nested_compound(depth: int) -> Tag:
    """指定した深さまで Compound を入れ子にする。ルートを含めた段数を depth とする。"""
    tag = t_compound([])

    # 内側から外側へ包んでいく
    for _ in range(depth - 1):
        tag = t_compound([("c", tag)])

    return tag


def build_all():
    """全ベクタを組み立てて書き出す。"""
    hello = hello_world_tag()
    add_vector(
        "nbt/hello_world", "nbt/hello_world.nbt",
        to_java_file("hello world", hello),
        "最小の Compound。ルート名が空でない例でもある")

    all_tags = all_tags_tag()
    add_vector(
        "nbt/all_tags", "nbt/all_tags.nbt",
        to_java_file("", all_tags),
        "全13タグを1つずつ含む")

    add_vector(
        "nbt/nested_deep", "nbt/nested_deep.nbt",
        to_java_file("", nested_compound(500)),
        "ネスト深さ 500。既定の上限 512 の直下")

    add_vector(
        "nbt/nested_too_deep", "nbt/nested_too_deep.nbt",
        to_java_file("", nested_compound(600)),
        "ネスト深さ 600。既定の上限 512 を超える",
        expect_error="LIMIT_EXCEEDED")

    add_vector(
        "nbt/empty_list", "nbt/empty_list.nbt",
        to_java_file("", t_compound([("empty", t_list(TAG_END, []))])),
        "空リスト（要素型 End）")

    add_vector(
        "nbt/empty_list_typed", "nbt/empty_list_typed.nbt",
        to_java_file("", t_compound([("empty", t_list(TAG_BYTE, []))])),
        "空リストだが要素型が Byte。第三者ツールが書いた形を壊さず往復できること")

    add_vector(
        "nbt/numeric_bounds", "nbt/numeric_bounds.nbt",
        to_java_file("", t_compound([
            ("byte_min", t_byte(-128)),
            ("byte_max", t_byte(127)),
            ("short_min", t_short(-32768)),
            ("short_max", t_short(32767)),
            ("int_min", t_int(-2147483648)),
            ("int_max", t_int(2147483647)),
            ("long_min", t_long(-9223372036854775808)),
            ("long_max", t_long(9223372036854775807)),
        ])),
        "各整数型の最小値・最大値")

    add_vector(
        "nbt/float_specials", "nbt/float_specials.nbt",
        to_java_file("", t_compound([
            ("float_positive_zero", t_float_bits(0x00000000)),
            ("float_negative_zero", t_float_bits(0x80000000)),
            ("float_infinity", t_float_bits(0x7F800000)),
            ("float_negative_infinity", t_float_bits(0xFF800000)),
            ("float_nan", t_float_bits(0x7FC00000)),
            ("double_positive_zero", t_double_bits(0x0000000000000000)),
            ("double_negative_zero", t_double_bits(0x8000000000000000)),
            ("double_infinity", t_double_bits(0x7FF0000000000000)),
            ("double_negative_infinity", t_double_bits(0xFFF0000000000000)),
            ("double_nan", t_double_bits(0x7FF8000000000000)),
        ])),
        "浮動小数点の特殊値。ビットパターンが保たれること")

    add_vector(
        "nbt/mutf8_nul", "nbt/mutf8_nul.nbt",
        to_java_file("", t_compound([("value", t_string("a\u0000b"))])),
        "U+0000 を含む文字列。C0 80 で符号化される")

    add_vector(
        "nbt/mutf8_supplementary", "nbt/mutf8_supplementary.nbt",
        to_java_file("", t_compound([("value", t_string("\U0001F600あ"))])),
        "補助文字（絵文字）と3バイト文字。CESU-8 になる")

    add_vector(
        "nbt/mutf8_lone_surrogate", "nbt/mutf8_lone_surrogate.nbt",
        to_java_file("", t_compound([("value", t_string_raw(bytes([0xED, 0xA0, 0xBD])))])),
        "孤立サロゲート。UTF-8 に写せないが往復できること")

    add_vector(
        "nbt/mutf8_max_length", "nbt/mutf8_max_length.nbt",
        to_java_file("", t_compound([("value", t_string("a" * 65535))])),
        "MUTF-8 で 65535 バイトちょうどの文字列。長さフィールドの上限")

    # 同じ内容を3種の圧縮で用意し、自動判定が効くことを確かめる
    plain = to_java_file("hello world", hello)
    add_vector(
        "nbt/uncompressed", "nbt/uncompressed.nbt", plain,
        "無圧縮。自動判定で読めること", compression="none")
    add_vector(
        "nbt/gzip", "nbt/gzip.nbt", gzip.compress(plain, mtime=0),
        "GZip 圧縮。自動判定で読めること", compression="gzip")
    add_vector(
        "nbt/zlib", "nbt/zlib.nbt", zlib.compress(plain, 6),
        "Zlib 圧縮。自動判定で読めること", compression="zlib")

    add_vector(
        "nbt/network_format", "nbt/network_format.nbt",
        to_network(t_compound([("x", t_int(1))])),
        "ネットワーク形式（無名ルート、1.20.2+）", fmt="network")

    # --- 異常系 ---

    truncated = plain[:-3]
    add_vector(
        "nbt/truncated", "nbt/truncated.nbt", truncated,
        "途中で切れた入力", expect_error="MALFORMED_DATA")

    huge = (struct.pack(">B", TAG_COMPOUND) + write_string("")
            + struct.pack(">B", TAG_BYTE_ARRAY) + write_string("a")
            + struct.pack(">i", 0x7FFFFFFF))
    add_vector(
        "nbt/huge_declared_length", "nbt/huge_declared_length.nbt", huge,
        "長さ 0x7FFFFFFF を宣言するだけの入力。確保前に弾くこと",
        expect_error="MALFORMED_DATA")

    unknown = struct.pack(">B", TAG_COMPOUND) + write_string("") + struct.pack(">B", 13)
    add_vector(
        "nbt/unknown_tag_id", "nbt/unknown_tag_id.nbt", unknown,
        "未知のタグID 13", expect_error="MALFORMED_DATA")

    negative = (struct.pack(">B", TAG_COMPOUND) + write_string("")
                + struct.pack(">B", TAG_INT_ARRAY) + write_string("a")
                + struct.pack(">i", -1))
    add_vector(
        "nbt/negative_length", "nbt/negative_length.nbt", negative,
        "長さフィールドが負値", expect_error="MALFORMED_DATA")

    trailing = plain + b"\xff"
    add_vector(
        "nbt/trailing_bytes", "nbt/trailing_bytes.nbt", trailing,
        "ルートの後に余分なバイトがある", expect_error="MALFORMED_DATA")

    # キーに孤立サロゲートを置いたベクタ。値と違いキーでは許さない（仕様 10 の 2.2章）
    lone_key = (struct.pack(">B", TAG_COMPOUND) + write_string("")
                + struct.pack(">B", TAG_INT)
                + struct.pack(">H", 3) + bytes([0xED, 0xA0, 0xBD])
                + struct.pack(">i", 1)
                + struct.pack(">B", TAG_END))
    add_vector(
        "nbt/mutf8_lone_surrogate_key", "nbt/mutf8_lone_surrogate_key.nbt", lone_key,
        "Compound のキーが孤立サロゲート。値と違いキーでは許さない",
        expect_error="MALFORMED_DATA")

    raw_nul = to_java_file("", t_compound([("value", t_string_raw(b"\x00"))]))
    add_vector(
        "nbt/mutf8_raw_nul", "nbt/mutf8_raw_nul.nbt", raw_nul,
        "MUTF-8 に反する素の 0x00 を含む文字列", expect_error="MALFORMED_DATA")



# ---------------------------------------------------------------------------
# Anvil リージョンファイル
# ---------------------------------------------------------------------------

SECTOR = 4096


class RegionBuilder:
    """リージョンファイルを手で組み立てる。

    ライブラリのセクタ確保ロジックを検証する側なので、ここでも実装を使わず
    仕様書の記述だけを根拠にバイト列を組む。
    """

    def __init__(self):
        # ヘッダ 2 セクタぶんをゼロで確保する
        self.sectors = [bytearray(SECTOR), bytearray(SECTOR)]
        self.locations = [(0, 0)] * 1024
        self.timestamps = [0] * 1024

    def _index(self, local_x, local_z):
        return local_x + local_z * 32

    def add_chunk(self, local_x, local_z, payload, compression=2,
                  timestamp=1700000000, external=False, at_sector=None):
        """チャンクを 1 つ置く。at_sector を指定すると配置先を固定できる。"""
        if external:
            body = b""
            scheme = compression | 0x80
        else:
            body = payload
            scheme = compression

        block = struct.pack(">iB", len(body) + 1, scheme) + body
        needed = (len(block) + SECTOR - 1) // SECTOR
        padded = block + bytes(needed * SECTOR - len(block))

        if at_sector is None:
            start = len(self.sectors)
            for offset in range(needed):
                self.sectors.append(bytearray(padded[offset * SECTOR:(offset + 1) * SECTOR]))
        else:
            start = at_sector
            # 指定位置まで空セクタで埋める
            while len(self.sectors) < start + needed:
                self.sectors.append(bytearray(SECTOR))
            for offset in range(needed):
                self.sectors[start + offset] = bytearray(
                    padded[offset * SECTOR:(offset + 1) * SECTOR])

        index = self._index(local_x, local_z)
        self.locations[index] = (start, needed)
        self.timestamps[index] = timestamp

    def set_location(self, local_x, local_z, offset, count):
        """ロケーションテーブルを直接書き換える。異常系ベクタ用。"""
        self.locations[self._index(local_x, local_z)] = (offset, count)

    def build(self):
        header = bytearray()
        for offset, count in self.locations:
            header += struct.pack(">I", (offset << 8) | count)
        for value in self.timestamps:
            header += struct.pack(">i", value)

        self.sectors[0] = bytearray(header[:SECTOR])
        self.sectors[1] = bytearray(header[SECTOR:SECTOR * 2])

        out = bytearray()
        for sector in self.sectors:
            out += sector
        return bytes(out)


def sample_chunk(x, z, extra=None):
    """チャンクらしい形の NBT を作る。実データの構造を最小限まねる。"""
    entries = [
        ("DataVersion", t_int(4903)),
        ("xPos", t_int(x)),
        ("zPos", t_int(z)),
        ("yPos", t_int(-4)),
        ("Status", t_string("minecraft:full")),
        ("sections", t_list(TAG_COMPOUND, [
            t_compound([
                ("Y", t_byte(-4)),
                ("block_states", t_compound([
                    ("palette", t_list(TAG_COMPOUND, [
                        t_compound([("Name", t_string("minecraft:air"))]),
                    ])),
                ])),
            ]),
        ])),
    ]

    if extra is not None:
        entries.append(extra)

    return to_java_file("", t_compound(entries))


def build_anvil():
    """Anvil のテストベクタを組み立てる。"""
    # 空のリージョン（ヘッダだけ）
    add_vector(
        "anvil/empty", "anvil/empty/r.0.0.mca", RegionBuilder().build(),
        "全エントリ 0 のリージョン。ヘッダ 2 セクタのみ")

    # チャンク 1 つ
    builder = RegionBuilder()
    builder.add_chunk(0, 0, zlib.compress(sample_chunk(0, 0), 6))
    add_vector(
        "anvil/single_chunk", "anvil/single_chunk/r.0.0.mca", builder.build(),
        "チャンクが 1 つだけ")

    # 隙間のある配置。読み書きしても他のチャンクを壊さないこと
    builder = RegionBuilder()
    builder.add_chunk(0, 0, zlib.compress(sample_chunk(0, 0), 6), at_sector=2)
    builder.add_chunk(5, 3, zlib.compress(sample_chunk(5, 3), 6), at_sector=6)
    builder.add_chunk(31, 31, zlib.compress(sample_chunk(31, 31), 6), at_sector=9)
    add_vector(
        "anvil/fragmented", "anvil/fragmented/r.0.0.mca", builder.build(),
        "セクタ 3〜5 と 7〜8 が空いた断片化した配置")

    # 圧縮方式 1 / 2 / 3 の混在
    builder = RegionBuilder()
    builder.add_chunk(0, 0, gzip.compress(sample_chunk(0, 0), mtime=0), compression=1)
    builder.add_chunk(1, 0, zlib.compress(sample_chunk(1, 0), 6), compression=2)
    builder.add_chunk(2, 0, sample_chunk(2, 0), compression=3)
    add_vector(
        "anvil/mixed_compression", "anvil/mixed_compression/r.0.0.mca", builder.build(),
        "圧縮方式ID 1 (GZip) / 2 (Zlib) / 3 (無圧縮) が混在")

    # 外部ファイル (.mcc) へ退避されたチャンク
    external_payload = zlib.compress(sample_chunk(0, 0), 6)
    builder = RegionBuilder()
    builder.add_chunk(0, 0, external_payload, compression=2, external=True)
    add_vector(
        "anvil/external_mcc", "anvil/external_mcc/r.0.0.mca", builder.build(),
        "チャンクが c.0.0.mcc へ退避されている（圧縮方式IDに 0x80 が立つ）")

    # .mcc 本体も同じディレクトリへ置く
    mcc_path = os.path.join(TESTDATA, "anvil", "external_mcc", "c.0.0.mcc")
    with open(mcc_path, "wb") as handle:
        handle.write(external_payload)

    # 異常系: ヘッダ領域を指すオフセット
    builder = RegionBuilder()
    builder.add_chunk(0, 0, zlib.compress(sample_chunk(0, 0), 6))
    builder.set_location(1, 0, 1, 1)
    add_vector(
        "anvil/bad_offset", "anvil/bad_offset/r.0.0.mca", builder.build(),
        "オフセットがヘッダ領域 (セクタ 1) を指している",
        expect_error="MALFORMED_DATA")

    # 異常系: 2 チャンクが同じセクタを指す
    builder = RegionBuilder()
    builder.add_chunk(0, 0, zlib.compress(sample_chunk(0, 0), 6), at_sector=2)
    builder.set_location(1, 0, 2, 1)
    add_vector(
        "anvil/overlapping_sectors", "anvil/overlapping_sectors/r.0.0.mca", builder.build(),
        "2 つのチャンクが同じセクタを指している",
        expect_error="MALFORMED_DATA")

    # 異常系: ファイル長がセクタ境界に揃っていない
    builder = RegionBuilder()
    builder.add_chunk(0, 0, zlib.compress(sample_chunk(0, 0), 6))
    add_vector(
        "anvil/unaligned_length", "anvil/unaligned_length/r.0.0.mca", builder.build() + b"\x00",
        "ファイル長が 4096 の倍数になっていない",
        expect_error="MALFORMED_DATA")

    # 異常系: 割り当てがファイル外へはみ出す
    builder = RegionBuilder()
    builder.add_chunk(0, 0, zlib.compress(sample_chunk(0, 0), 6))
    builder.set_location(1, 0, 900, 1)
    add_vector(
        "anvil/offset_out_of_file", "anvil/offset_out_of_file/r.0.0.mca", builder.build(),
        "オフセットがファイル末尾より後ろを指している",
        expect_error="MALFORMED_DATA")


# ---------------------------------------------------------------------------
# World / Block
# ---------------------------------------------------------------------------


def ceil_log2(count):
    """count 個の値を表すのに必要な最小ビット数。count == 1 なら 0。"""
    bits = 0

    # 1 を超える分だけシフトして数える
    while (1 << bits) < count:
        bits += 1

    return bits


def pack_indices(indices, bits):
    """添字の並びを、跨ぎなしで 64bit 整数の配列へ詰める。

    ライブラリの実装を検証する側なので、ここでも仕様書の記述だけを根拠に組む。
    """
    values_per_long = 64 // bits
    long_count = (len(indices) + values_per_long - 1) // values_per_long
    longs = [0] * long_count

    # 1 つの i64 に入りきらない分は捨てて、次の i64 の最下位ビットから始める
    for position, value in enumerate(indices):
        long_index = position // values_per_long
        bit_offset = (position % values_per_long) * bits
        longs[long_index] |= (value & ((1 << bits) - 1)) << bit_offset

    # 符号付き 64bit として書き出す
    return [value - (1 << 64) if value >= (1 << 63) else value for value in longs]


def block_palette_entry(name, properties=None):
    """ブロックのパレット要素。"""
    entries = []

    if properties is not None:
        entries.append(("Properties", t_compound(
            [(key, t_string(value)) for key, value in properties])))

    entries.append(("Name", t_string(name)))
    return t_compound(entries)


def paletted_container(palette_entries, indices, min_bits):
    """パレット付きコンテナを組み立てる。パレットが 1 要素なら data を書かない。

    キーは実データと同じく `data` -> `palette` の順に置く
    （docs/spec/31-paletted-container.md 4.1章）。
    """
    entries = []

    if len(palette_entries) > 1:
        bits = max(min_bits, ceil_log2(len(palette_entries)))
        entries.append(("data", t_long_array(pack_indices(indices, bits))))

    entries.append(("palette", t_list(palette_entries[0].tag_id, palette_entries)))
    return t_compound(entries)


def make_section(y, block_palette, block_indices, biome_palette, biome_indices):
    """セクションを 1 つ組み立てる。"""
    return t_compound([
        ("Y", t_byte(y)),
        ("block_states", paletted_container(block_palette, block_indices, 4)),
        ("biomes", paletted_container(biome_palette, biome_indices, 1)),
    ])


def block_entity(entity_id, x, y, z):
    """ブロックエンティティ 1 件。座標は絶対座標で持つ（実データと同じ）。"""
    return t_compound([
        ("id", t_string(entity_id)),
        ("x", t_int(x)),
        ("y", t_int(y)),
        ("z", t_int(z)),
    ])


def block_tick(block_id, x, y, z):
    """ブロックのティック予約 1 件。実データのキー名をなぞる。"""
    return t_compound([
        ("i", t_string(block_id)),
        ("p", t_int(0)),
        ("t", t_int(0)),
        ("x", t_int(x)),
        ("y", t_int(y)),
        ("z", t_int(z)),
    ])


def make_chunk(x, z, sections, status="minecraft:full",
               block_entities=None, block_ticks=None, fluid_ticks=None):
    """チャンクの NBT を組み立てる。実データの構造をなぞる。"""
    entries = [
        ("DataVersion", t_int(4903)),
        ("xPos", t_int(x)),
        ("zPos", t_int(z)),
        ("yPos", t_int(-4)),
        ("Status", t_string(status)),
        ("LastUpdate", t_long(449)),
        ("InhabitedTime", t_long(0)),
        ("isLightOn", t_byte(1)),
        ("Heightmaps", t_compound([
            ("WORLD_SURFACE", t_long_array([0] * 37)),
        ])),
    ]

    # 付随データは、空なら要素型 End の空リストになる（実データと同じ）
    for key, values in (("block_entities", block_entities),
                        ("block_ticks", block_ticks),
                        ("fluid_ticks", fluid_ticks)):
        if values is None or len(values) == 0:
            if key == "block_entities":
                entries.append((key, t_list(TAG_END, [])))
        else:
            entries.append((key, t_list(TAG_COMPOUND, values)))

    entries.append(("sections", t_list(TAG_COMPOUND, sections)))
    return to_java_file("", t_compound(entries))


AIR = block_palette_entry("minecraft:air")
STONE = block_palette_entry("minecraft:stone")
PLAINS = t_string("minecraft:plains")


def build_world():
    """World / Block のテストベクタを組み立てる。"""
    # パレット 1 要素。data を持たない
    add_vector(
        "world/palette_1", "world/palette_1.nbt",
        make_chunk(0, 0, [make_section(-4, [AIR], [0] * 4096, [PLAINS], [0] * 64)]),
        "パレット 1 要素のセクション（data 無し）")

    # パレット 5 要素 -> bits=4、端数なし（256 long）
    palette5 = [
        AIR, STONE,
        block_palette_entry("minecraft:dirt"),
        block_palette_entry("minecraft:gravel"),
        block_palette_entry("minecraft:bedrock"),
    ]
    indices5 = [(position * 7) % 5 for position in range(4096)]
    add_vector(
        "world/palette_5", "world/palette_5.nbt",
        make_chunk(0, 0, [make_section(-4, palette5, indices5, [PLAINS], [0] * 64)]),
        "パレット 5 要素 -> bits=4、data は 256 long（端数なし）")

    # パレット 17 要素 -> bits=5、最後の long に端数（342 long）
    palette17 = [AIR, STONE] + [
        block_palette_entry("minecraft:stone", [("variant", "v%d" % index)])
        for index in range(15)
    ]
    indices17 = [(position * 11) % 17 for position in range(4096)]
    add_vector(
        "world/palette_17", "world/palette_17.nbt",
        make_chunk(0, 0, [make_section(-4, palette17, indices17, [PLAINS], [0] * 64)]),
        "パレット 17 要素 -> bits=5、data は 342 long（最後に端数）")

    # 複数セクション + バイオーム 2 種（bits=1）
    biome_palette = [PLAINS, t_string("minecraft:desert")]
    biome_indices = [(position // 8) % 2 for position in range(64)]
    add_vector(
        "world/multi_section", "world/multi_section.nbt",
        make_chunk(1, 2, [
            make_section(-4, palette5, indices5, biome_palette, biome_indices),
            make_section(-3, [AIR], [0] * 4096, [PLAINS], [0] * 64),
            make_section(-2, palette17, indices17, biome_palette, biome_indices),
        ]),
        "セクション 3 個。バイオームも 2 種（bits=1）")

    # 未使用パレット要素を含む。compact() で減るはず
    palette_unused = [AIR, STONE,
                      block_palette_entry("minecraft:dirt"),
                      block_palette_entry("minecraft:sand")]
    indices_unused = [position % 2 for position in range(4096)]
    add_vector(
        "world/palette_unused", "world/palette_unused.nbt",
        make_chunk(0, 0, [make_section(-4, palette_unused, indices_unused,
                                       [PLAINS], [0] * 64)]),
        "参照されていないパレット要素が 2 つある。compact() で減る")

    # ブロックに紐づく付随データを持つチャンク。
    # ブロックを置き換えたとき、同じ座標の要素が取り除かれるかを見る。
    # チャンク (0,0) なので、絶対座標は x,z がそのまま。y は min_section_y*16 = -64 から
    add_vector(
        "world/block_entities", "world/block_entities.nbt",
        make_chunk(
            0, 0,
            [make_section(-4, palette5, indices5, [PLAINS], [0] * 64)],
            block_entities=[
                # chunk_edit が置き換える座標にあるもの（消えるはず）
                block_entity("minecraft:chest", 0, -64, 0),
                block_entity("minecraft:furnace", 1, -64, 1),
                # 触らない座標にあるもの（残るはず）
                block_entity("minecraft:barrel", 15, -50, 15),
            ],
            block_ticks=[
                block_tick("minecraft:water", 0, -64, 0),
                block_tick("minecraft:lava", 15, -50, 15),
            ],
            fluid_ticks=[
                block_tick("minecraft:water", 1, -64, 1),
            ]),
        "block_entities / block_ticks / fluid_ticks を持つチャンク")

    # 生成途中のチャンク
    add_vector(
        "world/proto_chunk", "world/proto_chunk.nbt",
        make_chunk(0, 0, [make_section(-4, [AIR], [0] * 4096, [PLAINS], [0] * 64)],
                   status="minecraft:structure_starts"),
        "生成途中のチャンク（Status が full でない）")

    # 異常系: 添字がパレットの範囲外
    broken = t_compound([
        ("data", t_long_array(pack_indices([5] * 4096, 4))),
        ("palette", t_list(TAG_COMPOUND, [AIR, STONE])),
    ])
    add_vector(
        "world/palette_index_out_of_range", "world/palette_index_out_of_range.nbt",
        to_java_file("", t_compound([
            ("DataVersion", t_int(4903)),
            ("xPos", t_int(0)),
            ("zPos", t_int(0)),
            ("yPos", t_int(-4)),
            ("Status", t_string("minecraft:full")),
            ("sections", t_list(TAG_COMPOUND, [t_compound([
                ("Y", t_byte(-4)),
                ("block_states", broken),
                ("biomes", paletted_container([PLAINS], [0] * 64, 1)),
            ])])),
        ])),
        "添字がパレットの範囲外を指している",
        expect_error="MALFORMED_DATA")

    # 異常系: data の長さがビット幅と合わない
    wrong_length = t_compound([
        ("data", t_long_array([0] * 100)),
        ("palette", t_list(TAG_COMPOUND, [AIR, STONE, block_palette_entry("minecraft:dirt")])),
    ])
    add_vector(
        "world/bitstorage_wrong_length", "world/bitstorage_wrong_length.nbt",
        to_java_file("", t_compound([
            ("DataVersion", t_int(4903)),
            ("xPos", t_int(0)),
            ("zPos", t_int(0)),
            ("yPos", t_int(-4)),
            ("Status", t_string("minecraft:full")),
            ("sections", t_list(TAG_COMPOUND, [t_compound([
                ("Y", t_byte(-4)),
                ("block_states", wrong_length),
                ("biomes", paletted_container([PLAINS], [0] * 64, 1)),
            ])])),
        ])),
        "data の長さがパレット長から求めたビット幅と合わない",
        expect_error="MALFORMED_DATA")

def write_manifest():
    """ベクタ一覧を manifest.json へ書き出す。"""
    manifest = {
        "comment": "spec/tools/build_testdata.py が生成する。手で編集しないこと",
        "vectors": VECTORS,
    }
    path = os.path.join(TESTDATA, "manifest.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_handwritten_expectations():
    """手書きの期待値。生成器そのものを検証するための起点になる。

    ここだけは 90-conformance.md と 00-conventions.md の記述を見ながら手で書く。
    他の期待値は検証済みの実装から生成するため、この 1 件が信頼の基点になる。
    """
    expected = (
        '{"format":"java","root_name":"hello world","root":'
        '{"type":"compound","value":[["name",'
        '{"type":"string","value":"Bananrama","mutf8":"42616e616e72616d61"}]]}}\n'
    )
    path = os.path.join(TESTDATA, "expect", "nbt", "hello_world.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(expected)


def main():
    build_all()
    build_anvil()
    build_world()
    write_manifest()
    write_handwritten_expectations()
    print("ベクタ %d 件を %s へ書き出した" % (len(VECTORS), TESTDATA))


if __name__ == "__main__":
    main()

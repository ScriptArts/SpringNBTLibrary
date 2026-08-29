"""適合性検証ツール。4言語すべてが同じインターフェースで同じ出力を出す。

``spec/run-conformance.sh`` がこのツールを4言語ぶん起動し、
出力を相互に diff することで「4言語が同一に振る舞う」ことを機械的に確かめる。

仕様: ``docs/spec/90-conformance.md`` 2.3章
"""

from __future__ import annotations

import os
import sys

from . import TARGET_DATA_VERSION
from .anvil import ChunkCompression, RegionFile, RegionFileMode
from .world import BlockState, Chunk, ChunkReadOptions, VersionMismatchAction
from .errors import SpringNbtError
from .nbt import (
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
    NbtTag,
    NbtWriteOptions,
    mutf8,
    read_file,
    write_bytes,
)
from .nbt import snbt as snbt_module

USAGE = """使い方:
  python -m spring_nbt_library.conformance decode  <入力パス> <出力JSONパス> [--format network]
  python -m spring_nbt_library.conformance encode  <入力パス> <出力バイナリパス> [--format network]
  python -m spring_nbt_library.conformance snbt    <入力パス> <出力SNBTパス> [--format network]
  python -m spring_nbt_library.conformance region-list    <入力mcaパス> <出力テキストパス>
  python -m spring_nbt_library.conformance region-rewrite <入力mcaパス> <出力mcaパス>
  python -m spring_nbt_library.conformance chunk-report   <入力チャンクnbt> <出力テキストパス>
  python -m spring_nbt_library.conformance chunk-edit     <入力チャンクnbt> <出力nbtパス>
  python -m spring_nbt_library.conformance version"""


# ---------------------------------------------------------------------------
# 正規化JSON
#
# 浮動小数点をビットパターンで、64bit 整数を10進文字列で表すのが要。
# 10進表記の丸めや JSON 数値の精度は処理系ごとに差が出るため、
# そのまま出すと4言語の出力が一致しない。
#
# 仕様: docs/spec/00-conventions.md 6章
# ---------------------------------------------------------------------------

_JSON_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


def _json_string(text: str) -> str:
    """JSON 文字列を書き出す。非 ASCII は必ず ``\\uXXXX`` へ逃がす。

    エスケープの単位は **UTF-16 コード単位**。
    C# / Java と桁数を揃えるため、補助文字はサロゲートペアの 2 つに分けて出す。
    """
    parts = ['"']

    # コードポイントごとに、必要なら UTF-16 コード単位へ分解して書く
    for character in text:
        if character in _JSON_ESCAPES:
            parts.append(_JSON_ESCAPES[character])
            continue

        code = ord(character)

        # ASCII の印字可能文字だけ生で出す
        if 0x20 <= code <= 0x7E:
            parts.append(character)
        elif code >= 0x10000:
            offset = code - 0x10000
            parts.append("\\u%04x" % (0xD800 + (offset >> 10)))
            parts.append("\\u%04x" % (0xDC00 + (offset & 0x3FF)))
        else:
            parts.append("\\u%04x" % code)

    parts.append('"')
    return "".join(parts)


def _hex_bits(data: bytes) -> str:
    return "0x" + data.hex()


def _to_hex(data: bytes) -> str:
    return data.hex()


def _json_tag(tag: NbtTag) -> str:
    parts = ['{"type":', _json_string(tag.type.as_string())]

    # list だけは value の前に element_type が入る（仕様が定めるキー順）
    if isinstance(tag, NbtList):
        parts.append(',"element_type":')
        parts.append(_json_string(tag.element_type.as_string()))

    parts.append(',"value":')

    import struct

    if isinstance(tag, (NbtByte, NbtShort, NbtInt)):
        parts.append("%d" % tag.value)
    elif isinstance(tag, NbtLong):
        # 64bit 整数は JSON 数値だと処理系によって精度が落ちるため10進文字列で表す
        parts.append(_json_string("%d" % tag.value))
    elif isinstance(tag, NbtFloat):
        parts.append(_json_string(_hex_bits(struct.pack(">f", tag.value))))
    elif isinstance(tag, NbtDouble):
        parts.append(_json_string(_hex_bits(struct.pack(">d", tag.value))))
    elif isinstance(tag, NbtString):
        parts.append(_json_string(tag.value))

        # MUTF-8 のバイト列も併記する。孤立サロゲートなど UTF-8 に写せない値を厳密に比較するため
        parts.append(',"mutf8":')
        parts.append(_json_string(_to_hex(mutf8.encode(tag.value))))
    elif isinstance(tag, (NbtByteArray, NbtIntArray)):
        parts.append("[" + ",".join("%d" % value for value in tag.value) + "]")
    elif isinstance(tag, NbtLongArray):
        # 64bit 整数は10進文字列の配列で表す
        parts.append("[" + ",".join(_json_string("%d" % value) for value in tag.value) + "]")
    elif isinstance(tag, NbtList):
        parts.append("[" + ",".join(_json_tag(item) for item in tag) + "]")
    elif isinstance(tag, NbtCompound):
        # JSON オブジェクトだと挿入順の保持が処理系依存になるため、組の配列で表す
        entries = []
        for key, value in tag.items():
            entries.append("[" + _json_string(key) + "," + _json_tag(value) + "]")
        parts.append("[" + ",".join(entries) + "]")
    else:
        raise SpringNbtError.malformed("JSON へ写せないタグ: %s" % tag.type.as_string())

    parts.append("}")
    return "".join(parts)


def normalized_json(named: NamedTag, fmt: NbtFormat) -> str:
    """ルートを含む全体を JSON 文字列へ変換する。末尾に改行を1つ付ける。"""
    return "".join([
        '{"format":', _json_string(fmt.value),
        ',"root_name":', _json_string(named.name),
        ',"root":', _json_tag(named.tag),
        "}\n",
    ])



# ---------------------------------------------------------------------------
# リージョンファイル
#
# 仕様: docs/spec/90-conformance.md 2.3章
# ---------------------------------------------------------------------------


def region_list(region: RegionFile) -> str:
    """存在するチャンクを 1 行 1 チャンクで書き出す。並びはロケーションテーブルの添字順。

    各行は「絶対X 絶対Z タイムスタンプ 圧縮方式 圧縮後バイト数 展開後バイト数 キー数」。
    """
    lines = ["region %d %d" % (region.region_x, region.region_z)]
    total = 0

    for position in region.chunk_positions():
        raw = region.read_chunk_raw(position.x, position.z)

        if raw is None:
            continue

        chunk = region.read_chunk(position.x, position.z)
        key_count = 0
        plain_length = 0

        if chunk is not None:
            key_count = len(chunk)
            plain_length = len(write_bytes(
                NamedTag("", chunk), NbtWriteOptions(compression=Compression.NONE)))

        lines.append("%d %d %d %s %d %d %d" % (
            position.x, position.z, region.timestamp(position.x, position.z),
            raw.compression.as_string(), len(raw.data), plain_length, key_count))
        total += 1

    lines.append("total %d" % total)
    return "\n".join(lines) + "\n"


def region_rewrite(source: RegionFile, output_path: str) -> None:
    """全チャンクを読み直し、無圧縮で新しいリージョンへ詰め直して書き出す。

    無圧縮にするのは、zlib の出力が処理系ごとに違い、
    圧縮したままでは言語間でバイトが一致しないため。
    """
    # 途中結果が残らないよう、書き出し先は必ず作り直す
    if os.path.exists(output_path):
        os.remove(output_path)

    with RegionFile.open(output_path, RegionFileMode.READ_WRITE) as destination:
        for position in source.chunk_positions():
            chunk = source.read_chunk(position.x, position.z)

            if chunk is None:
                continue

            destination.write_chunk(position.x, position.z, chunk, ChunkCompression.NONE)
            destination.set_timestamp(
                position.x, position.z, source.timestamp(position.x, position.z))

        destination.flush()



# ---------------------------------------------------------------------------
# チャンク（World レイヤ）
#
# 仕様: docs/spec/90-conformance.md 2.3章
# ---------------------------------------------------------------------------


def chunk_describe(chunk: Chunk) -> str:
    """チャンクの全ブロック・全バイオームを走査して集計する。

    パレットとビットストレージを端から端まで通すので、
    ビット詰めの実装が 1 か所でもずれれば集計値が変わる。
    """
    lines = ["chunk %d %d %d %s" % (chunk.x, chunk.z, chunk.min_section_y, chunk.status)]
    blocks = {}
    biomes = {}

    for section_y in chunk.section_ys:
        section = chunk.section(section_y)
        block_palette = 0
        biome_palette = 0
        block_bits = 0
        biome_bits = 0

        if section.has_block_states:
            block_palette = len(section.block_states.palette)
            block_bits = section.block_states.bits_per_entry

        if section.has_biomes:
            biome_palette = len(section.biomes.palette)
            biome_bits = section.biomes.bits_per_entry

        lines.append("section %d %d %d %d %d"
                     % (section_y, block_palette, block_bits, biome_palette, biome_bits))

        # 全ブロックを 1 つずつ読んで、状態の文字列表現ごとに数える
        for y in range(16):
            for z in range(16):
                for x in range(16):
                    block = chunk.get_block(x, (section_y * 16) + y, z)

                    if block is None:
                        continue

                    key = str(block)
                    blocks[key] = blocks.get(key, 0) + 1

        # バイオームは 4×4×4 単位なので、4 ブロックおきに見る
        for y in range(0, 16, 4):
            for z in range(0, 16, 4):
                for x in range(0, 16, 4):
                    biome = chunk.get_biome(x, (section_y * 16) + y, z)

                    if biome is None:
                        continue

                    biomes[biome] = biomes.get(biome, 0) + 1

    # 名前の昇順で出すので、内部の並びに関係なく同じ出力になる
    for key in sorted(blocks):
        lines.append("block %s %d" % (key, blocks[key]))

    for key in sorted(biomes):
        lines.append("biome %s %d" % (key, biomes[key]))

    return "\n".join(lines) + "\n"


def chunk_edit(chunk: Chunk) -> None:
    """決まった手順でチャンクを編集する。全言語で同じ結果になるはず。

    パレット拡張・ビット幅の再計算・未使用要素の掃除を一通り通す。
    """
    base_y = chunk.min_section_y * 16

    # パレットに無いブロックを次々に置き、ビット幅の拡張を起こす
    for index in range(20):
        state = BlockState.parse("minecraft:edited_%d[step=%d]" % (index, index))
        chunk.set_block(index % 16, base_y + (index // 16), index % 16, state)

    # プロパティ付きのブロックを、名前は同じで状態違いで置く
    chunk.set_block(1, base_y + 2, 1, BlockState.parse("minecraft:oak_stairs[facing=north,half=top]"))
    chunk.set_block(2, base_y + 2, 2, BlockState.parse("minecraft:oak_stairs[half=top,facing=north]"))
    chunk.set_block(3, base_y + 2, 3, BlockState.parse("oak_stairs[facing=south]"))

    # バイオームも書き換える
    chunk.set_biome(0, base_y, 0, "minecraft:desert")
    chunk.set_biome(8, base_y + 8, 8, "minecraft:jungle")

    # 使われなくなったパレット要素を掃除する
    chunk.compact()

    # 高さマップと光源は再計算しないので、無効化して Minecraft に任せる
    chunk.clear_heightmaps()
    chunk.invalidate_lighting()


def read_chunk_file(path: str) -> Chunk:
    """チャンク NBT のファイルを読む。"""
    named = read_file(path)

    # 検証では DataVersion の違いを警告にせず、そのまま読む
    options = ChunkReadOptions(on_version_mismatch=VersionMismatchAction.IGNORE)
    return Chunk.from_nbt(named.tag, options)


# ---------------------------------------------------------------------------
# コマンド
# ---------------------------------------------------------------------------


def _parse_format(args) -> NbtFormat:
    """``--format network`` が指定されていればネットワーク形式として読む。"""
    # 3 番目以降の引数からオプションを探す
    for index in range(3, len(args) - 1):
        if args[index] == "--format" and args[index + 1] == "network":
            return NbtFormat.NETWORK

    return NbtFormat.JAVA


def _write_text_file(path: str, content: str) -> None:
    """改行を変換せず、BOM も付けずに UTF-8 で書く。

    孤立サロゲートを含みうるため ``surrogatepass`` で符号化する。
    """
    with open(path, "wb") as handle:
        handle.write(content.encode("utf-8", "surrogatepass"))


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if len(argv) == 0:
        sys.stderr.write(USAGE + "\n")
        return 2

    command = argv[0]

    if command == "version":
        sys.stdout.write(
            "python spring-nbt-library 0.1.0 target_data_version=%d\n" % TARGET_DATA_VERSION)
        return 0

    if command not in ("decode", "encode", "snbt", "region-list", "region-rewrite",
                       "chunk-report", "chunk-edit"):
        sys.stderr.write(USAGE + "\n")
        return 2

    if len(argv) < 3:
        sys.stderr.write(USAGE + "\n")
        return 2

    fmt = _parse_format(argv)

    try:
        if command == "chunk-report":
            _write_text_file(argv[2], chunk_describe(read_chunk_file(argv[1])))
            return 0

        if command == "chunk-edit":
            chunk = read_chunk_file(argv[1])
            chunk_edit(chunk)
            options = NbtWriteOptions(compression=Compression.NONE)

            with open(argv[2], "wb") as handle:
                handle.write(write_bytes(NamedTag("", chunk.to_nbt()), options))

            return 0

        if command in ("region-list", "region-rewrite"):
            with RegionFile.open(argv[1], RegionFileMode.READ_ONLY) as region:
                if command == "region-list":
                    _write_text_file(argv[2], region_list(region))
                else:
                    region_rewrite(region, argv[2])

            return 0

        named = read_file(argv[1], NbtReadOptions(fmt=fmt))

        if command == "decode":
            _write_text_file(argv[2], normalized_json(named, fmt))
        elif command == "encode":
            options = NbtWriteOptions(fmt=fmt, compression=Compression.NONE)
            with open(argv[2], "wb") as handle:
                handle.write(write_bytes(named, options))
        else:
            _write_text_file(argv[2], snbt_module.write(named.tag) + "\n")
    except SpringNbtError as error:
        # 4言語で同じ ErrorCode を出すことが検証対象なので、コードを機械可読な形で出す
        sys.stderr.write("ERROR %s %s\n" % (error.code.as_string(), error.message))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

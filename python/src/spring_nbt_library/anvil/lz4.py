"""圧縮方式ID 4 (LZ4) のチャンクを展開する

素の LZ4 ブロックでも LZ4 フレーム形式でもなく、
独自ヘッダを持つブロックの連結である

書き込みには対応しない
書き戻すときは Zlib になる

仕様: docs/spec/20-anvil-region.md 3.1.1 / 3.1.2
"""

from __future__ import annotations

import struct

from ..errors import SpringNbtError

__all__ = ["decompress_lz4"]

#: ブロックの先頭に必ず置かれる 8 バイト
MAGIC = b"LZ4Block"

#: ブロックヘッダの長さ
HEADER_LENGTH = 21

#: トークン上位 4 ビット: 本体が無圧縮
METHOD_STORED = 0x10

#: トークン上位 4 ビット: 本体が LZ4 圧縮
METHOD_COMPRESSED = 0x20

#: マッチの最小長
MIN_MATCH = 4


def decompress_lz4(payload: bytes) -> bytes:
    """LZ4Block の連結を展開する

    :raises SpringNbtError: 形式に反する入力の場合 (MALFORMED_DATA)
    """
    blocks = []
    position = 0

    # 入力を使い切るまでブロックを読み続ける
    while position < len(payload):
        data, position = _decompress_block(payload, position)
        blocks.append(data)

    return b"".join(blocks)


def _decompress_block(payload: bytes, position: int):
    """ブロックを 1 つ展開し、中身と次のブロックの開始位置を返す"""
    if position + HEADER_LENGTH > len(payload):
        raise SpringNbtError.malformed(
            "LZ4: ブロックヘッダが足りない（%d バイト）" % (len(payload) - position))

    # マジックが違えばそもそも LZ4Block ではない
    if payload[position:position + len(MAGIC)] != MAGIC:
        raise SpringNbtError.malformed("LZ4: ブロックが LZ4Block で始まっていない")

    method = payload[position + 8] & 0xF0
    compressed_length = struct.unpack_from("<i", payload, position + 9)[0]
    original_length = struct.unpack_from("<i", payload, position + 13)[0]
    body = position + HEADER_LENGTH

    _validate_lengths(compressed_length, original_length)

    if body + compressed_length > len(payload):
        raise SpringNbtError.malformed("LZ4: ブロック本体が入力からはみ出している")

    if method == METHOD_STORED:
        # 無圧縮なら 2 つの長さは一致していなければならない
        if compressed_length != original_length:
            raise SpringNbtError.malformed(
                "LZ4: 無圧縮ブロックの長さが食い違う（%d と %d）"
                % (compressed_length, original_length))

        return payload[body:body + compressed_length], body + compressed_length

    # 圧縮されているなら素の LZ4 ブロックとして展開する
    if method == METHOD_COMPRESSED:
        data = _decompress_raw_block(
            payload[body:body + compressed_length], original_length)
        return data, body + compressed_length

    raise SpringNbtError.malformed("LZ4: 未知の圧縮方式 0x%02X" % method)


def _validate_lengths(compressed_length: int, original_length: int) -> None:
    """ヘッダに書かれた 2 つの長さが妥当か調べる"""
    if compressed_length < 0 or original_length < 0:
        raise SpringNbtError.malformed("LZ4: ブロックの長さが負値")

    # 片方だけが 0 になることはない
    if (compressed_length == 0) != (original_length == 0):
        raise SpringNbtError.malformed("LZ4: ブロックの長さが片方だけ 0")


def _decompress_raw_block(source: bytes, original_length: int) -> bytes:
    """素の LZ4 ブロックを展開する"""
    output = bytearray(original_length)
    position = 0
    written = 0

    # シーケンスを順に読む
    while position < len(source):
        token = source[position]
        position += 1

        literal_length = token >> 4

        # 15 なら追加バイトで長さが続く
        if literal_length == 15:
            extra, position = _read_length(source, position)
            literal_length += extra

        written, position = _copy_literals(
            source, position, output, written, literal_length)

        # リテラルを出し切って入力が尽きたら、そこで終わり
        if position >= len(source):
            break

        if position + 2 > len(source):
            raise SpringNbtError.malformed("LZ4: オフセットが入力からはみ出している")

        offset = source[position] | (source[position + 1] << 8)
        position += 2

        if offset == 0 or offset > written:
            raise SpringNbtError.malformed("LZ4: マッチのオフセットが不正: %d" % offset)

        match_length = (token & 0x0F) + MIN_MATCH

        # 下位 4 ビットが 15 なら追加バイトで長さが続く
        if (token & 0x0F) == 15:
            extra, position = _read_length(source, position)
            match_length += extra

        written = _copy_match(output, written, offset, match_length)

    if written != original_length:
        raise SpringNbtError.malformed(
            "LZ4: 展開後の長さが合わない（%d と %d）" % (written, original_length))

    return bytes(output)


def _read_length(source: bytes, position: int):
    """255 が続く形式の追加長さを読む"""
    total = 0

    # 255 未満のバイトが出るまで足し続ける
    while True:
        if position >= len(source):
            raise SpringNbtError.malformed("LZ4: 長さの追加バイトが途中で切れた")

        value = source[position]
        position += 1
        total += value

        if value != 255:
            return total, position


def _copy_literals(source: bytes, position: int, output: bytearray,
                   written: int, length: int):
    """リテラルをそのまま出力へ写す"""
    if position + length > len(source):
        raise SpringNbtError.malformed("LZ4: リテラルが入力からはみ出している")

    if written + length > len(output):
        raise SpringNbtError.malformed("LZ4: 展開後の長さを超えた")

    output[written:written + length] = source[position:position + length]
    return written + length, position + length


def _copy_match(output: bytearray, written: int, offset: int, length: int) -> int:
    """出力済みのバイト列からマッチを写す"""
    if written + length > len(output):
        raise SpringNbtError.malformed("LZ4: 展開後の長さを超えた")

    start = written - offset

    # コピー元と先は重なりうるので 1 バイトずつ写す
    for index in range(length):
        output[written + index] = output[start + index]

    return written + length

"""Anvil のリージョンファイル (``r.X.Z.mca``)。32×32 チャンクを格納する。

ファイル全体をメモリに読み込んで扱う。実データのリージョンは数 MB 程度で、
この方が「触っていないチャンクのバイト配置をそのまま保つ」ことを保証しやすい。
開いて何も変えずに :meth:`RegionFile.flush` すると、バイト単位で元と同じファイルになる。

仕様: ``docs/spec/20-anvil-region.md``
"""

from __future__ import annotations

import enum
import gzip
import os
import re
import struct
import time
import zlib
from typing import Dict, List, Optional

from ..errors import ErrorCode, SpringNbtError
from ..nbt import Compression, NamedTag, NbtCompound, NbtReadOptions, NbtWriteOptions
from ..nbt import read_bytes as read_nbt_bytes
from ..nbt import write_bytes as write_nbt_bytes

__all__ = [
    "SECTOR_SIZE",
    "ChunkCompression",
    "ChunkPos",
    "RawChunk",
    "RegionFile",
    "RegionFileMode",
    "RegionPos",
]

#: セクタ長。
SECTOR_SIZE = 4096

#: ロケーションテーブルとタイムスタンプテーブルが占めるセクタ数。
_HEADER_SECTORS = 2

#: 1リージョンに入るチャンク数。
_CHUNK_COUNT = 1024

#: 1チャンクが確保できるセクタ数の上限（長さフィールドが u8 のため）。
_MAX_SECTORS = 255

#: リージョン内に収められるペイロードの上限。超えると外部ファイルへ退避する。
_MAX_INLINE_PAYLOAD = (_MAX_SECTORS * SECTOR_SIZE) - 5

_REGION_NAME = re.compile(r"^r\.(-?\d+)\.(-?\d+)\.mca$")


class ChunkCompression(enum.Enum):
    """リージョンファイル内でチャンクに使われる圧縮方式。

    NBT 層の :class:`~spring_nbt_library.nbt.Compression` とは別物であることに注意。
    あちらはファイル全体の圧縮を表し、こちらはリージョン内の 1 チャンクに付く
    1 バイトのIDを表す。

    仕様: ``docs/spec/20-anvil-region.md`` 3.1章
    """

    #: GZip (RFC 1952)。実データではほぼ使われない。
    GZIP = 1

    #: Zlib (RFC 1950)。Minecraft が実際に書き出す方式。
    ZLIB = 2

    #: 無圧縮。
    NONE = 3

    #: LZ4（ブロック形式）。任意依存。
    LZ4 = 4

    #: サードパーティ製サーバのカスタム方式。中身は解釈できない。
    CUSTOM = 127

    def id(self) -> int:
        """仕様が定める圧縮方式ID。"""
        return self.value

    def as_string(self) -> str:
        """適合性テストで言語間比較に使う識別子。"""
        return _COMPRESSION_LABELS[self]

    @staticmethod
    def from_id(value: int) -> "ChunkCompression":
        """圧縮方式IDから :class:`ChunkCompression` を得る。

        :raises SpringNbtError: 未知のIDの場合。
        """
        # 仕様が定めるのは 1・2・3・4・127 の 5 種類だけ
        for candidate in ChunkCompression:
            if candidate.value == value:
                return candidate

        raise SpringNbtError.malformed("未知の圧縮方式ID: %d" % value)


_COMPRESSION_LABELS = {
    ChunkCompression.GZIP: "gzip",
    ChunkCompression.ZLIB: "zlib",
    ChunkCompression.NONE: "none",
    ChunkCompression.LZ4: "lz4",
    ChunkCompression.CUSTOM: "custom",
}


class RegionFileMode(enum.Enum):
    """リージョンファイルを開くときの動作。"""

    #: 読み取り専用。書き込み系の操作はエラーになる。
    READ_ONLY = "read_only"

    #: 読み書き。ファイルが無ければ空のリージョンとして扱う。
    READ_WRITE = "read_write"


class RegionPos:
    """リージョンの座標。1リージョンは 32×32 チャンクを担当する。"""

    __slots__ = ("x", "z")

    def __init__(self, x: int, z: int) -> None:
        self.x = x
        self.z = z

    def file_name(self) -> str:
        """このリージョンのファイル名（``r.X.Z.mca``）。"""
        return "r.%d.%d.mca" % (self.x, self.z)

    @staticmethod
    def from_file_name(file_name: str) -> Optional["RegionPos"]:
        """``r.X.Z.mca`` 形式のファイル名から座標を得る。解釈できなければ None。"""
        matched = _REGION_NAME.match(file_name)

        if matched is None:
            return None

        return RegionPos(int(matched.group(1)), int(matched.group(2)))

    def __eq__(self, other) -> bool:
        if not isinstance(other, RegionPos):
            return False

        return other.x == self.x and other.z == self.z

    def __hash__(self) -> int:
        return hash((self.x, self.z))

    def __repr__(self) -> str:
        return "RegionPos(%d, %d)" % (self.x, self.z)


class ChunkPos:
    """チャンクの絶対座標。"""

    __slots__ = ("x", "z")

    def __init__(self, x: int, z: int) -> None:
        self.x = x
        self.z = z

    def region(self) -> RegionPos:
        """このチャンクを含むリージョンの座標。

        Python の ``>>`` は算術右シフトなので負の座標でも正しく求まる。
        """
        return RegionPos(self.x >> 5, self.z >> 5)

    def local_x(self) -> int:
        """リージョン内でのX位置 (0..31)。"""
        return self.x & 31

    def local_z(self) -> int:
        """リージョン内でのZ位置 (0..31)。"""
        return self.z & 31

    def index(self) -> int:
        """ロケーションテーブル内の添字 (0..1023)。"""
        return self.local_x() + (self.local_z() * 32)

    def __eq__(self, other) -> bool:
        if not isinstance(other, ChunkPos):
            return False

        return other.x == self.x and other.z == self.z

    def __hash__(self) -> int:
        return hash((self.x, self.z))

    def __repr__(self) -> str:
        return "ChunkPos(%d, %d)" % (self.x, self.z)


class RawChunk:
    """リージョンファイルに格納されたままの、圧縮済みチャンクデータ。

    本ライブラリが解釈できない圧縮方式（LZ4 未導入、カスタム方式）でも
    これなら取り出せる。バックアップや別ツールへの受け渡しに使う。
    """

    __slots__ = ("compression", "data", "external")

    def __init__(self, compression: ChunkCompression, data: bytes,
                 external: bool = False) -> None:
        self.compression = compression
        self.data = data
        self.external = external

    def __repr__(self) -> str:
        return "RawChunk(%s, %d バイト, external=%s)" % (
            self.compression.as_string(), len(self.data), self.external)


class RegionFile:
    """リージョンファイル 1 つ分。"""

    def __init__(self, path: str, mode: RegionFileMode, position: RegionPos,
                 data: bytearray) -> None:
        self._path = path
        self._directory = os.path.dirname(path)

        if self._directory == "":
            self._directory = "."

        self._mode = mode
        self._data = data
        self.region_x = position.x
        self.region_z = position.z
        self._offsets = [0] * _CHUNK_COUNT
        self._sector_counts = [0] * _CHUNK_COUNT
        self._timestamps = [0] * _CHUNK_COUNT
        self._dirty = False
        self._closed = False
        self._parse_header()

    # -- 生成 ---------------------------------------------------------------

    @staticmethod
    def open(path: str, mode: RegionFileMode = RegionFileMode.READ_ONLY) -> "RegionFile":
        """リージョンファイルを開く。

        :param path: ``r.X.Z.mca`` という名前のファイル。座標はファイル名から読み取る。
        :param mode: 読み取り専用か読み書きか。
        """
        position = RegionPos.from_file_name(os.path.basename(path))

        if position is None:
            raise SpringNbtError.invalid_argument(
                "リージョンファイル名として解釈できない: %s" % os.path.basename(path))

        if os.path.exists(path):
            try:
                with open(path, "rb") as handle:
                    raw = bytearray(handle.read())
            except OSError as error:
                raise SpringNbtError(ErrorCode.IO, "ファイルを読めない: %s" % path) from error
        elif mode == RegionFileMode.READ_WRITE:
            # 読み書きモードなら、存在しないファイルは空のリージョンとして扱う
            raw = bytearray(_HEADER_SECTORS * SECTOR_SIZE)
        else:
            raise SpringNbtError(ErrorCode.IO, "ファイルが存在しない: %s" % path)

        return RegionFile(path, mode, position, raw)

    def __enter__(self) -> "RegionFile":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    # -- ヘッダ -------------------------------------------------------------

    def _parse_header(self) -> None:
        """ヘッダを解析し、ロケーションとタイムスタンプを取り込む。"""
        # 空ファイルは「チャンクが 1 つも無いリージョン」として受け入れる
        if len(self._data) == 0:
            self._data = bytearray(_HEADER_SECTORS * SECTOR_SIZE)
            return

        if len(self._data) < _HEADER_SECTORS * SECTOR_SIZE:
            raise SpringNbtError.malformed(
                "ヘッダが足りない: %d バイト（最低 %d バイト必要）"
                % (len(self._data), _HEADER_SECTORS * SECTOR_SIZE))

        if len(self._data) % SECTOR_SIZE != 0:
            raise SpringNbtError.malformed(
                "ファイル長がセクタ境界に揃っていない: %d バイト" % len(self._data))

        total_sectors = len(self._data) // SECTOR_SIZE
        sector_owner: Dict[int, int] = {}

        # ロケーションテーブルの 1024 エントリを順に取り込む
        for index in range(_CHUNK_COUNT):
            entry = struct.unpack_from(">I", self._data, index * 4)[0]
            offset = entry >> 8
            count = entry & 0xFF

            self._timestamps[index] = struct.unpack_from(
                ">i", self._data, SECTOR_SIZE + (index * 4))[0]

            if offset == 0 and count == 0:
                continue

            if offset < _HEADER_SECTORS:
                raise SpringNbtError.malformed(
                    "チャンク %d のオフセットがヘッダ領域を指している: %d" % (index, offset))

            if count == 0:
                raise SpringNbtError.malformed(
                    "チャンク %d のセクタ数が 0 なのにオフセットが設定されている" % index)

            if offset + count > total_sectors:
                raise SpringNbtError.malformed(
                    "チャンク %d の割り当てがファイル外へはみ出している" % index)

            # 同じセクタを 2 つのチャンクが指していたら、どちらかが壊れている
            for sector in range(offset, offset + count):
                owner = sector_owner.get(sector)

                if owner is not None:
                    raise SpringNbtError.malformed(
                        "セクタ %d がチャンク %d とチャンク %d で重複している"
                        % (sector, owner, index))

                sector_owner[sector] = index

            self._offsets[index] = offset
            self._sector_counts[index] = count

    def _write_header(self) -> None:
        """ロケーションテーブルとタイムスタンプテーブルを先頭 2 セクタへ書き戻す。"""
        for index in range(_CHUNK_COUNT):
            entry = (self._offsets[index] << 8) | self._sector_counts[index]
            struct.pack_into(">I", self._data, index * 4, entry)
            struct.pack_into(">i", self._data, SECTOR_SIZE + (index * 4),
                             self._timestamps[index])

    # -- 補助 ---------------------------------------------------------------

    def _index_of(self, chunk_x: int, chunk_z: int) -> int:
        """指定した座標がこのリージョンの担当範囲にあるか確認し、添字を返す。"""
        position = ChunkPos(chunk_x, chunk_z)
        region = position.region()

        if region.x != self.region_x or region.z != self.region_z:
            raise SpringNbtError.invalid_argument(
                "チャンク (%d, %d) はリージョン (%d, %d) の担当外"
                % (chunk_x, chunk_z, self.region_x, self.region_z))

        return position.index()

    def _ensure_writable(self) -> None:
        if self._mode == RegionFileMode.READ_ONLY:
            raise SpringNbtError.invalid_argument("読み取り専用で開いたリージョンには書き込めない")

    def _ensure_open(self) -> None:
        if self._closed:
            raise SpringNbtError.invalid_argument("既に閉じられたリージョンファイル")

    # -- 参照 ---------------------------------------------------------------

    def has_chunk(self, chunk_x: int, chunk_z: int) -> bool:
        """チャンクが存在するか。"""
        self._ensure_open()
        return self._sector_counts[self._index_of(chunk_x, chunk_z)] > 0

    def chunk_positions(self) -> List[ChunkPos]:
        """存在するチャンクの座標を、ロケーションテーブルの並び順で返す。"""
        self._ensure_open()
        result = []

        # 添字の昇順に走査する（local_z が外、local_x が内）
        for index in range(_CHUNK_COUNT):
            if self._sector_counts[index] == 0:
                continue

            local_x = index % 32
            local_z = index // 32
            result.append(ChunkPos((self.region_x * 32) + local_x,
                                   (self.region_z * 32) + local_z))

        return result

    def timestamp(self, chunk_x: int, chunk_z: int) -> int:
        """チャンクの最終更新時刻（Unix 秒）。存在しなければ 0。"""
        self._ensure_open()
        return self._timestamps[self._index_of(chunk_x, chunk_z)]

    def set_timestamp(self, chunk_x: int, chunk_z: int, value: int) -> None:
        """チャンクの最終更新時刻を設定する。"""
        self._ensure_open()
        self._ensure_writable()
        self._timestamps[self._index_of(chunk_x, chunk_z)] = value
        self._dirty = True

    def read_chunk_raw(self, chunk_x: int, chunk_z: int) -> Optional[RawChunk]:
        """チャンクを圧縮されたまま取り出す。存在しなければ None。"""
        self._ensure_open()
        index = self._index_of(chunk_x, chunk_z)

        if self._sector_counts[index] == 0:
            return None

        start = self._offsets[index] * SECTOR_SIZE
        length = struct.unpack_from(">i", self._data, start)[0]
        scheme_byte = self._data[start + 4]

        if length < 1:
            raise SpringNbtError.malformed(
                "チャンク (%d, %d) の length が不正: %d" % (chunk_x, chunk_z, length))

        if 4 + length > self._sector_counts[index] * SECTOR_SIZE:
            raise SpringNbtError.malformed(
                "チャンク (%d, %d) の length が確保セクタ数を超えている" % (chunk_x, chunk_z))

        external = (scheme_byte & 0x80) != 0
        compression = ChunkCompression.from_id(scheme_byte & 0x7F)

        if external:
            # 最上位ビットが立っている場合、本体は c.X.Z.mcc にある
            return RawChunk(compression, self._read_external_file(chunk_x, chunk_z), True)

        return RawChunk(compression, bytes(self._data[start + 5:start + 4 + length]), False)

    def read_chunk(self, chunk_x: int, chunk_z: int) -> Optional[NbtCompound]:
        """チャンクを NBT として読む。存在しなければ None。"""
        raw = self.read_chunk_raw(chunk_x, chunk_z)

        if raw is None:
            return None

        plain = _decompress_chunk(raw)
        return read_nbt_bytes(plain, NbtReadOptions(compression=Compression.NONE)).tag

    # -- 書き込み -----------------------------------------------------------

    def write_chunk(self, chunk_x: int, chunk_z: int, tag: NbtCompound,
                    compression: ChunkCompression = ChunkCompression.ZLIB) -> None:
        """チャンクを NBT として書き込む。"""
        plain = write_nbt_bytes(NamedTag("", tag),
                                NbtWriteOptions(compression=Compression.NONE))
        self.write_chunk_raw(
            chunk_x, chunk_z, RawChunk(compression, _compress_chunk(plain, compression)))

    def write_chunk_raw(self, chunk_x: int, chunk_z: int, raw: RawChunk) -> None:
        """圧縮済みのチャンクをそのまま書き込む。"""
        self._ensure_open()
        self._ensure_writable()

        index = self._index_of(chunk_x, chunk_z)
        use_external = len(raw.data) > _MAX_INLINE_PAYLOAD

        if use_external:
            # 1MiB を超えるチャンクは外部ファイルへ退避し、リージョンには目印だけ残す
            self._write_external_file(chunk_x, chunk_z, raw.data)
            payload = b""
            scheme_byte = raw.compression.id() | 0x80
        else:
            self._delete_external_file(chunk_x, chunk_z)
            payload = raw.data
            scheme_byte = raw.compression.id()

        needed = (4 + 1 + len(payload) + SECTOR_SIZE - 1) // SECTOR_SIZE

        if needed > _MAX_SECTORS:
            raise SpringNbtError.invalid_argument(
                "チャンクが大きすぎる: %d セクタ（上限 %d）" % (needed, _MAX_SECTORS))

        start = self._allocate_sectors(index, needed)

        # 確保した領域をゼロで埋めてから書く（前の内容を残さないため）
        for offset in range(start * SECTOR_SIZE, (start + needed) * SECTOR_SIZE):
            self._data[offset] = 0

        position = start * SECTOR_SIZE
        struct.pack_into(">i", self._data, position, 1 + len(payload))
        self._data[position + 4] = scheme_byte
        self._data[position + 5:position + 5 + len(payload)] = payload

        self._offsets[index] = start
        self._sector_counts[index] = needed
        self._timestamps[index] = int(time.time())
        self._dirty = True

    def delete_chunk(self, chunk_x: int, chunk_z: int) -> bool:
        """チャンクを削除する。削除できたら True。"""
        self._ensure_open()
        self._ensure_writable()

        index = self._index_of(chunk_x, chunk_z)

        if self._sector_counts[index] == 0:
            return False

        self._delete_external_file(chunk_x, chunk_z)
        self._offsets[index] = 0
        self._sector_counts[index] = 0
        self._timestamps[index] = 0
        self._dirty = True
        return True

    def _allocate_sectors(self, index: int, needed: int) -> int:
        """必要なセクタ数を確保し、開始セクタ番号を返す。

        既存の割り当てがちょうど同じ大きさならその場を使い、
        そうでなければ先頭から空き領域を探し、無ければ末尾へ追加する。
        """
        # 大きさが変わらないなら動かさない。触っていないチャンクの配置を保つため
        if self._sector_counts[index] == needed:
            return self._offsets[index]

        used = self._build_sector_usage(index)
        total_sectors = len(self._data) // SECTOR_SIZE
        run = 0

        # 先頭から連続した空き領域を探す
        for sector in range(_HEADER_SECTORS, total_sectors):
            if used[sector]:
                run = 0
                continue

            run += 1

            if run == needed:
                return sector - needed + 1

        # 見つからなければ末尾へ追加する。末尾の空きは再利用できる
        start = total_sectors - run
        self._resize((start + needed) * SECTOR_SIZE)
        return start

    def _build_sector_usage(self, ignore_index: int) -> List[bool]:
        """セクタの使用状況を作る。``ignore_index`` のチャンクは空きとして扱う。"""
        total_sectors = len(self._data) // SECTOR_SIZE
        used = [False] * total_sectors

        # ヘッダの 2 セクタは常に使用中
        for sector in range(min(_HEADER_SECTORS, total_sectors)):
            used[sector] = True

        # 他のチャンクが占めているセクタに印を付ける
        for other in range(_CHUNK_COUNT):
            if other == ignore_index or self._sector_counts[other] == 0:
                continue

            start = self._offsets[other]

            for sector in range(start, start + self._sector_counts[other]):
                if sector < total_sectors:
                    used[sector] = True

        return used

    def optimize(self) -> None:
        """全チャンクを隙間なく詰め直す。断片化したファイルを縮めたいときに使う。"""
        self._ensure_open()
        self._ensure_writable()

        collected = []

        # 先に全チャンクを取り出してから、新しい配置で書き直す
        for index in range(_CHUNK_COUNT):
            if self._sector_counts[index] == 0:
                continue

            local_x = index % 32
            local_z = index // 32
            raw = self.read_chunk_raw((self.region_x * 32) + local_x,
                                      (self.region_z * 32) + local_z)

            if raw is not None:
                collected.append((index, raw))

        saved_timestamps = list(self._timestamps)
        self._data = bytearray(_HEADER_SECTORS * SECTOR_SIZE)
        self._offsets = [0] * _CHUNK_COUNT
        self._sector_counts = [0] * _CHUNK_COUNT

        next_sector = _HEADER_SECTORS

        # 添字の昇順に、先頭から詰めて配置する
        for index, raw in collected:
            if raw.external:
                payload = b""
                scheme_byte = raw.compression.id() | 0x80
            else:
                payload = raw.data
                scheme_byte = raw.compression.id()

            needed = (4 + 1 + len(payload) + SECTOR_SIZE - 1) // SECTOR_SIZE
            self._resize((next_sector + needed) * SECTOR_SIZE)

            position = next_sector * SECTOR_SIZE
            struct.pack_into(">i", self._data, position, 1 + len(payload))
            self._data[position + 4] = scheme_byte
            self._data[position + 5:position + 5 + len(payload)] = payload

            self._offsets[index] = next_sector
            self._sector_counts[index] = needed
            next_sector += needed

        self._timestamps = saved_timestamps
        self._dirty = True

    def _resize(self, length: int) -> None:
        if len(self._data) >= length:
            return

        self._data.extend(bytearray(length - len(self._data)))

    # -- 出力 ---------------------------------------------------------------

    def flush(self) -> None:
        """変更をファイルへ書き出す。"""
        self._ensure_open()

        if self._mode == RegionFileMode.READ_ONLY:
            return

        self._write_header()

        try:
            with open(self._path, "wb") as handle:
                handle.write(self._data)
        except OSError as error:
            raise SpringNbtError(ErrorCode.IO, "ファイルへ書けない: %s" % self._path) from error

        self._dirty = False

    def to_bytes(self) -> bytes:
        """現在の内容をバイト列として組み立てる。ファイルには書かない。"""
        self._ensure_open()
        self._write_header()
        return bytes(self._data)

    def close(self) -> None:
        """変更があれば書き出してから閉じる。"""
        if self._closed:
            return

        if self._dirty and self._mode == RegionFileMode.READ_WRITE:
            self.flush()

        self._closed = True

    # -- 外部ファイル (.mcc) ------------------------------------------------

    def _external_path(self, chunk_x: int, chunk_z: int) -> str:
        return os.path.join(self._directory, "c.%d.%d.mcc" % (chunk_x, chunk_z))

    def _read_external_file(self, chunk_x: int, chunk_z: int) -> bytes:
        external = self._external_path(chunk_x, chunk_z)

        if not os.path.exists(external):
            raise SpringNbtError(
                ErrorCode.MALFORMED_DATA, "外部チャンクファイルが無い: %s" % external)

        try:
            with open(external, "rb") as handle:
                return handle.read()
        except OSError as error:
            raise SpringNbtError(
                ErrorCode.IO, "外部チャンクファイルを読めない: %s" % external) from error

    def _write_external_file(self, chunk_x: int, chunk_z: int, payload: bytes) -> None:
        external = self._external_path(chunk_x, chunk_z)

        try:
            with open(external, "wb") as handle:
                handle.write(payload)
        except OSError as error:
            raise SpringNbtError(
                ErrorCode.IO, "外部チャンクファイルへ書けない: %s" % external) from error

    def _delete_external_file(self, chunk_x: int, chunk_z: int) -> None:
        external = self._external_path(chunk_x, chunk_z)

        # 縮んで内部へ戻ったチャンクの残骸を消す
        if os.path.exists(external):
            try:
                os.remove(external)
            except OSError as error:
                raise SpringNbtError(
                    ErrorCode.IO, "外部チャンクファイルを削除できない: %s" % external) from error


def _decompress_chunk(raw: RawChunk) -> bytes:
    """圧縮済みペイロードを展開する。"""
    if raw.compression == ChunkCompression.NONE:
        return raw.data

    if raw.compression == ChunkCompression.GZIP:
        try:
            return gzip.decompress(raw.data)
        except OSError as error:
            raise SpringNbtError(
                ErrorCode.MALFORMED_DATA, "チャンクの圧縮データを展開できない") from error

    if raw.compression == ChunkCompression.ZLIB:
        try:
            return zlib.decompress(raw.data)
        except zlib.error as error:
            raise SpringNbtError(
                ErrorCode.MALFORMED_DATA, "チャンクの圧縮データを展開できない") from error

    raise SpringNbtError.unsupported_feature(
        "%s 圧縮のチャンクは扱えない。生バイトAPI (read_chunk_raw) を使うこと"
        % raw.compression.as_string())


def _compress_chunk(plain: bytes, compression: ChunkCompression) -> bytes:
    """ペイロードを指定の方式で圧縮する。"""
    if compression == ChunkCompression.NONE:
        return plain

    if compression == ChunkCompression.GZIP:
        # mtime を 0 に固定して、同じ入力から同じバイト列が出るようにする
        return gzip.compress(plain, mtime=0)

    if compression == ChunkCompression.ZLIB:
        return zlib.compress(plain, 9)

    raise SpringNbtError.unsupported_feature(
        "この圧縮方式では書き込めない: %s" % compression.as_string())

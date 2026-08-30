"""Anvil リージョンファイルの読み書き。

仕様: docs/spec/20-anvil-region.md

他言語版と同じ検証項目を持つ。
共通テストベクタによる言語間比較は spec/run-conformance.sh が担当し、
ここでは API の振る舞いを直接確かめる。
"""

from __future__ import annotations

import os
import shutil

import pytest

from spring_nbt_library import TARGET_DATA_VERSION, ErrorCode, SpringNbtError
from spring_nbt_library.anvil import (
    SECTOR_SIZE,
    ChunkCompression,
    ChunkPos,
    RegionFile,
    RegionFileMode,
    RegionFolder,
    RegionPos,
)
from spring_nbt_library.nbt import NbtByteArray, NbtCompound, NbtInt, NbtString

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VECTORS = os.path.join(REPO_ROOT, "spec", "testdata", "anvil")


def vector_dir(name: str) -> str:
    """共通テストベクタのディレクトリ。"""
    path = os.path.join(VECTORS, name)

    if not os.path.isdir(path):
        raise AssertionError("テストベクタが見つからない: anvil/%s" % name)

    return path


@pytest.fixture
def work(tmp_path):
    """テストごとの一時ディレクトリ。"""
    return str(tmp_path)


def copy_vector(name: str, work: str) -> str:
    """ベクタを一時ディレクトリへ複製し、書き込みテストで原本を汚さないようにする。"""
    destination = os.path.join(work, name)
    shutil.copytree(vector_dir(name), destination)
    return destination


def sample_chunk(x: int, z: int) -> NbtCompound:
    chunk = NbtCompound()
    chunk.set("DataVersion", NbtInt(TARGET_DATA_VERSION))
    chunk.set("xPos", NbtInt(x))
    chunk.set("zPos", NbtInt(z))
    chunk.set("yPos", NbtInt(-4))
    chunk.set("Status", NbtString("minecraft:full"))
    return chunk


def incompressible(length: int):
    """圧縮しても縮まないバイト列を作る。サイズの制御が効くようにするため。"""
    result = []
    state = 0x12345678

    # 線形合同法で疑似乱数を作る。テストの再現性を保つため固定の種を使う
    for _ in range(length):
        state = ((state * 1664525) + 1013904223) & 0xFFFFFFFF
        value = state >> 24

        if value >= 128:
            value -= 256

        result.append(value)

    return result


# ---------------------------------------------------------------------------
# 座標計算
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("chunk_x,chunk_z,region_x,region_z,local_x,local_z", [
    (0, 0, 0, 0, 0, 0),
    (31, 31, 0, 0, 31, 31),
    (32, 32, 1, 1, 0, 0),
    (-1, -1, -1, -1, 31, 31),
    (-32, -32, -1, -1, 0, 0),
    (-33, -33, -2, -2, 31, 31),
])
def test_chunk_position_math_handles_negative_coordinates(
        chunk_x, chunk_z, region_x, region_z, local_x, local_z):
    position = ChunkPos(chunk_x, chunk_z)

    # 算術右シフトなので負の座標でも正しく求まる
    assert position.region() == RegionPos(region_x, region_z)
    assert position.local_x() == local_x
    assert position.local_z() == local_z
    assert position.index() == local_x + local_z * 32


def test_region_file_name_roundtrips():
    assert RegionPos(-1, 2).file_name() == "r.-1.2.mca"
    assert RegionPos.from_file_name("r.-1.2.mca") == RegionPos(-1, 2)

    # 形式が違うものは受け付けない
    assert RegionPos.from_file_name("r.0.0.mcr") is None
    assert RegionPos.from_file_name("region.mca") is None
    assert RegionPos.from_file_name("r.a.0.mca") is None


# ---------------------------------------------------------------------------
# 読み込み
# ---------------------------------------------------------------------------


def test_empty_region_has_no_chunks():
    with RegionFile.open(os.path.join(vector_dir("empty"), "r.0.0.mca")) as region:
        assert region.chunk_positions() == []
        assert not region.has_chunk(0, 0)
        assert region.read_chunk(0, 0) is None


def test_reads_single_chunk():
    with RegionFile.open(os.path.join(vector_dir("single_chunk"), "r.0.0.mca")) as region:
        assert region.chunk_positions() == [ChunkPos(0, 0)]
        assert region.has_chunk(0, 0)

        chunk = region.read_chunk(0, 0)
        assert chunk.get_int("DataVersion") == TARGET_DATA_VERSION
        assert chunk.get_string("Status") == "minecraft:full"
        assert region.timestamp(0, 0) == 1700000000


def test_reads_every_compression_scheme():
    with RegionFile.open(os.path.join(vector_dir("mixed_compression"), "r.0.0.mca")) as region:
        assert region.read_chunk_raw(0, 0).compression == ChunkCompression.GZIP
        assert region.read_chunk_raw(1, 0).compression == ChunkCompression.ZLIB
        assert region.read_chunk_raw(2, 0).compression == ChunkCompression.NONE

        # 方式が違っても中身は同じように読める
        for x in range(3):
            assert region.read_chunk(x, 0).get_int("xPos") == x


def test_reads_lz4_chunks():
    with RegionFile.open(os.path.join(vector_dir("lz4"), "r.0.0.mca")) as region:
        # 1 ブロック / 2 ブロック連結 / 無圧縮ブロック / 重なりのあるマッチ
        for x in range(4):
            assert region.read_chunk_raw(x, 0).compression == ChunkCompression.LZ4
            assert region.read_chunk(x, 0).get_int("xPos") == x

        # 同じバイトの繰り返しは、重なりのあるマッチとして詰められている
        assert region.read_chunk(3, 0).get_string("filler") == "A" * 4000


def test_rejects_lz4_block_with_broken_magic():
    with RegionFile.open(os.path.join(vector_dir("lz4_bad_magic"), "r.0.0.mca")) as region:
        with pytest.raises(SpringNbtError) as error:
            region.read_chunk(0, 0)

        assert error.value.code == ErrorCode.MALFORMED_DATA


def test_writing_lz4_is_rejected(tmp_path):
    path = os.path.join(copy_vector("lz4", tmp_path), "r.0.0.mca")

    with RegionFile.open(path, RegionFileMode.READ_WRITE) as region:
        # LZ4 は読み込みのみ対応なので、圧縮して書き出すことはできない
        chunk = region.read_chunk(0, 0)

        with pytest.raises(SpringNbtError) as error:
            region.write_chunk(0, 0, chunk, ChunkCompression.LZ4)

        assert error.value.code == ErrorCode.UNSUPPORTED_FEATURE


def test_untouched_lz4_chunks_keep_their_compression(tmp_path):
    path = os.path.join(copy_vector("lz4", tmp_path), "r.0.0.mca")

    with open(path, "rb") as handle:
        before = handle.read()

    # 触らずに閉じるだけ。生バイトを素通しするので LZ4 のまま残る
    with RegionFile.open(path, RegionFileMode.READ_WRITE):
        pass

    with open(path, "rb") as handle:
        assert handle.read() == before


def test_reads_chunk_stored_in_external_file():
    with RegionFile.open(os.path.join(vector_dir("external_mcc"), "r.0.0.mca")) as region:
        raw = region.read_chunk_raw(0, 0)
        assert raw.external
        assert raw.compression == ChunkCompression.ZLIB
        assert region.read_chunk(0, 0).get_string("Status") == "minecraft:full"


@pytest.mark.parametrize("vector", [
    "bad_offset",
    "overlapping_sectors",
    "unaligned_length",
    "offset_out_of_file",
])
def test_broken_headers_are_rejected(vector):
    with pytest.raises(SpringNbtError) as info:
        RegionFile.open(os.path.join(vector_dir(vector), "r.0.0.mca"))

    assert info.value.code == ErrorCode.MALFORMED_DATA


def test_chunk_outside_the_region_is_rejected():
    with RegionFile.open(os.path.join(vector_dir("empty"), "r.0.0.mca")) as region:
        # r.0.0 が担当するのは 0..31 の範囲だけ
        with pytest.raises(SpringNbtError) as info:
            region.has_chunk(32, 0)

        assert info.value.code == ErrorCode.INVALID_ARGUMENT


def test_read_only_region_rejects_writes():
    with RegionFile.open(os.path.join(vector_dir("empty"), "r.0.0.mca")) as region:
        with pytest.raises(SpringNbtError) as info:
            region.write_chunk(0, 0, sample_chunk(0, 0))

        assert info.value.code == ErrorCode.INVALID_ARGUMENT


# ---------------------------------------------------------------------------
# 書き込み
# ---------------------------------------------------------------------------


def test_opening_and_flushing_without_changes_keeps_bytes_identical(work):
    # 触っていないチャンクの配置を保つことが、既存ワールドを壊さない前提になる
    directory = copy_vector("fragmented", work)
    path = os.path.join(directory, "r.0.0.mca")

    with open(path, "rb") as handle:
        original = handle.read()

    with RegionFile.open(path, RegionFileMode.READ_WRITE) as region:
        region.flush()

    with open(path, "rb") as handle:
        assert handle.read() == original


def test_writes_and_reads_back_a_chunk(work):
    path = os.path.join(work, "r.0.0.mca")

    with RegionFile.open(path, RegionFileMode.READ_WRITE) as region:
        region.write_chunk(3, 4, sample_chunk(3, 4))
        region.flush()

    with RegionFile.open(path) as reopened:
        assert reopened.has_chunk(3, 4)
        assert reopened.read_chunk(3, 4).get_int("xPos") == 3

    # 書き出したファイルは必ずセクタ境界に揃う
    assert os.path.getsize(path) % SECTOR_SIZE == 0


def test_rewriting_the_same_size_keeps_the_chunk_in_place(work):
    directory = copy_vector("fragmented", work)
    path = os.path.join(directory, "r.0.0.mca")
    original_length = os.path.getsize(path)

    with RegionFile.open(path, RegionFileMode.READ_WRITE) as region:
        # 同じ内容を書き直すので、必要セクタ数は変わらない
        region.write_chunk(0, 0, region.read_chunk(0, 0))
        region.flush()

    # その場で上書きされるので、ファイルは伸びない
    assert os.path.getsize(path) == original_length

    with RegionFile.open(path) as reopened:
        assert len(reopened.chunk_positions()) == 3


def test_growing_chunk_is_relocated_without_breaking_others(work):
    directory = copy_vector("fragmented", work)
    path = os.path.join(directory, "r.0.0.mca")

    # 5 セクタぶんになる大きなチャンクを作る
    big = sample_chunk(0, 0)
    big.set("filler", NbtByteArray(incompressible(5 * SECTOR_SIZE)))

    with RegionFile.open(path, RegionFileMode.READ_WRITE) as region:
        region.write_chunk(0, 0, big)
        region.flush()

    with RegionFile.open(path) as reopened:
        # 動かした結果、他の 2 チャンクが壊れていないこと
        assert len(reopened.chunk_positions()) == 3
        assert reopened.read_chunk(5, 3).get_int("xPos") == 5
        assert reopened.read_chunk(31, 31).get_int("xPos") == 31
        assert len(reopened.read_chunk(0, 0).get_byte_array("filler")) == 5 * SECTOR_SIZE


def test_deleted_chunk_disappears_and_others_survive(work):
    directory = copy_vector("fragmented", work)
    path = os.path.join(directory, "r.0.0.mca")

    with RegionFile.open(path, RegionFileMode.READ_WRITE) as region:
        assert region.delete_chunk(5, 3)
        assert not region.delete_chunk(5, 3)
        region.flush()

    with RegionFile.open(path) as reopened:
        assert not reopened.has_chunk(5, 3)
        assert reopened.timestamp(5, 3) == 0
        assert len(reopened.chunk_positions()) == 2


def test_freed_sectors_are_reused(work):
    directory = copy_vector("fragmented", work)
    path = os.path.join(directory, "r.0.0.mca")
    original_length = os.path.getsize(path)

    with RegionFile.open(path, RegionFileMode.READ_WRITE) as region:
        region.delete_chunk(5, 3)
        region.write_chunk(7, 7, sample_chunk(7, 7))
        region.flush()

    # 空いたセクタへ収まるので、ファイルは伸びない
    assert os.path.getsize(path) == original_length

    with RegionFile.open(path) as reopened:
        assert reopened.read_chunk(7, 7).get_int("xPos") == 7


def test_optimize_compacts_the_file(work):
    directory = copy_vector("fragmented", work)
    path = os.path.join(directory, "r.0.0.mca")
    original_length = os.path.getsize(path)

    with RegionFile.open(path, RegionFileMode.READ_WRITE) as region:
        region.optimize()
        region.flush()

    optimized_length = os.path.getsize(path)

    # 隙間が詰まるぶん小さくなる
    assert optimized_length < original_length
    assert optimized_length % SECTOR_SIZE == 0

    with RegionFile.open(path) as reopened:
        assert len(reopened.chunk_positions()) == 3
        assert reopened.timestamp(0, 0) == 1700000000
        assert reopened.read_chunk(31, 31).get_int("xPos") == 31


def test_huge_chunk_goes_to_external_file_and_comes_back(work):
    path = os.path.join(work, "r.0.0.mca")

    # 1MiB を超えるよう、圧縮の効かないデータを詰める
    huge = sample_chunk(1, 2)
    huge.set("filler", NbtByteArray(incompressible(1200 * 1024)))

    with RegionFile.open(path, RegionFileMode.READ_WRITE) as region:
        region.write_chunk(1, 2, huge, ChunkCompression.NONE)
        region.flush()

    external = os.path.join(work, "c.1.2.mcc")
    assert os.path.exists(external), "外部ファイルへ退避されていない"

    with RegionFile.open(path) as reopened:
        assert reopened.read_chunk_raw(1, 2).external
        assert len(reopened.read_chunk(1, 2).get_byte_array("filler")) == 1200 * 1024

    # 小さく書き直すと内部へ戻り、外部ファイルは消える
    with RegionFile.open(path, RegionFileMode.READ_WRITE) as region:
        region.write_chunk(1, 2, sample_chunk(1, 2))
        region.flush()

    assert not os.path.exists(external), "内部へ戻ったのに外部ファイルが残っている"

    with RegionFile.open(path) as final:
        assert not final.read_chunk_raw(1, 2).external


def test_timestamp_can_be_set_explicitly(work):
    path = os.path.join(work, "r.0.0.mca")

    with RegionFile.open(path, RegionFileMode.READ_WRITE) as region:
        region.write_chunk(0, 0, sample_chunk(0, 0))
        region.set_timestamp(0, 0, 1234567890)
        region.flush()

    with RegionFile.open(path) as reopened:
        assert reopened.timestamp(0, 0) == 1234567890


# ---------------------------------------------------------------------------
# RegionFolder
# ---------------------------------------------------------------------------


def test_folder_resolves_chunks_across_regions(work):
    with RegionFolder.open(work, RegionFileMode.READ_WRITE) as folder:
        folder.write_chunk(0, 0, sample_chunk(0, 0))
        folder.write_chunk(-1, -1, sample_chunk(-1, -1))
        folder.write_chunk(40, 40, sample_chunk(40, 40))
        folder.flush()

    # 3 つの異なるリージョンへ振り分けられる
    for name in ["r.0.0.mca", "r.-1.-1.mca", "r.1.1.mca"]:
        assert os.path.exists(os.path.join(work, name))

    with RegionFolder.open(work) as reopened:
        assert len(reopened.region_positions()) == 3
        assert len(reopened.chunk_positions()) == 3
        assert reopened.read_chunk(-1, -1).get_int("xPos") == -1
        assert reopened.read_chunk(100, 100) is None
        assert not reopened.has_chunk(100, 100)


def test_キャッシュ上限を超えると古いリージョンから閉じる(work):
    """RegionFile はファイル全体をメモリへ載せるので、上限が要る。"""
    # 上限 2 で 4 リージョンへ書く。古いものは閉じられるが内容は失われない
    with RegionFolder.open(work, RegionFileMode.READ_WRITE, max_cached_regions=2) as folder:
        for region in range(4):
            folder.write_chunk(region * 32, 0, sample_chunk(region * 32, 0))
            assert folder.cached_region_count <= 2

        folder.flush()

    # 追い出されたリージョンも、書き出されてから閉じられている
    with RegionFolder.open(work) as reopened:
        assert len(reopened.region_positions()) == 4

        for region in range(4):
            assert reopened.read_chunk(region * 32, 0).get_int("xPos") == region * 32


def test_キャッシュ上限が0以下ならINVALID_ARGUMENT(work):
    with pytest.raises(SpringNbtError) as error:
        RegionFolder.open(work, RegionFileMode.READ_ONLY, max_cached_regions=0)

    assert error.value.code == ErrorCode.INVALID_ARGUMENT

#!/usr/bin/env python3
"""実ワールドを読み取り専用で走査し、実データ耐性を確かめる。

合成のテストベクタだけでは、実際の Minecraft が書き出すデータの網羅性に届かない。
このツールは手元のワールドを丸ごと読んで、次を確認する。

  1. すべての `.dat` / `.nbt` を読み、ラウンドトリップ（読む→書く→バイト一致）を検証
  2. すべての `.mca` のヘッダを解析し、全チャンクを展開して NBT として読み、同じく検証
  3. 使われている圧縮方式・チャンク構造の統計を出す（仕様書とのズレを見つけるため）
  4. World レイヤ（`MinecraftWorld` / `Chunk` / `PalettedContainer`）で解釈し直し、
     NBT へ書き戻したものが元と一致するか、ブロックが読み出せるかを検証

**このツールは一切書き込まない。** 引数のワールドは読み取りのみで開く。
とはいえ Minecraft が起動していない状態で実行すること（書き込み途中を読む可能性があるため）。

使い方:
    python3 spec/tools/scan_world.py "<ワールドのパス>"
    python3 spec/tools/scan_world.py "<ワールドのパス>" --verbose

仕様: docs/spec/90-conformance.md
"""

from __future__ import annotations

import argparse
import gzip
import os
import struct
import sys
import zlib
from collections import Counter

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "python", "src"))

from spring_nbt_library import SpringNbtError  # noqa: E402
from spring_nbt_library.anvil import RegionFile, RegionFileMode  # noqa: E402
from spring_nbt_library.nbt import (  # noqa: E402
    Compression,
    NamedTag,
    NbtCompound,
    NbtReadOptions,
    NbtWriteOptions,
    read_bytes,
    write_bytes,
)
from spring_nbt_library.world import (  # noqa: E402
    Chunk,
    ChunkReadOptions,
    ChunkWriteOptions,
    MinecraftWorld,
    VersionMismatchAction,
    WorldOpenOptions,
)

#: リージョンファイルのセクタ長。
SECTOR = 4096

READ_OPTIONS = NbtReadOptions(compression=Compression.NONE)
WRITE_OPTIONS = NbtWriteOptions(compression=Compression.NONE)


class Scanner:
    """走査の状態と結果をまとめて持つ。"""

    def __init__(self, verbose: bool) -> None:
        self.verbose = verbose
        self.stats = Counter()
        self.failures = []
        self.root_keys = Counter()
        self.chunk_keys = Counter()
        self.section_keys = Counter()
        self.entity_keys = Counter()
        self.poi_keys = Counter()
        self.data_versions = Counter()
        self.chunk_statuses = Counter()
        self.palette_shapes = Counter()

    # -- 検証 ---------------------------------------------------------------

    def check_roundtrip(self, label: str, plain: bytes):
        """展開済みバイト列を読み、書き戻して一致するか確かめる。"""
        try:
            named = read_bytes(plain, READ_OPTIONS)
        except SpringNbtError as error:
            self.failures.append("%s: 読めない -> %s" % (label, error))
            return None

        try:
            encoded = write_bytes(named, WRITE_OPTIONS)
        except SpringNbtError as error:
            self.failures.append("%s: 書けない -> %s" % (label, error))
            return named

        if encoded != plain:
            self.failures.append(
                "%s: ラウンドトリップでバイトが変わった (%d -> %d)"
                % (label, len(plain), len(encoded)))
            return named

        self.stats["roundtrip_ok"] += 1
        return named

    # -- .dat / .nbt --------------------------------------------------------

    def scan_nbt_file(self, path: str, label: str) -> None:
        with open(path, "rb") as handle:
            raw = handle.read()

        try:
            plain, method = decompress_any(raw)
        except Exception as error:  # noqa: BLE001
            self.failures.append("%s: 展開できない -> %s" % (label, error))
            return

        self.stats["nbt_files"] += 1
        self.stats["nbt_compression_" + method] += 1

        named = self.check_roundtrip(label, plain)

        if named is None:
            return

        for key in named.tag.keys():
            self.root_keys[key] += 1

        version = named.tag.opt_int("DataVersion")
        if version is not None:
            self.data_versions[version] += 1

    # -- .mca ---------------------------------------------------------------

    def scan_region_file(self, path: str, label: str, kind: str) -> None:
        """リージョンファイルをライブラリで開き、全チャンクを検証する。"""
        try:
            region = RegionFile.open(path, RegionFileMode.READ_ONLY)
        except SpringNbtError as error:
            self.failures.append("%s: 開けない -> %s" % (label, error))
            return

        self.stats["region_files"] += 1

        # 開いて何も変えずに書き戻した結果が原本と一致すること。
        # 「触っていないチャンクの配置を保つ」という約束を実データで確かめる部分
        with open(path, "rb") as handle:
            original = handle.read()

        if region.to_bytes() != original:
            self.failures.append("%s: 無変更で書き戻すとバイトが変わる" % label)

        for position in region.chunk_positions():
            self.stats["chunks_present"] += 1
            where = "%s [%d,%d]" % (label, position.x, position.z)

            try:
                raw = region.read_chunk_raw(position.x, position.z)
            except SpringNbtError as error:
                self.failures.append("%s: 生データを取り出せない -> %s" % (where, error))
                continue

            if raw is None:
                continue

            self.stats["chunk_compression_%d" % raw.compression.id()] += 1

            if raw.external:
                self.stats["chunk_external_mcc"] += 1

            try:
                named = read_bytes(
                    _decompress_for_scan(raw), READ_OPTIONS)
            except SpringNbtError as error:
                self.failures.append("%s: 読めない -> %s" % (where, error))
                continue

            plain = _decompress_for_scan(raw)

            try:
                encoded = write_bytes(named, WRITE_OPTIONS)
            except SpringNbtError as error:
                self.failures.append("%s: 書けない -> %s" % (where, error))
                continue

            if encoded != plain:
                self.failures.append(
                    "%s: ラウンドトリップでバイトが変わった (%d -> %d)"
                    % (where, len(plain), len(encoded)))
                continue

            self.stats["roundtrip_ok"] += 1
            self.collect_chunk_stats(named.tag, kind)

        region.close()

    # -- 統計 ---------------------------------------------------------------

    def collect_chunk_stats(self, root: NbtCompound, kind: str) -> None:
        """チャンクの構造を集計する。仕様書と実データのズレを見つけるため。"""
        version = root.opt_int("DataVersion")

        if version is not None:
            self.data_versions[version] += 1

        if kind == "entities":
            for key in root.keys():
                self.entity_keys[key] += 1
            return

        if kind == "poi":
            for key in root.keys():
                self.poi_keys[key] += 1
            return

        for key in root.keys():
            self.chunk_keys[key] += 1

        status = root.opt_string("Status")
        if status is not None:
            self.chunk_statuses[status] += 1

        sections = root.opt_list("sections")
        if sections is None:
            return

        for section in sections:
            if not isinstance(section, NbtCompound):
                continue

            for key in section.keys():
                self.section_keys[key] += 1

            self.check_paletted_container(section, "block_states", 4096, 4)
            self.check_paletted_container(section, "biomes", 64, 1)

    def check_paletted_container(self, section: NbtCompound, key: str,
                                 entry_count: int, min_bits: int) -> None:
        """パレットの長さから求めたビット幅と、実際の data 長が一致するか確かめる。

        仕様 31 の計算式が実データに合っているかを直接検証する部分。
        """
        container = section.opt_compound(key)

        if container is None:
            return

        palette = container.opt_list("palette")

        if palette is None:
            self.failures.append("%s に palette が無い" % key)
            return

        bits = max(min_bits, ceil_log2(len(palette)))
        values_per_long = 64 // bits
        expected = (entry_count + values_per_long - 1) // values_per_long

        data = container.opt_long_array("data")

        if data is None:
            # パレットが 1 要素なら data は無くてよい
            if len(palette) != 1:
                self.failures.append(
                    "%s: palette=%d なのに data が無い" % (key, len(palette)))
            else:
                self.palette_shapes["%s palette=1 (data無し)" % key] += 1
            return

        if len(data) != expected:
            self.failures.append(
                "%s: palette=%d bits=%d なら data は %d long のはずだが %d long"
                % (key, len(palette), bits, expected, len(data)))
            return

        self.palette_shapes["%s bits=%d data=%d long" % (key, bits, len(data))] += 1

    # -- 出力 ---------------------------------------------------------------

    def report(self) -> int:
        print("=" * 72)
        print("走査結果")
        print("=" * 72)

        for key in sorted(self.stats):
            print("  %-34s %d" % (key, self.stats[key]))

        print()
        print("DataVersion: %s" % dict(self.data_versions))

        sections = [
            ("*.dat / *.nbt のルート直下キー", self.root_keys),
            ("チャンク (region) のルート直下キー", self.chunk_keys),
            ("セクションのキー", self.section_keys),
            ("entities チャンクのキー", self.entity_keys),
            ("poi チャンクのキー", self.poi_keys),
            ("Status", self.chunk_statuses),
        ]

        for title, counter in sections:
            if len(counter) == 0:
                continue

            print()
            print("--- %s ---" % title)
            limit = len(counter)

            if not self.verbose:
                limit = 25

            for key, count in counter.most_common(limit):
                print("  %-44s %d" % (key, count))

        if self.verbose and len(self.palette_shapes) > 0:
            print()
            print("--- パレットとビット幅の組み合わせ ---")
            for key, count in self.palette_shapes.most_common():
                print("  %-44s %d" % (key, count))

        print()

        if len(self.failures) > 0:
            print("!!! 失敗 %d 件 !!!" % len(self.failures))

            for failure in self.failures[:40]:
                print("  - %s" % failure)

            if len(self.failures) > 40:
                print("  … 他 %d 件" % (len(self.failures) - 40))

            return 1

        print("失敗なし。すべて読み込み・ラウンドトリップ成功。")
        return 0




class WorldScanner:
    """World レイヤを通してワールドを読み直し、解釈が正しいかを確かめる。

    Anvil レイヤの走査は「NBT として読めるか」までしか見ない。
    ここではさらに `Chunk` / `PalettedContainer` を通して、
    パレットとビット詰めの解釈・再エンコードが元データと一致するかを確認する。
    """

    #: 全ブロックを 1 つずつ読む対象のチャンク数の既定値。全チャンクだと時間がかかりすぎる。
    DEFAULT_BLOCK_SAMPLE = 40

    def __init__(self, verbose: bool, block_sample: int) -> None:
        self.verbose = verbose
        self.block_sample = block_sample
        self.stats = Counter()
        self.failures = []
        self.blocks = Counter()
        self.biomes = Counter()
        self.dimensions = []

    def scan(self, directory: str) -> None:
        """ワールドを読み取り専用で開いて走査する。"""
        # writable=False なので、この先どの経路でも書き込みは起きない
        world = MinecraftWorld.open(directory, WorldOpenOptions(writable=False))

        try:
            self._scan_level(world)

            # 次元ごとに、地形チャンクをすべて解釈し直す
            for dimension_id in world.dimension_ids():
                self.dimensions.append(dimension_id)
                dimension = world.dimension(dimension_id)

                if dimension is None:
                    self.failures.append("%s: 次元を開けない" % dimension_id)
                    continue

                self._scan_dimension(dimension_id, dimension)
        finally:
            world.close()

    def _scan_level(self, world: MinecraftWorld) -> None:
        """level.dat と、そこから分離されたデータファイルを読む。"""
        level = world.level
        self.stats["level_data_version=%d" % level.data_version] += 1
        self.stats["level_version=%s" % level.version_name] += 1

        # 26.x で level.dat から分離された各ファイルが読めるか確かめる
        for name in ("game_rules", "weather", "world_gen_settings", "world_clocks",
                     "random_sequences", "scoreboard", "custom_boss_events"):
            if world.data_file(name) is not None:
                self.stats["data_file:%s" % name] += 1

        for uuid in world.player_ids():
            if world.player(uuid) is None:
                self.failures.append("players/data/%s.dat を読めない" % uuid)
            else:
                self.stats["player_files"] += 1

    def _scan_dimension(self, dimension_id: str, dimension) -> None:
        """1 つの次元の全チャンクを World レイヤで解釈する。"""
        positions = dimension.chunk_positions()
        self.stats["dimension_chunks"] += len(positions)
        sampled = 0

        # チャンクを 1 つずつ読み、再エンコードが元と一致するかを見る
        for position in positions:
            label = "%s (%d, %d)" % (dimension_id, position.x, position.z)
            folder = dimension.region_folder()
            original = folder.read_chunk(position.x, position.z)

            if original is None:
                self.failures.append("%s: 位置表にあるのに読めない" % label)
                continue

            try:
                chunk = Chunk.from_nbt(
                    original,
                    ChunkReadOptions(on_version_mismatch=VersionMismatchAction.IGNORE))
            except SpringNbtError as error:
                self.failures.append("%s: チャンクとして解釈できない: %s" % (label, error))
                continue

            self.stats["chunks_parsed"] += 1
            self.stats["sections_parsed"] += len(chunk.section_ys)

            if not self._check_roundtrip(label, original, chunk):
                continue

            # 先頭のいくつかだけ、全ブロック・全バイオームを走査する
            if sampled < self.block_sample and chunk.is_fully_generated:
                self._walk_blocks(label, chunk)
                sampled += 1

        self.stats["block_sampled_chunks"] += sampled

    def _check_roundtrip(self, label: str, original: NbtCompound, chunk: Chunk) -> bool:
        """World レイヤで読んで書き戻した結果が、元の NBT と一致するかを見る。

        セクションは毎回パレットとビット詰めを組み直して書き出されるので、
        これが一致するならエンコード側の解釈も正しいことになる。
        """
        # to_nbt は raw を書き換えるので、比較用のバイト列は先に取っておく
        expected = write_bytes(NamedTag("", original), WRITE_OPTIONS)

        try:
            rebuilt = chunk.to_nbt(ChunkWriteOptions(allow_foreign_data_version=True))
        except SpringNbtError as error:
            self.failures.append("%s: 書き戻せない: %s" % (label, error))
            return False

        actual = write_bytes(NamedTag("", rebuilt), WRITE_OPTIONS)

        if actual != expected:
            self.failures.append(
                "%s: World レイヤ経由の再エンコードが元と違う (%d bytes / %d bytes)"
                % (label, len(expected), len(actual)))
            return False

        self.stats["chunks_roundtrip_ok"] += 1
        return True

    def _walk_blocks(self, label: str, chunk: Chunk) -> None:
        """チャンク内のブロックとバイオームを 1 つずつ読み出す。

        ビット詰めの取り出しを端から端まで通すので、
        どこか 1 か所でも境界の扱いを誤っていれば例外か異常な値になる。
        """
        for section_y in chunk.section_ys:
            base = section_y * 16

            # セクション内の 16×16×16 をすべて読む
            for y in range(16):
                for z in range(16):
                    for x in range(16):
                        block = chunk.get_block(x, base + y, z)

                        if block is not None:
                            self.blocks[block.name] += 1

            # バイオームは 4×4×4 単位なので 4 ブロックおきに読む
            for y in range(0, 16, 4):
                for z in range(0, 16, 4):
                    for x in range(0, 16, 4):
                        biome = chunk.get_biome(x, base + y, z)

                        if biome is not None:
                            self.biomes[biome] += 1

        self.stats["blocks_walked"] += len(chunk.section_ys) * 4096

    def report(self) -> int:
        print()
        print("=" * 72)
        print("World レイヤの検証")
        print("=" * 72)

        for key in sorted(self.stats):
            print("  %-40s %d" % (key, self.stats[key]))

        print()
        print("次元: %s" % ", ".join(self.dimensions))

        blocks = ("ブロック種別", self.blocks)
        biomes = ("バイオーム", self.biomes)

        for title, counter in (blocks, biomes):
            if len(counter) == 0:
                continue

            print()
            print("--- %s (種類 %d) ---" % (title, len(counter)))
            limit = len(counter)

            if not self.verbose:
                limit = 15

            for key, count in counter.most_common(limit):
                print("  %-44s %d" % (key, count))

        print()

        if len(self.failures) > 0:
            print("!!! World レイヤの失敗 %d 件 !!!" % len(self.failures))

            for failure in self.failures[:40]:
                print("  - %s" % failure)

            if len(self.failures) > 40:
                print("  … 他 %d 件" % (len(self.failures) - 40))

            return 1

        print("World レイヤの失敗なし。全チャンクの再エンコードが元と一致。")
        return 0


def _decompress_for_scan(raw):
    """走査用に、圧縮方式に応じて展開する。扱えない方式は呼び出し側で弾く。"""
    if raw.compression.as_string() == "gzip":
        return gzip.decompress(raw.data)

    if raw.compression.as_string() == "zlib":
        return zlib.decompress(raw.data)

    return raw.data


def ceil_log2(value: int) -> int:
    """value 個の値を表すのに必要な最小ビット数。value == 1 なら 0。"""
    bits = 0

    # 1 を超える分だけシフトして数える
    while (1 << bits) < value:
        bits += 1

    return bits


def decompress_any(raw: bytes):
    """先頭バイトから方式を判定して展開する。"""
    if len(raw) >= 2 and raw[0] == 0x1F and raw[1] == 0x8B:
        return gzip.decompress(raw), "gzip"

    if len(raw) >= 2 and (raw[0] & 0x0F) == 0x08 and (((raw[0] << 8) | raw[1]) % 31) == 0:
        return zlib.decompress(raw), "zlib"

    return raw, "none"


def region_kind(path: str) -> str:
    """リージョンファイルの種別を、置かれているディレクトリから判定する。"""
    if os.sep + "entities" + os.sep in path:
        return "entities"

    if os.sep + "poi" + os.sep in path:
        return "poi"

    return "region"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="実ワールドを読み取り専用で走査して検証する")
    parser.add_argument("world", help="ワールドディレクトリのパス")
    parser.add_argument("--verbose", action="store_true", help="集計を省略せずに出す")
    parser.add_argument("--block-sample", type=int,
                        default=WorldScanner.DEFAULT_BLOCK_SAMPLE,
                        help="全ブロックを 1 つずつ読む対象チャンク数（次元ごと）")
    args = parser.parse_args()

    if not os.path.isdir(args.world):
        sys.stderr.write("ワールドディレクトリが見つからない: %s\n" % args.world)
        return 2

    scanner = Scanner(args.verbose)

    # ワールド配下を丸ごと辿る
    for dirpath, _dirnames, filenames in os.walk(args.world):
        for filename in sorted(filenames):
            path = os.path.join(dirpath, filename)
            label = os.path.relpath(path, args.world)

            if filename.endswith((".dat", ".dat_old", ".nbt")):
                scanner.scan_nbt_file(path, label)
            elif filename.endswith(".mca"):
                scanner.scan_region_file(path, label, region_kind(path))
            elif filename.endswith(".mcc"):
                scanner.stats["mcc_files"] += 1

    status = scanner.report()

    # World レイヤでも読み直して、パレットとビット詰めの解釈を確かめる
    world_scanner = WorldScanner(args.verbose, args.block_sample)

    try:
        world_scanner.scan(args.world)
    except SpringNbtError as error:
        sys.stderr.write("World レイヤの走査に失敗: %s\n" % error)
        return 1

    if world_scanner.report() != 0:
        status = 1

    return status


if __name__ == "__main__":
    sys.exit(main())

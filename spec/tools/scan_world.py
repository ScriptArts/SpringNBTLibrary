#!/usr/bin/env python3
"""実ワールドを読み取り専用で走査し、実データ耐性を確かめる。

合成のテストベクタだけでは、実際のMinecraftが書き出すデータを網羅できない。
このツールは手元のワールドを丸ごと読んで、次を確認する。

  1. すべての`.dat` / `.nbt`を読み、ラウンドトリップ（読む→書く→バイト一致）を検証
  2. すべての`.mca`のヘッダを解析し、無変更で書き戻した結果が原本とバイト一致するかを検証。
     さらに全チャンクを展開してNBTとして読み、同じくラウンドトリップを検証
  3. 使われている圧縮方式・チャンク構造の統計を出す（仕様書とのズレを見つけるため）。
     1.17までの形式（`Level.Sections`の`Palette` / `BlockStates`）も、
     ライブラリを通さずに元のNBTから数える
  4. Worldレイヤ（`MinecraftWorld` / `Chunk` / `PalettedContainer`）で解釈し直し、
     NBTへ書き戻したものが元と一致するか、ブロックが読み出せるかを検証。
     26.1より前の構成のワールドも同じく開き、チャンクは自身のDataVersionで決まる世代ごとに数える。
     セクションやキーの並びだけが違う場合も失敗に数える

次のファイルは失敗に数えず、種類ごとに数えて飛ばす。

  - `uid.dat`: 16バイトの生のUUIDで、NBTではない
  - 0バイトの`.mca`: Minecraftがチャンクを書く前のファイルを残すことがある

**このツールは一切書き込まない。** 引数のワールドは読み取りのみで開く。
とはいえMinecraftが起動していない状態で実行すること（書き込み途中を読む可能性があるため）。

使い方:
    python3 spec/tools/scan_world.py "<ワールドのパス>"
    python3 spec/tools/scan_world.py "<ワールドのパス>" --verbose
"""

from __future__ import annotations

import argparse
import gzip
import os
import sys
import zlib
from collections import Counter, defaultdict
from typing import Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "python", "src"))

from spring_nbt_library import MIN_SUPPORTED_DATA_VERSION, ErrorCode, SpringNbtError  # noqa: E402
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

#: ``uid.dat``の長さ。中身は16バイトの生のUUID
UID_FILE_SIZE = 16

READ_OPTIONS = NbtReadOptions(compression=Compression.NONE)
WRITE_OPTIONS = NbtWriteOptions(compression=Compression.NONE)

#: チャンクの形式の世代の名前と、その世代が始まるDataVersion
#: 境界の昇順に並べる
GENERATIONS = (
    ("C1", MIN_SUPPORTED_DATA_VERSION),
    ("C2", 2203),
    ("C3", 2529),
    ("C4", 2844),
    ("C5", 5006),
)

#: どの世代でも解釈せず、元のNBTだけを持つチャンクの区分
#: DataVersionが無いか、下限より古いチャンクが当たる
RAW_ONLY = "raw-only"

#: 本体が``Level``の中にあり、セクションの直下に``Palette`` / ``BlockStates``を持つ世代
LEGACY_GENERATIONS = ("C1", "C2", "C3")

#: ``BlockStates``のビット詰めで、値が64bitの境目をまたぐ世代
SPANNING_GENERATIONS = ("C1", "C2")

#: バイオームIDを列ごとに持つ世代（``int[256]``）
#: C2とC3は4×4×4ブロックごと（``int[1024]``）
COLUMN_BIOME_GENERATIONS = ("C1",)

#: 1.15以降の数値のバイオームIDが持つ高さの上限
BIOME_IDS_MAX_Y = 255

#: 生成を終えたとみなす``Status``の値（名前空間を外した形）
#: ``postprocessed``と``fullchunk``は1.13だけで使われる
GENERATED_STATUSES = ("full", "postprocessed", "fullchunk")

#: 26.1以降の構成（L2）が始まるDataVersion
L2_MIN_DATA_VERSION = 4786

#: 飛ばしたファイルの種類
SKIP_UID = "uid.dat（NBTでない）"
SKIP_EMPTY_REGION = "0バイトの.mca"


def generation_of(data_version: Optional[int]) -> str:
    """チャンク自身のDataVersionから世代の名前を返す
    DataVersionが無いか下限より古ければ``RAW_ONLY``
    """
    # DataVersionの無いチャンクは1.9より前のもので、どの世代でも解釈しない
    if data_version is None:
        return RAW_ONLY

    result = RAW_ONLY
    # 表は境界の昇順なので、境界に届いた最後の世代が当てはまる
    for name, minimum in GENERATIONS:
        # 境界に届いた世代だけを候補にする
        if data_version >= minimum:
            result = name

    return result


def describe_data_version(data_version: Optional[int]) -> str:
    """集計の表に出すDataVersionの書き方"""
    # DataVersionの無いチャンクは数字の代わりに「無し」と出す
    if data_version is None:
        return "無し"

    return str(data_version)


def data_version_sort_key(data_version: Optional[int]) -> int:
    """DataVersionの昇順に並べるための値
    DataVersionの無いものを先頭に置く
    """
    # 無いものは、どのDataVersionよりも前に並べる
    if data_version is None:
        return -1

    return data_version


def strip_namespace(status: str) -> str:
    """``Status``の値から名前空間を外す
    1.19までは名前空間の無い``full``で、1.20以降は``minecraft:full``で入る
    """
    prefix = "minecraft:"

    # 名前空間付きの値だけ先頭を外す
    if status.startswith(prefix):
        return status[len(prefix):]

    return status


def region_skip_reason(path: str) -> Optional[str]:
    """飛ばすリージョンファイルなら、その種類を返す
    飛ばさないファイルならNone
    """
    size = os.path.getsize(path)

    # Minecraftはチャンクを書く前の0バイトのファイルを残すことがある
    if size == 0:
        return SKIP_EMPTY_REGION

    return None


def is_uid_file(path: str) -> bool:
    """``uid.dat``（16バイトの生のUUID）か"""
    # 名前と長さの両方が合うものだけを飛ばし、それ以外は普通に検証する
    if os.path.basename(path) != "uid.dat":
        return False

    return os.path.getsize(path) == UID_FILE_SIZE


class Scanner:
    """走査の状態と結果をまとめて持つ。"""

    def __init__(self, verbose: bool) -> None:
        self.verbose = verbose
        self.stats = Counter()
        self.failures = []
        self.skipped = Counter()
        self.root_keys = Counter()
        self.chunk_keys = Counter()
        self.level_keys = Counter()
        self.section_keys = Counter()
        self.legacy_section_keys = Counter()
        self.entity_keys = Counter()
        self.poi_keys = Counter()
        self.data_versions = Counter()
        self.chunk_statuses = Counter()
        self.palette_shapes = Counter()
        self.palette_entries = Counter()
        self.legacy_sections = Counter()
        self.biome_shapes = Counter()
        self.light_flags = Counter()
        self.container_orders = Counter()

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
        # uid.datはNBTではないので、失敗に数えずに飛ばす
        if is_uid_file(path):
            self.skipped[SKIP_UID] += 1
            return

        with open(path, "rb") as handle:
            raw = handle.read()

        try:
            plain, method = decompress_any(raw)
        except Exception as error:  # noqa: BLE001
            self.failures.append("%s: 展開できない -> %s" % (label, error))
            return

        self.stats["nbt_files"] += 1
        self.stats["nbt_files%s" % os.path.splitext(path)[1]] += 1
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
        reason = region_skip_reason(path)

        # 飛ばす種類のファイルは、失敗に数えずに種類ごとに数える
        if reason is not None:
            self.skipped[reason] += 1
            return

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

        expected = original

        # 長さが4096の倍数でないファイルは、末尾をゼロで埋めて組み立てる
        if len(original) % SECTOR != 0:
            self.stats["region_files_unaligned"] += 1
            expected = original + bytes(SECTOR - (len(original) % SECTOR))

        if region.to_bytes() != expected:
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
            self.stats["chunk_roundtrip_ok"] += 1
            self.collect_chunk_stats(where, named.tag, kind)

        region.close()

    # -- 統計 ---------------------------------------------------------------

    def collect_chunk_stats(self, where: str, root: NbtCompound, kind: str) -> None:
        """チャンクの構造を集計する。仕様書と実データのズレを見つけるため。

        ライブラリの解釈を通さずに元のNBTから数えるので、
        世代の表の値（BlockStatesの長さ、Statusの値など）を独立に確かめられる
        """
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

        generation = generation_of(version)
        body = root.opt_compound("Level")
        # 1.17までの形式は本体がLevelの中にある
        if body is None:
            body = root
        else:
            # Levelの直下のキーも数える
            for key in body.keys():
                self.level_keys[key] += 1

        status = body.opt_string("Status")

        # Statusの値は世代ごとに数える
        if status is not None:
            self.chunk_statuses["%s %s" % (generation, status)] += 1

        self.collect_light_flag(version, body, status)

        # 解釈しないチャンクは、セクションの形を数えない
        if generation == RAW_ONLY:
            return

        # 1.17までの形式は、セクションの直下のPaletteとBlockStatesを数える
        if generation in LEGACY_GENERATIONS:
            self.collect_legacy_sections(where, generation, body)
            self.collect_biome_ids(generation, body)
            return

        sections = root.opt_list("sections")
        if sections is None:
            return

        for section in sections:
            if not isinstance(section, NbtCompound):
                continue

            for key in section.keys():
                self.section_keys[key] += 1

            self.check_paletted_container(where, section, "block_states", 4096, 4)
            self.check_paletted_container(where, section, "biomes", 64, 1)

    def collect_light_flag(self, version: Optional[int], body: NbtCompound,
                           status: Optional[str]) -> None:
        """``isLightOn``の有無を、DataVersionと生成の段階ごとに数える

        ``isLightOn``が入ったDataVersionを実データで確かめるため
        """
        stage = "Status無し"
        # 生成を終えたチャンクとそれ以外を分けて数える
        if status is not None:
            stage = "生成途中"
            # 名前空間を外してから、生成済みとみなす値と比べる
            if strip_namespace(status) in GENERATED_STATUSES:
                stage = "生成済み"

        has_flag = "isLightOn" in body
        self.light_flags[(version, stage, has_flag)] += 1

    def collect_legacy_sections(self, where: str, generation: str,
                                body: NbtCompound) -> None:
        """1.17までの形式のセクションの``Palette``と``BlockStates``を数える

        ``BlockStates``の長さが世代の詰め方（またぐ・またがない）と合うか、
        パレットが1要素のセクションにも``BlockStates``があるかを確かめる
        """
        sections = body.opt_list("Sections")

        # 生成の初めの段階のチャンクはセクションを持たない
        if sections is None:
            self.legacy_sections["%sのSectionsが無いチャンク" % generation] += 1
            return

        # セクションごとに、ブロックの持ち方を数える
        for section in sections:
            # Compound以外の要素は数えない
            if not isinstance(section, NbtCompound):
                continue

            # セクションのキーの並びを数える
            for key in section.keys():
                self.legacy_section_keys[key] += 1

            palette = section.opt_list("Palette")
            states = section.opt_long_array("BlockStates")

            # 光源だけを持つセクションは、どちらも持たない
            if palette is None and states is None:
                self.legacy_sections["%sのPaletteもBlockStatesも無いセクション" % generation] += 1
                continue

            # 片方だけのセクションは、Minecraftもブロックを読まない
            if palette is None or states is None:
                self.legacy_sections["%sのPaletteとBlockStatesの片方だけのセクション" % generation] += 1
                continue

            # パレットの要素の形を数える
            for entry in palette:
                self.palette_entries["Palette %s" % describe_palette_entry(entry)] += 1

            self.check_block_states_length(where, generation, len(palette), len(states))

    def check_block_states_length(self, where: str, generation: str,
                                  palette_length: int, states_length: int) -> None:
        """``BlockStates``の長さが世代の詰め方と合うかを確かめる"""
        bits = max(4, ceil_log2(palette_length))
        values_per_long = 64 // bits
        packed = (4096 + values_per_long - 1) // values_per_long
        spanning = ((4096 * bits) + 63) // 64
        expected = packed
        layout = "またがない"
        # 1.15までは値が64bitの境目をまたいで詰まる
        if generation in SPANNING_GENERATIONS:
            expected = spanning
            layout = "またぐ"

        # 長さが世代の詰め方と合わなければ、表の境界か詰め方の理解が違う
        if states_length != expected:
            self.failures.append(
                "%s: %sのPalette=%d bits=%dなら、%s詰め方でBlockStatesは%d longのはずだが%d long"
                % (where, generation, palette_length, bits, layout, expected, states_length))
            return

        # 詰め方で長さが変わるビット幅のときだけ、詰め方を確かめたことになる
        if packed != spanning:
            self.legacy_sections["%sの%s詰め方を長さで確かめたセクション" % (generation, layout)] += 1
        else:
            self.legacy_sections["%sの詰め方で長さが変わらないビット幅のセクション" % generation] += 1

        # パレットが1要素でもBlockStatesがあるかを数える
        if palette_length == 1:
            self.legacy_sections["%sのPalette=1のセクションでBlockStates=%d long"
                                 % (generation, states_length)] += 1

        self.palette_shapes["%s Palette bits=%d BlockStates=%d long"
                            % (generation, bits, states_length)] += 1

    def collect_biome_ids(self, generation: str, body: NbtCompound) -> None:
        """1.17までの形式の``Biomes``の型と長さを数える"""
        biomes = body.opt("Biomes")
        shape = "無し"
        # 型と要素数を書き出す
        if biomes is not None:
            shape = "%s[%d]" % (biomes.type.as_string(), len(biomes.value))

        self.biome_shapes["%s Biomes %s" % (generation, shape)] += 1

    def check_paletted_container(self, where: str, section: NbtCompound, key: str,
                                 entry_count: int, min_bits: int) -> None:
        """パレットの長さから求めたビット幅と、実際のdata長が一致するか確かめる。

        ビット幅の計算式が実データに合っているかを直接検証する部分。
        """
        container = section.opt_compound(key)

        if container is None:
            return

        # dataとpaletteの両方を持つコンテナは、キーの並びを数える
        if len(container) > 1:
            self.container_orders["%s %s" % (key, ",".join(container.keys()))] += 1

        palette = container.opt_list("palette")

        if palette is None:
            self.failures.append("%s: %sにpaletteが無い" % (where, key))
            return

        # パレットの要素の形を数える。形式が変わったときに最初に表れる部分
        for entry in palette:
            self.palette_entries["%s %s" % (key, describe_palette_entry(entry))] += 1

        bits = max(min_bits, ceil_log2(len(palette)))
        values_per_long = 64 // bits
        expected = (entry_count + values_per_long - 1) // values_per_long

        data = container.opt_long_array("data")

        if data is None:
            # パレットが1要素ならdataは無くてよい
            if len(palette) != 1:
                self.failures.append(
                    "%s: %s: palette=%dなのにdataが無い" % (where, key, len(palette)))
            else:
                self.palette_shapes["%s palette=1 (data無し)" % key] += 1
            return

        if len(data) != expected:
            self.failures.append(
                "%s: %s: palette=%d bits=%dならdataは%d longのはずだが%d long"
                % (where, key, len(palette), bits, expected, len(data)))
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

        print_counter("飛ばしたファイル", self.skipped, None)

        sections = [
            ("*.dat / *.nbt のルート直下キー", self.root_keys),
            ("チャンク (region) のルート直下キー", self.chunk_keys),
            ("チャンクのLevelの直下キー（1.17まで）", self.level_keys),
            ("セクションのキー", self.section_keys),
            ("セクションのキー（1.17まで）", self.legacy_section_keys),
            ("entities チャンクのキー", self.entity_keys),
            ("poi チャンクのキー", self.poi_keys),
            ("パレットの要素の形", self.palette_entries),
        ]

        for title, counter in sections:
            limit = len(counter)
            # 省略する設定では上位だけを出す
            if not self.verbose:
                limit = 25

            print_counter(title, counter, limit)

        # 世代の表と突き合わせる値は省略せずに出す
        print_counter("世代ごとのStatus", self.chunk_statuses, None)
        print_counter("1.17までのセクションの形", self.legacy_sections, None)
        print_counter("1.17までのBiomesの形", self.biome_shapes, None)
        print_counter("パレット付きコンテナのキーの並び（1.18以降）", self.container_orders, None)
        self.report_light_flags()

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

    def report_light_flags(self) -> None:
        """``isLightOn``の有無を、DataVersionと生成の段階ごとに出す"""
        if len(self.light_flags) == 0:
            return

        print()
        print("--- isLightOnの有無（地形のチャンク） ---")
        print("  %-10s %-10s %10s %10s" % ("DataVersion", "段階", "あり", "無し"))
        rows = set((version, stage) for version, stage, _ in self.light_flags)

        # DataVersionの昇順に、段階ごとの件数を並べる
        for version, stage in sorted(rows, key=lambda row: (data_version_sort_key(row[0]), row[1])):
            print("  %-10s %-10s %10d %10d"
                  % (describe_data_version(version), stage,
                     self.light_flags[(version, stage, True)],
                     self.light_flags[(version, stage, False)]))


def print_counter(title: str, counter: Counter, limit: Optional[int]) -> None:
    """件数の表を多い順に出す
    limitがNoneならすべて出す
    """
    # 空の表は見出しも出さない
    if len(counter) == 0:
        return

    print()
    print("--- %s ---" % title)

    for key, count in counter.most_common(limit):
        print("  %-44s %d" % (key, count))


def describe_palette_entry(entry) -> str:
    """パレットの要素の形を短い文字列で表す

    文字列ならその型名、Compoundならキーの並びを出す
    異種リストの包み``{"": <値>}``は、包まれた値の型も添える
    """
    # Compound以外は型名だけで足りる
    if not isinstance(entry, NbtCompound):
        return entry.type.as_string()

    keys = list(entry.keys())

    # 異種リストの包みは、中身の型が分かるようにする
    if keys == [""]:
        return "compound{\"\"} -> %s" % entry.get("").type.as_string()

    return "compound{%s}" % ",".join(keys)


class WorldScanner:
    """Worldレイヤを通してワールドを読み直し、解釈が正しいかを確かめる。

    Anvilレイヤの走査は「NBTとして読めるか」までしか見ない。
    ここではさらに`Chunk` / `PalettedContainer`を通して、
    パレットとビット詰めの解釈・再エンコードが元データと一致するかを確認する。
    件数はチャンク自身のDataVersionごとに数え、世代ごとの件数もそこから出す
    """

    #: 全ブロックを1つずつ読む対象のチャンク数の既定値（次元とDataVersionの組ごと）
    #: 全チャンクだと時間がかかりすぎる
    DEFAULT_BLOCK_SAMPLE = 40

    def __init__(self, verbose: bool, block_sample: int) -> None:
        self.verbose = verbose
        self.block_sample = block_sample
        self.stats = Counter()
        self.failures = []
        self.skipped = Counter()
        self.blocks = Counter()
        self.biomes = Counter()
        self.biome_ids = Counter()
        self.dimensions = []
        #: チャンク自身のDataVersionごとの件数
        #: DataVersionの無いチャンクはNoneに数える
        self.per_version = defaultdict(Counter)

    def scan(self, directory: str) -> None:
        """ワールドを読み取り専用で開いて走査する。"""
        # writable=Falseなので、この先どの経路でも書き込みは起きない
        try:
            world = MinecraftWorld.open(directory, WorldOpenOptions(writable=False))
        except SpringNbtError as error:
            self.failures.append("ワールドを開けない: %s" % error)
            return

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
        """level.datと、そこから分離されたデータファイルを読む。"""
        level = world.level
        getters = (
            ("data_version", lambda: level.data_version),
            ("version_name", lambda: level.version_name),
            ("level_name", lambda: level.level_name),
            ("time", lambda: level.time),
            ("game_type", lambda: level.game_type),
            ("spawn_pos", lambda: level.spawn_pos),
            ("spawn_dimension", lambda: level.spawn_dimension),
            ("difficulty", lambda: level.difficulty),
            ("is_hardcore", lambda: level.is_hardcore),
        )

        # level.datの取得子がどの構成でも読めるかを確かめる
        for name, getter in getters:
            try:
                getter()
            except SpringNbtError as error:
                # 構成の世代に無い値は、UNSUPPORTED_FEATUREになるのが正しい
                if error.code == ErrorCode.UNSUPPORTED_FEATURE:
                    self.stats["level_getter_unsupported:%s" % name] += 1
                    continue

                self.failures.append("level.datの%sを読めない: %s" % (name, error))
                continue

            self.stats["level_getter_ok:%s" % name] += 1

        # 構成の世代はlevel.datのDataVersionで決まる
        try:
            data_version = level.data_version
        except SpringNbtError:
            return

        layout = "L1"
        # 26.1以降はL2の構成
        if data_version >= L2_MIN_DATA_VERSION:
            layout = "L2"

        self.stats["level_data_version=%d" % data_version] += 1
        self.stats["level_layout=%s" % layout] += 1

        # 26.xでlevel.datから分離された各ファイルが読めるか確かめる
        for name in ("game_rules", "weather", "world_gen_settings", "world_clocks",
                     "random_sequences", "scoreboard", "custom_boss_events"):
            # 構成に無いファイルは数えない
            if world.data_file(name) is not None:
                self.stats["data_file:%s" % name] += 1

        # プレイヤーデータがすべて読めるかを確かめる
        for uuid in world.player_ids():
            # 一覧にあるのに読めなければ失敗
            if world.player(uuid) is None:
                self.failures.append("プレイヤー%sを読めない" % uuid)
            else:
                self.stats["player_files"] += 1

    def _scan_dimension(self, dimension_id: str, dimension) -> None:
        """1つの次元の全チャンクをWorldレイヤで解釈する。

        リージョンファイルを1つずつ開くので、開けないファイルがあっても残りを走査できる
        """
        folder = dimension.region_folder()

        # 地形のリージョンフォルダが無い次元は数えるものが無い
        if folder is None:
            return

        sampled = Counter()

        # リージョンファイルごとに、その中のチャンクを順に読む
        for region_position in folder.region_positions():
            path = os.path.join(folder.directory, region_position.file_name())
            reason = region_skip_reason(path)

            # 飛ばす種類のファイルは、失敗に数えずに種類ごとに数える
            if reason is not None:
                self.skipped[reason] += 1
                continue

            try:
                region = folder.region(region_position.x, region_position.z)
            except SpringNbtError as error:
                self.failures.append("%s %s: 開けない: %s"
                                     % (dimension_id, region_position.file_name(), error))
                continue

            # 読み取り専用で消えたファイルは無いものとして扱う
            if region is None:
                continue

            # 位置表にあるチャンクを1つずつ解釈し直す
            for position in region.chunk_positions():
                self._scan_chunk(dimension_id, region, position, sampled)

    def _scan_chunk(self, dimension_id: str, region: RegionFile, position,
                    sampled: Counter) -> None:
        """チャンク1つをWorldレイヤで解釈し、書き戻しが元と一致するかを見る"""
        label = "%s (%d, %d)" % (dimension_id, position.x, position.z)

        try:
            original = region.read_chunk(position.x, position.z)
        except SpringNbtError as error:
            self.failures.append("%s: 読めない: %s" % (label, error))
            return

        if original is None:
            self.failures.append("%s: 位置表にあるのに読めない" % label)
            return

        version = original.opt_int("DataVersion")
        generation = generation_of(version)
        counts = self.per_version[version]
        counts["chunks"] += 1

        # 書き戻しはrawを書き換えるので、比較用のバイト列は解釈する前に取っておく
        expected = write_bytes(NamedTag("", original), WRITE_OPTIONS)

        try:
            chunk = Chunk.from_nbt(
                original,
                ChunkReadOptions(on_version_mismatch=VersionMismatchAction.IGNORE))
        except SpringNbtError as error:
            self.failures.append("%s: チャンクとして解釈できない: %s" % (label, error))
            return

        # 書き戻しが元と一致しなければ、その先の確認はしない
        if not self._check_roundtrip(label, expected, chunk):
            return

        counts["roundtrip_ok"] += 1

        # 元のNBTだけを持つチャンクは、ブロックのAPIが止まることだけを確かめる
        if generation == RAW_ONLY:
            self._check_raw_only(label, chunk)
            return

        block_sections = 0
        packed_sections = 0
        # ブロックを持つセクションと、そのうちビット詰めのdataを持つセクションを数える
        for section_y in chunk.section_ys:
            section = chunk.section(section_y)

            # 光源だけのセクションは数えない
            if not section.has_block_states:
                continue

            block_sections += 1

            # パレットが2要素以上なら、ブロックはビット詰めのdataから読む
            if len(section.block_states.palette) > 1:
                packed_sections += 1

        counts["sections"] += len(chunk.section_ys)
        counts["block_sections"] += block_sections
        counts["packed_sections"] += packed_sections

        try:
            generated = chunk.is_fully_generated
        except SpringNbtError as error:
            self.failures.append("%s: 生成済みかを判定できない: %s" % (label, error))
            return

        # 生成途中のチャンクは全ブロックを読まない
        if not generated:
            return

        counts["generated"] += 1

        # 全セクションがパレット1要素のチャンクは、ビット詰めを通らないので数に入れない
        if packed_sections == 0:
            return

        # 次元とDataVersionの組ごとに、先頭から決まった数だけ全ブロックを読む
        # 形式の違うチャンクが混ざったワールドでも、古いチャンクを読み漏らさないため
        if sampled[version] >= self.block_sample:
            return

        try:
            self._walk_blocks(chunk, generation, counts)
        except SpringNbtError as error:
            self.failures.append("%s: ブロックかバイオームを読めない: %s" % (label, error))
            return

        sampled[version] += 1

    def _check_roundtrip(self, label: str, expected: bytes, chunk: Chunk) -> bool:
        """Worldレイヤで読んで書き戻した結果が、元のNBTと一致するかを見る。

        セクションは毎回パレットとビット詰めを組み直して書き出されるので、
        これが一致するならエンコード側の解釈も正しいことになる。
        セクションの並びやパレット付きコンテナのキーの並びも、読んだときのまま残るはず
        """
        try:
            rebuilt = chunk.to_nbt(ChunkWriteOptions(allow_foreign_data_version=True))
        except SpringNbtError as error:
            self.failures.append("%s: 書き戻せない: %s" % (label, error))
            return False

        actual = write_bytes(NamedTag("", rebuilt), WRITE_OPTIONS)

        # 並びも含めてバイト単位で一致しなければ失敗
        if actual != expected:
            self.failures.append(
                "%s: Worldレイヤ経由の再エンコードが元と違う (%d bytes / %d bytes)"
                % (label, len(expected), len(actual)))
            return False

        self.stats["chunks_roundtrip_ok"] += 1
        return True

    def _check_raw_only(self, label: str, chunk: Chunk) -> None:
        """元のNBTだけを持つチャンクで、ブロックのAPIがUNSUPPORTED_DATA_VERSIONになるかを見る"""
        try:
            chunk.get_block(0, 0, 0)
        except SpringNbtError as error:
            # 期待どおりのエラーなら数えて終わる
            if error.code == ErrorCode.UNSUPPORTED_DATA_VERSION:
                self.stats["raw_only_block_api_refused"] += 1
                return

            self.failures.append("%s: 元のNBTだけを持つチャンクのget_blockが別のエラー: %s"
                                 % (label, error))
            return

        self.failures.append("%s: 元のNBTだけを持つチャンクでget_blockが通った" % label)

    def _walk_blocks(self, chunk: Chunk, generation: str, counts: Counter) -> None:
        """チャンク内のブロックとバイオームを1つずつ読み出す。

        ビット詰めの取り出しを端から端まで通すので、
        どこか1か所でも境界の扱いを誤っていれば例外か異常な値になる。
        1.17までの形式はバイオームを数値のIDで持つので、``get_biome_id``で数える
        """
        for section_y in chunk.section_ys:
            base = section_y * 16

            # セクション内の16×16×16をすべて読む
            for y in range(16):
                for z in range(16):
                    for x in range(16):
                        block = chunk.get_block(x, base + y, z)

                        if block is not None:
                            self.blocks[block.name] += 1
                            counts["blocks_read"] += 1

            # 数値のIDで持つ世代は、セクションとは別にチャンク全体で数える
            if generation in LEGACY_GENERATIONS:
                continue

            # バイオームは4×4×4単位なので4ブロックおきに読む
            for y in range(0, 16, 4):
                for z in range(0, 16, 4):
                    for x in range(0, 16, 4):
                        biome = chunk.get_biome(x, base + y, z)

                        if biome is not None:
                            self.biomes[biome] += 1

        # 1.17までの形式は、数値のバイオームIDを数える
        if generation in LEGACY_GENERATIONS:
            self._count_biome_ids(chunk, generation)

        counts["walked_chunks"] += 1

    def _count_biome_ids(self, chunk: Chunk, generation: str) -> None:
        """数値のバイオームIDを、持っている単位ごとに1回ずつ数える"""
        # 1.14までの形式は列ごとに持つので、高さを見ずに16×16列を読む
        if generation in COLUMN_BIOME_GENERATIONS:
            for z in range(16):
                for x in range(16):
                    biome_id = chunk.get_biome_id(x, 0, z)

                    # Biomesを読めない列は数えない
                    if biome_id is not None:
                        self.biome_ids[biome_id] += 1
            return

        # 1.15以降は4×4×4単位で、高さ0..255の分を持つ
        for y in range(0, BIOME_IDS_MAX_Y + 1, 4):
            for z in range(0, 16, 4):
                for x in range(0, 16, 4):
                    biome_id = chunk.get_biome_id(x, y, z)

                    # Biomesを読めない位置は数えない
                    if biome_id is not None:
                        self.biome_ids[biome_id] += 1

    def generation_counts(self) -> Counter:
        """世代ごとに、DataVersionごとの件数を足し合わせる"""
        result = defaultdict(Counter)

        # DataVersionごとの件数を、その世代の行へ足す
        for version, counts in self.per_version.items():
            result[generation_of(version)].update(counts)

        return result

    def report(self) -> int:
        print()
        print("=" * 72)
        print("Worldレイヤの検証")
        print("=" * 72)

        for key in sorted(self.stats):
            print("  %-40s %d" % (key, self.stats[key]))

        print()
        print("次元: %s" % ", ".join(self.dimensions))

        print_counter("飛ばしたリージョンファイル", self.skipped, None)

        columns = ("chunks", "roundtrip_ok", "generated", "sections",
                   "block_sections", "packed_sections", "walked_chunks", "blocks_read")
        header = "  %-12s %-9s" % ("DataVersion", "世代") \
            + "".join(" %14s" % column for column in columns)

        print()
        print("--- チャンクのDataVersionごとの件数 ---")
        print(header)

        # DataVersionの昇順に並べる
        for version in sorted(self.per_version, key=data_version_sort_key):
            counts = self.per_version[version]
            print("  %-12s %-9s" % (describe_data_version(version), generation_of(version))
                  + "".join(" %14d" % counts[column] for column in columns))

        generations = self.generation_counts()
        order = [RAW_ONLY] + [name for name, _ in GENERATIONS]

        print()
        print("--- 世代ごとの件数 ---")
        print("  %-22s" % "世代" + "".join(" %14s" % column for column in columns))

        # 古い世代から順に並べる
        for generation in order:
            # そのワールドに無い世代は出さない
            if generation not in generations:
                continue

            counts = generations[generation]
            print("  %-22s" % generation
                  + "".join(" %14d" % counts[column] for column in columns))

        blocks = ("ブロック種別", self.blocks)
        biomes = ("バイオーム", self.biomes)
        biome_ids = ("数値のバイオームID", self.biome_ids)

        # ブロック、バイオーム、数値のバイオームIDの順に、多いものから出す
        for title, counter in (blocks, biomes, biome_ids):
            # 1件も数えていない集計は、見出しごと出さない
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
            print("!!! Worldレイヤの失敗 %d 件 !!!" % len(self.failures))

            for failure in self.failures[:40]:
                print("  - %s" % failure)

            if len(self.failures) > 40:
                print("  … 他 %d 件" % (len(self.failures) - 40))

            return 1

        print("Worldレイヤの失敗なし。全チャンクの再エンコードが元と一致。")
        return 0


def _decompress_for_scan(raw):
    """走査用に、圧縮方式に応じて展開する。扱えない方式は呼び出し側で弾く。"""
    if raw.compression.as_string() == "gzip":
        return gzip.decompress(raw.data)

    if raw.compression.as_string() == "zlib":
        return zlib.decompress(raw.data)

    return raw.data


def ceil_log2(value: int) -> int:
    """value個の値を表すのに必要な最小ビット数。value == 1なら0。"""
    bits = 0

    # 1を超える分だけシフトして数える
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


def scan_world(directory: str, verbose: bool,
               block_sample: int) -> Tuple[Scanner, WorldScanner]:
    """ワールドをAnvilレイヤとWorldレイヤの両方で走査する
    結果の集計は戻り値の2つが持つ
    """
    scanner = Scanner(verbose)

    # ワールド配下を丸ごと辿る
    for dirpath, dirnames, filenames in os.walk(directory):
        # 辿る順をファイルシステムに依存させない
        dirnames.sort()

        for filename in sorted(filenames):
            path = os.path.join(dirpath, filename)
            label = os.path.relpath(path, directory)

            if filename.endswith((".dat", ".dat_old", ".nbt")):
                scanner.scan_nbt_file(path, label)
            elif filename.endswith(".mca"):
                scanner.scan_region_file(path, label, region_kind(path))
            elif filename.endswith(".mcc"):
                scanner.stats["mcc_files"] += 1

    # Worldレイヤでも読み直して、パレットとビット詰めの解釈を確かめる
    world_scanner = WorldScanner(verbose, block_sample)
    world_scanner.scan(directory)
    return scanner, world_scanner


def main() -> int:
    parser = argparse.ArgumentParser(
        description="実ワールドを読み取り専用で走査して検証する")
    parser.add_argument("world", help="ワールドディレクトリのパス")
    parser.add_argument("--verbose", action="store_true", help="集計を省略せずに出す")
    parser.add_argument("--block-sample", type=int,
                        default=WorldScanner.DEFAULT_BLOCK_SAMPLE,
                        help="全ブロックを1つずつ読む対象チャンク数（次元とDataVersionの組ごと）")
    args = parser.parse_args()

    if not os.path.isdir(args.world):
        sys.stderr.write("ワールドディレクトリが見つからない: %s\n" % args.world)
        return 2

    scanner, world_scanner = scan_world(args.world, args.verbose, args.block_sample)
    status = scanner.report()
    # どちらかのレイヤに失敗があれば終了コード1
    if world_scanner.report() != 0:
        status = 1

    return status


if __name__ == "__main__":
    sys.exit(main())

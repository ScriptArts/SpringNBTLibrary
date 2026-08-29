"""World / Block レイヤ。

仕様: docs/spec/30-chunk-format.md / 31-paletted-container.md / 40-world-layout.md

他言語版と同じ検証項目を持つ。
共通テストベクタによる言語間比較は spec/run-conformance.sh が担当し、
ここでは API の振る舞いを直接確かめる。
"""

from __future__ import annotations

import os

import pytest

from spring_nbt_library import TARGET_DATA_VERSION, ErrorCode, SpringNbtError
from spring_nbt_library.nbt import (
    Compression,
    NamedTag,
    NbtCompound,
    NbtInt,
    NbtString,
    NbtWriteOptions,
    read_file,
    write_bytes,
)
from spring_nbt_library.world import (
    BitStorage,
    BlockState,
    Chunk,
    ChunkReadOptions,
    ChunkWriteOptions,
    MinecraftWorld,
    PalettedContainer,
    VersionMismatchAction,
    ceil_log2,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VECTORS = os.path.join(REPO_ROOT, "spec", "testdata", "world")


def vector_path(name: str) -> str:
    """共通テストベクタ（world/*.nbt）のパス。"""
    path = os.path.join(VECTORS, name + ".nbt")

    if not os.path.isfile(path):
        raise AssertionError("テストベクタが見つからない: world/%s.nbt" % name)

    return path


def load_chunk(name: str, options: ChunkReadOptions = None) -> Chunk:
    """テストベクタをチャンクとして読む。"""
    return Chunk.from_nbt(read_file(vector_path(name)).tag, options)


def block_entry(name: str) -> NbtCompound:
    """ブロックのパレット要素を作る。"""
    entry = NbtCompound()
    entry.set("Name", NbtString(name))
    return entry


class TestBlockState:
    """ブロック状態の文字列表現。仕様: docs/spec/30-chunk-format.md 2.1.1章"""

    def test_名前空間を省略するとminecraftが補われる(self):
        state = BlockState.parse("stone")
        assert state.name == "minecraft:stone"
        assert len(state.properties) == 0
        assert str(state) == "minecraft:stone"

    def test_プロパティは名前の昇順に並ぶ(self):
        state = BlockState.parse("minecraft:oak_stairs[waterlogged=false,facing=north,half=top]")
        assert str(state) == "minecraft:oak_stairs[facing=north,half=top,waterlogged=false]"

    def test_並び順が違っても同じブロックとして等しい(self):
        first = BlockState.parse("minecraft:oak_stairs[facing=north,half=top]")
        second = BlockState.parse("minecraft:oak_stairs[half=top,facing=north]")
        assert first == second
        assert hash(first) == hash(second)

    def test_名前が同じでもプロパティが違えば等しくない(self):
        first = BlockState.parse("minecraft:oak_stairs[facing=north]")
        second = BlockState.parse("minecraft:oak_stairs[facing=south]")
        assert first != second

    def test_withで作り直しても元は変わらない(self):
        original = BlockState.parse("minecraft:oak_stairs[facing=north]")
        changed = original.with_property("facing", "south")
        assert original.property("facing") == "north"
        assert changed.property("facing") == "south"

    def test_存在しないプロパティはNone(self):
        assert BlockState.parse("minecraft:stone").property("facing") is None

    def test_NBTとの相互変換でプロパティが保たれる(self):
        state = BlockState.parse("minecraft:oak_stairs[facing=north,half=top]")
        nbt = state.to_nbt()
        assert nbt.get_string("Name") == "minecraft:oak_stairs"
        assert nbt.get_compound("Properties").get_string("facing") == "north"
        assert BlockState.from_nbt(nbt) == state

    def test_プロパティ無しのNBTにはPropertiesを書かない(self):
        assert BlockState.parse("minecraft:air").to_nbt().opt_compound("Properties") is None

    @pytest.mark.parametrize("text", [
        "",
        "minecraft:oak_stairs[facing=north",
        "minecraft:oak_stairs[facing]",
        "minecraft:oak_stairs[facing=north,facing=south]",
        "minecraft:oak_stairs[]extra",
    ])
    def test_壊れた文字列はINVALID_ARGUMENT(self, text):
        with pytest.raises(SpringNbtError) as error:
            BlockState.parse(text)

        assert error.value.code == ErrorCode.INVALID_ARGUMENT


class TestBitStorage:
    """跨ぎなしのビット詰め。仕様: docs/spec/31-paletted-container.md 2章"""

    @pytest.mark.parametrize("bits,entry_count,expected", [
        (4, 4096, 256),
        (5, 4096, 342),
        (1, 64, 1),
        (6, 64, 7),
    ])
    def test_必要なlong数は跨ぎなしで求まる(self, bits, entry_count, expected):
        assert BitStorage.long_count(bits, entry_count) == expected

    def test_書いた値をそのまま読み出せる(self):
        storage = BitStorage.create(5, 4096)

        # 全エントリに位置由来の値を書いて、取りこぼしが無いか確かめる
        for index in range(4096):
            storage.set(index, index % 32)

        for index in range(4096):
            assert storage.get(index) == index % 32

    def test_long境界を跨がずに詰める(self):
        storage = BitStorage.create(5, 4096)

        # bits=5 なら 1 つの long に 12 個。12 個目は次の long の最下位から始まる
        storage.set(11, 31)
        storage.set(12, 1)
        longs = storage.to_longs()

        assert longs[0] == 31 << 55
        assert longs[1] == 1

    def test_ビット幅を広げても値が保たれる(self):
        storage = BitStorage.create(4, 4096)

        for index in range(4096):
            storage.set(index, index % 16)

        widened = storage.resize(5)
        assert widened.bits_per_entry == 5
        assert len(widened.to_longs()) == 342

        for index in range(4096):
            assert widened.get(index) == index % 16

    def test_ビット幅に対して長さが合わない配列はMALFORMED_DATA(self):
        with pytest.raises(SpringNbtError) as error:
            BitStorage.from_longs([0] * 100, 4, 4096)

        assert error.value.code == ErrorCode.MALFORMED_DATA

    def test_寛容モードなら長さからビット幅を逆算する(self):
        # 4096 エントリを 342 long で表せるのは bits=5 のときだけ
        storage = BitStorage.from_longs([0] * 342, 4, 4096, lenient=True)
        assert storage.bits_per_entry == 5

    def test_ビット幅に収まらない値はINVALID_ARGUMENT(self):
        storage = BitStorage.create(4, 64)

        with pytest.raises(SpringNbtError) as error:
            storage.set(0, 16)

        assert error.value.code == ErrorCode.INVALID_ARGUMENT

    def test_範囲外の添字はINVALID_ARGUMENT(self):
        storage = BitStorage.create(4, 64)

        with pytest.raises(SpringNbtError) as error:
            storage.get(64)

        assert error.value.code == ErrorCode.INVALID_ARGUMENT


class TestPalettedContainer:
    """パレット付きコンテナ。仕様: docs/spec/31-paletted-container.md"""

    @pytest.mark.parametrize("count,expected", [(1, 0), (2, 1), (4, 2), (5, 3), (17, 5)])
    def test_必要ビット数はceil_log2(self, count, expected):
        assert ceil_log2(count) == expected

    def test_単一値のコンテナはdataを持たない(self):
        container = PalettedContainer.filled(block_entry("minecraft:air"), 4096, 4)
        assert container.bits_per_entry == 0

        nbt = container.to_nbt()
        assert nbt.opt_long_array("data") is None
        assert len(nbt.get_list("palette")) == 1

    def test_値を足すとパレットとビット幅が広がる(self):
        container = PalettedContainer.filled(block_entry("minecraft:air"), 4096, 4)

        # パレットを 17 要素まで増やして bits=4 から 5 への拡張を起こす
        for index in range(17):
            container.set(index, block_entry("minecraft:block_%d" % index))

        assert len(container.palette) == 18
        assert container.bits_per_entry == 5
        assert len(container.to_nbt().get_long_array("data")) == 342

    def test_書き出しはdataが先でpaletteが後(self):
        # 実データがこの順なので、無変更で書き戻したときにバイト単位で一致する
        container = PalettedContainer.filled(block_entry("minecraft:air"), 4096, 4)
        container.set(0, block_entry("minecraft:stone"))

        assert list(container.to_nbt().keys()) == ["data", "palette"]

    def test_compactで未使用のパレット要素が消える(self):
        container = PalettedContainer.filled(block_entry("minecraft:air"), 4096, 4)
        container.set(0, block_entry("minecraft:stone"))
        container.set(0, block_entry("minecraft:dirt"))
        assert len(container.palette) == 3

        container.compact()

        # 残るのは実際に使われている air と dirt の 2 つ
        assert len(container.palette) == 2
        assert container.get(0).get_string("Name") == "minecraft:dirt"

    def test_fillで単一値に戻る(self):
        container = PalettedContainer.filled(block_entry("minecraft:air"), 4096, 4)
        container.set(0, block_entry("minecraft:stone"))
        container.fill(block_entry("minecraft:water"))

        assert len(container.palette) == 1
        assert container.bits_per_entry == 0
        assert container.get(4095).get_string("Name") == "minecraft:water"

    def test_範囲外の添字はINVALID_ARGUMENT(self):
        container = PalettedContainer.filled(block_entry("minecraft:air"), 4096, 4)

        with pytest.raises(SpringNbtError) as error:
            container.get(4096)

        assert error.value.code == ErrorCode.INVALID_ARGUMENT


class TestChunk:
    """チャンクの解釈。仕様: docs/spec/30-chunk-format.md"""

    def test_パレット1要素のチャンクを読める(self):
        chunk = load_chunk("palette_1")

        assert chunk.data_version == TARGET_DATA_VERSION
        assert chunk.x == 0
        assert chunk.z == 0
        assert chunk.min_section_y == -4
        assert chunk.is_fully_generated
        assert chunk.section_ys == [-4]
        assert chunk.get_block(0, -64, 0).name == "minecraft:air"
        assert chunk.get_biome(0, -64, 0) == "minecraft:plains"

    def test_ビット幅5のチャンクを端から端まで読める(self):
        chunk = load_chunk("palette_17")
        head = ["minecraft:air", "minecraft:stone"]

        # ベクタの添字は (位置 * 11) % 17。パレット先頭 2 つだけ名前が違う
        for position in range(4096):
            palette_index = (position * 11) % 17
            block = chunk.get_block(position & 15, -64 + (position >> 8), (position >> 4) & 15)

            if palette_index < 2:
                assert str(block) == head[palette_index]
            else:
                assert str(block) == "minecraft:stone[variant=v%d]" % (palette_index - 2)

    def test_セクションの無い高さはNone(self):
        chunk = load_chunk("palette_1")
        assert chunk.get_block(0, 100, 0) is None
        assert chunk.section(0) is None

    def test_生成途中のチャンクはfullではない(self):
        chunk = load_chunk("proto_chunk")
        assert chunk.status == "minecraft:structure_starts"
        assert not chunk.is_fully_generated

    def test_ブロックを置くとその場所だけ変わる(self):
        chunk = load_chunk("palette_1")
        chunk.set_block(3, -60, 7, BlockState.parse("minecraft:oak_stairs[facing=north,half=top]"))

        assert str(chunk.get_block(3, -60, 7)) == "minecraft:oak_stairs[facing=north,half=top]"
        assert chunk.get_block(3, -60, 6).name == "minecraft:air"
        assert chunk.get_block(4, -60, 7).name == "minecraft:air"

    def test_バイオームは4ブロック単位で効く(self):
        chunk = load_chunk("palette_1")
        chunk.set_biome(0, -64, 0, "minecraft:desert")

        # 同じ 4×4×4 の枠内はまとめて変わる
        assert chunk.get_biome(3, -61, 3) == "minecraft:desert"
        assert chunk.get_biome(4, -64, 0) == "minecraft:plains"

    def test_compactで未使用のパレット要素が消える(self):
        chunk = load_chunk("palette_unused")
        before = chunk.section(-4).to_nbt()
        assert len(before.get_compound("block_states").get_list("palette")) == 4

        chunk.compact()

        after = chunk.section(-4).to_nbt()
        assert len(after.get_compound("block_states").get_list("palette")) == 2

    def test_無変更で書き戻すと元と同じNBTになる(self):
        named = read_file(vector_path("multi_section"))
        options = NbtWriteOptions(compression=Compression.NONE)
        before = write_bytes(named, options)

        chunk = Chunk.from_nbt(named.tag)
        after = write_bytes(NamedTag(named.name, chunk.to_nbt()), options)

        assert after == before

    def test_高さマップと光源を無効化できる(self):
        chunk = load_chunk("palette_1")
        chunk.clear_heightmaps()
        chunk.invalidate_lighting()

        raw = chunk.to_nbt()
        assert raw.opt_compound("Heightmaps") is None
        assert raw.get_bool("isLightOn") is False

    def test_添字が範囲外のチャンクはMALFORMED_DATA(self):
        with pytest.raises(SpringNbtError) as error:
            load_chunk("palette_index_out_of_range")

        assert error.value.code == ErrorCode.MALFORMED_DATA

    def test_data長が合わないチャンクはMALFORMED_DATA(self):
        with pytest.raises(SpringNbtError) as error:
            load_chunk("bitstorage_wrong_length")

        assert error.value.code == ErrorCode.MALFORMED_DATA

    def test_チャンク内の相対座標が範囲外ならINVALID_ARGUMENT(self):
        chunk = load_chunk("palette_1")

        with pytest.raises(SpringNbtError) as error:
            chunk.get_block(16, -64, 0)

        assert error.value.code == ErrorCode.INVALID_ARGUMENT


class TestDataVersion:
    """バージョンポリシー。仕様: docs/spec/30-chunk-format.md 5章"""

    @staticmethod
    def foreign_chunk() -> NbtCompound:
        """DataVersion だけを差し替えたチャンクを作る。"""
        root = read_file(vector_path("palette_1")).tag
        root.set("DataVersion", NbtInt(3953))
        return root

    def test_既定では警告として通す(self):
        warnings = []
        options = ChunkReadOptions(
            on_version_mismatch=VersionMismatchAction.WARN,
            on_warning=warnings.append)

        chunk = Chunk.from_nbt(self.foreign_chunk(), options)
        assert chunk.data_version == 3953
        assert len(warnings) == 1

    def test_ERRORを指定すると読み込みで弾く(self):
        options = ChunkReadOptions(on_version_mismatch=VersionMismatchAction.ERROR)

        with pytest.raises(SpringNbtError) as error:
            Chunk.from_nbt(self.foreign_chunk(), options)

        assert error.value.code == ErrorCode.UNSUPPORTED_DATA_VERSION

    def test_IGNOREなら何も起きない(self):
        warnings = []
        options = ChunkReadOptions(
            on_version_mismatch=VersionMismatchAction.IGNORE,
            on_warning=warnings.append)

        Chunk.from_nbt(self.foreign_chunk(), options)
        assert len(warnings) == 0

    def test_別バージョン由来のチャンクは既定で書き戻せない(self):
        chunk = Chunk.from_nbt(
            self.foreign_chunk(),
            ChunkReadOptions(on_version_mismatch=VersionMismatchAction.IGNORE))

        with pytest.raises(SpringNbtError) as error:
            chunk.to_nbt()

        assert error.value.code == ErrorCode.UNSUPPORTED_DATA_VERSION

    def test_許可すれば対象バージョンとして書き戻す(self):
        chunk = Chunk.from_nbt(
            self.foreign_chunk(),
            ChunkReadOptions(on_version_mismatch=VersionMismatchAction.IGNORE))

        # 書き戻しは常に対象バージョンへ揃える
        written = chunk.to_nbt(ChunkWriteOptions(allow_foreign_data_version=True))
        assert written.get_int("DataVersion") == TARGET_DATA_VERSION

    def test_対象バージョンのチャンクはそのまま書き戻せる(self):
        chunk = load_chunk("palette_1")
        assert chunk.to_nbt().get_int("DataVersion") == TARGET_DATA_VERSION


class TestMinecraftWorld:
    """ワールドを開く。仕様: docs/spec/40-world-layout.md"""

    def test_存在しないディレクトリはIO(self, tmp_path):
        with pytest.raises(SpringNbtError) as error:
            MinecraftWorld.open(str(tmp_path / "missing"))

        assert error.value.code == ErrorCode.IO

    def test_levelDatが無いディレクトリはIO(self, tmp_path):
        with pytest.raises(SpringNbtError) as error:
            MinecraftWorld.open(str(tmp_path))

        assert error.value.code == ErrorCode.IO

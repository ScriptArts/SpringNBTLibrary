"""World / Blockレイヤ

他言語版と同じ検証項目を持つ
共通テストベクタによる言語間比較はspec/run-conformance.shが担当し、ここではAPIの振る舞いを直接確かめる
"""

from __future__ import annotations

import os

import pytest

from spring_nbt_library import (
    MIN_SUPPORTED_DATA_VERSION,
    TARGET_DATA_VERSION,
    ErrorCode,
    SpringNbtError,
)
from spring_nbt_library.nbt import (
    Compression,
    NamedTag,
    NbtByte,
    NbtCompound,
    NbtInt,
    NbtIntArray,
    NbtList,
    NbtLongArray,
    NbtString,
    TagType,
    NbtWriteOptions,
    read_file,
    write_bytes,
    write_file,
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
    WorldOpenOptions,
    ceil_log2,
)
from spring_nbt_library.anvil import RegionFile, RegionFileMode

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VECTORS = os.path.join(REPO_ROOT, "spec", "testdata", "world")


def vector_path(name: str) -> str:
    """共通テストベクタ（world/*.nbt）のパス"""
    path = os.path.join(VECTORS, name + ".nbt")

    if not os.path.isfile(path):
        raise AssertionError("テストベクタが見つからない: world/%s.nbt" % name)

    return path


def load_chunk(name: str, options: ChunkReadOptions = None) -> Chunk:
    """テストベクタをチャンクとして読む"""
    return Chunk.from_nbt(read_file(vector_path(name)).tag, options)


def block_entry(name: str) -> NbtString:
    """プロパティの無いブロックのパレット要素を作る
    26.3からはブロックIDだけの文字列で入る
    """
    return NbtString(name)


def wrapped(tag) -> NbtCompound:
    """異種リストの要素を包むCompoundを作る"""
    wrapper = NbtCompound()
    wrapper.set("", tag)
    return wrapper


def name_properties(name: str, properties=None) -> NbtCompound:
    """26.2までの形式（Name / Properties）のパレット要素を作る"""
    entry = NbtCompound()
    entry.set_string("Name", name)

    # プロパティがあるときだけPropertiesを足す
    if properties is not None:
        properties_tag = NbtCompound()

        # 渡された順に入れる
        for key, value in properties:
            properties_tag.set_string(key, value)

        entry.set("Properties", properties_tag)

    return entry


def id_properties(name: str, properties) -> NbtCompound:
    """26.3からの形式（id / properties）のパレット要素を作る"""
    entry = NbtCompound()
    entry.set_string("id", name)
    properties_tag = NbtCompound()

    # 渡された順に入れる
    for key, value in properties:
        properties_tag.set_string(key, value)

    entry.set("properties", properties_tag)
    return entry


#: 扱える形式の下限より古く、1.13より前でもあるDataVersion
#: どの世代でも解釈しない
PRE_FLATTENING_DATA_VERSION = 1400


def pre_flattening_chunk() -> NbtCompound:
    """1.13より前のようにLevelに本体を包み、ブロックを数値IDで持つチャンクを作る"""
    section = NbtCompound()
    section.set_byte("Y", 0)
    section.set_byte_array("Blocks", [1] * 4096)
    section.set_byte_array("Data", [0] * 2048)
    sections = NbtList(TagType.COMPOUND)
    sections.append(section)

    level = NbtCompound()
    level.set_int("xPos", 3)
    level.set_int("zPos", -2)
    level.set("Sections", sections)

    root = NbtCompound()
    root.set_int("DataVersion", PRE_FLATTENING_DATA_VERSION)
    root.set("Level", level)
    return root


def level_chunk(data_version: int) -> NbtCompound:
    """1.17までのようにLevelに本体を包んだチャンクを作る"""
    level = NbtCompound()
    level.set_int("xPos", 0)
    level.set_int("zPos", 0)
    level.set_string("Status", "full")
    level.set("Sections", NbtList(TagType.COMPOUND))

    root = NbtCompound()
    root.set_int("DataVersion", data_version)
    root.set("Level", level)
    return root


def chunk_bytes(tag: NbtCompound) -> bytes:
    """チャンクのNBTを無圧縮のバイト列にする"""
    return write_bytes(NamedTag("", tag), NbtWriteOptions(compression=Compression.NONE))


class TestBlockState:
    """ブロック状態の文字列表現
    """

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
        assert list(nbt.keys()) == ["id", "properties"]
        assert nbt.get_string("id") == "minecraft:oak_stairs"
        assert nbt.get_compound("properties").get_string("facing") == "north"
        assert BlockState.from_nbt(nbt) == state

    def test_プロパティ無しのブロックは文字列になる(self):
        assert BlockState.parse("minecraft:air").to_nbt() == NbtString("minecraft:air")

    def test_文字列のパレット要素を読める(self):
        state = BlockState.from_nbt(NbtString("minecraft:stone"))
        assert state.name == "minecraft:stone"
        assert len(state.properties) == 0

    def test_包まれたパレット要素を読める(self):
        state = BlockState.from_nbt(wrapped(NbtString("minecraft:stone")))
        assert str(state) == "minecraft:stone"

    def test_propertiesの無いCompoundも読める(self):
        entry = NbtCompound()
        entry.set("id", NbtString("minecraft:stone"))
        assert str(BlockState.from_nbt(entry)) == "minecraft:stone"

    def test_パレット要素が26_2までの形式ならMALFORMED_DATA(self):
        entry = NbtCompound()
        entry.set("Name", NbtString("minecraft:stone"))

        with pytest.raises(SpringNbtError) as error:
            BlockState.from_nbt(entry)

        assert error.value.code == ErrorCode.MALFORMED_DATA

    def test_文字列でもCompoundでもない要素はUNEXPECTED_TAG_TYPE(self):
        with pytest.raises(SpringNbtError) as error:
            BlockState.from_nbt(NbtInt(1))

        assert error.value.code == ErrorCode.UNEXPECTED_TAG_TYPE

    def test_DataVersion2844ではName_Propertiesを読む(self):
        properties = NbtCompound()
        properties.set("facing", NbtString("north"))
        entry = NbtCompound()
        entry.set("Name", NbtString("minecraft:oak_stairs"))
        entry.set("Properties", properties)

        state = BlockState.from_nbt_for_data_version(entry, 2844)
        assert str(state) == "minecraft:oak_stairs[facing=north]"

    def test_DataVersion2844でidを持つ要素はMALFORMED_DATA(self):
        entry = NbtCompound()
        entry.set("id", NbtString("minecraft:stone"))

        with pytest.raises(SpringNbtError) as error:
            BlockState.from_nbt_for_data_version(entry, 2844)

        assert error.value.code == ErrorCode.MALFORMED_DATA

    def test_DataVersion2844で文字列の要素はUNEXPECTED_TAG_TYPE(self):
        with pytest.raises(SpringNbtError) as error:
            BlockState.from_nbt_for_data_version(NbtString("minecraft:stone"), 2844)

        assert error.value.code == ErrorCode.UNEXPECTED_TAG_TYPE

    def test_DataVersion2844でPropertiesの値が文字列でなければUNEXPECTED_TAG_TYPE(self):
        properties = NbtCompound()
        properties.set("facing", NbtInt(1))
        entry = NbtCompound()
        entry.set("Name", NbtString("minecraft:oak_stairs"))
        entry.set("Properties", properties)

        with pytest.raises(SpringNbtError) as error:
            BlockState.from_nbt_for_data_version(entry, 2844)

        assert error.value.code == ErrorCode.UNEXPECTED_TAG_TYPE

    def test_DataVersion2844ではName_Propertiesで書く(self):
        plain = BlockState.parse("minecraft:stone").to_nbt_for_data_version(2844)
        expected = NbtCompound()
        expected.set("Name", NbtString("minecraft:stone"))
        assert plain == expected
        assert "Properties" not in plain

        stairs = BlockState.parse("minecraft:oak_stairs[half=top,facing=north]")
        nbt = stairs.to_nbt_for_data_version(2844)
        assert list(nbt.keys()) == ["Name", "Properties"]
        assert nbt.get_string("Name") == "minecraft:oak_stairs"
        assert list(nbt.get_compound("Properties").keys()) == ["facing", "half"]
        assert BlockState.from_nbt_for_data_version(nbt, 2844) == stairs

    @pytest.mark.parametrize("data_version", [5006, 5023])
    def test_DataVersion5006以降はfrom_nbtとto_nbtと同じ(self, data_version):
        stairs = BlockState.parse("minecraft:oak_stairs[facing=north,half=top]")
        assert stairs.to_nbt_for_data_version(data_version) == stairs.to_nbt()

        plain = BlockState.parse("minecraft:stone")
        assert plain.to_nbt_for_data_version(data_version) == NbtString("minecraft:stone")

        assert BlockState.from_nbt_for_data_version(NbtString("minecraft:stone"), data_version) == plain
        assert BlockState.from_nbt_for_data_version(stairs.to_nbt(), data_version) == stairs
        wrapper = wrapped(NbtString("minecraft:stone"))
        assert BlockState.from_nbt_for_data_version(wrapper, data_version) == BlockState.from_nbt(wrapper)

    def test_DataVersion1519で境界の形式を扱える(self):
        state = BlockState.parse("minecraft:oak_stairs[facing=north]")
        assert BlockState.from_nbt_for_data_version(state.to_nbt_for_data_version(1519), 1519) == state

    def test_DataVersionが1519未満ならINVALID_ARGUMENT(self):
        with pytest.raises(SpringNbtError) as read_error:
            BlockState.from_nbt_for_data_version(NbtString("minecraft:stone"), 1518)

        assert read_error.value.code == ErrorCode.INVALID_ARGUMENT

        with pytest.raises(SpringNbtError) as write_error:
            BlockState.parse("minecraft:stone").to_nbt_for_data_version(1518)

        assert write_error.value.code == ErrorCode.INVALID_ARGUMENT

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
    """跨ぎなしのビット詰め
    """

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

        # bits=5なら1つのlongに12個
        # 添字12は次のlongの最下位から始まる
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
        # 4096エントリを342 longで表せるのはbits=5のときだけ
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
    """パレット付きコンテナ
    """

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

        # 17種のブロックを足してパレットを18要素にし、bits=4から5への拡張を起こす
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

        # 残るのは実際に使われているairとdirtの2つ
        assert len(container.palette) == 2
        assert container.get(0).value == "minecraft:dirt"

    def test_fillで単一値に戻る(self):
        container = PalettedContainer.filled(block_entry("minecraft:air"), 4096, 4)
        container.set(0, block_entry("minecraft:stone"))
        container.fill(block_entry("minecraft:water"))

        assert len(container.palette) == 1
        assert container.bits_per_entry == 0
        assert container.get(4095).value == "minecraft:water"

    def test_文字列だけのパレットは文字列のリストで書く(self):
        container = PalettedContainer.filled(block_entry("minecraft:air"), 4096, 4)
        container.set(0, block_entry("minecraft:stone"))

        palette = container.to_nbt().get_list("palette")
        assert palette.element_type == TagType.STRING
        assert palette[1] == NbtString("minecraft:stone")

    def test_型が混ざったパレットは文字列を包んでCompoundのリストで書く(self):
        stairs = BlockState.parse("minecraft:oak_stairs[facing=north]").to_nbt()
        container = PalettedContainer.filled(block_entry("minecraft:air"), 4096, 4)
        container.set(0, stairs)

        palette = container.to_nbt().get_list("palette")
        assert palette.element_type == TagType.COMPOUND
        assert palette[0] == wrapped(NbtString("minecraft:air"))
        assert palette[1] == stairs

    def test_包まれたパレットは包みを外して持ち元どおりに書き戻す(self):
        stairs = BlockState.parse("minecraft:oak_stairs[facing=north]").to_nbt()
        palette = NbtList(TagType.COMPOUND)
        palette.append(wrapped(NbtString("minecraft:air")))
        palette.append(stairs)

        # パレット2要素ならbits=4で256 long
        nbt = NbtCompound()
        nbt.set("data", NbtLongArray([0] * 256))
        nbt.set("palette", palette)

        container = PalettedContainer.from_nbt(nbt, 4096, 4)

        # 包みは外れ、要素は文字列とCompoundとして並ぶ
        assert container.palette[0] == NbtString("minecraft:air")
        assert container.palette[1] == stairs

        # 書き戻すと、また包まれて元と同じになる
        assert container.to_nbt() == nbt

    def test_compactでCompoundが消えると文字列のリストに戻る(self):
        stairs = BlockState.parse("minecraft:oak_stairs[facing=north]").to_nbt()
        container = PalettedContainer.filled(block_entry("minecraft:air"), 4096, 4)
        container.set(0, stairs)
        container.set(0, block_entry("minecraft:stone"))

        container.compact()

        palette = container.to_nbt().get_list("palette")
        assert palette.element_type == TagType.STRING
        assert len(palette) == 2

    def test_範囲外の添字はINVALID_ARGUMENT(self):
        container = PalettedContainer.filled(block_entry("minecraft:air"), 4096, 4)

        with pytest.raises(SpringNbtError) as error:
            container.get(4096)

        assert error.value.code == ErrorCode.INVALID_ARGUMENT


class TestChunk:
    """チャンクの解釈
    """

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

        # ベクタの添字は (位置 * 11) % 17
        # パレットの先頭2つだけ名前が違う
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

    def test_ブロックを文字列でも置ける(self):
        chunk = load_chunk("palette_1")
        chunk.set_block(3, -60, 7, "minecraft:oak_stairs[facing=north,half=top]")

        assert str(chunk.get_block(3, -60, 7)) == "minecraft:oak_stairs[facing=north,half=top]"

    def test_変更したチャンクには印が付く(self):
        chunk = load_chunk("palette_1")
        assert chunk.is_modified is False

        chunk.set_block(3, -60, 7, "minecraft:stone")
        assert chunk.is_modified is True

        # 保存済みとして印を外せる
        chunk.is_modified = False
        assert chunk.is_modified is False

        # 同じ状態を置き直すだけなら何も起きないので印も付かない
        chunk.set_block(3, -60, 7, "minecraft:stone")
        assert chunk.is_modified is False

        chunk.clear_heightmaps()
        assert chunk.is_modified is True

    def test_バイオームは4ブロック単位で効く(self):
        chunk = load_chunk("palette_1")
        chunk.set_biome(0, -64, 0, "minecraft:desert")

        # 同じ4×4×4の枠内はまとめて変わる
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

    def test_ブロックを置き換えると同じ座標の付随データが消える(self):
        chunk = load_chunk("block_entities")
        assert len(chunk.raw.get_list("block_entities")) == 3
        assert len(chunk.raw.get_list("block_ticks")) == 2
        assert len(chunk.raw.get_list("fluid_ticks")) == 1

        # (0,-64,0)にはchestとblock_tick、(1,-64,1)にはfurnaceとfluid_tickがある
        chunk.set_block(0, -64, 0, BlockState.parse("minecraft:stone"))
        chunk.set_block(1, -64, 1, BlockState.parse("minecraft:stone"))

        entities = chunk.raw.get_list("block_entities")

        # 触っていない(15,-50,15)のbarrelだけが残る
        assert len(entities) == 1
        assert entities[0].get_string("id") == "minecraft:barrel"

        ticks = chunk.raw.get_list("block_ticks")
        assert len(ticks) == 1
        assert ticks[0].get_int("x") == 15

        assert len(chunk.raw.get_list("fluid_ticks")) == 0

    def test_同じブロックを置き直しても付随データは消えない(self):
        chunk = load_chunk("block_entities")
        current = chunk.get_block(0, -64, 0)

        # 変化が無いなら付随データを触る理由がない
        chunk.set_block(0, -64, 0, current)

        assert len(chunk.raw.get_list("block_entities")) == 3
        assert len(chunk.raw.get_list("block_ticks")) == 2

    def test_別のチャンクの同じ相対座標は消さない(self):
        # 付随データは絶対座標で持つので、チャンク座標を間違えると無関係な要素を消してしまう
        root = read_file(vector_path("block_entities")).tag
        root.set("xPos", NbtInt(1))
        root.set("zPos", NbtInt(1))

        chunk = Chunk.from_nbt(root)
        chunk.set_block(0, -64, 0, BlockState.parse("minecraft:stone"))

        # このチャンクの(0,-64,0)は絶対座標(16,-64,16)
        # どれとも一致しない
        assert len(chunk.raw.get_list("block_entities")) == 3

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
    """バージョンポリシー
    """

    @staticmethod
    def foreign_chunk() -> NbtCompound:
        """DataVersionだけを、扱える形式の下限より古い値に差し替えたチャンクを作る"""
        root = read_file(vector_path("palette_1")).tag
        root.set("DataVersion", NbtInt(PRE_FLATTENING_DATA_VERSION))
        return root

    def test_既定では警告として通す(self):
        warnings = []
        options = ChunkReadOptions(
            on_version_mismatch=VersionMismatchAction.WARN,
            on_warning=warnings.append)

        chunk = Chunk.from_nbt(self.foreign_chunk(), options)
        assert chunk.data_version == PRE_FLATTENING_DATA_VERSION
        assert len(warnings) == 1

    def test_DataVersionが26_2のチャンクは警告を出さずに読める(self):
        warnings = []
        options = ChunkReadOptions(
            on_version_mismatch=VersionMismatchAction.WARN,
            on_warning=warnings.append)

        # 26.2の形式も扱う形式に含まれる
        load_chunk("palette_old_format", options)
        assert warnings == []

    def test_扱える形式の下限は1_18(self):
        assert MIN_SUPPORTED_DATA_VERSION == 2844

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

    def test_許可すれば古いチャンクも元のバージョンのまま書き戻せる(self):
        chunk = Chunk.from_nbt(
            self.foreign_chunk(),
            ChunkReadOptions(on_version_mismatch=VersionMismatchAction.IGNORE))

        # DataVersionは読んだ値のまま残す
        written = chunk.to_nbt(ChunkWriteOptions(allow_foreign_data_version=True))
        assert written.get_int("DataVersion") == PRE_FLATTENING_DATA_VERSION

    def test_対象バージョンのチャンクはそのまま書き戻せる(self):
        chunk = load_chunk("palette_1")
        assert chunk.to_nbt().get_int("DataVersion") == TARGET_DATA_VERSION

    @staticmethod
    def newer_chunk() -> NbtCompound:
        """対象より新しいDataVersionを持つチャンクを作る"""
        root = read_file(vector_path("palette_1")).tag
        root.set("DataVersion", NbtInt(5100))
        return root

    def test_新しいバージョンのチャンクは警告を出さない(self):
        warnings = []
        options = ChunkReadOptions(
            on_version_mismatch=VersionMismatchAction.WARN,
            on_warning=warnings.append)

        # 形式が同じであれば、新しいバージョンでも警告を出さずに読める
        chunk = Chunk.from_nbt(self.newer_chunk(), options)
        assert chunk.data_version == 5100
        assert warnings == []

    def test_新しいバージョンのチャンクはERRORでも通る(self):
        options = ChunkReadOptions(on_version_mismatch=VersionMismatchAction.ERROR)
        assert Chunk.from_nbt(self.newer_chunk(), options).data_version == 5100

    def test_新しいバージョンのチャンクはそのまま書き戻せる(self):
        chunk = Chunk.from_nbt(self.newer_chunk())

        # 許可を出さなくても書き戻せて、DataVersionも変わらない
        assert chunk.to_nbt().get_int("DataVersion") == 5100


class TestChunkFormat:
    """チャンクの形式の世代
    """

    def test_DataVersion4903のチャンクを読み無変更で書き戻すと元と同じになる(self):
        named = read_file(vector_path("v4903_edit"))
        before = chunk_bytes(named.tag)
        chunk = Chunk.from_nbt(named.tag)

        # ベクタの添字は (位置 * 7) % 5
        assert chunk.data_version == 4903
        assert str(chunk.get_block(0, -64, 0)) == "minecraft:air"
        assert str(chunk.get_block(1, -64, 0)) == "minecraft:dirt"
        assert str(chunk.get_block(2, -64, 0)) == "minecraft:oak_stairs[facing=west,half=top]"
        assert str(chunk.get_block(3, -64, 0)) == "minecraft:stone"
        assert str(chunk.get_block(4, -64, 0)) == "minecraft:oak_stairs[facing=east,half=bottom]"
        assert chunk.get_biome(0, -64, 0) == "minecraft:plains"

        assert chunk_bytes(chunk.to_nbt()) == before

    def test_DataVersion4903のチャンクに置いたブロックはName_Propertiesで入る(self):
        chunk = load_chunk("v4903_edit")
        chunk.set_block(5, -64, 5, BlockState.parse("minecraft:oak_stairs[facing=north]"))
        written = chunk.to_nbt()

        # パレットの末尾に26.2の形式で足される
        palette = written.get_list("sections")[0].get_compound("block_states").get_list("palette")
        assert palette[len(palette) - 1] == name_properties(
            "minecraft:oak_stairs", [("facing", "north")])

        # DataVersionは読んだ値のまま
        assert written.get_int("DataVersion") == 4903

        # 読み直しても同じ状態が返る
        reread = Chunk.from_nbt(written)
        assert str(reread.get_block(5, -64, 5)) == "minecraft:oak_stairs[facing=north]"

    def test_形式の違うチャンクはそれぞれ読んだ形式で書き出す(self):
        old = load_chunk("v4903_edit")
        new = load_chunk("palette_5")

        # 2つのチャンクに同じ手順で同じブロックを置く
        for chunk in (old, new):
            chunk.set_block(5, -64, 5, BlockState.parse("minecraft:oak_stairs[facing=north]"))
            chunk.set_block(6, -64, 6, BlockState.parse("minecraft:edited_plain"))

        old_written = old.to_nbt()
        old_palette = old_written.get_list("sections")[0].get_compound(
            "block_states").get_list("palette")
        assert old_palette[len(old_palette) - 2] == name_properties(
            "minecraft:oak_stairs", [("facing", "north")])
        assert old_palette[len(old_palette) - 1] == name_properties("minecraft:edited_plain")
        assert old_written.get_int("DataVersion") == 4903

        new_written = new.to_nbt()
        new_palette = new_written.get_list("sections")[0].get_compound(
            "block_states").get_list("palette")
        # 型の混ざったパレットはCompoundのリストになり、文字列の要素だけが包まれる
        assert new_palette[len(new_palette) - 2] == id_properties(
            "minecraft:oak_stairs", [("facing", "north")])
        assert new_palette[len(new_palette) - 1] == wrapped(NbtString("minecraft:edited_plain"))
        assert new_written.get_int("DataVersion") == TARGET_DATA_VERSION

    def test_指定した世代とLevelの有無が食い違えばMALFORMED_DATA(self):
        options = ChunkReadOptions(
            on_version_mismatch=VersionMismatchAction.IGNORE, format_data_version=5023)

        # Levelを持つチャンクを、Levelの無い世代で読ませる
        with pytest.raises(SpringNbtError) as error:
            Chunk.from_nbt(level_chunk(2586), options)

        assert error.value.code == ErrorCode.MALFORMED_DATA

    def test_世代を指定しても下限より古いチャンクは書き戻せない(self):
        options = ChunkReadOptions(
            on_version_mismatch=VersionMismatchAction.IGNORE, format_data_version=5023)
        chunk = Chunk.from_nbt(pre_flattening_chunk(), options)

        with pytest.raises(SpringNbtError) as error:
            chunk.to_nbt()

        assert error.value.code == ErrorCode.UNSUPPORTED_DATA_VERSION

    def test_世代に1519未満を指定するとINVALID_ARGUMENT(self):
        options = ChunkReadOptions(format_data_version=1518)

        with pytest.raises(SpringNbtError) as error:
            Chunk.from_nbt(read_file(vector_path("palette_1")).tag, options)

        assert error.value.code == ErrorCode.INVALID_ARGUMENT

    def test_DataVersionが1519未満のチャンクは元のNBTだけを持つ(self):
        root = pre_flattening_chunk()
        before = chunk_bytes(root)
        options = ChunkReadOptions(on_version_mismatch=VersionMismatchAction.IGNORE)
        chunk = Chunk.from_nbt(root, options)

        # 座標はLevelの中から読み、セクションは解釈しない
        assert chunk.x == 3
        assert chunk.z == -2
        assert chunk.section_ys == []

        # ブロック・バイオーム・高さマップ・光源の操作はどれも受け付けない
        operations = [
            lambda: chunk.get_block(0, 0, 0),
            lambda: chunk.set_block(0, 0, 0, "minecraft:stone"),
            lambda: chunk.get_biome(0, 0, 0),
            lambda: chunk.set_biome(0, 0, 0, "minecraft:plains"),
            lambda: chunk.clear_heightmaps(),
            lambda: chunk.invalidate_lighting(),
        ]

        # 操作ごとにUNSUPPORTED_DATA_VERSIONになることを確かめる
        for operation in operations:
            with pytest.raises(SpringNbtError) as error:
                operation()

            assert error.value.code == ErrorCode.UNSUPPORTED_DATA_VERSION

        # 許可すれば、読んだNBTがそのまま返る
        written = chunk.to_nbt(ChunkWriteOptions(allow_foreign_data_version=True))
        assert chunk_bytes(written) == before

    def test_世代を選んだDataVersionを返す(self):
        tag = read_file(vector_path("v4903_edit")).tag
        assert Chunk.from_nbt(tag).format_data_version == 4903

        # 指定すれば、チャンク自身のDataVersionではなくその値になる
        chunk = Chunk.from_nbt(tag, ChunkReadOptions(format_data_version=5023))
        assert chunk.format_data_version == 5023
        assert chunk.data_version == 4903


def write_level(directory, entries):
    """``Data``に指定の項目だけを持つlevel.datを書く"""
    data = NbtCompound()

    for key, tag in entries.items():
        data.set(key, tag)

    root = NbtCompound()
    root.set("Data", data)
    write_file(str(directory / "level.dat"), NamedTag("", root))


def write_dat(path, entries):
    """指定の項目を持つ.datを、フォルダごと作って書く"""
    path.parent.mkdir(parents=True, exist_ok=True)
    root = NbtCompound()

    for key, tag in entries.items():
        root.set(key, tag)

    write_file(str(path), NamedTag("", root))


def make_l1_world(directory):
    """L1の合成ワールドを作る"""
    write_level(directory, {"DataVersion": NbtInt(3953)})

    for folder in ("region", "DIM-1/region", "DIM1/region", "dimensions/mymap/arena/region"):
        (directory / folder).mkdir(parents=True)


class TestMinecraftWorld:
    """ワールドを開く
    """

    def test_存在しないディレクトリはIO(self, tmp_path):
        with pytest.raises(SpringNbtError) as error:
            MinecraftWorld.open(str(tmp_path / "missing"))

        assert error.value.code == ErrorCode.IO

    def test_levelDatが無いディレクトリはIO(self, tmp_path):
        with pytest.raises(SpringNbtError) as error:
            MinecraftWorld.open(str(tmp_path))

        assert error.value.code == ErrorCode.IO

    def test_次元経由で読んだチャンクの警告も通知先へ届く(self, tmp_path):
        region = tmp_path / "dimensions" / "minecraft" / "overworld" / "region"
        region.mkdir(parents=True)

        # DataVersionが扱える形式より古いチャンクを1つだけ持つワールドを作る
        write_level(tmp_path, {"DataVersion": NbtInt(5023)})

        chunk = read_file(vector_path("palette_1")).tag
        chunk.set("DataVersion", NbtInt(PRE_FLATTENING_DATA_VERSION))

        with RegionFile.open(str(region / "r.0.0.mca"), RegionFileMode.READ_WRITE) as file:
            file.write_chunk(0, 0, chunk)

        warnings = []
        options = WorldOpenOptions(chunk_read=ChunkReadOptions(on_warning=warnings.append))

        with MinecraftWorld.open(str(tmp_path), options) as world:
            assert world.dimension("minecraft:overworld").chunk(0, 0) is not None

        # ワールドを開くときに渡した通知先が、次元経由の読み込みでも呼ばれる
        assert len(warnings) == 1


class TestWorldLayout:
    """ワールドの構成の世代（L1とL2）
    """

    def test_world_l1_dimensions(self, tmp_path):
        make_l1_world(tmp_path)

        with MinecraftWorld.open(str(tmp_path)) as world:
            assert world.dimension_ids() == [
                "minecraft:overworld", "minecraft:the_nether",
                "minecraft:the_end", "mymap:arena"]
            assert world.dimension("minecraft:overworld").directory == str(tmp_path)
            assert world.dimension("minecraft:the_nether").directory == str(tmp_path / "DIM-1")
            assert world.dimension("minecraft:the_end").directory == str(tmp_path / "DIM1")
            assert world.dimension("mymap:arena").directory == str(
                tmp_path / "dimensions" / "mymap" / "arena")

            # 次元が無ければNone
            assert world.dimension("mymap:missing") is None

    def test_L1で存在しない標準の次元は並ばない(self, tmp_path):
        write_level(tmp_path, {"DataVersion": NbtInt(3953)})
        (tmp_path / "region").mkdir()

        with MinecraftWorld.open(str(tmp_path)) as world:
            assert world.dimension_ids() == ["minecraft:overworld"]
            assert world.dimension("minecraft:the_nether") is None

    def test_L1ではdimensionsの下の標準の次元は並ばない(self, tmp_path):
        write_level(tmp_path, {"DataVersion": NbtInt(3953)})
        (tmp_path / "dimensions" / "minecraft" / "the_nether" / "region").mkdir(parents=True)

        with MinecraftWorld.open(str(tmp_path)) as world:
            assert "minecraft:the_nether" not in world.dimension_ids()
            assert world.dimension("minecraft:the_nether") is None

    def test_world_l1_players(self, tmp_path):
        make_l1_world(tmp_path)
        write_dat(tmp_path / "playerdata" / "b-uuid.dat", {"Health": NbtInt(20)})
        write_dat(tmp_path / "playerdata" / "a-uuid.dat", {"Health": NbtInt(7)})

        with MinecraftWorld.open(str(tmp_path)) as world:
            assert world.player_ids() == ["a-uuid", "b-uuid"]
            assert world.player("a-uuid").get_int("Health") == 7
            assert world.player("missing") is None

    def test_world_l1_data_file(self, tmp_path):
        make_l1_world(tmp_path)
        write_dat(tmp_path / "data" / "scoreboard.dat", {"Value": NbtInt(1)})
        write_dat(tmp_path / "DIM-1" / "data" / "raids_nether.dat", {"Value": NbtInt(2)})

        with MinecraftWorld.open(str(tmp_path)) as world:
            assert world.data_file("scoreboard").get_int("Value") == 1
            assert world.data_file("missing") is None
            assert world.dimension("minecraft:the_nether").data_file(
                "raids_nether").get_int("Value") == 2

            # オーバーワールドの次元は、ワールドと同じdata/を読む
            assert world.dimension("minecraft:overworld").data_file(
                "scoreboard").get_int("Value") == 1

    def test_level_data_l1_getters(self, tmp_path):
        write_level(tmp_path, {
            "DataVersion": NbtInt(3953),
            "SpawnX": NbtInt(10),
            "SpawnY": NbtInt(64),
            "SpawnZ": NbtInt(-5),
            "Difficulty": NbtByte(2),
            "hardcore": NbtByte(1),
        })

        with MinecraftWorld.open(str(tmp_path)) as world:
            assert world.level.spawn_pos == [10, 64, -5]
            assert world.level.difficulty == "normal"
            assert world.level.is_hardcore is True

            with pytest.raises(SpringNbtError) as error:
                world.level.spawn_dimension

            assert error.value.code == ErrorCode.UNSUPPORTED_FEATURE

    @pytest.mark.parametrize("number,name", [(0, "peaceful"), (1, "easy"), (2, "normal"), (3, "hard")])
    def test_L1の難易度は数値を名前に直す(self, tmp_path, number, name):
        write_level(tmp_path, {"DataVersion": NbtInt(3953), "Difficulty": NbtByte(number)})

        with MinecraftWorld.open(str(tmp_path)) as world:
            assert world.level.difficulty == name

    @pytest.mark.parametrize("number", [-1, 4])
    def test_L1の難易度が範囲外ならMALFORMED_DATA(self, tmp_path, number):
        write_level(tmp_path, {"DataVersion": NbtInt(3953), "Difficulty": NbtByte(number)})

        with MinecraftWorld.open(str(tmp_path)) as world:
            with pytest.raises(SpringNbtError) as error:
                world.level.difficulty

            assert error.value.code == ErrorCode.MALFORMED_DATA

    def test_world_l2_unchanged(self, tmp_path):
        data = NbtCompound()
        data.set("DataVersion", NbtInt(5023))
        spawn = NbtCompound()
        spawn.set("pos", NbtIntArray([1, 2, 3]))
        spawn.set("dimension", NbtString("minecraft:overworld"))
        data.set("spawn", spawn)
        settings = NbtCompound()
        settings.set("difficulty", NbtString("hard"))
        settings.set("hardcore", NbtByte(1))
        data.set("difficulty_settings", settings)
        root = NbtCompound()
        root.set("Data", data)
        write_file(str(tmp_path / "level.dat"), NamedTag("", root))

        (tmp_path / "dimensions" / "minecraft" / "overworld").mkdir(parents=True)
        (tmp_path / "dimensions" / "minecraft" / "the_end").mkdir(parents=True)
        write_dat(tmp_path / "players" / "data" / "u.dat", {"Health": NbtInt(3)})
        write_dat(tmp_path / "data" / "minecraft" / "weather.dat", {"Value": NbtInt(4)})
        write_dat(tmp_path / "dimensions" / "minecraft" / "the_end" / "data" / "minecraft"
                  / "raids.dat", {"Value": NbtInt(5)})

        with MinecraftWorld.open(str(tmp_path)) as world:
            assert world.level.spawn_pos == [1, 2, 3]
            assert world.level.spawn_dimension == "minecraft:overworld"
            assert world.level.difficulty == "hard"
            assert world.level.is_hardcore is True
            assert world.dimension_ids() == ["minecraft:overworld", "minecraft:the_end"]
            assert world.player_ids() == ["u"]
            assert world.data_file("weather").get_int("Value") == 4
            assert world.dimension("the_end").data_file("raids").get_int("Value") == 5

    def test_DataVersionが無いlevelDatはL1として読む(self, tmp_path):
        write_level(tmp_path, {})
        (tmp_path / "DIM1").mkdir()

        with MinecraftWorld.open(str(tmp_path)) as world:
            assert world.dimension_ids() == ["minecraft:the_end"]

    def test_world_override_layout(self, tmp_path):
        # level.datは26.3を名乗るが、構成はL1
        write_level(tmp_path, {"DataVersion": NbtInt(5023), "SpawnX": NbtInt(1),
                               "SpawnY": NbtInt(2), "SpawnZ": NbtInt(3)})
        (tmp_path / "region").mkdir()

        with MinecraftWorld.open(str(tmp_path)) as plain:
            assert plain.dimension_ids() == []

        options = WorldOpenOptions(format_data_version=3953)

        with MinecraftWorld.open(str(tmp_path), options) as world:
            assert world.dimension_ids() == ["minecraft:overworld"]
            assert world.level.spawn_pos == [1, 2, 3]

        with pytest.raises(SpringNbtError) as error:
            MinecraftWorld.open(str(tmp_path), WorldOpenOptions(format_data_version=1518))

        assert error.value.code == ErrorCode.INVALID_ARGUMENT

    def test_ワールドの指定は読むチャンクの世代にも効く(self, tmp_path):
        write_level(tmp_path, {"DataVersion": NbtInt(5023)})
        region = tmp_path / "dimensions" / "minecraft" / "overworld" / "region"
        region.mkdir(parents=True)
        chunk = read_file(vector_path("palette_1")).tag

        with RegionFile.open(str(region / "r.0.0.mca"), RegionFileMode.READ_WRITE) as file:
            file.write_chunk(0, 0, chunk)

        # ワールドの指定がchunk_readの指定より優先される
        read_options = ChunkReadOptions(format_data_version=5023)
        options = WorldOpenOptions(chunk_read=read_options, format_data_version=5006)

        with MinecraftWorld.open(str(tmp_path), options) as world:
            loaded = world.dimension("minecraft:overworld").chunk(0, 0)
            assert loaded.format_data_version == 5006

        # 渡したオプションは書き換えない
        assert read_options.format_data_version == 5023

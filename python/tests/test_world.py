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
    NbtByteArray,
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


def sections_in_order(sections: NbtList, order) -> NbtList:
    """セクションの一覧を、指定したYの並びに並べ替えた新しいリストを作る"""
    result = NbtList(TagType.COMPOUND)

    # 指定の順に、Yの合うセクションを探して足す
    for section_y in order:
        # Yの合うセクションだけを足す
        for section in sections:
            if section.get_byte("Y") == section_y:
                result.append(section)

    return result


def reorder_block_states(root: NbtCompound) -> None:
    """最初のセクションのblock_statesを、palette、data、ほかのキーの順に並べ替える"""
    section = root.get_list("sections")[0]
    container = section.get_compound("block_states")
    reordered = NbtCompound()
    reordered.set("palette", container.get("palette"))
    reordered.set("data", container.get("data"))
    reordered.set_int("extra", 7)
    section.set("block_states", reordered)


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

    def test_またぐ詰め方で長さが合う(self):
        assert BitStorage._long_count_with(5, 4096, True) == 320
        assert BitStorage._long_count_with(4, 4096, True) == 256

    def test_またぐ詰め方では値が64bitの境目をまたいで並ぶ(self):
        storage = BitStorage._create_with(5, 4096, True)

        # 添字12はビット60から64までなので、data[0]の上位4bitとdata[1]の最下位bitに分かれる
        storage.set(12, 0b10111)
        longs = storage.to_longs()

        assert ((longs[0] & 0xFFFFFFFFFFFFFFFF) >> 60) & 0b1111 == 0b0111
        assert longs[1] & 1 == 1
        assert storage.get(12) == 0b10111

    def test_またぐ詰め方で境目の値を上書きしても隣が壊れない(self):
        storage = BitStorage._create_with(5, 4096, True)
        storage.set(11, 0b11111)
        storage.set(13, 0b11111)

        # 添字12は境目をまたぐので、書き込みのたびに両隣が保たれるか確かめる
        for value in (0b11111, 0b00000, 0b10101):
            storage.set(12, value)
            assert storage.get(12) == value
            assert storage.get(11) == 0b11111
            assert storage.get(13) == 0b11111

    def test_またぐ詰め方で最後のlongの末尾まで読み書きできる(self):
        storage = BitStorage._create_with(5, 4096, True)
        storage.set(4094, 0b10101)
        storage.set(4095, 0b11011)

        # 添字4095はビット20475から20479で、最後のlongのビット59から63に収まる
        assert storage.get(4094) == 0b10101
        assert storage.get(4095) == 0b11011
        assert (storage.to_longs()[319] & 0xFFFFFFFFFFFFFFFF) >> 59 == 0b11011

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

    def test_またぐ詰め方のコンテナは17種類目でビット幅が5になる(self):
        palette = [block_entry("minecraft:block_%d" % index) for index in range(16)]
        container = PalettedContainer._from_parts(
            palette, [0] * 256, 4096, 4, True, False, False)
        assert container.bits_per_entry == 4

        # 全エントリに位置由来の値を書いてから、17種類目を1つ足す
        for index in range(4096):
            container.set(index, block_entry("minecraft:block_%d" % (index % 16)))

        container.set(7, block_entry("minecraft:block_16"))
        assert container.bits_per_entry == 5
        assert len(container._to_parts()[1]) == 320

        for index in range(4096):
            expected = "minecraft:block_%d" % (index % 16)

            if index == 7:
                expected = "minecraft:block_16"

            assert container.get(index) == block_entry(expected)

    @pytest.mark.parametrize("spanning", [False, True])
    def test_dataが必ず書かれる形式なら1要素のパレットでもビット幅4のdataを返す(self, spanning):
        container = PalettedContainer._from_parts(
            [block_entry("minecraft:air")], [0] * 256, 4096, 4, spanning, True, False)

        palette, data = container._to_parts()
        assert len(palette) == 1
        assert data == [0] * 256

    @pytest.mark.parametrize("spanning", [False, True])
    def test_dataが必ず書かれる形式でdataが無ければMALFORMED_DATA(self, spanning):
        with pytest.raises(SpringNbtError) as error:
            PalettedContainer._from_parts(
                [block_entry("minecraft:air")], None, 4096, 4, spanning, True, False)

        assert error.value.code == ErrorCode.MALFORMED_DATA

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

    def test_読んだときのセクションの並びで書き戻す(self):
        root = read_file(vector_path("multi_section")).tag
        root.set("sections", sections_in_order(root.get_list("sections"), [-2, -4, -3]))
        before = chunk_bytes(root)
        chunk = Chunk.from_nbt(root)

        # Yの昇順でない並びでも、無変更なら元とバイト単位で一致する
        assert chunk_bytes(chunk.to_nbt()) == before

        # 1つのセクションを書き換えても並びは変わらない
        chunk.set_block(0, -48, 0, "minecraft:stone")
        written = chunk.to_nbt()

        assert [section.get_byte("Y") for section in written.get_list("sections")] == [-2, -4, -3]
        assert chunk.section_ys == [-4, -3, -2]

    def test_paletteが先のコンテナはその並びのまま書き戻す(self):
        root = read_file(vector_path("palette_17")).tag
        reorder_block_states(root)
        before = chunk_bytes(root)
        chunk = Chunk.from_nbt(root)

        # 無変更なら元とバイト単位で一致する
        assert chunk_bytes(chunk.to_nbt()) == before

        # ビット幅の変わらない書き換えなら、キーの並びもほかのキーも保つ
        chunk.set_block(0, -64, 0, "minecraft:edited")
        container = chunk.to_nbt().get_list("sections")[0].get_compound("block_states")

        assert list(container.keys()) == ["palette", "data", "extra"]
        assert len(container.get_list("palette")) == 18

    def test_dataが要らなくなれば消しまた要るときは読んだときの位置に戻す(self):
        root = read_file(vector_path("palette_17")).tag
        reorder_block_states(root)
        chunk = Chunk.from_nbt(root)

        # パレットが1要素になればdataだけを消し、ほかのキーの位置は保つ
        chunk.section(-4).block_states.fill(NbtString("minecraft:stone"))
        container = chunk.to_nbt().get_list("sections")[0].get_compound("block_states")
        assert list(container.keys()) == ["palette", "extra"]

        # 読んだときにあったdataは、読んだときの位置に戻す
        chunk.set_block(0, -64, 0, "minecraft:edited")
        container = chunk.to_nbt().get_list("sections")[0].get_compound("block_states")
        assert list(container.keys()) == ["palette", "data", "extra"]

    def test_読んだときに無かったdataはライブラリの並びで先に置く(self):
        root = read_file(vector_path("palette_1")).tag
        root.get_list("sections")[0].get_compound("block_states").set_int("extra", 7)
        before = chunk_bytes(root)
        chunk = Chunk.from_nbt(root)

        # 無変更なら元とバイト単位で一致する
        assert chunk_bytes(chunk.to_nbt()) == before

        # パレットが育ってdataが要るようになれば、dataを先に置きほかのキーを後ろに残す
        chunk.set_block(0, -64, 0, "minecraft:edited")
        container = chunk.to_nbt().get_list("sections")[0].get_compound("block_states")
        assert list(container.keys()) == ["data", "palette", "extra"]

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

    def test_扱える形式の下限は1_13(self):
        assert MIN_SUPPORTED_DATA_VERSION == 1519

        warnings = []
        options = ChunkReadOptions(
            on_version_mismatch=VersionMismatchAction.WARN,
            on_warning=warnings.append)

        # 1.13の正式版より1つ古いチャンクは、読み込みで警告になる
        root = pre_flattening_chunk()
        root.set_int("DataVersion", 1518)
        Chunk.from_nbt(root, options)
        assert len(warnings) == 1

        # 1.13の正式版のチャンクは警告を出さない
        Chunk.from_nbt(level_chunk(1519), options)
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
            lambda: chunk.get_biome_id(0, 0, 0),
            lambda: chunk.set_biome_id(0, 0, 0, 1),
            lambda: chunk.clear_heightmaps(),
            lambda: chunk.invalidate_lighting(),
            lambda: chunk.min_section_y,
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

    def test_C5の世代で26_2のチャンクを読むとブロックの取得でMALFORMED_DATA(self):
        options = ChunkReadOptions(format_data_version=5023)
        chunk = load_chunk("v4903_edit", options)

        # パレットの要素がName / Propertiesなので、26.3の形式としては読めない
        with pytest.raises(SpringNbtError) as error:
            chunk.get_block(0, -64, 0)

        assert error.value.code == ErrorCode.MALFORMED_DATA

    def test_ルートの直下にsectionsがあるチャンクを1_16の世代で読むとMALFORMED_DATA(self):
        options = ChunkReadOptions(format_data_version=2586)

        # Levelの無いチャンクを、Levelに本体を包む世代で読ませる
        with pytest.raises(SpringNbtError) as error:
            load_chunk("palette_1", options)

        assert error.value.code == ErrorCode.MALFORMED_DATA

    def test_名前空間の無いfullも生成済みとみなす(self):
        root = read_file(vector_path("v4903_edit")).tag
        root.set_string("Status", "full")
        chunk = Chunk.from_nbt(root)

        assert chunk.status == "full"
        assert chunk.is_fully_generated


#: 1.16.5の形式のテストベクタのLevel.Biomes
LEVEL_BIOMES = [(index * 3) % 11 + 1 for index in range(1024)]


def level_vector() -> NbtCompound:
    """1.16.5の形式のテストベクタをNBTのまま読む"""
    return read_file(vector_path("v2586_level")).tag


def level_section(root: NbtCompound, section_y: int) -> NbtCompound:
    """Level.SectionsからY位置の合うセクションを探す"""
    # Yが一致する要素を返す
    for section in root.get_compound("Level").get_list("Sections"):
        # Yの合うセクションだけを対象にする
        if section.get_byte("Y") == section_y:
            return section

    raise AssertionError("Y=%d のセクションが無い" % section_y)


def positions(values: NbtList) -> list:
    """付随データの要素の座標を並べる"""
    return [(entry.get_int("x"), entry.get_int("y"), entry.get_int("z")) for entry in values]


class TestLevelChunk:
    """1.16〜1.17の形式（本体がLevelの中）のチャンク
    """

    def test_DataVersion2586のチャンクも読んだときのセクションの並びで書き戻す(self):
        root = level_vector()
        level = root.get_compound("Level")
        level.set("Sections", sections_in_order(level.get_list("Sections"), [1, -1, 0]))
        before = chunk_bytes(root)
        chunk = Chunk.from_nbt(root)

        # Yの昇順でない並びでも、無変更なら元とバイト単位で一致する
        assert chunk_bytes(chunk.to_nbt()) == before

        # 1つのセクションを書き換えても並びは変わらない
        chunk.set_block(0, 16, 0, "minecraft:stone")
        sections = chunk.to_nbt().get_compound("Level").get_list("Sections")

        assert [section.get_byte("Y") for section in sections] == [1, -1, 0]

    def test_DataVersion2586のチャンクを読み無変更で書き戻すと元と同じになる(self):
        root = level_vector()
        before = chunk_bytes(root)
        chunk = Chunk.from_nbt(root)

        assert chunk.data_version == 2586
        assert chunk.x == 2
        assert chunk.z == -1
        assert chunk.min_section_y == 0
        assert chunk.status == "full"
        assert chunk.is_fully_generated
        assert chunk.section_ys == [-1, 0, 1]

        # ベクタの添字は (位置 * 7) % 5
        assert str(chunk.get_block(0, 0, 0)) == "minecraft:air"
        assert str(chunk.get_block(1, 0, 0)) == "minecraft:dirt"
        assert str(chunk.get_block(2, 0, 0)) == "minecraft:oak_stairs[facing=west,half=top]"
        assert str(chunk.get_block(3, 0, 0)) == "minecraft:stone"
        assert str(chunk.get_block(4, 0, 0)) == "minecraft:oak_stairs[facing=east,half=bottom]"
        assert str(chunk.get_block(15, 31, 15)) == "minecraft:air"

        # Paletteの無いセクションと、セクションの無い高さはブロックを持たない
        assert not chunk.section(-1).has_block_states
        assert chunk.get_block(0, -1, 0) is None
        assert chunk.get_block(0, 32, 0) is None

        assert chunk_bytes(chunk.to_nbt()) == before

    def test_DataVersion2586のチャンクでブロックを置くとLevelの付随データが消える(self):
        chunk = Chunk.from_nbt(level_vector())

        # 絶対座標はx = 32 + 相対x、z = -16 + 相対z
        chunk.set_block(0, 0, 0, "minecraft:stone")
        chunk.set_block(1, 0, 1, "minecraft:stone")
        chunk.set_block(2, 2, 2, "minecraft:oak_stairs[facing=north]")
        written = chunk.to_nbt()
        level = written.get_compound("Level")

        assert positions(level.get_list("TileEntities")) == [(47, 20, -1)]
        assert len(level.get_list("TileTicks")) == 0
        assert positions(level.get_list("LiquidTicks")) == [(40, 5, -10)]

        # ルートには付随データのキーを作らない
        assert "block_entities" not in written
        assert "TileEntities" not in written

        # パレットの末尾にName / Propertiesの形式で足され、BlockStatesも書き直される
        section = level_section(written, 0)
        palette = section.get_list("Palette")
        assert palette[len(palette) - 1] == name_properties(
            "minecraft:oak_stairs", [("facing", "north")])
        assert len(section.get_long_array("BlockStates")) == 256
        assert written.get_int("DataVersion") == 2586

        # 読み直しても同じ状態が返る
        reread = Chunk.from_nbt(written)
        assert str(reread.get_block(2, 2, 2)) == "minecraft:oak_stairs[facing=north]"
        assert str(reread.get_block(0, 0, 0)) == "minecraft:stone"

    def test_DataVersion2586のチャンクのバイオームIDを読み書きできる(self):
        chunk = Chunk.from_nbt(level_vector())

        assert chunk.get_biome_id(0, 0, 0) == LEVEL_BIOMES[0]
        assert chunk.get_biome_id(5, 70, 9) == LEVEL_BIOMES[17 * 16 + 2 * 4 + 1]
        assert chunk.get_biome_id(15, 255, 15) == LEVEL_BIOMES[1023]

        # 高さ0..255の外は値を持たない
        assert chunk.get_biome_id(0, -1, 0) is None
        assert chunk.get_biome_id(0, 256, 0) is None

        chunk.set_biome_id(5, 70, 9, 42)
        assert chunk.is_modified
        assert chunk.get_biome_id(4, 68, 8) == 42

        written = chunk.to_nbt()
        assert written.get_compound("Level").get_int_array("Biomes")[17 * 16 + 2 * 4 + 1] == 42

    @pytest.mark.parametrize("y", [-1, 256])
    def test_高さ0から255の外へバイオームIDを書くとINVALID_ARGUMENT(self, y):
        chunk = Chunk.from_nbt(level_vector())

        with pytest.raises(SpringNbtError) as error:
            chunk.set_biome_id(0, y, 0, 1)

        assert error.value.code == ErrorCode.INVALID_ARGUMENT

    @pytest.mark.parametrize("biome_id", [2 ** 31, -(2 ** 31) - 1])
    def test_intの範囲に収まらないバイオームIDはINVALID_ARGUMENT(self, biome_id):
        chunk = Chunk.from_nbt(level_vector())

        with pytest.raises(SpringNbtError) as error:
            chunk.set_biome_id(0, 0, 0, biome_id)

        assert error.value.code == ErrorCode.INVALID_ARGUMENT
        assert chunk.get_biome_id(0, 0, 0) == LEVEL_BIOMES[0]

    @pytest.mark.parametrize("biomes", [None, NbtIntArray([]), NbtIntArray([1] * 256),
                                        NbtByteArray([1] * 256)])
    def test_Biomesを読めないチャンクのバイオームIDはNoneで書き込めない(self, biomes):
        root = level_vector()
        level = root.get_compound("Level")
        level.remove("Biomes")

        # Noneなら Biomes を持たないチャンクにする
        if biomes is not None:
            level.set("Biomes", biomes)

        before = chunk_bytes(root)
        chunk = Chunk.from_nbt(root)
        assert chunk.get_biome_id(0, 0, 0) is None

        with pytest.raises(SpringNbtError) as error:
            chunk.set_biome_id(0, 0, 0, 1)

        assert error.value.code == ErrorCode.INVALID_ARGUMENT

        # 元のNBTはそのまま残る
        assert chunk_bytes(chunk.to_nbt()) == before

    def test_DataVersion2586のチャンクではバイオーム名のAPIはUNSUPPORTED_FEATURE(self):
        chunk = Chunk.from_nbt(level_vector())

        # セクションの無い高さでも、形式で決まるので同じエラーになる
        operations = [
            lambda: chunk.get_biome(0, 0, 0),
            lambda: chunk.get_biome(0, 200, 0),
            lambda: chunk.set_biome(0, 0, 0, "minecraft:plains"),
        ]

        # 操作ごとにUNSUPPORTED_FEATUREになることを確かめる
        for operation in operations:
            with pytest.raises(SpringNbtError) as error:
                operation()

            assert error.value.code == ErrorCode.UNSUPPORTED_FEATURE

    @pytest.mark.parametrize("name", ["palette_1", "v4903_edit"])
    def test_バイオームIDのAPIは1_18以降のチャンクではUNSUPPORTED_FEATURE(self, name):
        chunk = load_chunk(name)

        with pytest.raises(SpringNbtError) as error:
            chunk.get_biome_id(0, 0, 0)

        assert error.value.code == ErrorCode.UNSUPPORTED_FEATURE

        with pytest.raises(SpringNbtError) as error:
            chunk.set_biome_id(0, 0, 0, 1)

        assert error.value.code == ErrorCode.UNSUPPORTED_FEATURE

    def test_DataVersion2586のチャンクの高さマップと光源を無効化できる(self):
        chunk = Chunk.from_nbt(level_vector())
        chunk.clear_heightmaps()
        chunk.invalidate_lighting()
        written = chunk.to_nbt()
        level = written.get_compound("Level")

        assert level.opt_compound("Heightmaps") is None
        assert level.get_byte("isLightOn") == 0

        # ルートには作らない
        assert "isLightOn" not in written

    def test_isLightOnの無いDataVersion2586のチャンクは光源を無効化できない(self):
        root = level_vector()
        root.get_compound("Level").remove("isLightOn")
        before = chunk_bytes(root)
        chunk = Chunk.from_nbt(root)

        with pytest.raises(SpringNbtError) as error:
            chunk.invalidate_lighting()

        assert error.value.code == ErrorCode.UNSUPPORTED_FEATURE
        assert chunk_bytes(chunk.to_nbt()) == before

    def test_生成途中のDataVersion2586のチャンクは生成済みではない(self):
        root = level_vector()
        root.get_compound("Level").set_string("Status", "structure_starts")
        chunk = Chunk.from_nbt(root)

        assert not chunk.is_fully_generated

    @pytest.mark.parametrize("key", ["BlockStates", "Palette"])
    def test_PaletteとBlockStatesの片方しか無いセクションはブロックを持たない(self, key):
        root = level_vector()
        level_section(root, 1).remove(key)
        before = chunk_bytes(root)
        chunk = Chunk.from_nbt(root)

        # Minecraftも両方がそろったセクションだけを読むので、ブロックの無いセクションとして扱う
        assert not chunk.section(1).has_block_states
        assert chunk.get_block(0, 16, 0) is None

        with pytest.raises(SpringNbtError) as error:
            chunk.set_block(0, 16, 0, "minecraft:stone")

        assert error.value.code == ErrorCode.INVALID_ARGUMENT

        # 元のNBTはそのまま残る
        assert chunk_bytes(chunk.to_nbt()) == before

    def test_Properties_Nameの並びの要素と同じ状態を置いてもパレットは増えない(self):
        root = level_vector()
        palette_before = list(level_section(root, 0).get_list("Palette"))
        chunk = Chunk.from_nbt(root)

        # 実データと同じくProperties -> Nameの並びで入っている状態を、プロパティの並びを変えて置く
        chunk.set_block(0, 0, 0, "minecraft:oak_stairs[half=bottom,facing=east]")
        written = chunk.to_nbt()

        # 同じ状態の要素を使い回すので、パレットは元のまま
        assert list(level_section(written, 0).get_list("Palette")) == palette_before
        reread = Chunk.from_nbt(written)
        assert str(reread.get_block(0, 0, 0)) == "minecraft:oak_stairs[facing=east,half=bottom]"

    def test_Paletteの要素がCompoundでなければUNEXPECTED_TAG_TYPE(self):
        root = level_vector()
        palette = NbtList(TagType.STRING)
        palette.append(NbtString("minecraft:air"))
        level_section(root, 1).set("Palette", palette)

        with pytest.raises(SpringNbtError) as error:
            Chunk.from_nbt(root)

        assert error.value.code == ErrorCode.UNEXPECTED_TAG_TYPE


#: 1.15.2の形式のテストベクタの0段目のパレットを、ブロック状態の文字列表現で並べたもの
SPANNING_STATES = (
    ["minecraft:air", "minecraft:stone"]
    + ["minecraft:oak_stairs[facing=%s,half=%s]" % (facing, half)
       for half in ("bottom", "top")
       for facing in ("east", "north", "south", "west")]
    + ["minecraft:" + name
       for name in ("dirt", "gravel", "sand", "bedrock", "cobblestone", "oak_planks", "glass")]
)

#: 1.15.2の形式のテストベクタのLevel.Biomes
SPANNING_BIOMES = [(index * 5) % 13 + 1 for index in range(1024)]

#: 1.14.4の形式のテストベクタのLevel.Biomes
BIOMES_2D = [(index * 7) % 61 + 1 for index in range(256)]

#: 1.16.5と1.14.4の形式のテストベクタの0段目のパレットを、ブロック状態の文字列表現で並べたもの
LEVEL_STATES = [
    "minecraft:air",
    "minecraft:stone",
    "minecraft:dirt",
    "minecraft:oak_stairs[facing=east,half=bottom]",
    "minecraft:oak_stairs[facing=west,half=top]",
]


def spanning_vector() -> NbtCompound:
    """1.15.2の形式のテストベクタをNBTのまま読む"""
    return read_file(vector_path("v2230_spanning")).tag


def biomes_2d_vector() -> NbtCompound:
    """1.14.4の形式のテストベクタをNBTのまま読む"""
    return read_file(vector_path("v1976_biomes_2d")).tag


class TestLegacyChunk:
    """1.13〜1.15の形式（ビット詰めが64bitの境目をまたぐ）のチャンク
    """

    def test_DataVersion2230のまたぐ詰め方のチャンクを読み無変更で書き戻すと元と同じになる(self):
        root = spanning_vector()
        before = chunk_bytes(root)
        chunk = Chunk.from_nbt(root)

        assert chunk.data_version == 2230
        assert chunk.x == -3
        assert chunk.z == 5
        assert chunk.min_section_y == 0
        assert chunk.is_fully_generated
        assert chunk.section_ys == [-1, 0, 1]
        assert len(chunk.section(0).block_states.palette) == 17
        assert chunk.section(0).block_states.bits_per_entry == 5

        # ベクタの添字は (位置 * 7) % 17
        # ビット幅5なので、位置12や25の値は64bitの境目をまたぐ
        assert str(chunk.get_block(12, 0, 0)) == SPANNING_STATES[(12 * 7) % 17]
        assert str(chunk.get_block(9, 0, 1)) == SPANNING_STATES[(25 * 7) % 17]

        # 全ブロックが元の添字どおりに読める
        for position in range(4096):
            block = chunk.get_block(position & 15, position >> 8, (position >> 4) & 15)
            assert str(block) == SPANNING_STATES[(position * 7) % 17]

        assert str(chunk.get_block(15, 31, 15)) == "minecraft:air"
        assert chunk.get_block(0, -1, 0) is None

        assert chunk_bytes(chunk.to_nbt()) == before

    def test_DataVersion2230のチャンクでパレットが育ってもまたぐ詰め方で書き戻す(self):
        chunk = Chunk.from_nbt(spanning_vector())

        # 20種類を足してパレットを37要素にし、ビット幅を5から6へ広げる
        for index in range(20):
            chunk.set_block(index % 16, index // 16, 0, "minecraft:edited_%d" % index)

        written = chunk.to_nbt()
        section = level_section(written, 0)

        # またぐ詰め方なので、長さは ceil(4096 * 6 / 64) = 384
        assert len(section.get_list("Palette")) == 37
        assert len(section.get_long_array("BlockStates")) == 384
        assert written.get_int("DataVersion") == 2230

        reread = Chunk.from_nbt(written)

        # 置いたブロックと、触っていないブロックの両方が読み直せる
        for position in range(4096):
            x = position & 15
            y = position >> 8
            z = (position >> 4) & 15
            index = (y * 16) + x
            block = reread.get_block(x, y, z)

            # 置いた位置だけ新しい状態になる
            if z == 0 and index < 20:
                assert str(block) == "minecraft:edited_%d" % index
            else:
                assert str(block) == SPANNING_STATES[(position * 7) % 17]

    def test_DataVersion2230のチャンクのバイオームIDは4ブロック単位で読める(self):
        chunk = Chunk.from_nbt(spanning_vector())

        assert chunk.get_biome_id(5, 70, 9) == SPANNING_BIOMES[17 * 16 + 2 * 4 + 1]
        assert chunk.get_biome_id(0, 256, 0) is None

    def test_DataVersion1976のチャンクを読み無変更で書き戻すと元と同じになる(self):
        root = biomes_2d_vector()
        before = chunk_bytes(root)
        chunk = Chunk.from_nbt(root)

        assert chunk.data_version == 1976
        assert chunk.x == 4
        assert chunk.z == -2
        assert chunk.min_section_y == 0
        assert chunk.section_ys == [0, 1]

        # ベクタの添字は (位置 * 7) % 5
        assert str(chunk.get_block(0, 0, 0)) == "minecraft:air"
        assert str(chunk.get_block(1, 0, 0)) == "minecraft:dirt"
        assert str(chunk.get_block(2, 0, 0)) == "minecraft:oak_stairs[facing=west,half=top]"
        assert str(chunk.get_block(3, 0, 0)) == "minecraft:stone"
        assert str(chunk.get_block(4, 0, 0)) == "minecraft:oak_stairs[facing=east,half=bottom]"
        assert str(chunk.get_block(15, 31, 15)) == "minecraft:air"

        assert chunk_bytes(chunk.to_nbt()) == before

    def test_DataVersion1976のチャンクでパレットが育ってもまたぐ詰め方で書き戻す(self):
        chunk = Chunk.from_nbt(biomes_2d_vector())

        # 12種類を足してパレットを17要素にし、ビット幅を4から5へ広げる
        for index in range(12):
            chunk.set_block(index, 0, 0, "minecraft:edited_%d" % index)

        written = chunk.to_nbt()
        section = level_section(written, 0)

        # またぐ詰め方なので、長さは ceil(4096 * 5 / 64) = 320（またがない詰め方なら342）
        assert len(section.get_list("Palette")) == 17
        assert len(section.get_long_array("BlockStates")) == 320

        reread = Chunk.from_nbt(written)

        # 置いたブロックと、触っていないブロックの両方が読み直せる
        for position in range(4096):
            block = reread.get_block(position & 15, position >> 8, (position >> 4) & 15)

            # 置いた位置だけ新しい状態になる
            if position < 12:
                assert str(block) == "minecraft:edited_%d" % position
            else:
                assert str(block) == LEVEL_STATES[(position * 7) % 5]

    def test_DataVersion1976のバイオームIDは高さに関係なく列ごとに読み書きできる(self):
        chunk = Chunk.from_nbt(biomes_2d_vector())

        # 添字は z * 16 + x で、yは見ない
        assert chunk.get_biome_id(3, 0, 7) == BIOMES_2D[7 * 16 + 3]
        assert chunk.get_biome_id(3, 200, 7) == BIOMES_2D[7 * 16 + 3]
        assert chunk.get_biome_id(3, -10, 7) == BIOMES_2D[7 * 16 + 3]
        assert chunk.get_biome_id(3, 300, 7) == BIOMES_2D[7 * 16 + 3]
        assert chunk.get_biome_id(7, 0, 3) == BIOMES_2D[3 * 16 + 7]

        chunk.set_biome_id(3, 1000, 7, 42)
        assert chunk.is_modified
        assert chunk.get_biome_id(3, 0, 7) == 42

        # 同じ列の値だけが変わる
        biomes = chunk.to_nbt().get_compound("Level").get_int_array("Biomes")
        assert biomes[7 * 16 + 3] == 42
        assert biomes[3 * 16 + 7] == BIOMES_2D[3 * 16 + 7]

    @pytest.mark.parametrize("biomes", [None, NbtIntArray([]), NbtIntArray([1] * 1024),
                                        NbtByteArray([1] * 256)])
    def test_DataVersion1976のBiomesを読めないチャンクのバイオームIDはNoneで書き込めない(
            self, biomes):
        root = biomes_2d_vector()
        level = root.get_compound("Level")
        level.remove("Biomes")

        # Noneなら Biomes を持たないチャンクにする
        if biomes is not None:
            level.set("Biomes", biomes)

        before = chunk_bytes(root)
        chunk = Chunk.from_nbt(root)
        assert chunk.get_biome_id(0, 0, 0) is None

        with pytest.raises(SpringNbtError) as error:
            chunk.set_biome_id(0, 0, 0, 1)

        assert error.value.code == ErrorCode.INVALID_ARGUMENT

        # 元のNBTはそのまま残る
        assert chunk_bytes(chunk.to_nbt()) == before

    def test_DataVersion1976のチャンクではバイオーム名のAPIはUNSUPPORTED_FEATURE(self):
        chunk = Chunk.from_nbt(biomes_2d_vector())

        with pytest.raises(SpringNbtError) as error:
            chunk.get_biome(0, 0, 0)

        assert error.value.code == ErrorCode.UNSUPPORTED_FEATURE

    def test_isLightOnの無い1_13の形式のチャンクは光源を無効化できない(self):
        root = biomes_2d_vector()
        root.set_int("DataVersion", 1519)
        root.get_compound("Level").remove("isLightOn")
        before = chunk_bytes(root)
        chunk = Chunk.from_nbt(root)

        with pytest.raises(SpringNbtError) as error:
            chunk.invalidate_lighting()

        assert error.value.code == ErrorCode.UNSUPPORTED_FEATURE
        assert chunk_bytes(chunk.to_nbt()) == before

    @pytest.mark.parametrize("status, expected", [
        ("full", True),
        ("postprocessed", True),
        ("fullchunk", True),
        ("mobs_spawned", False),
        ("decorated", False),
    ])
    def test_形式が1_14までならpostprocessedとfullchunkも生成済みとみなす(self, status, expected):
        root = biomes_2d_vector()
        root.get_compound("Level").set_string("Status", status)

        assert Chunk.from_nbt(root).is_fully_generated == expected

    def test_形式が1_15ならpostprocessedを生成済みとみなさない(self):
        root = spanning_vector()
        root.get_compound("Level").set_string("Status", "postprocessed")

        assert not Chunk.from_nbt(root).is_fully_generated

    def test_Statusの無いチャンクは生成済みとみなさない(self):
        options = ChunkReadOptions(on_version_mismatch=VersionMismatchAction.IGNORE)
        legacy = biomes_2d_vector()
        legacy.get_compound("Level").remove("Status")

        # 1.13より前のチャンクはStatusを持たない
        assert not Chunk.from_nbt(pre_flattening_chunk(), options).is_fully_generated
        assert not Chunk.from_nbt(legacy).is_fully_generated

    def test_Statusが文字列でないチャンクは生成済みとみなさない(self):
        root = biomes_2d_vector()
        root.get_compound("Level").set_int("Status", 1)
        chunk = Chunk.from_nbt(root)

        # 生成段階の取得子は、いまと同じく型の違いをエラーにする
        with pytest.raises(SpringNbtError) as error:
            chunk.status

        assert error.value.code == ErrorCode.UNEXPECTED_TAG_TYPE
        assert not chunk.is_fully_generated

    def test_DataVersionの無いチャンクは元のNBTだけを持つ(self):
        root = pre_flattening_chunk()
        root.remove("DataVersion")
        before = chunk_bytes(root)
        warnings = []
        options = ChunkReadOptions(
            on_version_mismatch=VersionMismatchAction.WARN,
            on_warning=warnings.append)
        chunk = Chunk.from_nbt(root, options)

        # 1.13より前と同じく、読み込みで警告になる
        assert len(warnings) == 1

        # 座標はLevelの中から読み、セクションは解釈しない
        assert chunk.x == 3
        assert chunk.z == -2
        assert chunk.section_ys == []
        assert chunk.format_data_version == -1

        # DataVersionの取得子は、いまと同じく無ければエラー
        with pytest.raises(SpringNbtError):
            chunk.data_version

        # ブロック・バイオーム・高さマップ・光源の操作はどれも受け付けない
        operations = [
            lambda: chunk.get_block(0, 0, 0),
            lambda: chunk.set_block(0, 0, 0, "minecraft:stone"),
            lambda: chunk.get_biome(0, 0, 0),
            lambda: chunk.set_biome(0, 0, 0, "minecraft:plains"),
            lambda: chunk.get_biome_id(0, 0, 0),
            lambda: chunk.set_biome_id(0, 0, 0, 1),
            lambda: chunk.clear_heightmaps(),
            lambda: chunk.invalidate_lighting(),
            lambda: chunk.min_section_y,
            lambda: chunk.to_nbt(),
        ]

        # 操作ごとにUNSUPPORTED_DATA_VERSIONになることを確かめる
        for operation in operations:
            with pytest.raises(SpringNbtError) as error:
                operation()

            assert error.value.code == ErrorCode.UNSUPPORTED_DATA_VERSION

        # 許可すれば、読んだNBTがそのまま返る
        written = chunk.to_nbt(ChunkWriteOptions(allow_foreign_data_version=True))
        assert chunk_bytes(written) == before

    def test_DataVersionの無いチャンクはERRORなら読み込みで弾く(self):
        root = pre_flattening_chunk()
        root.remove("DataVersion")
        options = ChunkReadOptions(on_version_mismatch=VersionMismatchAction.ERROR)

        with pytest.raises(SpringNbtError) as error:
            Chunk.from_nbt(root, options)

        assert error.value.code == ErrorCode.UNSUPPORTED_DATA_VERSION

    def test_DataVersionの無いチャンクも世代を指定すればその値を返す(self):
        root = pre_flattening_chunk()
        root.remove("DataVersion")
        options = ChunkReadOptions(
            on_version_mismatch=VersionMismatchAction.IGNORE, format_data_version=2230)
        chunk = Chunk.from_nbt(root, options)

        # 指定しても世代は選ばず、元のNBTだけを持つ
        assert chunk.format_data_version == 2230

        with pytest.raises(SpringNbtError) as error:
            chunk.get_block(0, 0, 0)

        assert error.value.code == ErrorCode.UNSUPPORTED_DATA_VERSION


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

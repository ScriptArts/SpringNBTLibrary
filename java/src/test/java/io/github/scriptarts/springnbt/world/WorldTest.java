package io.github.scriptarts.springnbt.world;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import io.github.scriptarts.springnbt.ErrorCode;
import io.github.scriptarts.springnbt.SpringNbt;
import io.github.scriptarts.springnbt.SpringNbtException;
import io.github.scriptarts.springnbt.anvil.RegionFile;
import io.github.scriptarts.springnbt.anvil.RegionFileMode;
import io.github.scriptarts.springnbt.nbt.Compression;
import io.github.scriptarts.springnbt.nbt.NamedTag;
import io.github.scriptarts.springnbt.nbt.NbtCompound;
import io.github.scriptarts.springnbt.nbt.NbtInt;
import io.github.scriptarts.springnbt.nbt.NbtList;
import io.github.scriptarts.springnbt.nbt.NbtIo;
import io.github.scriptarts.springnbt.nbt.NbtLongArray;
import io.github.scriptarts.springnbt.nbt.NbtString;
import io.github.scriptarts.springnbt.nbt.NbtTag;
import io.github.scriptarts.springnbt.nbt.TagType;
import io.github.scriptarts.springnbt.nbt.NbtWriteOptions;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.function.Executable;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;

/**
 * World / Blockレイヤ
 *
 * <p>他言語版と同じ検証項目を持つ
 */
class WorldTest {

    /** 共通テストベクタ（world/*.nbt）のパス */
    private static Path vectorPath(String name) {
        Path current = Path.of("").toAbsolutePath();

        // 実行ディレクトリからリポジトリ直下まで遡ってspec/testdataを探す
        while (current != null) {
            Path candidate = current.resolve("spec").resolve("testdata")
                    .resolve("world").resolve(name + ".nbt");

            if (Files.isRegularFile(candidate)) {
                return candidate;
            }

            current = current.getParent();
        }

        throw new IllegalStateException("テストベクタが見つからない: world/" + name + ".nbt");
    }

    /** テストベクタをチャンクとして読む */
    private static Chunk loadChunk(String name) {
        return loadChunk(name, ChunkReadOptions.defaults());
    }

    private static Chunk loadChunk(String name, ChunkReadOptions options) {
        NamedTag named = NbtIo.readFile(vectorPath(name), null);
        return Chunk.fromNbt((NbtCompound) named.tag(), options);
    }

    /** 異種リストの要素を包むCompoundを作る */
    private static NbtCompound wrapped(NbtTag tag) {
        NbtCompound wrapper = new NbtCompound();
        wrapper.set("", tag);
        return wrapper;
    }

    /** 26.2までの形式（Name / Properties）のパレット要素を作る */
    private static NbtCompound nameProperties(String name, String... properties) {
        NbtCompound entry = new NbtCompound();
        entry.setString("Name", name);

        // プロパティがあるときだけPropertiesを足す
        if (properties.length > 0) {
            NbtCompound propertiesTag = new NbtCompound();

            // キーと値の組を渡された順に入れる
            for (int index = 0; index < properties.length; index += 2) {
                propertiesTag.setString(properties[index], properties[index + 1]);
            }

            entry.set("Properties", propertiesTag);
        }

        return entry;
    }

    /** 26.3からの形式（id / properties）のパレット要素を作る */
    private static NbtCompound idProperties(String name, String... properties) {
        NbtCompound entry = new NbtCompound();
        entry.setString("id", name);
        NbtCompound propertiesTag = new NbtCompound();

        // キーと値の組を渡された順に入れる
        for (int index = 0; index < properties.length; index += 2) {
            propertiesTag.setString(properties[index], properties[index + 1]);
        }

        entry.set("properties", propertiesTag);
        return entry;
    }

    /**
     * 扱える形式の下限より古く、1.13より前でもあるDataVersion
     * どの世代でも解釈しない
     */
    private static final int PRE_FLATTENING_DATA_VERSION = 1400;

    /** 1.13より前のようにLevelに本体を包み、ブロックを数値IDで持つチャンクを作る */
    private static NbtCompound preFlatteningChunk() {
        byte[] blocks = new byte[4096];
        Arrays.fill(blocks, (byte) 1);

        NbtCompound section = new NbtCompound();
        section.setByte("Y", (byte) 0);
        section.setByteArray("Blocks", blocks);
        section.setByteArray("Data", new byte[2048]);
        NbtList sections = new NbtList(TagType.COMPOUND);
        sections.add(section);

        NbtCompound level = new NbtCompound();
        level.setInt("xPos", 3);
        level.setInt("zPos", -2);
        level.set("Sections", sections);

        NbtCompound root = new NbtCompound();
        root.setInt("DataVersion", PRE_FLATTENING_DATA_VERSION);
        root.set("Level", level);
        return root;
    }

    /** 1.17までのようにLevelに本体を包んだチャンクを作る */
    private static NbtCompound levelChunk(int dataVersion) {
        NbtCompound level = new NbtCompound();
        level.setInt("xPos", 0);
        level.setInt("zPos", 0);
        level.setString("Status", "full");
        level.set("Sections", new NbtList(TagType.COMPOUND));

        NbtCompound root = new NbtCompound();
        root.setInt("DataVersion", dataVersion);
        root.set("Level", level);
        return root;
    }

    /** チャンクのNBTを無圧縮のバイト列にする */
    private static byte[] chunkBytes(NbtCompound tag) {
        return NbtIo.writeBytes(new NamedTag("", tag), new NbtWriteOptions().setCompression(Compression.NONE));
    }

    /** 書き出したチャンクの最初のセクションのブロックのパレット */
    private static NbtList firstBlockPalette(NbtCompound written) {
        NbtCompound section = (NbtCompound) written.getList("sections").get(0);
        return section.getCompound("block_states").getList("palette");
    }

    @Nested
    class BlockStateTest {

        @Test
        void 名前空間を省略するとminecraftが補われる() {
            BlockState state = BlockState.parse("stone");
            assertEquals("minecraft:stone", state.name());
            assertTrue(state.properties().isEmpty());
            assertEquals("minecraft:stone", state.toString());
        }

        @Test
        void プロパティは名前の昇順に並ぶ() {
            BlockState state = BlockState.parse("minecraft:oak_stairs[waterlogged=false,facing=north,half=top]");
            assertEquals("minecraft:oak_stairs[facing=north,half=top,waterlogged=false]", state.toString());
        }

        @Test
        void 並び順が違っても同じブロックとして等しい() {
            BlockState first = BlockState.parse("minecraft:oak_stairs[facing=north,half=top]");
            BlockState second = BlockState.parse("minecraft:oak_stairs[half=top,facing=north]");
            assertEquals(first, second);
            assertEquals(first.hashCode(), second.hashCode());
        }

        @Test
        void 名前が同じでもプロパティが違えば等しくない() {
            assertNotEquals(
                    BlockState.parse("minecraft:oak_stairs[facing=north]"),
                    BlockState.parse("minecraft:oak_stairs[facing=south]"));
        }

        @Test
        void withで作り直しても元は変わらない() {
            BlockState original = BlockState.parse("minecraft:oak_stairs[facing=north]");
            BlockState changed = original.with("facing", "south");
            assertEquals("north", original.property("facing"));
            assertEquals("south", changed.property("facing"));
        }

        @Test
        void 存在しないプロパティはnull() {
            assertNull(BlockState.parse("minecraft:stone").property("facing"));
        }

        @Test
        void NBTとの相互変換でプロパティが保たれる() {
            BlockState state = BlockState.parse("minecraft:oak_stairs[facing=north,half=top]");
            NbtCompound nbt = (NbtCompound) state.toNbt();
            assertEquals(List.of("id", "properties"), new ArrayList<>(nbt.keys()));
            assertEquals("minecraft:oak_stairs", nbt.getString("id"));
            assertEquals("north", nbt.getCompound("properties").getString("facing"));
            assertEquals(state, BlockState.fromNbt(nbt));
        }

        @Test
        void プロパティ無しのブロックは文字列になる() {
            assertEquals(new NbtString("minecraft:air"), BlockState.parse("minecraft:air").toNbt());
        }

        @Test
        void 文字列のパレット要素を読める() {
            BlockState state = BlockState.fromNbt(new NbtString("minecraft:stone"));
            assertEquals("minecraft:stone", state.name());
            assertTrue(state.properties().isEmpty());
        }

        @Test
        void 包まれたパレット要素を読める() {
            BlockState state = BlockState.fromNbt(wrapped(new NbtString("minecraft:stone")));
            assertEquals("minecraft:stone", state.toString());
        }

        @Test
        void propertiesの無いCompoundも読める() {
            NbtCompound entry = new NbtCompound();
            entry.set("id", new NbtString("minecraft:stone"));
            assertEquals("minecraft:stone", BlockState.fromNbt(entry).toString());
        }

        @Test
        void パレット要素が26_2までの形式ならMALFORMED_DATA() {
            NbtCompound entry = new NbtCompound();
            entry.set("Name", new NbtString("minecraft:stone"));
            SpringNbtException error = assertThrows(SpringNbtException.class, () -> BlockState.fromNbt(entry));
            assertEquals(ErrorCode.MALFORMED_DATA, error.code());
        }

        @Test
        void 文字列でもCompoundでもない要素はUNEXPECTED_TAG_TYPE() {
            SpringNbtException error = assertThrows(SpringNbtException.class,
                    () -> BlockState.fromNbt(new NbtInt(1)));
            assertEquals(ErrorCode.UNEXPECTED_TAG_TYPE, error.code());
        }

        @Test
        void DataVersion2844ではName_Propertiesを読む() {
            NbtCompound properties = new NbtCompound();
            properties.set("facing", new NbtString("north"));
            NbtCompound entry = new NbtCompound();
            entry.set("Name", new NbtString("minecraft:oak_stairs"));
            entry.set("Properties", properties);

            BlockState state = BlockState.fromNbtForDataVersion(entry, 2844);
            assertEquals("minecraft:oak_stairs[facing=north]", state.toString());
        }

        @Test
        void DataVersion2844でidを持つ要素はMALFORMED_DATA() {
            NbtCompound entry = new NbtCompound();
            entry.set("id", new NbtString("minecraft:stone"));
            SpringNbtException error = assertThrows(SpringNbtException.class,
                    () -> BlockState.fromNbtForDataVersion(entry, 2844));
            assertEquals(ErrorCode.MALFORMED_DATA, error.code());
        }

        @Test
        void DataVersion2844で文字列の要素はUNEXPECTED_TAG_TYPE() {
            SpringNbtException error = assertThrows(SpringNbtException.class,
                    () -> BlockState.fromNbtForDataVersion(new NbtString("minecraft:stone"), 2844));
            assertEquals(ErrorCode.UNEXPECTED_TAG_TYPE, error.code());
        }

        @Test
        void DataVersion2844でPropertiesの値が文字列でなければUNEXPECTED_TAG_TYPE() {
            NbtCompound properties = new NbtCompound();
            properties.set("facing", new NbtInt(1));
            NbtCompound entry = new NbtCompound();
            entry.set("Name", new NbtString("minecraft:oak_stairs"));
            entry.set("Properties", properties);
            SpringNbtException error = assertThrows(SpringNbtException.class,
                    () -> BlockState.fromNbtForDataVersion(entry, 2844));
            assertEquals(ErrorCode.UNEXPECTED_TAG_TYPE, error.code());
        }

        @Test
        void DataVersion2844ではName_Propertiesで書く() {
            NbtCompound plain = (NbtCompound) BlockState.parse("minecraft:stone").toNbtForDataVersion(2844);
            NbtCompound expected = new NbtCompound();
            expected.set("Name", new NbtString("minecraft:stone"));
            assertEquals(expected, plain);
            assertFalse(plain.containsKey("Properties"));

            BlockState stairs = BlockState.parse("minecraft:oak_stairs[half=top,facing=north]");
            NbtCompound nbt = (NbtCompound) stairs.toNbtForDataVersion(2844);
            assertEquals(List.of("Name", "Properties"), new ArrayList<>(nbt.keys()));
            assertEquals("minecraft:oak_stairs", nbt.getString("Name"));
            assertEquals(List.of("facing", "half"), new ArrayList<>(nbt.getCompound("Properties").keys()));
            assertEquals(stairs, BlockState.fromNbtForDataVersion(nbt, 2844));
        }

        @ParameterizedTest
        @ValueSource(ints = {5006, 5023})
        void DataVersion5006以降はfromNbtとtoNbtと同じ(int dataVersion) {
            BlockState stairs = BlockState.parse("minecraft:oak_stairs[facing=north,half=top]");
            assertEquals(stairs.toNbt(), stairs.toNbtForDataVersion(dataVersion));

            BlockState plain = BlockState.parse("minecraft:stone");
            assertEquals(new NbtString("minecraft:stone"), plain.toNbtForDataVersion(dataVersion));

            assertEquals(plain, BlockState.fromNbtForDataVersion(new NbtString("minecraft:stone"), dataVersion));
            assertEquals(stairs, BlockState.fromNbtForDataVersion(stairs.toNbt(), dataVersion));
            NbtCompound wrapper = wrapped(new NbtString("minecraft:stone"));
            assertEquals(BlockState.fromNbt(wrapper), BlockState.fromNbtForDataVersion(wrapper, dataVersion));
        }

        @Test
        void DataVersion1519で境界の形式を扱える() {
            BlockState state = BlockState.parse("minecraft:oak_stairs[facing=north]");
            assertEquals(state, BlockState.fromNbtForDataVersion(state.toNbtForDataVersion(1519), 1519));
        }

        @Test
        void DataVersionが1519未満ならINVALID_ARGUMENT() {
            SpringNbtException readError = assertThrows(SpringNbtException.class,
                    () -> BlockState.fromNbtForDataVersion(new NbtString("minecraft:stone"), 1518));
            assertEquals(ErrorCode.INVALID_ARGUMENT, readError.code());

            SpringNbtException writeError = assertThrows(SpringNbtException.class,
                    () -> BlockState.parse("minecraft:stone").toNbtForDataVersion(1518));
            assertEquals(ErrorCode.INVALID_ARGUMENT, writeError.code());
        }

        @ParameterizedTest
        @ValueSource(strings = {
            "",
            "minecraft:oak_stairs[facing=north",
            "minecraft:oak_stairs[facing]",
            "minecraft:oak_stairs[facing=north,facing=south]",
            "minecraft:oak_stairs[]extra",
        })
        void 壊れた文字列はINVALID_ARGUMENT(String text) {
            SpringNbtException error = assertThrows(SpringNbtException.class, () -> BlockState.parse(text));
            assertEquals(ErrorCode.INVALID_ARGUMENT, error.code());
        }
    }

    @Nested
    class BitStorageTest {

        @ParameterizedTest
        @CsvSource({"4,4096,256", "5,4096,342", "1,64,1", "6,64,7"})
        void 必要なlong数は跨ぎなしで求まる(int bits, int entryCount, int expected) {
            assertEquals(expected, BitStorage.longCount(bits, entryCount));
        }

        @Test
        void 書いた値をそのまま読み出せる() {
            BitStorage storage = BitStorage.create(5, 4096);

            // 全エントリに位置由来の値を書いて、取りこぼしが無いか確かめる
            for (int index = 0; index < 4096; index++) {
                storage.set(index, index % 32);
            }

            for (int index = 0; index < 4096; index++) {
                assertEquals(index % 32, storage.get(index));
            }
        }

        @Test
        void long境界を跨がずに詰める() {
            BitStorage storage = BitStorage.create(5, 4096);

            // bits=5なら1つのlongに12個
            // 添字12は次のlongの最下位から始まる
            storage.set(11, 31);
            storage.set(12, 1);
            long[] longs = storage.toLongs();

            assertEquals(31L << 55, longs[0]);
            assertEquals(1L, longs[1]);
        }

        @Test
        void ビット幅を広げても値が保たれる() {
            BitStorage storage = BitStorage.create(4, 4096);

            for (int index = 0; index < 4096; index++) {
                storage.set(index, index % 16);
            }

            BitStorage widened = storage.resize(5);
            assertEquals(5, widened.bitsPerEntry());
            assertEquals(342, widened.toLongs().length);

            for (int index = 0; index < 4096; index++) {
                assertEquals(index % 16, widened.get(index));
            }
        }

        @Test
        void ビット幅に対して長さが合わない配列はMALFORMED_DATA() {
            SpringNbtException error = assertThrows(SpringNbtException.class,
                    () -> BitStorage.fromLongs(new long[100], 4, 4096, false));
            assertEquals(ErrorCode.MALFORMED_DATA, error.code());
        }

        @Test
        void 寛容モードなら長さからビット幅を逆算する() {
            // 4096エントリを342 longで表せるのはbits=5のときだけ
            BitStorage storage = BitStorage.fromLongs(new long[342], 4, 4096, true);
            assertEquals(5, storage.bitsPerEntry());
        }

        @Test
        void ビット幅に収まらない値はINVALID_ARGUMENT() {
            BitStorage storage = BitStorage.create(4, 64);
            SpringNbtException error = assertThrows(SpringNbtException.class, () -> storage.set(0, 16));
            assertEquals(ErrorCode.INVALID_ARGUMENT, error.code());
        }

        @Test
        void 範囲外の添字はINVALID_ARGUMENT() {
            BitStorage storage = BitStorage.create(4, 64);
            SpringNbtException error = assertThrows(SpringNbtException.class, () -> storage.get(64));
            assertEquals(ErrorCode.INVALID_ARGUMENT, error.code());
        }
    }

    @Nested
    class PalettedContainerTest {

        /**
         * プロパティの無いブロックのパレット要素を作る
         * 26.3からはブロックIDだけの文字列で入る
         */
        private NbtString blockEntry(String name) {
            return new NbtString(name);
        }

        @ParameterizedTest
        @CsvSource({"1,0", "2,1", "4,2", "5,3", "17,5"})
        void 必要ビット数はceilLog2(int count, int expected) {
            assertEquals(expected, PalettedContainer.ceilLog2(count));
        }

        @Test
        void 単一値のコンテナはdataを持たない() {
            PalettedContainer container = PalettedContainer.filled(blockEntry("minecraft:air"), 4096, 4);
            assertEquals(0, container.bitsPerEntry());

            NbtCompound nbt = container.toNbt();
            assertNull(nbt.optLongArray("data"));
            assertEquals(1, nbt.getList("palette").size());
        }

        @Test
        void 値を足すとパレットとビット幅が広がる() {
            PalettedContainer container = PalettedContainer.filled(blockEntry("minecraft:air"), 4096, 4);

            // 17種のブロックを足してパレットを18要素にし、bits=4から5への拡張を起こす
            for (int index = 0; index < 17; index++) {
                container.set(index, blockEntry("minecraft:block_" + index));
            }

            assertEquals(18, container.palette().size());
            assertEquals(5, container.bitsPerEntry());
            assertEquals(342, container.toNbt().getLongArray("data").length);
        }

        @Test
        void 書き出しはdataが先でpaletteが後() {
            // 実データがこの順なので、無変更で書き戻したときにバイト単位で一致する
            PalettedContainer container = PalettedContainer.filled(blockEntry("minecraft:air"), 4096, 4);
            container.set(0, blockEntry("minecraft:stone"));

            assertArrayEquals(new String[] {"data", "palette"},
                    container.toNbt().keys().toArray(new String[0]));
        }

        @Test
        void compactで未使用のパレット要素が消える() {
            PalettedContainer container = PalettedContainer.filled(blockEntry("minecraft:air"), 4096, 4);
            container.set(0, blockEntry("minecraft:stone"));
            container.set(0, blockEntry("minecraft:dirt"));
            assertEquals(3, container.palette().size());

            container.compact();

            // 残るのは実際に使われているairとdirtの2つ
            assertEquals(2, container.palette().size());
            assertEquals("minecraft:dirt", ((NbtString) container.get(0)).value());
        }

        @Test
        void fillで単一値に戻る() {
            PalettedContainer container = PalettedContainer.filled(blockEntry("minecraft:air"), 4096, 4);
            container.set(0, blockEntry("minecraft:stone"));
            container.fill(blockEntry("minecraft:water"));

            assertEquals(1, container.palette().size());
            assertEquals(0, container.bitsPerEntry());
            assertEquals("minecraft:water", ((NbtString) container.get(4095)).value());
        }

        @Test
        void 文字列だけのパレットは文字列のリストで書く() {
            PalettedContainer container = PalettedContainer.filled(blockEntry("minecraft:air"), 4096, 4);
            container.set(0, blockEntry("minecraft:stone"));

            NbtList palette = container.toNbt().getList("palette");
            assertEquals(TagType.STRING, palette.elementType());
            assertEquals(new NbtString("minecraft:stone"), palette.get(1));
        }

        @Test
        void 型が混ざったパレットは文字列を包んでCompoundのリストで書く() {
            NbtTag stairs = BlockState.parse("minecraft:oak_stairs[facing=north]").toNbt();
            PalettedContainer container = PalettedContainer.filled(blockEntry("minecraft:air"), 4096, 4);
            container.set(0, stairs);

            NbtList palette = container.toNbt().getList("palette");
            assertEquals(TagType.COMPOUND, palette.elementType());
            assertEquals(wrapped(new NbtString("minecraft:air")), palette.get(0));
            assertEquals(stairs, palette.get(1));
        }

        @Test
        void 包まれたパレットは包みを外して持ち元どおりに書き戻す() {
            NbtTag stairs = BlockState.parse("minecraft:oak_stairs[facing=north]").toNbt();
            NbtList palette = new NbtList(TagType.COMPOUND);
            palette.add(wrapped(new NbtString("minecraft:air")));
            palette.add(stairs);

            // パレット2要素ならbits=4で256 long
            NbtCompound nbt = new NbtCompound();
            nbt.set("data", new NbtLongArray(new long[256]));
            nbt.set("palette", palette);

            PalettedContainer container = PalettedContainer.fromNbt(nbt, 4096, 4, false);

            // 包みは外れ、要素は文字列とCompoundとして並ぶ
            assertEquals(new NbtString("minecraft:air"), container.palette().get(0));
            assertEquals(stairs, container.palette().get(1));

            // 書き戻すと、また包まれて元と同じになる
            assertEquals(nbt, container.toNbt());
        }

        @Test
        void compactでCompoundが消えると文字列のリストに戻る() {
            NbtTag stairs = BlockState.parse("minecraft:oak_stairs[facing=north]").toNbt();
            PalettedContainer container = PalettedContainer.filled(blockEntry("minecraft:air"), 4096, 4);
            container.set(0, stairs);
            container.set(0, blockEntry("minecraft:stone"));

            container.compact();

            NbtList palette = container.toNbt().getList("palette");
            assertEquals(TagType.STRING, palette.elementType());
            assertEquals(2, palette.size());
        }

        @Test
        void 範囲外の添字はINVALID_ARGUMENT() {
            PalettedContainer container = PalettedContainer.filled(blockEntry("minecraft:air"), 4096, 4);
            SpringNbtException error = assertThrows(SpringNbtException.class, () -> container.get(4096));
            assertEquals(ErrorCode.INVALID_ARGUMENT, error.code());
        }
    }

    @Nested
    class ChunkTest {

        @Test
        void パレット1要素のチャンクを読める() {
            Chunk chunk = loadChunk("palette_1");

            assertEquals(SpringNbt.TARGET_DATA_VERSION, chunk.dataVersion());
            assertEquals(0, chunk.x());
            assertEquals(0, chunk.z());
            assertEquals(-4, chunk.minSectionY());
            assertTrue(chunk.isFullyGenerated());
            assertEquals(List.of(-4), List.copyOf(chunk.sectionYs()));
            assertEquals("minecraft:air", chunk.getBlock(0, -64, 0).name());
            assertEquals("minecraft:plains", chunk.getBiome(0, -64, 0));
        }

        @Test
        void ビット幅5のチャンクを端から端まで読める() {
            Chunk chunk = loadChunk("palette_17");
            String[] head = {"minecraft:air", "minecraft:stone"};

            // ベクタの添字は (位置 * 11) % 17
            // パレットの先頭2つだけ名前が違う
            for (int position = 0; position < 4096; position++) {
                int paletteIndex = (position * 11) % 17;
                BlockState block = chunk.getBlock(
                        position & 15, -64 + (position >> 8), (position >> 4) & 15);

                if (paletteIndex < 2) {
                    assertEquals(head[paletteIndex], block.toString());
                } else {
                    assertEquals("minecraft:stone[variant=v" + (paletteIndex - 2) + "]", block.toString());
                }
            }
        }

        @Test
        void セクションの無い高さはnull() {
            Chunk chunk = loadChunk("palette_1");
            assertNull(chunk.getBlock(0, 100, 0));
            assertNull(chunk.section(0));
        }

        @Test
        void 生成途中のチャンクはfullではない() {
            Chunk chunk = loadChunk("proto_chunk");
            assertEquals("minecraft:structure_starts", chunk.status());
            assertFalse(chunk.isFullyGenerated());
        }

        @Test
        void ブロックを置くとその場所だけ変わる() {
            Chunk chunk = loadChunk("palette_1");
            chunk.setBlock(3, -60, 7, BlockState.parse("minecraft:oak_stairs[facing=north,half=top]"));

            assertEquals("minecraft:oak_stairs[facing=north,half=top]", chunk.getBlock(3, -60, 7).toString());
            assertEquals("minecraft:air", chunk.getBlock(3, -60, 6).name());
            assertEquals("minecraft:air", chunk.getBlock(4, -60, 7).name());
        }

        @Test
        void ブロックを文字列でも置ける() {
            Chunk chunk = loadChunk("palette_1");
            chunk.setBlock(3, -60, 7, "minecraft:oak_stairs[facing=north,half=top]");

            assertEquals("minecraft:oak_stairs[facing=north,half=top]",
                    chunk.getBlock(3, -60, 7).toString());
        }

        @Test
        void 変更したチャンクには印が付く() {
            Chunk chunk = loadChunk("palette_1");
            assertFalse(chunk.isModified());

            chunk.setBlock(3, -60, 7, "minecraft:stone");
            assertTrue(chunk.isModified());

            // 保存済みとして印を外せる
            chunk.setIsModified(false);
            assertFalse(chunk.isModified());

            // 同じ状態を置き直すだけなら何も起きないので印も付かない
            chunk.setBlock(3, -60, 7, "minecraft:stone");
            assertFalse(chunk.isModified());

            chunk.clearHeightmaps();
            assertTrue(chunk.isModified());
        }

        @Test
        void バイオームは4ブロック単位で効く() {
            Chunk chunk = loadChunk("palette_1");
            chunk.setBiome(0, -64, 0, "minecraft:desert");

            // 同じ4×4×4の枠内はまとめて変わる
            assertEquals("minecraft:desert", chunk.getBiome(3, -61, 3));
            assertEquals("minecraft:plains", chunk.getBiome(4, -64, 0));
        }

        @Test
        void compactで未使用のパレット要素が消える() {
            Chunk chunk = loadChunk("palette_unused");
            assertEquals(4, chunk.section(-4).toNbt().getCompound("block_states").getList("palette").size());

            chunk.compact();

            assertEquals(2, chunk.section(-4).toNbt().getCompound("block_states").getList("palette").size());
        }

        @Test
        void 無変更で書き戻すと元と同じNBTになる() {
            NamedTag named = NbtIo.readFile(vectorPath("multi_section"), null);
            NbtWriteOptions options = new NbtWriteOptions().setCompression(Compression.NONE);
            byte[] before = NbtIo.writeBytes(named, options);

            Chunk chunk = Chunk.fromNbt((NbtCompound) named.tag(), ChunkReadOptions.defaults());
            byte[] after = NbtIo.writeBytes(
                    new NamedTag(named.name(), chunk.toNbt(ChunkWriteOptions.defaults())), options);

            assertArrayEquals(before, after);
        }

        @Test
        void ブロックを置き換えると同じ座標の付随データが消える() {
            Chunk chunk = loadChunk("block_entities");
            assertEquals(3, chunk.raw().getList("block_entities").size());
            assertEquals(2, chunk.raw().getList("block_ticks").size());
            assertEquals(1, chunk.raw().getList("fluid_ticks").size());

            // (0,-64,0)にはchestとblock_tick、(1,-64,1)にはfurnaceとfluid_tickがある
            chunk.setBlock(0, -64, 0, BlockState.parse("minecraft:stone"));
            chunk.setBlock(1, -64, 1, BlockState.parse("minecraft:stone"));

            NbtList entities = chunk.raw().getList("block_entities");

            // 触っていない(15,-50,15)のbarrelだけが残る
            assertEquals(1, entities.size());
            assertEquals("minecraft:barrel", ((NbtCompound) entities.get(0)).getString("id"));

            NbtList ticks = chunk.raw().getList("block_ticks");
            assertEquals(1, ticks.size());
            assertEquals(15, ((NbtCompound) ticks.get(0)).getInt("x"));

            assertEquals(0, chunk.raw().getList("fluid_ticks").size());
        }

        @Test
        void 同じブロックを置き直しても付随データは消えない() {
            Chunk chunk = loadChunk("block_entities");
            BlockState current = chunk.getBlock(0, -64, 0);

            // 変化が無いなら付随データを触る理由がない
            chunk.setBlock(0, -64, 0, current);

            assertEquals(3, chunk.raw().getList("block_entities").size());
            assertEquals(2, chunk.raw().getList("block_ticks").size());
        }

        @Test
        void 別のチャンクの同じ相対座標は消さない() {
            // 付随データは絶対座標で持つので、チャンク座標を間違えると無関係な要素を消してしまう
            NamedTag named = NbtIo.readFile(vectorPath("block_entities"), null);
            NbtCompound root = (NbtCompound) named.tag();
            root.set("xPos", new NbtInt(1));
            root.set("zPos", new NbtInt(1));

            Chunk chunk = Chunk.fromNbt(root, ChunkReadOptions.defaults());
            chunk.setBlock(0, -64, 0, BlockState.parse("minecraft:stone"));

            // このチャンクの(0,-64,0)は絶対座標(16,-64,16)
            // どれとも一致しない
            assertEquals(3, chunk.raw().getList("block_entities").size());
        }

        @Test
        void 高さマップと光源を無効化できる() {
            Chunk chunk = loadChunk("palette_1");
            chunk.clearHeightmaps();
            chunk.invalidateLighting();

            NbtCompound raw = chunk.toNbt(ChunkWriteOptions.defaults());
            assertNull(raw.optCompound("Heightmaps"));
            assertFalse(raw.getBool("isLightOn"));
        }

        @Test
        void 添字が範囲外のチャンクはMALFORMED_DATA() {
            SpringNbtException error = assertThrows(SpringNbtException.class,
                    () -> loadChunk("palette_index_out_of_range"));
            assertEquals(ErrorCode.MALFORMED_DATA, error.code());
        }

        @Test
        void data長が合わないチャンクはMALFORMED_DATA() {
            SpringNbtException error = assertThrows(SpringNbtException.class,
                    () -> loadChunk("bitstorage_wrong_length"));
            assertEquals(ErrorCode.MALFORMED_DATA, error.code());
        }

        @Test
        void チャンク内の相対座標が範囲外ならINVALID_ARGUMENT() {
            Chunk chunk = loadChunk("palette_1");
            SpringNbtException error = assertThrows(SpringNbtException.class,
                    () -> chunk.getBlock(16, -64, 0));
            assertEquals(ErrorCode.INVALID_ARGUMENT, error.code());
        }
    }

    @Nested
    class DataVersionTest {

        /** DataVersionだけを、扱える形式の下限より古い値に差し替えたチャンクを作る */
        private NbtCompound foreignChunk() {
            NamedTag named = NbtIo.readFile(vectorPath("palette_1"), null);
            NbtCompound root = (NbtCompound) named.tag();
            root.set("DataVersion", new NbtInt(PRE_FLATTENING_DATA_VERSION));
            return root;
        }

        @Test
        void 既定では警告として通す() {
            List<String> warnings = new ArrayList<>();
            ChunkReadOptions options = new ChunkReadOptions()
                    .setOnVersionMismatch(VersionMismatchAction.WARN)
                    .setOnWarning(warnings::add);

            Chunk chunk = Chunk.fromNbt(foreignChunk(), options);
            assertEquals(PRE_FLATTENING_DATA_VERSION, chunk.dataVersion());
            assertEquals(1, warnings.size());
        }

        @Test
        void DataVersionが26_2のチャンクは警告を出さずに読める() {
            List<String> warnings = new ArrayList<>();
            ChunkReadOptions options = new ChunkReadOptions()
                    .setOnVersionMismatch(VersionMismatchAction.WARN)
                    .setOnWarning(warnings::add);

            // 26.2の形式も扱う形式に含まれる
            loadChunk("palette_old_format", options);
            assertTrue(warnings.isEmpty());
        }

        @Test
        void 扱える形式の下限は1_18() {
            assertEquals(2844, SpringNbt.MIN_SUPPORTED_DATA_VERSION);
        }

        @Test
        void ERRORを指定すると読み込みで弾く() {
            ChunkReadOptions options = new ChunkReadOptions()
                    .setOnVersionMismatch(VersionMismatchAction.ERROR);

            SpringNbtException error = assertThrows(SpringNbtException.class,
                    () -> Chunk.fromNbt(foreignChunk(), options));
            assertEquals(ErrorCode.UNSUPPORTED_DATA_VERSION, error.code());
        }

        @Test
        void IGNOREなら何も起きない() {
            List<String> warnings = new ArrayList<>();
            ChunkReadOptions options = new ChunkReadOptions()
                    .setOnVersionMismatch(VersionMismatchAction.IGNORE)
                    .setOnWarning(warnings::add);

            Chunk.fromNbt(foreignChunk(), options);
            assertTrue(warnings.isEmpty());
        }

        @Test
        void 別バージョン由来のチャンクは既定で書き戻せない() {
            Chunk chunk = Chunk.fromNbt(foreignChunk(),
                    new ChunkReadOptions().setOnVersionMismatch(VersionMismatchAction.IGNORE));

            SpringNbtException error = assertThrows(SpringNbtException.class,
                    () -> chunk.toNbt(ChunkWriteOptions.defaults()));
            assertEquals(ErrorCode.UNSUPPORTED_DATA_VERSION, error.code());
        }

        @Test
        void 許可すれば古いチャンクも元のバージョンのまま書き戻せる() {
            Chunk chunk = Chunk.fromNbt(foreignChunk(),
                    new ChunkReadOptions().setOnVersionMismatch(VersionMismatchAction.IGNORE));
            ChunkWriteOptions write = new ChunkWriteOptions().setAllowForeignDataVersion(true);

            // DataVersionは読んだ値のまま残す
            assertEquals(PRE_FLATTENING_DATA_VERSION, chunk.toNbt(write).getInt("DataVersion"));
        }

        /** 対象より新しいDataVersionを持つチャンクを作る */
        private NbtCompound newerChunk() {
            NamedTag named = NbtIo.readFile(vectorPath("palette_1"), null);
            NbtCompound root = (NbtCompound) named.tag();
            root.setInt("DataVersion", 5100);
            return root;
        }

        @Test
        void 新しいバージョンのチャンクは警告を出さない() {
            List<String> warnings = new ArrayList<>();
            ChunkReadOptions options = new ChunkReadOptions()
                    .setOnVersionMismatch(VersionMismatchAction.WARN)
                    .setOnWarning(warnings::add);

            // 形式が同じであれば、新しいバージョンでも警告を出さずに読める
            Chunk chunk = Chunk.fromNbt(newerChunk(), options);
            assertEquals(5100, chunk.dataVersion());
            assertTrue(warnings.isEmpty());
        }

        @Test
        void 新しいバージョンのチャンクはエラー設定でも通る() {
            ChunkReadOptions options = new ChunkReadOptions()
                    .setOnVersionMismatch(VersionMismatchAction.ERROR);
            assertEquals(5100, Chunk.fromNbt(newerChunk(), options).dataVersion());
        }

        @Test
        void 新しいバージョンのチャンクはそのまま書き戻せる() {
            Chunk chunk = Chunk.fromNbt(newerChunk(), null);

            // 許可を出さなくても書き戻せて、DataVersionも変わらない
            assertEquals(5100, chunk.toNbt(null).getInt("DataVersion"));
        }

        @Test
        void 対象バージョンのチャンクはそのまま書き戻せる() {
            Chunk chunk = loadChunk("palette_1");
            assertEquals(SpringNbt.TARGET_DATA_VERSION,
                    chunk.toNbt(ChunkWriteOptions.defaults()).getInt("DataVersion"));
        }
    }

    @Nested
    class ChunkFormatTest {

        @Test
        void DataVersion4903のチャンクを読み無変更で書き戻すと元と同じになる() {
            NbtCompound tag = (NbtCompound) NbtIo.readFile(vectorPath("v4903_edit"), null).tag();
            byte[] before = chunkBytes(tag);
            Chunk chunk = Chunk.fromNbt(tag, ChunkReadOptions.defaults());

            // ベクタの添字は (位置 * 7) % 5
            assertEquals(4903, chunk.dataVersion());
            assertEquals("minecraft:air", chunk.getBlock(0, -64, 0).toString());
            assertEquals("minecraft:dirt", chunk.getBlock(1, -64, 0).toString());
            assertEquals("minecraft:oak_stairs[facing=west,half=top]", chunk.getBlock(2, -64, 0).toString());
            assertEquals("minecraft:stone", chunk.getBlock(3, -64, 0).toString());
            assertEquals("minecraft:oak_stairs[facing=east,half=bottom]", chunk.getBlock(4, -64, 0).toString());
            assertEquals("minecraft:plains", chunk.getBiome(0, -64, 0));

            assertArrayEquals(before, chunkBytes(chunk.toNbt(ChunkWriteOptions.defaults())));
        }

        @Test
        void DataVersion4903のチャンクに置いたブロックはName_Propertiesで入る() {
            Chunk chunk = loadChunk("v4903_edit");
            chunk.setBlock(5, -64, 5, BlockState.parse("minecraft:oak_stairs[facing=north]"));
            NbtCompound written = chunk.toNbt(ChunkWriteOptions.defaults());

            // パレットの末尾に26.2の形式で足される
            NbtList palette = firstBlockPalette(written);
            assertEquals(nameProperties("minecraft:oak_stairs", "facing", "north"), palette.get(palette.size() - 1));

            // DataVersionは読んだ値のまま
            assertEquals(4903, written.getInt("DataVersion"));

            // 読み直しても同じ状態が返る
            Chunk reread = Chunk.fromNbt(written, ChunkReadOptions.defaults());
            assertEquals("minecraft:oak_stairs[facing=north]", reread.getBlock(5, -64, 5).toString());
        }

        @Test
        void 形式の違うチャンクはそれぞれ読んだ形式で書き出す() {
            Chunk older = loadChunk("v4903_edit");
            Chunk newer = loadChunk("palette_5");

            // 2つのチャンクに同じ手順で同じブロックを置く
            for (Chunk chunk : List.of(older, newer)) {
                chunk.setBlock(5, -64, 5, BlockState.parse("minecraft:oak_stairs[facing=north]"));
                chunk.setBlock(6, -64, 6, BlockState.parse("minecraft:edited_plain"));
            }

            NbtCompound olderWritten = older.toNbt(ChunkWriteOptions.defaults());
            NbtList olderPalette = firstBlockPalette(olderWritten);
            assertEquals(nameProperties("minecraft:oak_stairs", "facing", "north"),
                    olderPalette.get(olderPalette.size() - 2));
            assertEquals(nameProperties("minecraft:edited_plain"), olderPalette.get(olderPalette.size() - 1));
            assertEquals(4903, olderWritten.getInt("DataVersion"));

            NbtCompound newerWritten = newer.toNbt(ChunkWriteOptions.defaults());
            NbtList newerPalette = firstBlockPalette(newerWritten);

            // 型の混ざったパレットはCompoundのリストになり、文字列の要素だけが包まれる
            assertEquals(idProperties("minecraft:oak_stairs", "facing", "north"),
                    newerPalette.get(newerPalette.size() - 2));
            assertEquals(wrapped(new NbtString("minecraft:edited_plain")),
                    newerPalette.get(newerPalette.size() - 1));
            assertEquals(SpringNbt.TARGET_DATA_VERSION, newerWritten.getInt("DataVersion"));
        }

        @Test
        void 指定した世代とLevelの有無が食い違えばMALFORMED_DATA() {
            ChunkReadOptions options = new ChunkReadOptions()
                    .setOnVersionMismatch(VersionMismatchAction.IGNORE)
                    .setFormatDataVersion(5023);

            // Levelを持つチャンクを、Levelの無い世代で読ませる
            SpringNbtException error = assertThrows(SpringNbtException.class,
                    () -> Chunk.fromNbt(levelChunk(2586), options));
            assertEquals(ErrorCode.MALFORMED_DATA, error.code());
        }

        @Test
        void 世代を指定しても下限より古いチャンクは書き戻せない() {
            ChunkReadOptions options = new ChunkReadOptions()
                    .setOnVersionMismatch(VersionMismatchAction.IGNORE)
                    .setFormatDataVersion(5023);
            Chunk chunk = Chunk.fromNbt(preFlatteningChunk(), options);

            SpringNbtException error = assertThrows(SpringNbtException.class,
                    () -> chunk.toNbt(ChunkWriteOptions.defaults()));
            assertEquals(ErrorCode.UNSUPPORTED_DATA_VERSION, error.code());
        }

        @Test
        void 世代に1519未満を指定するとINVALID_ARGUMENT() {
            ChunkReadOptions options = new ChunkReadOptions().setFormatDataVersion(1518);

            SpringNbtException error = assertThrows(SpringNbtException.class,
                    () -> loadChunk("palette_1", options));
            assertEquals(ErrorCode.INVALID_ARGUMENT, error.code());
        }

        @Test
        void DataVersionが1519未満のチャンクは元のNBTだけを持つ() {
            NbtCompound root = preFlatteningChunk();
            byte[] before = chunkBytes(root);
            Chunk chunk = Chunk.fromNbt(root,
                    new ChunkReadOptions().setOnVersionMismatch(VersionMismatchAction.IGNORE));

            // 座標はLevelの中から読み、セクションは解釈しない
            assertEquals(3, chunk.x());
            assertEquals(-2, chunk.z());
            assertTrue(chunk.sectionYs().isEmpty());

            // ブロック・バイオーム・高さマップ・光源の操作はどれも受け付けない
            List<Executable> operations = List.of(
                    () -> chunk.getBlock(0, 0, 0),
                    () -> chunk.setBlock(0, 0, 0, "minecraft:stone"),
                    () -> chunk.getBiome(0, 0, 0),
                    () -> chunk.setBiome(0, 0, 0, "minecraft:plains"),
                    chunk::clearHeightmaps,
                    chunk::invalidateLighting);

            // 操作ごとにUNSUPPORTED_DATA_VERSIONになることを確かめる
            for (Executable operation : operations) {
                SpringNbtException error = assertThrows(SpringNbtException.class, operation);
                assertEquals(ErrorCode.UNSUPPORTED_DATA_VERSION, error.code());
            }

            // 許可すれば、読んだNBTがそのまま返る
            ChunkWriteOptions write = new ChunkWriteOptions().setAllowForeignDataVersion(true);
            assertArrayEquals(before, chunkBytes(chunk.toNbt(write)));
        }

        @Test
        void 世代を選んだDataVersionを返す() {
            NbtCompound tag = (NbtCompound) NbtIo.readFile(vectorPath("v4903_edit"), null).tag();
            assertEquals(4903, Chunk.fromNbt(tag, ChunkReadOptions.defaults()).formatDataVersion());

            // 指定すれば、チャンク自身のDataVersionではなくその値になる
            Chunk chunk = Chunk.fromNbt(tag, new ChunkReadOptions().setFormatDataVersion(5023));
            assertEquals(5023, chunk.formatDataVersion());
            assertEquals(4903, chunk.dataVersion());
        }
    }

    @Nested
    class MinecraftWorldTest {

        @TempDir
        Path work;

        @Test
        void 存在しないディレクトリはIO() {
            Path missing = work.resolve("missing");
            SpringNbtException error = assertThrows(SpringNbtException.class,
                    () -> MinecraftWorld.open(missing));
            assertEquals(ErrorCode.IO, error.code());
        }

        @Test
        void levelDatが無いディレクトリはIO() {
            SpringNbtException error = assertThrows(SpringNbtException.class,
                    () -> MinecraftWorld.open(work));
            assertEquals(ErrorCode.IO, error.code());
        }

        @Test
        void 次元経由で読んだチャンクの警告も通知先へ届く() throws Exception {
            Path region = work.resolve("dimensions").resolve("minecraft").resolve("overworld").resolve("region");
            Files.createDirectories(region);

            // DataVersionが扱える形式より古いチャンクを1つだけ持つワールドを作る
            NbtCompound level = new NbtCompound();
            level.set("Data", new NbtCompound());
            NbtIo.writeFile(work.resolve("level.dat"), new NamedTag("", level), null);

            NbtCompound chunk = (NbtCompound) NbtIo.readFile(vectorPath("palette_1"), null).tag();
            chunk.set("DataVersion", new NbtInt(PRE_FLATTENING_DATA_VERSION));

            try (RegionFile file = RegionFile.open(region.resolve("r.0.0.mca"), RegionFileMode.READ_WRITE)) {
                file.writeChunk(0, 0, chunk);
            }

            List<String> warnings = new ArrayList<>();
            WorldOpenOptions options = WorldOpenOptions.defaults()
                    .setChunkRead(ChunkReadOptions.defaults().setOnWarning(warnings::add));

            try (MinecraftWorld world = MinecraftWorld.open(work, options)) {
                assertNotNull(world.dimension(Dimension.OVERWORLD).chunk(0, 0));
            }

            // ワールドを開くときに渡した通知先が、次元経由の読み込みでも呼ばれる
            assertEquals(1, warnings.size());
        }
    }
}

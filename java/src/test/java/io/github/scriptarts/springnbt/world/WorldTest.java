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
import io.github.scriptarts.springnbt.nbt.NbtByte;
import io.github.scriptarts.springnbt.nbt.NbtByteArray;
import io.github.scriptarts.springnbt.nbt.NbtInt;
import io.github.scriptarts.springnbt.nbt.NbtIntArray;
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
import java.util.Map;
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

    /** セクションの一覧を、指定したYの並びに並べ替えた新しいリストを作る */
    private static NbtList sectionsInOrder(NbtList sections, int... order) {
        NbtList result = new NbtList(TagType.COMPOUND);

        // 指定の順に、Yの合うセクションを探して足す
        for (int sectionY : order) {
            // Yの合うセクションだけを足す
            for (NbtTag entry : sections) {
                NbtCompound section = (NbtCompound) entry;

                if (section.getByte("Y") == sectionY) {
                    result.add(section);
                }
            }
        }

        return result;
    }

    /** 書き出したセクションの一覧のYを並べる */
    private static List<Integer> sectionYOrder(NbtList sections) {
        List<Integer> result = new ArrayList<>();

        // 一覧の並びのままYを取り出す
        for (NbtTag entry : sections) {
            result.add((int) ((NbtCompound) entry).getByte("Y"));
        }

        return result;
    }

    /** 最初のセクションのblock_statesを、palette、data、ほかのキーの順に並べ替える */
    private static void reorderBlockStates(NbtCompound root) {
        NbtCompound section = (NbtCompound) root.getList("sections").get(0);
        NbtCompound container = section.getCompound("block_states");
        NbtCompound reordered = new NbtCompound();
        reordered.set("palette", container.get("palette"));
        reordered.set("data", container.get("data"));
        reordered.setInt("extra", 7);
        section.set("block_states", reordered);
    }

    /** 書き出したチャンクの最初のセクションのblock_states */
    private static NbtCompound firstBlockStates(NbtCompound written) {
        return ((NbtCompound) written.getList("sections").get(0)).getCompound("block_states");
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
        void またぐ詰め方で長さが合う() {
            assertEquals(320, BitStorage.longCount(5, 4096, true));
            assertEquals(256, BitStorage.longCount(4, 4096, true));
        }

        @Test
        void またぐ詰め方では値が64bitの境目をまたいで並ぶ() {
            BitStorage storage = BitStorage.create(5, 4096, true);

            // 添字12はビット60から64までなので、data[0]の上位4bitとdata[1]の最下位bitに分かれる
            storage.set(12, 0b10111);
            long[] longs = storage.toLongs();

            assertEquals(0b0111L, (longs[0] >>> 60) & 0b1111L);
            assertEquals(1L, longs[1] & 1L);
            assertEquals(0b10111, storage.get(12));
        }

        @Test
        void またぐ詰め方で境目の値を上書きしても隣が壊れない() {
            BitStorage storage = BitStorage.create(5, 4096, true);
            storage.set(11, 0b11111);
            storage.set(13, 0b11111);

            // 添字12は境目をまたぐので、書き込みのたびに両隣が保たれるか確かめる
            for (int value : new int[] {0b11111, 0b00000, 0b10101}) {
                storage.set(12, value);
                assertEquals(value, storage.get(12));
                assertEquals(0b11111, storage.get(11));
                assertEquals(0b11111, storage.get(13));
            }
        }

        @Test
        void またぐ詰め方で最後のlongの末尾まで読み書きできる() {
            BitStorage storage = BitStorage.create(5, 4096, true);
            storage.set(4094, 0b10101);
            storage.set(4095, 0b11011);

            // 添字4095はビット20475から20479で、最後のlongのビット59から63に収まる
            assertEquals(0b10101, storage.get(4094));
            assertEquals(0b11011, storage.get(4095));
            assertEquals(0b11011L, storage.toLongs()[319] >>> 59);
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
        void またぐ詰め方のコンテナは17種類目でビット幅が5になる() {
            List<NbtTag> palette = new ArrayList<>();

            for (int index = 0; index < 16; index++) {
                palette.add(blockEntry("minecraft:block_" + index));
            }

            PalettedContainer container = PalettedContainer.fromParts(
                    palette, new long[256], 4096, 4, true, false, false);
            assertEquals(4, container.bitsPerEntry());

            // 全エントリに位置由来の値を書いてから、17種類目を1つ足す
            for (int index = 0; index < 4096; index++) {
                container.set(index, blockEntry("minecraft:block_" + (index % 16)));
            }

            container.set(7, blockEntry("minecraft:block_16"));
            assertEquals(5, container.bitsPerEntry());
            assertEquals(320, container.toParts().data().length);

            for (int index = 0; index < 4096; index++) {
                String expected = "minecraft:block_" + (index % 16);

                if (index == 7) {
                    expected = "minecraft:block_16";
                }

                assertEquals(new NbtString(expected), container.get(index));
            }
        }

        @ParameterizedTest
        @ValueSource(booleans = {false, true})
        void dataが必ず書かれる形式なら1要素のパレットでもビット幅4のdataを返す(boolean spanning) {
            PalettedContainer container = PalettedContainer.fromParts(
                    List.of(blockEntry("minecraft:air")), new long[256], 4096, 4, spanning, true, false);

            PalettedContainer.Parts parts = container.toParts();
            assertEquals(1, parts.palette().size());
            assertArrayEquals(new long[256], parts.data());
        }

        @ParameterizedTest
        @ValueSource(booleans = {false, true})
        void dataが必ず書かれる形式でdataが無ければMALFORMED_DATA(boolean spanning) {
            SpringNbtException error = assertThrows(SpringNbtException.class,
                    () -> PalettedContainer.fromParts(
                            List.of(blockEntry("minecraft:air")), null, 4096, 4, spanning, true, false));
            assertEquals(ErrorCode.MALFORMED_DATA, error.code());
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
        void 読んだときのセクションの並びで書き戻す() {
            NbtCompound root = (NbtCompound) NbtIo.readFile(vectorPath("multi_section"), null).tag();
            root.set("sections", sectionsInOrder(root.getList("sections"), -2, -4, -3));
            byte[] before = chunkBytes(root);
            Chunk chunk = Chunk.fromNbt(root, ChunkReadOptions.defaults());

            // Yの昇順でない並びでも、無変更なら元とバイト単位で一致する
            assertArrayEquals(before, chunkBytes(chunk.toNbt(ChunkWriteOptions.defaults())));

            // 1つのセクションを書き換えても並びは変わらない
            chunk.setBlock(0, -48, 0, "minecraft:stone");
            NbtCompound written = chunk.toNbt(ChunkWriteOptions.defaults());

            assertEquals(List.of(-2, -4, -3), sectionYOrder(written.getList("sections")));
            assertEquals(List.of(-4, -3, -2), new ArrayList<>(chunk.sectionYs()));
        }

        @Test
        void paletteが先のコンテナはその並びのまま書き戻す() {
            NbtCompound root = (NbtCompound) NbtIo.readFile(vectorPath("palette_17"), null).tag();
            reorderBlockStates(root);
            byte[] before = chunkBytes(root);
            Chunk chunk = Chunk.fromNbt(root, ChunkReadOptions.defaults());

            // 無変更なら元とバイト単位で一致する
            assertArrayEquals(before, chunkBytes(chunk.toNbt(ChunkWriteOptions.defaults())));

            // ビット幅の変わらない書き換えなら、キーの並びもほかのキーも保つ
            chunk.setBlock(0, -64, 0, "minecraft:edited");
            NbtCompound container = firstBlockStates(chunk.toNbt(ChunkWriteOptions.defaults()));

            assertEquals(List.of("palette", "data", "extra"), new ArrayList<>(container.keys()));
            assertEquals(18, container.getList("palette").size());
        }

        @Test
        void dataが要らなくなれば消しまた要るときは読んだときの位置に戻す() {
            NbtCompound root = (NbtCompound) NbtIo.readFile(vectorPath("palette_17"), null).tag();
            reorderBlockStates(root);
            Chunk chunk = Chunk.fromNbt(root, ChunkReadOptions.defaults());

            // パレットが1要素になればdataだけを消し、ほかのキーの位置は保つ
            chunk.section(-4).blockStates().fill(new NbtString("minecraft:stone"));
            NbtCompound container = firstBlockStates(chunk.toNbt(ChunkWriteOptions.defaults()));
            assertEquals(List.of("palette", "extra"), new ArrayList<>(container.keys()));

            // 読んだときにあったdataは、読んだときの位置に戻す
            chunk.setBlock(0, -64, 0, "minecraft:edited");
            container = firstBlockStates(chunk.toNbt(ChunkWriteOptions.defaults()));
            assertEquals(List.of("palette", "data", "extra"), new ArrayList<>(container.keys()));
        }

        @Test
        void 読んだときに無かったdataはライブラリの並びで先に置く() {
            NbtCompound root = (NbtCompound) NbtIo.readFile(vectorPath("palette_1"), null).tag();
            ((NbtCompound) root.getList("sections").get(0)).getCompound("block_states").setInt("extra", 7);
            byte[] before = chunkBytes(root);
            Chunk chunk = Chunk.fromNbt(root, ChunkReadOptions.defaults());

            // 無変更なら元とバイト単位で一致する
            assertArrayEquals(before, chunkBytes(chunk.toNbt(ChunkWriteOptions.defaults())));

            // パレットが育ってdataが要るようになれば、dataを先に置きほかのキーを後ろに残す
            chunk.setBlock(0, -64, 0, "minecraft:edited");
            NbtCompound container = firstBlockStates(chunk.toNbt(ChunkWriteOptions.defaults()));
            assertEquals(List.of("data", "palette", "extra"), new ArrayList<>(container.keys()));
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
        void 扱える形式の下限は1_13() {
            assertEquals(1519, SpringNbt.MIN_SUPPORTED_DATA_VERSION);

            List<String> warnings = new ArrayList<>();
            ChunkReadOptions options = new ChunkReadOptions()
                    .setOnVersionMismatch(VersionMismatchAction.WARN)
                    .setOnWarning(warnings::add);

            // 1.13の正式版より1つ古いチャンクは、読み込みで警告になる
            NbtCompound root = preFlatteningChunk();
            root.setInt("DataVersion", 1518);
            Chunk.fromNbt(root, options);
            assertEquals(1, warnings.size());

            // 1.13の正式版のチャンクは警告を出さない
            Chunk.fromNbt(levelChunk(1519), options);
            assertEquals(1, warnings.size());
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
                    () -> chunk.getBiomeId(0, 0, 0),
                    () -> chunk.setBiomeId(0, 0, 0, 1),
                    chunk::clearHeightmaps,
                    chunk::invalidateLighting,
                    chunk::minSectionY);

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

        @Test
        void C5の世代で26_2のチャンクを読むとブロックの取得でMALFORMED_DATA() {
            Chunk chunk = loadChunk("v4903_edit", new ChunkReadOptions().setFormatDataVersion(5023));

            // パレットの要素がName / Propertiesなので、26.3の形式としては読めない
            SpringNbtException error = assertThrows(SpringNbtException.class, () -> chunk.getBlock(0, -64, 0));
            assertEquals(ErrorCode.MALFORMED_DATA, error.code());
        }

        @Test
        void ルートの直下にsectionsがあるチャンクを1_16の世代で読むとMALFORMED_DATA() {
            ChunkReadOptions options = new ChunkReadOptions().setFormatDataVersion(2586);

            // Levelの無いチャンクを、Levelに本体を包む世代で読ませる
            SpringNbtException error = assertThrows(SpringNbtException.class,
                    () -> loadChunk("palette_1", options));
            assertEquals(ErrorCode.MALFORMED_DATA, error.code());
        }

        @Test
        void 名前空間の無いfullも生成済みとみなす() {
            NbtCompound root = (NbtCompound) NbtIo.readFile(vectorPath("v4903_edit"), null).tag();
            root.setString("Status", "full");
            Chunk chunk = Chunk.fromNbt(root, ChunkReadOptions.defaults());

            assertEquals("full", chunk.status());
            assertTrue(chunk.isFullyGenerated());
        }
    }

    /** 1.16.5の形式のテストベクタのLevel.Biomesの値 */
    private static int levelBiome(int index) {
        return ((index * 3) % 11) + 1;
    }

    /** 1.16.5の形式のテストベクタをNBTのまま読む */
    private static NbtCompound levelVector() {
        return (NbtCompound) NbtIo.readFile(vectorPath("v2586_level"), null).tag();
    }

    /** Level.SectionsからY位置の合うセクションを探す */
    private static NbtCompound levelSection(NbtCompound root, int sectionY) {
        // Yが一致する要素を返す
        for (NbtTag entry : root.getCompound("Level").getList("Sections")) {
            NbtCompound section = (NbtCompound) entry;

            // Yの合うセクションだけを対象にする
            if (section.getByte("Y") == sectionY) {
                return section;
            }
        }

        throw new IllegalStateException("Y=" + sectionY + " のセクションが無い");
    }

    /** 付随データの要素の座標を並べる */
    private static List<List<Integer>> positions(NbtList values) {
        List<List<Integer>> result = new ArrayList<>();

        // 要素ごとに絶対座標を取り出す
        for (NbtTag entry : values) {
            NbtCompound compound = (NbtCompound) entry;
            result.add(List.of(compound.getInt("x"), compound.getInt("y"), compound.getInt("z")));
        }

        return result;
    }

    @Nested
    class LevelChunkTest {

        @Test
        void DataVersion2586のチャンクも読んだときのセクションの並びで書き戻す() {
            NbtCompound root = levelVector();
            NbtCompound level = root.getCompound("Level");
            level.set("Sections", sectionsInOrder(level.getList("Sections"), 1, -1, 0));
            byte[] before = chunkBytes(root);
            Chunk chunk = Chunk.fromNbt(root, ChunkReadOptions.defaults());

            // Yの昇順でない並びでも、無変更なら元とバイト単位で一致する
            assertArrayEquals(before, chunkBytes(chunk.toNbt(ChunkWriteOptions.defaults())));

            // 1つのセクションを書き換えても並びは変わらない
            chunk.setBlock(0, 16, 0, "minecraft:stone");
            NbtList sections = chunk.toNbt(ChunkWriteOptions.defaults()).getCompound("Level").getList("Sections");

            assertEquals(List.of(1, -1, 0), sectionYOrder(sections));
        }

        @Test
        void DataVersion2586のチャンクを読み無変更で書き戻すと元と同じになる() {
            NbtCompound root = levelVector();
            byte[] before = chunkBytes(root);
            Chunk chunk = Chunk.fromNbt(root, ChunkReadOptions.defaults());

            assertEquals(2586, chunk.dataVersion());
            assertEquals(2, chunk.x());
            assertEquals(-1, chunk.z());
            assertEquals(0, chunk.minSectionY());
            assertEquals("full", chunk.status());
            assertTrue(chunk.isFullyGenerated());
            assertEquals(List.of(-1, 0, 1), new ArrayList<>(chunk.sectionYs()));

            // ベクタの添字は (位置 * 7) % 5
            assertEquals("minecraft:air", chunk.getBlock(0, 0, 0).toString());
            assertEquals("minecraft:dirt", chunk.getBlock(1, 0, 0).toString());
            assertEquals("minecraft:oak_stairs[facing=west,half=top]", chunk.getBlock(2, 0, 0).toString());
            assertEquals("minecraft:stone", chunk.getBlock(3, 0, 0).toString());
            assertEquals("minecraft:oak_stairs[facing=east,half=bottom]", chunk.getBlock(4, 0, 0).toString());
            assertEquals("minecraft:air", chunk.getBlock(15, 31, 15).toString());

            // Paletteの無いセクションと、セクションの無い高さはブロックを持たない
            assertFalse(chunk.section(-1).hasBlockStates());
            assertNull(chunk.getBlock(0, -1, 0));
            assertNull(chunk.getBlock(0, 32, 0));

            assertArrayEquals(before, chunkBytes(chunk.toNbt(null)));
        }

        @Test
        void DataVersion2586のチャンクでブロックを置くとLevelの付随データが消える() {
            Chunk chunk = Chunk.fromNbt(levelVector(), ChunkReadOptions.defaults());

            // 絶対座標はx = 32 + 相対x、z = -16 + 相対z
            chunk.setBlock(0, 0, 0, "minecraft:stone");
            chunk.setBlock(1, 0, 1, "minecraft:stone");
            chunk.setBlock(2, 2, 2, "minecraft:oak_stairs[facing=north]");
            NbtCompound written = chunk.toNbt(null);
            NbtCompound level = written.getCompound("Level");

            assertEquals(List.of(List.of(47, 20, -1)), positions(level.getList("TileEntities")));
            assertEquals(0, level.getList("TileTicks").size());
            assertEquals(List.of(List.of(40, 5, -10)), positions(level.getList("LiquidTicks")));

            // ルートには付随データのキーを作らない
            assertFalse(written.containsKey("block_entities"));
            assertFalse(written.containsKey("TileEntities"));

            // パレットの末尾にName / Propertiesの形式で足され、BlockStatesも書き直される
            NbtCompound section = levelSection(written, 0);
            NbtList palette = section.getList("Palette");
            assertEquals(nameProperties("minecraft:oak_stairs", "facing", "north"), palette.get(palette.size() - 1));
            assertEquals(256, section.getLongArray("BlockStates").length);
            assertEquals(2586, written.getInt("DataVersion"));

            // 読み直しても同じ状態が返る
            Chunk reread = Chunk.fromNbt(written, ChunkReadOptions.defaults());
            assertEquals("minecraft:oak_stairs[facing=north]", reread.getBlock(2, 2, 2).toString());
            assertEquals("minecraft:stone", reread.getBlock(0, 0, 0).toString());
        }

        @Test
        void DataVersion2586のチャンクのバイオームIDを読み書きできる() {
            Chunk chunk = Chunk.fromNbt(levelVector(), ChunkReadOptions.defaults());

            assertEquals(levelBiome(0), chunk.getBiomeId(0, 0, 0));
            assertEquals(levelBiome((17 * 16) + (2 * 4) + 1), chunk.getBiomeId(5, 70, 9));
            assertEquals(levelBiome(1023), chunk.getBiomeId(15, 255, 15));

            // 高さ0..255の外は値を持たない
            assertNull(chunk.getBiomeId(0, -1, 0));
            assertNull(chunk.getBiomeId(0, 256, 0));

            chunk.setBiomeId(5, 70, 9, 42);
            assertTrue(chunk.isModified());
            assertEquals(42, chunk.getBiomeId(4, 68, 8));

            NbtCompound written = chunk.toNbt(null);
            assertEquals(42, written.getCompound("Level").getIntArray("Biomes")[(17 * 16) + (2 * 4) + 1]);
        }

        @ParameterizedTest
        @ValueSource(ints = {-1, 256})
        void 高さ0から255の外へバイオームIDを書くとINVALID_ARGUMENT(int y) {
            Chunk chunk = Chunk.fromNbt(levelVector(), ChunkReadOptions.defaults());

            SpringNbtException error = assertThrows(SpringNbtException.class, () -> chunk.setBiomeId(0, y, 0, 1));
            assertEquals(ErrorCode.INVALID_ARGUMENT, error.code());
        }

        @ParameterizedTest
        @ValueSource(strings = {"absent", "int0", "int256", "byte256"})
        void Biomesを読めないチャンクのバイオームIDはnullで書き込めない(String kind) {
            NbtCompound root = levelVector();
            NbtCompound level = root.getCompound("Level");
            level.remove("Biomes");

            // 種類ごとに、読めない形のBiomesを置く
            if (kind.equals("int0")) {
                level.set("Biomes", new NbtIntArray(new int[0]));
            } else if (kind.equals("int256")) {
                int[] values = new int[256];
                Arrays.fill(values, 1);
                level.set("Biomes", new NbtIntArray(values));
            } else if (kind.equals("byte256")) {
                byte[] values = new byte[256];
                Arrays.fill(values, (byte) 1);
                level.set("Biomes", new NbtByteArray(values));
            }

            byte[] before = chunkBytes(root);
            Chunk chunk = Chunk.fromNbt(root, ChunkReadOptions.defaults());
            assertNull(chunk.getBiomeId(0, 0, 0));

            SpringNbtException error = assertThrows(SpringNbtException.class, () -> chunk.setBiomeId(0, 0, 0, 1));
            assertEquals(ErrorCode.INVALID_ARGUMENT, error.code());

            // 元のNBTはそのまま残る
            assertArrayEquals(before, chunkBytes(chunk.toNbt(null)));
        }

        @Test
        void DataVersion2586のチャンクではバイオーム名のAPIはUNSUPPORTED_FEATURE() {
            Chunk chunk = Chunk.fromNbt(levelVector(), ChunkReadOptions.defaults());

            // セクションの無い高さでも、形式で決まるので同じエラーになる
            List<Executable> operations = List.of(
                    () -> chunk.getBiome(0, 0, 0),
                    () -> chunk.getBiome(0, 200, 0),
                    () -> chunk.setBiome(0, 0, 0, "minecraft:plains"));

            // 操作ごとにUNSUPPORTED_FEATUREになることを確かめる
            for (Executable operation : operations) {
                SpringNbtException error = assertThrows(SpringNbtException.class, operation);
                assertEquals(ErrorCode.UNSUPPORTED_FEATURE, error.code());
            }
        }

        @ParameterizedTest
        @ValueSource(strings = {"palette_1", "v4903_edit"})
        void バイオームIDのAPIは1_18以降のチャンクではUNSUPPORTED_FEATURE(String name) {
            Chunk chunk = loadChunk(name);

            SpringNbtException error = assertThrows(SpringNbtException.class, () -> chunk.getBiomeId(0, 0, 0));
            assertEquals(ErrorCode.UNSUPPORTED_FEATURE, error.code());

            error = assertThrows(SpringNbtException.class, () -> chunk.setBiomeId(0, 0, 0, 1));
            assertEquals(ErrorCode.UNSUPPORTED_FEATURE, error.code());
        }

        @Test
        void DataVersion2586のチャンクの高さマップと光源を無効化できる() {
            Chunk chunk = Chunk.fromNbt(levelVector(), ChunkReadOptions.defaults());
            chunk.clearHeightmaps();
            chunk.invalidateLighting();
            NbtCompound written = chunk.toNbt(null);
            NbtCompound level = written.getCompound("Level");

            assertNull(level.optCompound("Heightmaps"));
            assertEquals(0, level.getByte("isLightOn"));

            // ルートには作らない
            assertFalse(written.containsKey("isLightOn"));
        }

        @Test
        void isLightOnの無いDataVersion2586のチャンクは光源を無効化できない() {
            NbtCompound root = levelVector();
            root.getCompound("Level").remove("isLightOn");
            byte[] before = chunkBytes(root);
            Chunk chunk = Chunk.fromNbt(root, ChunkReadOptions.defaults());

            SpringNbtException error = assertThrows(SpringNbtException.class, chunk::invalidateLighting);
            assertEquals(ErrorCode.UNSUPPORTED_FEATURE, error.code());
            assertArrayEquals(before, chunkBytes(chunk.toNbt(null)));
        }

        @Test
        void 生成途中のDataVersion2586のチャンクは生成済みではない() {
            NbtCompound root = levelVector();
            root.getCompound("Level").setString("Status", "structure_starts");

            assertFalse(Chunk.fromNbt(root, ChunkReadOptions.defaults()).isFullyGenerated());
        }

        @ParameterizedTest
        @ValueSource(strings = {"BlockStates", "Palette"})
        void PaletteとBlockStatesの片方しか無いセクションはブロックを持たない(String key) {
            NbtCompound root = levelVector();
            levelSection(root, 1).remove(key);
            byte[] before = chunkBytes(root);
            Chunk chunk = Chunk.fromNbt(root, ChunkReadOptions.defaults());

            // Minecraftも両方がそろったセクションだけを読むので、ブロックの無いセクションとして扱う
            assertFalse(chunk.section(1).hasBlockStates());
            assertNull(chunk.getBlock(0, 16, 0));

            SpringNbtException error = assertThrows(SpringNbtException.class,
                    () -> chunk.setBlock(0, 16, 0, "minecraft:stone"));
            assertEquals(ErrorCode.INVALID_ARGUMENT, error.code());

            // 元のNBTはそのまま残る
            assertArrayEquals(before, chunkBytes(chunk.toNbt(null)));
        }

        @Test
        void Properties_Nameの並びの要素と同じ状態を置いてもパレットは増えない() {
            NbtCompound root = levelVector();
            NbtTag paletteBefore = levelSection(root, 0).getList("Palette").copy();
            Chunk chunk = Chunk.fromNbt(root, ChunkReadOptions.defaults());

            // 実データと同じくProperties -> Nameの並びで入っている状態を、プロパティの並びを変えて置く
            chunk.setBlock(0, 0, 0, "minecraft:oak_stairs[half=bottom,facing=east]");
            NbtCompound written = chunk.toNbt(null);

            // 同じ状態の要素を使い回すので、パレットは元のまま
            assertEquals(paletteBefore, levelSection(written, 0).getList("Palette"));
            Chunk reread = Chunk.fromNbt(written, ChunkReadOptions.defaults());
            assertEquals("minecraft:oak_stairs[facing=east,half=bottom]", reread.getBlock(0, 0, 0).toString());
        }

        @Test
        void Paletteの要素がCompoundでなければUNEXPECTED_TAG_TYPE() {
            NbtCompound root = levelVector();
            NbtList palette = new NbtList(TagType.STRING);
            palette.add(new NbtString("minecraft:air"));
            levelSection(root, 1).set("Palette", palette);

            SpringNbtException error = assertThrows(SpringNbtException.class,
                    () -> Chunk.fromNbt(root, ChunkReadOptions.defaults()));
            assertEquals(ErrorCode.UNEXPECTED_TAG_TYPE, error.code());
        }
    }

    /** 1.15.2の形式のテストベクタの0段目のパレットを、ブロック状態の文字列表現で並べたもの */
    private static List<String> spanningStates() {
        List<String> states = new ArrayList<>(List.of("minecraft:air", "minecraft:stone"));

        // 階段は下半分の4方向、上半分の4方向の順に並ぶ
        for (String half : List.of("bottom", "top")) {
            // 向きは名前の順に並ぶ
            for (String facing : List.of("east", "north", "south", "west")) {
                states.add("minecraft:oak_stairs[facing=" + facing + ",half=" + half + "]");
            }
        }

        // プロパティの無いブロックを後ろに並べる
        for (String name : List.of("dirt", "gravel", "sand", "bedrock", "cobblestone", "oak_planks", "glass")) {
            states.add("minecraft:" + name);
        }

        return states;
    }

    /** 1.15.2の形式のテストベクタのLevel.Biomesの値 */
    private static int spanningBiome(int index) {
        return ((index * 5) % 13) + 1;
    }

    /** 1.14.4の形式のテストベクタのLevel.Biomesの値 */
    private static int biome2D(int index) {
        return ((index * 7) % 61) + 1;
    }

    /** 1.16.5と1.14.4の形式のテストベクタの0段目のパレットを、ブロック状態の文字列表現で並べたもの */
    private static final List<String> LEVEL_STATES = List.of(
            "minecraft:air",
            "minecraft:stone",
            "minecraft:dirt",
            "minecraft:oak_stairs[facing=east,half=bottom]",
            "minecraft:oak_stairs[facing=west,half=top]");

    /** 1.15.2の形式のテストベクタをNBTのまま読む */
    private static NbtCompound spanningVector() {
        return (NbtCompound) NbtIo.readFile(vectorPath("v2230_spanning"), null).tag();
    }

    /** 1.14.4の形式のテストベクタをNBTのまま読む */
    private static NbtCompound biomes2DVector() {
        return (NbtCompound) NbtIo.readFile(vectorPath("v1976_biomes_2d"), null).tag();
    }

    /** DataVersionを持たないチャンクを作る */
    private static NbtCompound chunkWithoutDataVersion() {
        NbtCompound root = preFlatteningChunk();
        root.remove("DataVersion");
        return root;
    }

    @Nested
    class LegacyChunkTest {

        @Test
        void DataVersion2230のまたぐ詰め方のチャンクを読み無変更で書き戻すと元と同じになる() {
            NbtCompound root = spanningVector();
            byte[] before = chunkBytes(root);
            Chunk chunk = Chunk.fromNbt(root, ChunkReadOptions.defaults());
            List<String> states = spanningStates();

            assertEquals(2230, chunk.dataVersion());
            assertEquals(-3, chunk.x());
            assertEquals(5, chunk.z());
            assertEquals(0, chunk.minSectionY());
            assertTrue(chunk.isFullyGenerated());
            assertEquals(List.of(-1, 0, 1), new ArrayList<>(chunk.sectionYs()));
            assertEquals(17, chunk.section(0).blockStates().palette().size());
            assertEquals(5, chunk.section(0).blockStates().bitsPerEntry());

            // ベクタの添字は (位置 * 7) % 17
            // ビット幅5なので、位置12や25の値は64bitの境目をまたぐ
            assertEquals(states.get((12 * 7) % 17), chunk.getBlock(12, 0, 0).toString());
            assertEquals(states.get((25 * 7) % 17), chunk.getBlock(9, 0, 1).toString());

            // 全ブロックが元の添字どおりに読める
            for (int position = 0; position < 4096; position++) {
                BlockState block = chunk.getBlock(position & 15, position >> 8, (position >> 4) & 15);
                assertEquals(states.get((position * 7) % 17), block.toString());
            }

            assertEquals("minecraft:air", chunk.getBlock(15, 31, 15).toString());
            assertNull(chunk.getBlock(0, -1, 0));

            assertArrayEquals(before, chunkBytes(chunk.toNbt(null)));
        }

        @Test
        void DataVersion2230のチャンクでパレットが育ってもまたぐ詰め方で書き戻す() {
            Chunk chunk = Chunk.fromNbt(spanningVector(), ChunkReadOptions.defaults());
            List<String> states = spanningStates();

            // 20種類を足してパレットを37要素にし、ビット幅を5から6へ広げる
            for (int index = 0; index < 20; index++) {
                chunk.setBlock(index % 16, index / 16, 0, "minecraft:edited_" + index);
            }

            NbtCompound written = chunk.toNbt(null);
            NbtCompound section = levelSection(written, 0);

            // またぐ詰め方なので、長さは ceil(4096 * 6 / 64) = 384
            assertEquals(37, section.getList("Palette").size());
            assertEquals(384, section.getLongArray("BlockStates").length);
            assertEquals(2230, written.getInt("DataVersion"));

            Chunk reread = Chunk.fromNbt(written, ChunkReadOptions.defaults());

            // 置いたブロックと、触っていないブロックの両方が読み直せる
            for (int position = 0; position < 4096; position++) {
                int x = position & 15;
                int y = position >> 8;
                int z = (position >> 4) & 15;
                int index = (y * 16) + x;
                String block = reread.getBlock(x, y, z).toString();

                // 置いた位置だけ新しい状態になる
                if (z == 0 && index < 20) {
                    assertEquals("minecraft:edited_" + index, block);
                } else {
                    assertEquals(states.get((position * 7) % 17), block);
                }
            }
        }

        @Test
        void DataVersion2230のチャンクのバイオームIDは4ブロック単位で読める() {
            Chunk chunk = Chunk.fromNbt(spanningVector(), ChunkReadOptions.defaults());

            assertEquals(spanningBiome((17 * 16) + (2 * 4) + 1), chunk.getBiomeId(5, 70, 9));
            assertNull(chunk.getBiomeId(0, 256, 0));
        }

        @Test
        void DataVersion1976のチャンクを読み無変更で書き戻すと元と同じになる() {
            NbtCompound root = biomes2DVector();
            byte[] before = chunkBytes(root);
            Chunk chunk = Chunk.fromNbt(root, ChunkReadOptions.defaults());

            assertEquals(1976, chunk.dataVersion());
            assertEquals(4, chunk.x());
            assertEquals(-2, chunk.z());
            assertEquals(0, chunk.minSectionY());
            assertEquals(List.of(0, 1), new ArrayList<>(chunk.sectionYs()));

            // ベクタの添字は (位置 * 7) % 5
            assertEquals("minecraft:air", chunk.getBlock(0, 0, 0).toString());
            assertEquals("minecraft:dirt", chunk.getBlock(1, 0, 0).toString());
            assertEquals("minecraft:oak_stairs[facing=west,half=top]", chunk.getBlock(2, 0, 0).toString());
            assertEquals("minecraft:stone", chunk.getBlock(3, 0, 0).toString());
            assertEquals("minecraft:oak_stairs[facing=east,half=bottom]", chunk.getBlock(4, 0, 0).toString());
            assertEquals("minecraft:air", chunk.getBlock(15, 31, 15).toString());

            assertArrayEquals(before, chunkBytes(chunk.toNbt(null)));
        }

        @Test
        void DataVersion1976のチャンクでパレットが育ってもまたぐ詰め方で書き戻す() {
            Chunk chunk = Chunk.fromNbt(biomes2DVector(), ChunkReadOptions.defaults());

            // 12種類を足してパレットを17要素にし、ビット幅を4から5へ広げる
            for (int index = 0; index < 12; index++) {
                chunk.setBlock(index, 0, 0, "minecraft:edited_" + index);
            }

            NbtCompound written = chunk.toNbt(null);
            NbtCompound section = levelSection(written, 0);

            // またぐ詰め方なので、長さは ceil(4096 * 5 / 64) = 320（またがない詰め方なら342）
            assertEquals(17, section.getList("Palette").size());
            assertEquals(320, section.getLongArray("BlockStates").length);

            Chunk reread = Chunk.fromNbt(written, ChunkReadOptions.defaults());

            // 置いたブロックと、触っていないブロックの両方が読み直せる
            for (int position = 0; position < 4096; position++) {
                String block = reread.getBlock(position & 15, position >> 8, (position >> 4) & 15).toString();

                // 置いた位置だけ新しい状態になる
                if (position < 12) {
                    assertEquals("minecraft:edited_" + position, block);
                } else {
                    assertEquals(LEVEL_STATES.get((position * 7) % 5), block);
                }
            }
        }

        @Test
        void DataVersion1976のバイオームIDは高さに関係なく列ごとに読み書きできる() {
            Chunk chunk = Chunk.fromNbt(biomes2DVector(), ChunkReadOptions.defaults());

            // 添字は z * 16 + x で、yは見ない
            assertEquals(biome2D((7 * 16) + 3), chunk.getBiomeId(3, 0, 7));
            assertEquals(biome2D((7 * 16) + 3), chunk.getBiomeId(3, 200, 7));
            assertEquals(biome2D((7 * 16) + 3), chunk.getBiomeId(3, -10, 7));
            assertEquals(biome2D((7 * 16) + 3), chunk.getBiomeId(3, 300, 7));
            assertEquals(biome2D((3 * 16) + 7), chunk.getBiomeId(7, 0, 3));

            chunk.setBiomeId(3, 1000, 7, 42);
            assertTrue(chunk.isModified());
            assertEquals(42, chunk.getBiomeId(3, 0, 7));

            // 同じ列の値だけが変わる
            int[] biomes = chunk.toNbt(null).getCompound("Level").getIntArray("Biomes");
            assertEquals(42, biomes[(7 * 16) + 3]);
            assertEquals(biome2D((3 * 16) + 7), biomes[(3 * 16) + 7]);
        }

        @ParameterizedTest
        @ValueSource(strings = {"absent", "int0", "int1024", "byte256"})
        void DataVersion1976のBiomesを読めないチャンクのバイオームIDはnullで書き込めない(String kind) {
            NbtCompound root = biomes2DVector();
            NbtCompound level = root.getCompound("Level");
            level.remove("Biomes");

            // 種類ごとに、読めない形のBiomesを置く
            if (kind.equals("int0")) {
                level.set("Biomes", new NbtIntArray(new int[0]));
            } else if (kind.equals("int1024")) {
                int[] values = new int[1024];
                Arrays.fill(values, 1);
                level.set("Biomes", new NbtIntArray(values));
            } else if (kind.equals("byte256")) {
                byte[] values = new byte[256];
                Arrays.fill(values, (byte) 1);
                level.set("Biomes", new NbtByteArray(values));
            }

            byte[] before = chunkBytes(root);
            Chunk chunk = Chunk.fromNbt(root, ChunkReadOptions.defaults());
            assertNull(chunk.getBiomeId(0, 0, 0));

            SpringNbtException error = assertThrows(SpringNbtException.class, () -> chunk.setBiomeId(0, 0, 0, 1));
            assertEquals(ErrorCode.INVALID_ARGUMENT, error.code());

            // 元のNBTはそのまま残る
            assertArrayEquals(before, chunkBytes(chunk.toNbt(null)));
        }

        @Test
        void DataVersion1976のチャンクではバイオーム名のAPIはUNSUPPORTED_FEATURE() {
            Chunk chunk = Chunk.fromNbt(biomes2DVector(), ChunkReadOptions.defaults());

            SpringNbtException error = assertThrows(SpringNbtException.class, () -> chunk.getBiome(0, 0, 0));
            assertEquals(ErrorCode.UNSUPPORTED_FEATURE, error.code());
        }

        @Test
        void isLightOnの無い1_13の形式のチャンクは光源を無効化できない() {
            NbtCompound root = biomes2DVector();
            root.setInt("DataVersion", 1519);
            root.getCompound("Level").remove("isLightOn");
            byte[] before = chunkBytes(root);
            Chunk chunk = Chunk.fromNbt(root, ChunkReadOptions.defaults());

            SpringNbtException error = assertThrows(SpringNbtException.class, chunk::invalidateLighting);
            assertEquals(ErrorCode.UNSUPPORTED_FEATURE, error.code());
            assertArrayEquals(before, chunkBytes(chunk.toNbt(null)));
        }

        @ParameterizedTest
        @CsvSource({
            "full, true",
            "postprocessed, true",
            "fullchunk, true",
            "mobs_spawned, false",
            "decorated, false",
        })
        void 形式が1_14までならpostprocessedとfullchunkも生成済みとみなす(String status, boolean expected) {
            NbtCompound root = biomes2DVector();
            root.getCompound("Level").setString("Status", status);

            assertEquals(expected, Chunk.fromNbt(root, ChunkReadOptions.defaults()).isFullyGenerated());
        }

        @Test
        void 形式が1_15ならpostprocessedを生成済みとみなさない() {
            NbtCompound root = spanningVector();
            root.getCompound("Level").setString("Status", "postprocessed");

            assertFalse(Chunk.fromNbt(root, ChunkReadOptions.defaults()).isFullyGenerated());
        }

        @Test
        void Statusの無いチャンクは生成済みとみなさない() {
            ChunkReadOptions options = new ChunkReadOptions().setOnVersionMismatch(VersionMismatchAction.IGNORE);
            NbtCompound legacy = biomes2DVector();
            legacy.getCompound("Level").remove("Status");

            // 1.13より前のチャンクはStatusを持たない
            assertFalse(Chunk.fromNbt(preFlatteningChunk(), options).isFullyGenerated());
            assertFalse(Chunk.fromNbt(legacy, ChunkReadOptions.defaults()).isFullyGenerated());
        }

        @Test
        void Statusが文字列でないチャンクは生成済みとみなさない() {
            NbtCompound root = biomes2DVector();
            root.getCompound("Level").setInt("Status", 1);
            Chunk chunk = Chunk.fromNbt(root, ChunkReadOptions.defaults());

            // 生成段階の取得子は、いまと同じく型の違いをエラーにする
            SpringNbtException error = assertThrows(SpringNbtException.class, chunk::status);
            assertEquals(ErrorCode.UNEXPECTED_TAG_TYPE, error.code());
            assertFalse(chunk.isFullyGenerated());
        }

        @Test
        void DataVersionの無いチャンクは元のNBTだけを持つ() {
            NbtCompound root = chunkWithoutDataVersion();
            byte[] before = chunkBytes(root);
            List<String> warnings = new ArrayList<>();
            ChunkReadOptions options = new ChunkReadOptions()
                    .setOnVersionMismatch(VersionMismatchAction.WARN)
                    .setOnWarning(warnings::add);
            Chunk chunk = Chunk.fromNbt(root, options);

            // 1.13より前と同じく、読み込みで警告になる
            assertEquals(1, warnings.size());

            // 座標はLevelの中から読み、セクションは解釈しない
            assertEquals(3, chunk.x());
            assertEquals(-2, chunk.z());
            assertTrue(chunk.sectionYs().isEmpty());
            assertEquals(-1, chunk.formatDataVersion());

            // DataVersionの取得子は、いまと同じく無ければエラー
            assertThrows(SpringNbtException.class, chunk::dataVersion);

            // ブロック・バイオーム・高さマップ・光源の操作はどれも受け付けない
            List<Executable> operations = List.of(
                    () -> chunk.getBlock(0, 0, 0),
                    () -> chunk.setBlock(0, 0, 0, "minecraft:stone"),
                    () -> chunk.getBiome(0, 0, 0),
                    () -> chunk.setBiome(0, 0, 0, "minecraft:plains"),
                    () -> chunk.getBiomeId(0, 0, 0),
                    () -> chunk.setBiomeId(0, 0, 0, 1),
                    chunk::clearHeightmaps,
                    chunk::invalidateLighting,
                    chunk::minSectionY,
                    () -> chunk.toNbt(null));

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
        void DataVersionの無いチャンクはERRORなら読み込みで弾く() {
            ChunkReadOptions options = new ChunkReadOptions().setOnVersionMismatch(VersionMismatchAction.ERROR);

            SpringNbtException error = assertThrows(SpringNbtException.class,
                    () -> Chunk.fromNbt(chunkWithoutDataVersion(), options));
            assertEquals(ErrorCode.UNSUPPORTED_DATA_VERSION, error.code());
        }

        @Test
        void DataVersionの無いチャンクも世代を指定すればその値を返す() {
            ChunkReadOptions options = new ChunkReadOptions()
                    .setOnVersionMismatch(VersionMismatchAction.IGNORE)
                    .setFormatDataVersion(2230);
            Chunk chunk = Chunk.fromNbt(chunkWithoutDataVersion(), options);

            // 指定しても世代は選ばず、元のNBTだけを持つ
            assertEquals(2230, chunk.formatDataVersion());

            SpringNbtException error = assertThrows(SpringNbtException.class, () -> chunk.getBlock(0, 0, 0));
            assertEquals(ErrorCode.UNSUPPORTED_DATA_VERSION, error.code());
        }
    }

    /** {@code Data}に指定の項目だけを持つlevel.datを書く */
    private static void writeLevel(Path directory, Map<String, NbtTag> entries) {
        NbtCompound data = new NbtCompound();

        for (Map.Entry<String, NbtTag> entry : entries.entrySet()) {
            data.set(entry.getKey(), entry.getValue());
        }

        NbtCompound root = new NbtCompound();
        root.set("Data", data);
        NbtIo.writeFile(directory.resolve("level.dat"), new NamedTag("", root), null);
    }

    /** 指定の項目を持つ.datを、フォルダごと作って書く */
    private static void writeDat(Path path, Map<String, NbtTag> entries) throws Exception {
        Files.createDirectories(path.getParent());
        NbtCompound root = new NbtCompound();

        for (Map.Entry<String, NbtTag> entry : entries.entrySet()) {
            root.set(entry.getKey(), entry.getValue());
        }

        NbtIo.writeFile(path, new NamedTag("", root), null);
    }

    /** L1の合成ワールドを作る */
    private static void makeL1World(Path directory) throws Exception {
        writeLevel(directory, Map.of("DataVersion", new NbtInt(3953)));

        for (String folder : new String[] {"region", "DIM-1/region", "DIM1/region", "dimensions/mymap/arena/region"}) {
            Files.createDirectories(directory.resolve(folder));
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
            writeLevel(work, Map.of("DataVersion", new NbtInt(5023)));

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

    @Nested
    class WorldLayoutTest {

        @TempDir
        Path work;

        @Test
        void world_l1_dimensions() throws Exception {
            makeL1World(work);

            try (MinecraftWorld world = MinecraftWorld.open(work)) {
                assertEquals(
                        List.of("minecraft:overworld", "minecraft:the_nether", "minecraft:the_end", "mymap:arena"),
                        world.dimensionIds());
                assertEquals(work, world.dimension("minecraft:overworld").directory());
                assertEquals(work.resolve("DIM-1"), world.dimension("minecraft:the_nether").directory());
                assertEquals(work.resolve("DIM1"), world.dimension("minecraft:the_end").directory());
                assertEquals(work.resolve("dimensions/mymap/arena"), world.dimension("mymap:arena").directory());

                // 次元が無ければnull
                assertNull(world.dimension("mymap:missing"));
            }
        }

        @Test
        void L1で存在しない標準の次元は並ばない() throws Exception {
            writeLevel(work, Map.of("DataVersion", new NbtInt(3953)));
            Files.createDirectories(work.resolve("region"));

            try (MinecraftWorld world = MinecraftWorld.open(work)) {
                assertEquals(List.of("minecraft:overworld"), world.dimensionIds());
                assertNull(world.dimension("minecraft:the_nether"));
            }
        }

        @Test
        void L1ではdimensionsの下の標準の次元は並ばない() throws Exception {
            writeLevel(work, Map.of("DataVersion", new NbtInt(3953)));
            Files.createDirectories(work.resolve("dimensions/minecraft/the_nether/region"));

            try (MinecraftWorld world = MinecraftWorld.open(work)) {
                assertFalse(world.dimensionIds().contains("minecraft:the_nether"));
                assertNull(world.dimension("minecraft:the_nether"));
            }
        }

        @Test
        void world_l1_players() throws Exception {
            makeL1World(work);
            writeDat(work.resolve("playerdata/b-uuid.dat"), Map.of("Health", new NbtInt(20)));
            writeDat(work.resolve("playerdata/a-uuid.dat"), Map.of("Health", new NbtInt(7)));

            try (MinecraftWorld world = MinecraftWorld.open(work)) {
                assertEquals(List.of("a-uuid", "b-uuid"), world.playerIds());
                assertEquals(7, world.player("a-uuid").getInt("Health"));
                assertNull(world.player("missing"));
            }
        }

        @Test
        void world_l1_data_file() throws Exception {
            makeL1World(work);
            writeDat(work.resolve("data/scoreboard.dat"), Map.of("Value", new NbtInt(1)));
            writeDat(work.resolve("DIM-1/data/raids_nether.dat"), Map.of("Value", new NbtInt(2)));

            try (MinecraftWorld world = MinecraftWorld.open(work)) {
                assertEquals(1, world.dataFile("scoreboard").getInt("Value"));
                assertNull(world.dataFile("missing"));
                assertEquals(2, world.dimension("minecraft:the_nether").dataFile("raids_nether").getInt("Value"));

                // オーバーワールドの次元は、ワールドと同じdata/を読む
                assertEquals(1, world.dimension("minecraft:overworld").dataFile("scoreboard").getInt("Value"));
            }
        }

        @Test
        void level_data_l1_getters() {
            writeLevel(work, Map.of(
                    "DataVersion", new NbtInt(3953),
                    "SpawnX", new NbtInt(10),
                    "SpawnY", new NbtInt(64),
                    "SpawnZ", new NbtInt(-5),
                    "Difficulty", new NbtByte((byte) 2),
                    "hardcore", new NbtByte((byte) 1)));

            try (MinecraftWorld world = MinecraftWorld.open(work)) {
                assertArrayEquals(new int[] {10, 64, -5}, world.level().spawnPos());
                assertEquals("normal", world.level().difficulty());
                assertTrue(world.level().isHardcore());

                SpringNbtException error = assertThrows(SpringNbtException.class,
                        () -> world.level().spawnDimension());
                assertEquals(ErrorCode.UNSUPPORTED_FEATURE, error.code());
            }
        }

        @ParameterizedTest
        @CsvSource({"0,peaceful", "1,easy", "2,normal", "3,hard"})
        void L1の難易度は数値を名前に直す(int number, String name) {
            writeLevel(work, Map.of("DataVersion", new NbtInt(3953), "Difficulty", new NbtByte((byte) number)));

            try (MinecraftWorld world = MinecraftWorld.open(work)) {
                assertEquals(name, world.level().difficulty());
            }
        }

        @ParameterizedTest
        @ValueSource(ints = {-1, 4})
        void L1の難易度が範囲外ならMALFORMED_DATA(int number) {
            writeLevel(work, Map.of("DataVersion", new NbtInt(3953), "Difficulty", new NbtByte((byte) number)));

            try (MinecraftWorld world = MinecraftWorld.open(work)) {
                SpringNbtException error = assertThrows(SpringNbtException.class,
                        () -> world.level().difficulty());
                assertEquals(ErrorCode.MALFORMED_DATA, error.code());
            }
        }

        @Test
        void world_l2_unchanged() throws Exception {
            NbtCompound spawn = new NbtCompound();
            spawn.set("pos", new NbtIntArray(new int[] {1, 2, 3}));
            spawn.set("dimension", new NbtString("minecraft:overworld"));
            NbtCompound settings = new NbtCompound();
            settings.set("difficulty", new NbtString("hard"));
            settings.set("hardcore", new NbtByte((byte) 1));
            writeLevel(work, Map.of(
                    "DataVersion", new NbtInt(5023),
                    "spawn", spawn,
                    "difficulty_settings", settings));

            Files.createDirectories(work.resolve("dimensions/minecraft/overworld"));
            Files.createDirectories(work.resolve("dimensions/minecraft/the_end"));
            writeDat(work.resolve("players/data/u.dat"), Map.of("Health", new NbtInt(3)));
            writeDat(work.resolve("data/minecraft/weather.dat"), Map.of("Value", new NbtInt(4)));
            writeDat(work.resolve("dimensions/minecraft/the_end/data/minecraft/raids.dat"),
                    Map.of("Value", new NbtInt(5)));

            try (MinecraftWorld world = MinecraftWorld.open(work)) {
                assertArrayEquals(new int[] {1, 2, 3}, world.level().spawnPos());
                assertEquals("minecraft:overworld", world.level().spawnDimension());
                assertEquals("hard", world.level().difficulty());
                assertTrue(world.level().isHardcore());
                assertEquals(List.of("minecraft:overworld", "minecraft:the_end"), world.dimensionIds());
                assertEquals(List.of("u"), world.playerIds());
                assertEquals(4, world.dataFile("weather").getInt("Value"));
                assertEquals(5, world.dimension("the_end").dataFile("raids").getInt("Value"));
            }
        }

        @Test
        void DataVersionが無いlevelDatはL1として読む() throws Exception {
            writeLevel(work, Map.of());
            Files.createDirectories(work.resolve("DIM1"));

            try (MinecraftWorld world = MinecraftWorld.open(work)) {
                assertEquals(List.of("minecraft:the_end"), world.dimensionIds());
            }
        }

        @Test
        void world_override_layout() throws Exception {
            // level.datは26.3を名乗るが、構成はL1
            writeLevel(work, Map.of(
                    "DataVersion", new NbtInt(5023),
                    "SpawnX", new NbtInt(1),
                    "SpawnY", new NbtInt(2),
                    "SpawnZ", new NbtInt(3)));
            Files.createDirectories(work.resolve("region"));

            try (MinecraftWorld plain = MinecraftWorld.open(work)) {
                assertTrue(plain.dimensionIds().isEmpty());
            }

            WorldOpenOptions options = WorldOpenOptions.defaults().setFormatDataVersion(3953);

            try (MinecraftWorld world = MinecraftWorld.open(work, options)) {
                assertEquals(List.of("minecraft:overworld"), world.dimensionIds());
                assertArrayEquals(new int[] {1, 2, 3}, world.level().spawnPos());
            }

            SpringNbtException error = assertThrows(SpringNbtException.class,
                    () -> MinecraftWorld.open(work, WorldOpenOptions.defaults().setFormatDataVersion(1518)));
            assertEquals(ErrorCode.INVALID_ARGUMENT, error.code());
        }

        @Test
        void ワールドの指定は読むチャンクの世代にも効く() throws Exception {
            writeLevel(work, Map.of("DataVersion", new NbtInt(5023)));
            Path region = work.resolve("dimensions/minecraft/overworld/region");
            Files.createDirectories(region);
            NbtCompound chunk = (NbtCompound) NbtIo.readFile(vectorPath("palette_1"), null).tag();

            try (RegionFile file = RegionFile.open(region.resolve("r.0.0.mca"), RegionFileMode.READ_WRITE)) {
                file.writeChunk(0, 0, chunk);
            }

            // ワールドの指定がchunkReadの指定より優先される
            ChunkReadOptions readOptions = ChunkReadOptions.defaults().setFormatDataVersion(5023);
            WorldOpenOptions options = WorldOpenOptions.defaults()
                    .setChunkRead(readOptions)
                    .setFormatDataVersion(5006);

            try (MinecraftWorld world = MinecraftWorld.open(work, options)) {
                Chunk loaded = world.dimension("minecraft:overworld").chunk(0, 0);
                assertEquals(5006, loaded.formatDataVersion());
            }

            // 渡したオプションは書き換えない
            assertEquals(5023, readOptions.formatDataVersion());
        }
    }
}

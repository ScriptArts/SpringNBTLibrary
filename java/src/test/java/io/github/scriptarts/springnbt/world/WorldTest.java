package io.github.scriptarts.springnbt.world;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import io.github.scriptarts.springnbt.ErrorCode;
import io.github.scriptarts.springnbt.SpringNbt;
import io.github.scriptarts.springnbt.SpringNbtException;
import io.github.scriptarts.springnbt.nbt.Compression;
import io.github.scriptarts.springnbt.nbt.NamedTag;
import io.github.scriptarts.springnbt.nbt.NbtCompound;
import io.github.scriptarts.springnbt.nbt.NbtInt;
import io.github.scriptarts.springnbt.nbt.NbtList;
import io.github.scriptarts.springnbt.nbt.NbtIo;
import io.github.scriptarts.springnbt.nbt.NbtString;
import io.github.scriptarts.springnbt.nbt.NbtWriteOptions;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;

/**
 * World / Block レイヤ。
 *
 * <p>仕様: {@code docs/spec/30-chunk-format.md} / {@code 31-paletted-container.md} /
 * {@code 40-world-layout.md}
 *
 * <p>他言語版と同じ検証項目を持つ。
 */
class WorldTest {

    /** 共通テストベクタ（world/*.nbt）のパス。 */
    private static Path vectorPath(String name) {
        Path current = Path.of("").toAbsolutePath();

        // 実行ディレクトリからリポジトリ直下まで遡って spec/testdata を探す
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

    /** テストベクタをチャンクとして読む。 */
    private static Chunk loadChunk(String name) {
        return loadChunk(name, ChunkReadOptions.defaults());
    }

    private static Chunk loadChunk(String name, ChunkReadOptions options) {
        NamedTag named = NbtIo.readFile(vectorPath(name), null);
        return Chunk.fromNbt((NbtCompound) named.tag(), options);
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
            NbtCompound nbt = state.toNbt();
            assertEquals("minecraft:oak_stairs", nbt.getString("Name"));
            assertEquals("north", nbt.getCompound("Properties").getString("facing"));
            assertEquals(state, BlockState.fromNbt(nbt));
        }

        @Test
        void プロパティ無しのNBTにはPropertiesを書かない() {
            assertNull(BlockState.parse("minecraft:air").toNbt().optCompound("Properties"));
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

            // bits=5 なら 1 つの long に 12 個。12 個目は次の long の最下位から始まる
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
            // 4096 エントリを 342 long で表せるのは bits=5 のときだけ
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

        private NbtCompound blockEntry(String name) {
            NbtCompound entry = new NbtCompound();
            entry.set("Name", new NbtString(name));
            return entry;
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

            // パレットを 17 要素まで増やして bits=4 から 5 への拡張を起こす
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

            // 残るのは実際に使われている air と dirt の 2 つ
            assertEquals(2, container.palette().size());
            assertEquals("minecraft:dirt", ((NbtCompound) container.get(0)).getString("Name"));
        }

        @Test
        void fillで単一値に戻る() {
            PalettedContainer container = PalettedContainer.filled(blockEntry("minecraft:air"), 4096, 4);
            container.set(0, blockEntry("minecraft:stone"));
            container.fill(blockEntry("minecraft:water"));

            assertEquals(1, container.palette().size());
            assertEquals(0, container.bitsPerEntry());
            assertEquals("minecraft:water", ((NbtCompound) container.get(4095)).getString("Name"));
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

            // ベクタの添字は (位置 * 11) % 17。パレット先頭 2 つだけ名前が違う
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
        void バイオームは4ブロック単位で効く() {
            Chunk chunk = loadChunk("palette_1");
            chunk.setBiome(0, -64, 0, "minecraft:desert");

            // 同じ 4×4×4 の枠内はまとめて変わる
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

            // (0,-64,0) には chest と block_tick、(1,-64,1) には furnace と fluid_tick がある
            chunk.setBlock(0, -64, 0, BlockState.parse("minecraft:stone"));
            chunk.setBlock(1, -64, 1, BlockState.parse("minecraft:stone"));

            NbtList entities = chunk.raw().getList("block_entities");

            // 触っていない (15,-50,15) の barrel だけが残る
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
            // 付随データは絶対座標で持つので、チャンク座標を取り違えると
            // 無関係な要素を消してしまう
            NamedTag named = NbtIo.readFile(vectorPath("block_entities"), null);
            NbtCompound root = (NbtCompound) named.tag();
            root.set("xPos", new NbtInt(1));
            root.set("zPos", new NbtInt(1));

            Chunk chunk = Chunk.fromNbt(root, ChunkReadOptions.defaults());
            chunk.setBlock(0, -64, 0, BlockState.parse("minecraft:stone"));

            // このチャンクの (0,-64,0) は絶対座標 (16,-64,16)。どれとも一致しない
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

        /** DataVersion だけを差し替えたチャンクを作る。 */
        private NbtCompound foreignChunk() {
            NamedTag named = NbtIo.readFile(vectorPath("palette_1"), null);
            NbtCompound root = (NbtCompound) named.tag();
            root.set("DataVersion", new NbtInt(3953));
            return root;
        }

        @Test
        void 既定では警告として通す() {
            List<String> warnings = new ArrayList<>();
            ChunkReadOptions options = new ChunkReadOptions()
                    .setOnVersionMismatch(VersionMismatchAction.WARN)
                    .setOnWarning(warnings::add);

            Chunk chunk = Chunk.fromNbt(foreignChunk(), options);
            assertEquals(3953, chunk.dataVersion());
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
        void 許可すれば対象バージョンとして書き戻す() {
            Chunk chunk = Chunk.fromNbt(foreignChunk(),
                    new ChunkReadOptions().setOnVersionMismatch(VersionMismatchAction.IGNORE));
            ChunkWriteOptions write = new ChunkWriteOptions().setAllowForeignDataVersion(true);

            // 書き戻しは常に対象バージョンへ揃える
            assertEquals(SpringNbt.TARGET_DATA_VERSION, chunk.toNbt(write).getInt("DataVersion"));
        }

        @Test
        void 対象バージョンのチャンクはそのまま書き戻せる() {
            Chunk chunk = loadChunk("palette_1");
            assertEquals(SpringNbt.TARGET_DATA_VERSION,
                    chunk.toNbt(ChunkWriteOptions.defaults()).getInt("DataVersion"));
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
    }
}

package io.github.scriptarts.springnbt.anvil;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import io.github.scriptarts.springnbt.ErrorCode;
import io.github.scriptarts.springnbt.SpringNbt;
import io.github.scriptarts.springnbt.SpringNbtException;
import io.github.scriptarts.springnbt.nbt.NbtByteArray;
import io.github.scriptarts.springnbt.nbt.NbtCompound;
import io.github.scriptarts.springnbt.nbt.NbtInt;
import io.github.scriptarts.springnbt.nbt.NbtString;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;

/**
 * Anvil リージョンファイルの読み書き。
 *
 * <p>仕様: {@code docs/spec/20-anvil-region.md}
 *
 * <p>他言語版と同じ検証項目を持つ。
 * 共通テストベクタによる言語間比較は {@code spec/run-conformance.sh} が担当し、
 * ここでは API の振る舞いを直接確かめる。
 */
class RegionFileTest {

    @TempDir
    Path work;

    /** 共通テストベクタのディレクトリ。 */
    private static Path vectorDir(String name) {
        Path current = Path.of("").toAbsolutePath();

        // 実行ディレクトリからリポジトリ直下まで遡って spec/testdata を探す
        while (current != null) {
            Path candidate = current.resolve("spec").resolve("testdata").resolve("anvil").resolve(name);

            if (Files.isDirectory(candidate)) {
                return candidate;
            }

            current = current.getParent();
        }

        throw new IllegalStateException("テストベクタが見つからない: anvil/" + name);
    }

    /** ベクタを一時ディレクトリへ複製し、書き込みテストで原本を汚さないようにする。 */
    private Path copyVector(String name) throws IOException {
        Path source = vectorDir(name);
        Path destination = work.resolve(name);
        Files.createDirectories(destination);

        try (Stream<Path> files = Files.list(source)) {
            for (Path file : files.toList()) {
                Files.copy(file, destination.resolve(file.getFileName()));
            }
        }

        return destination;
    }

    private static NbtCompound sampleChunk(int x, int z) {
        NbtCompound chunk = new NbtCompound();
        chunk.set("DataVersion", new NbtInt(SpringNbt.TARGET_DATA_VERSION));
        chunk.set("xPos", new NbtInt(x));
        chunk.set("zPos", new NbtInt(z));
        chunk.set("yPos", new NbtInt(-4));
        chunk.set("Status", new NbtString("minecraft:full"));
        return chunk;
    }

    /** 圧縮しても縮まないバイト列を作る。サイズの制御が効くようにするため。 */
    private static byte[] incompressible(int length) {
        byte[] result = new byte[length];
        int state = 0x12345678;

        // 線形合同法で疑似乱数を作る。テストの再現性を保つため固定の種を使う
        for (int index = 0; index < length; index++) {
            state = (state * 1664525) + 1013904223;
            result[index] = (byte) (state >>> 24);
        }

        return result;
    }

    private static ErrorCode codeOf(Runnable action) {
        return assertThrows(SpringNbtException.class, action::run).code();
    }

    // -- 座標計算 -----------------------------------------------------------

    @ParameterizedTest
    @CsvSource({
        "0, 0, 0, 0, 0, 0",
        "31, 31, 0, 0, 31, 31",
        "32, 32, 1, 1, 0, 0",
        "-1, -1, -1, -1, 31, 31",
        "-32, -32, -1, -1, 0, 0",
        "-33, -33, -2, -2, 31, 31",
    })
    void chunkPositionMathHandlesNegativeCoordinates(
            int chunkX, int chunkZ, int regionX, int regionZ, int localX, int localZ) {
        ChunkPos position = new ChunkPos(chunkX, chunkZ);

        // 算術右シフトなので負の座標でも正しく求まる
        assertEquals(new RegionPos(regionX, regionZ), position.region());
        assertEquals(localX, position.localX());
        assertEquals(localZ, position.localZ());
        assertEquals(localX + (localZ * 32), position.index());
    }

    @Test
    void regionFileNameRoundtrips() {
        assertEquals("r.-1.2.mca", new RegionPos(-1, 2).fileName());
        assertEquals(new RegionPos(-1, 2), RegionPos.fromFileName("r.-1.2.mca"));

        // 形式が違うものは受け付けない
        assertNull(RegionPos.fromFileName("r.0.0.mcr"));
        assertNull(RegionPos.fromFileName("region.mca"));
        assertNull(RegionPos.fromFileName("r.a.0.mca"));
    }

    // -- 読み込み -----------------------------------------------------------

    @Test
    void emptyRegionHasNoChunks() {
        try (RegionFile region = RegionFile.open(vectorDir("empty").resolve("r.0.0.mca"))) {
            assertTrue(region.chunkPositions().isEmpty());
            assertFalse(region.hasChunk(0, 0));
            assertNull(region.readChunk(0, 0));
        }
    }

    @Test
    void readsSingleChunk() {
        try (RegionFile region = RegionFile.open(vectorDir("single_chunk").resolve("r.0.0.mca"))) {
            assertEquals(List.of(new ChunkPos(0, 0)), region.chunkPositions());
            assertTrue(region.hasChunk(0, 0));

            NbtCompound chunk = region.readChunk(0, 0);
            assertNotNull(chunk);
            assertEquals(SpringNbt.TARGET_DATA_VERSION, chunk.getInt("DataVersion"));
            assertEquals("minecraft:full", chunk.getString("Status"));
            assertEquals(1700000000, region.timestamp(0, 0));
        }
    }

    @Test
    void readsEveryCompressionScheme() {
        try (RegionFile region =
                RegionFile.open(vectorDir("mixed_compression").resolve("r.0.0.mca"))) {
            assertEquals(ChunkCompression.GZIP, region.readChunkRaw(0, 0).compression());
            assertEquals(ChunkCompression.ZLIB, region.readChunkRaw(1, 0).compression());
            assertEquals(ChunkCompression.NONE, region.readChunkRaw(2, 0).compression());

            // 方式が違っても中身は同じように読める
            for (int x = 0; x < 3; x++) {
                assertEquals(x, region.readChunk(x, 0).getInt("xPos"));
            }
        }
    }

    @Test
    void readsChunkStoredInExternalFile() {
        try (RegionFile region =
                RegionFile.open(vectorDir("external_mcc").resolve("r.0.0.mca"))) {
            RawChunk raw = region.readChunkRaw(0, 0);
            assertNotNull(raw);
            assertTrue(raw.external());
            assertEquals(ChunkCompression.ZLIB, raw.compression());
            assertEquals("minecraft:full", region.readChunk(0, 0).getString("Status"));
        }
    }

    @ParameterizedTest
    @ValueSource(strings = {
        "bad_offset", "overlapping_sectors", "unaligned_length", "offset_out_of_file",
    })
    void brokenHeadersAreRejected(String vector) {
        assertEquals(ErrorCode.MALFORMED_DATA,
                codeOf(() -> RegionFile.open(vectorDir(vector).resolve("r.0.0.mca")).close()));
    }

    @Test
    void chunkOutsideTheRegionIsRejected() {
        try (RegionFile region = RegionFile.open(vectorDir("empty").resolve("r.0.0.mca"))) {
            // r.0.0 が担当するのは 0..31 の範囲だけ
            assertEquals(ErrorCode.INVALID_ARGUMENT, codeOf(() -> region.hasChunk(32, 0)));
        }
    }

    @Test
    void readOnlyRegionRejectsWrites() {
        try (RegionFile region = RegionFile.open(vectorDir("empty").resolve("r.0.0.mca"))) {
            assertEquals(ErrorCode.INVALID_ARGUMENT,
                    codeOf(() -> region.writeChunk(0, 0, sampleChunk(0, 0))));
        }
    }

    // -- 書き込み -----------------------------------------------------------

    @Test
    void openingAndFlushingWithoutChangesKeepsBytesIdentical() throws IOException {
        // 触っていないチャンクの配置を保つことが、既存ワールドを壊さない前提になる
        Path path = copyVector("fragmented").resolve("r.0.0.mca");
        byte[] original = Files.readAllBytes(path);

        try (RegionFile region = RegionFile.open(path, RegionFileMode.READ_WRITE)) {
            region.flush();
        }

        assertArrayEquals(original, Files.readAllBytes(path));
    }

    @Test
    void writesAndReadsBackAChunk() throws IOException {
        Path path = work.resolve("r.0.0.mca");

        try (RegionFile region = RegionFile.open(path, RegionFileMode.READ_WRITE)) {
            region.writeChunk(3, 4, sampleChunk(3, 4));
            region.flush();
        }

        try (RegionFile reopened = RegionFile.open(path)) {
            assertTrue(reopened.hasChunk(3, 4));
            assertEquals(3, reopened.readChunk(3, 4).getInt("xPos"));
        }

        // 書き出したファイルは必ずセクタ境界に揃う
        assertEquals(0, Files.size(path) % RegionFile.SECTOR_SIZE);
    }

    @Test
    void rewritingTheSameSizeKeepsTheChunkInPlace() throws IOException {
        Path path = copyVector("fragmented").resolve("r.0.0.mca");
        long originalLength = Files.size(path);

        try (RegionFile region = RegionFile.open(path, RegionFileMode.READ_WRITE)) {
            // 同じ内容を書き直すので、必要セクタ数は変わらない
            region.writeChunk(0, 0, region.readChunk(0, 0));
            region.flush();
        }

        // その場で上書きされるので、ファイルは伸びない
        assertEquals(originalLength, Files.size(path));

        try (RegionFile reopened = RegionFile.open(path)) {
            assertEquals(3, reopened.chunkPositions().size());
        }
    }

    @Test
    void growingChunkIsRelocatedWithoutBreakingOthers() throws IOException {
        Path path = copyVector("fragmented").resolve("r.0.0.mca");

        // 5 セクタぶんになる大きなチャンクを作る
        NbtCompound big = sampleChunk(0, 0);
        big.set("filler", new NbtByteArray(incompressible(5 * RegionFile.SECTOR_SIZE)));

        try (RegionFile region = RegionFile.open(path, RegionFileMode.READ_WRITE)) {
            region.writeChunk(0, 0, big);
            region.flush();
        }

        try (RegionFile reopened = RegionFile.open(path)) {
            // 動かした結果、他の 2 チャンクが壊れていないこと
            assertEquals(3, reopened.chunkPositions().size());
            assertEquals(5, reopened.readChunk(5, 3).getInt("xPos"));
            assertEquals(31, reopened.readChunk(31, 31).getInt("xPos"));
            assertEquals(5 * RegionFile.SECTOR_SIZE,
                    reopened.readChunk(0, 0).getByteArray("filler").length);
        }
    }

    @Test
    void deletedChunkDisappearsAndOthersSurvive() throws IOException {
        Path path = copyVector("fragmented").resolve("r.0.0.mca");

        try (RegionFile region = RegionFile.open(path, RegionFileMode.READ_WRITE)) {
            assertTrue(region.deleteChunk(5, 3));
            assertFalse(region.deleteChunk(5, 3));
            region.flush();
        }

        try (RegionFile reopened = RegionFile.open(path)) {
            assertFalse(reopened.hasChunk(5, 3));
            assertEquals(0, reopened.timestamp(5, 3));
            assertEquals(2, reopened.chunkPositions().size());
        }
    }

    @Test
    void freedSectorsAreReused() throws IOException {
        Path path = copyVector("fragmented").resolve("r.0.0.mca");
        long originalLength = Files.size(path);

        try (RegionFile region = RegionFile.open(path, RegionFileMode.READ_WRITE)) {
            region.deleteChunk(5, 3);
            region.writeChunk(7, 7, sampleChunk(7, 7));
            region.flush();
        }

        // 空いたセクタへ収まるので、ファイルは伸びない
        assertEquals(originalLength, Files.size(path));

        try (RegionFile reopened = RegionFile.open(path)) {
            assertEquals(7, reopened.readChunk(7, 7).getInt("xPos"));
        }
    }

    @Test
    void optimizeCompactsTheFile() throws IOException {
        Path path = copyVector("fragmented").resolve("r.0.0.mca");
        long originalLength = Files.size(path);

        try (RegionFile region = RegionFile.open(path, RegionFileMode.READ_WRITE)) {
            region.optimize();
            region.flush();
        }

        long optimizedLength = Files.size(path);

        // 隙間が詰まるぶん小さくなる
        assertTrue(optimizedLength < originalLength,
                "詰め直しても縮んでいない: " + originalLength + " -> " + optimizedLength);
        assertEquals(0, optimizedLength % RegionFile.SECTOR_SIZE);

        try (RegionFile reopened = RegionFile.open(path)) {
            assertEquals(3, reopened.chunkPositions().size());
            assertEquals(1700000000, reopened.timestamp(0, 0));
            assertEquals(31, reopened.readChunk(31, 31).getInt("xPos"));
        }
    }

    @Test
    void hugeChunkGoesToExternalFileAndComesBack() throws IOException {
        Path path = work.resolve("r.0.0.mca");

        // 1MiB を超えるよう、圧縮の効かないデータを詰める
        NbtCompound huge = sampleChunk(1, 2);
        huge.set("filler", new NbtByteArray(incompressible(1200 * 1024)));

        try (RegionFile region = RegionFile.open(path, RegionFileMode.READ_WRITE)) {
            region.writeChunk(1, 2, huge, ChunkCompression.NONE);
            region.flush();
        }

        Path external = work.resolve("c.1.2.mcc");
        assertTrue(Files.exists(external), "外部ファイルへ退避されていない");

        try (RegionFile reopened = RegionFile.open(path)) {
            assertTrue(reopened.readChunkRaw(1, 2).external());
            assertEquals(1200 * 1024, reopened.readChunk(1, 2).getByteArray("filler").length);
        }

        // 小さく書き直すと内部へ戻り、外部ファイルは消える
        try (RegionFile region = RegionFile.open(path, RegionFileMode.READ_WRITE)) {
            region.writeChunk(1, 2, sampleChunk(1, 2));
            region.flush();
        }

        assertFalse(Files.exists(external), "内部へ戻ったのに外部ファイルが残っている");

        try (RegionFile finalRegion = RegionFile.open(path)) {
            assertFalse(finalRegion.readChunkRaw(1, 2).external());
        }
    }

    @Test
    void timestampCanBeSetExplicitly() {
        Path path = work.resolve("r.0.0.mca");

        try (RegionFile region = RegionFile.open(path, RegionFileMode.READ_WRITE)) {
            region.writeChunk(0, 0, sampleChunk(0, 0));
            region.setTimestamp(0, 0, 1234567890);
            region.flush();
        }

        try (RegionFile reopened = RegionFile.open(path)) {
            assertEquals(1234567890, reopened.timestamp(0, 0));
        }
    }

    // -- RegionFolder -------------------------------------------------------

    @Test
    void folderResolvesChunksAcrossRegions() {
        try (RegionFolder folder = RegionFolder.open(work, RegionFileMode.READ_WRITE)) {
            folder.writeChunk(0, 0, sampleChunk(0, 0));
            folder.writeChunk(-1, -1, sampleChunk(-1, -1));
            folder.writeChunk(40, 40, sampleChunk(40, 40));
            folder.flush();
        }

        // 3 つの異なるリージョンへ振り分けられる
        assertTrue(Files.exists(work.resolve("r.0.0.mca")));
        assertTrue(Files.exists(work.resolve("r.-1.-1.mca")));
        assertTrue(Files.exists(work.resolve("r.1.1.mca")));

        try (RegionFolder reopened = RegionFolder.open(work)) {
            assertEquals(3, reopened.regionPositions().size());
            assertEquals(3, reopened.chunkPositions().size());
            assertEquals(-1, reopened.readChunk(-1, -1).getInt("xPos"));
            assertNull(reopened.readChunk(100, 100));
            assertFalse(reopened.hasChunk(100, 100));
        }
    }
}

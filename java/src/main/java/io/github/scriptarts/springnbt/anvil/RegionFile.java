package io.github.scriptarts.springnbt.anvil;

import io.github.scriptarts.springnbt.ErrorCode;
import io.github.scriptarts.springnbt.SpringNbtException;
import io.github.scriptarts.springnbt.nbt.Compression;
import io.github.scriptarts.springnbt.nbt.NamedTag;
import io.github.scriptarts.springnbt.nbt.NbtCompound;
import io.github.scriptarts.springnbt.nbt.NbtIo;
import io.github.scriptarts.springnbt.nbt.NbtReadOptions;
import io.github.scriptarts.springnbt.nbt.NbtWriteOptions;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.zip.Deflater;
import java.util.zip.DeflaterOutputStream;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;
import java.util.zip.InflaterInputStream;

/**
 * Anvil のリージョンファイル ({@code r.X.Z.mca})。32×32 チャンクを格納する。
 *
 * <p>ファイル全体をメモリに読み込んで扱う。実データのリージョンは数 MB 程度で、
 * この方が「触っていないチャンクのバイト配置をそのまま保つ」ことを保証しやすい。
 * 開いて何も変えずに {@link #flush()} すると、バイト単位で元と同じファイルになる。
 *
 * <p>仕様: {@code docs/spec/20-anvil-region.md}
 */
public final class RegionFile implements AutoCloseable {

    /** セクタ長。 */
    public static final int SECTOR_SIZE = 4096;

    /** ロケーションテーブルとタイムスタンプテーブルが占めるセクタ数。 */
    private static final int HEADER_SECTORS = 2;

    /** 1リージョンに入るチャンク数。 */
    private static final int CHUNK_COUNT = 1024;

    /** 1チャンクが確保できるセクタ数の上限（長さフィールドが u8 のため）。 */
    private static final int MAX_SECTORS = 255;

    /** リージョン内に収められるペイロードの上限。超えると外部ファイルへ退避する。 */
    private static final int MAX_INLINE_PAYLOAD = (MAX_SECTORS * SECTOR_SIZE) - 5;

    private final Path path;
    private final Path directory;
    private final RegionFileMode mode;
    private final int regionX;
    private final int regionZ;
    private final int[] offsets = new int[CHUNK_COUNT];
    private final int[] sectorCounts = new int[CHUNK_COUNT];
    private final int[] timestamps = new int[CHUNK_COUNT];

    private byte[] data;
    private boolean dirty;
    private boolean closed;

    private RegionFile(Path path, RegionFileMode mode, RegionPos position, byte[] data) {
        this.path = path;
        this.mode = mode;
        this.data = data;
        this.regionX = position.x();
        this.regionZ = position.z();

        Path parent = path.getParent();
        if (parent == null) {
            this.directory = Path.of(".");
        } else {
            this.directory = parent;
        }

        parseHeader();
    }

    /**
     * このリージョンのX座標。
     *
     * @return 座標
     */
    public int regionX() {
        return regionX;
    }

    /**
     * このリージョンのZ座標。
     *
     * @return 座標
     */
    public int regionZ() {
        return regionZ;
    }

    /**
     * リージョンファイルを開く。
     *
     * @param path {@code r.X.Z.mca} という名前のファイル。座標はファイル名から読み取る
     * @param mode 読み取り専用か読み書きか
     * @return 開いたリージョン
     * @throws SpringNbtException ファイル名から座標を読み取れない、または読み込みに失敗した場合
     */
    public static RegionFile open(Path path, RegionFileMode mode) {
        Objects.requireNonNull(path, "path");
        RegionPos position = RegionPos.fromFileName(path.getFileName().toString());

        if (position == null) {
            throw SpringNbtException.invalidArgument(
                    "リージョンファイル名として解釈できない: " + path.getFileName());
        }

        byte[] raw;

        if (Files.exists(path)) {
            try {
                raw = Files.readAllBytes(path);
            } catch (IOException error) {
                throw new SpringNbtException(ErrorCode.IO, "ファイルを読めない: " + path, error);
            }
        } else if (mode == RegionFileMode.READ_WRITE) {
            // 読み書きモードなら、存在しないファイルは空のリージョンとして扱う
            raw = new byte[HEADER_SECTORS * SECTOR_SIZE];
        } else {
            throw new SpringNbtException(ErrorCode.IO, "ファイルが存在しない: " + path);
        }

        return new RegionFile(path, mode, position, raw);
    }

    /**
     * 読み取り専用でリージョンファイルを開く。
     *
     * @param path ファイルパス
     * @return 開いたリージョン
     */
    public static RegionFile open(Path path) {
        return open(path, RegionFileMode.READ_ONLY);
    }

    /** ヘッダを解析し、ロケーションとタイムスタンプを取り込む。 */
    private void parseHeader() {
        // 空ファイルは「チャンクが 1 つも無いリージョン」として受け入れる
        if (data.length == 0) {
            data = new byte[HEADER_SECTORS * SECTOR_SIZE];
            return;
        }

        if (data.length < HEADER_SECTORS * SECTOR_SIZE) {
            throw SpringNbtException.malformed("ヘッダが足りない: " + data.length + " バイト（最低 "
                    + (HEADER_SECTORS * SECTOR_SIZE) + " バイト必要）");
        }

        if (data.length % SECTOR_SIZE != 0) {
            throw SpringNbtException.malformed(
                    "ファイル長がセクタ境界に揃っていない: " + data.length + " バイト");
        }

        int totalSectors = data.length / SECTOR_SIZE;
        Map<Integer, Integer> sectorOwner = new HashMap<>();

        // ロケーションテーブルの 1024 エントリを順に取り込む
        for (int index = 0; index < CHUNK_COUNT; index++) {
            long entry = readUnsigned(index * 4, 4);
            int offset = (int) (entry >>> 8);
            int count = (int) (entry & 0xFF);

            timestamps[index] = (int) readUnsigned(SECTOR_SIZE + (index * 4), 4);

            if (offset == 0 && count == 0) {
                continue;
            }

            if (offset < HEADER_SECTORS) {
                throw SpringNbtException.malformed(
                        "チャンク " + index + " のオフセットがヘッダ領域を指している: " + offset);
            }

            if (count == 0) {
                throw SpringNbtException.malformed(
                        "チャンク " + index + " のセクタ数が 0 なのにオフセットが設定されている");
            }

            if (offset + count > totalSectors) {
                throw SpringNbtException.malformed(
                        "チャンク " + index + " の割り当てがファイル外へはみ出している");
            }

            // 同じセクタを 2 つのチャンクが指していたら、どちらかが壊れている
            for (int sector = offset; sector < offset + count; sector++) {
                Integer owner = sectorOwner.put(sector, index);

                if (owner != null) {
                    throw SpringNbtException.malformed("セクタ " + sector + " がチャンク " + owner
                            + " とチャンク " + index + " で重複している");
                }
            }

            offsets[index] = offset;
            sectorCounts[index] = count;
        }
    }

    /** 指定した座標がこのリージョンの担当範囲にあるか確認し、添字を返す。 */
    private int indexOf(int chunkX, int chunkZ) {
        ChunkPos position = new ChunkPos(chunkX, chunkZ);
        RegionPos region = position.region();

        if (region.x() != regionX || region.z() != regionZ) {
            throw SpringNbtException.invalidArgument("チャンク (" + chunkX + ", " + chunkZ
                    + ") はリージョン (" + regionX + ", " + regionZ + ") の担当外");
        }

        return position.index();
    }

    private void ensureWritable() {
        if (mode == RegionFileMode.READ_ONLY) {
            throw SpringNbtException.invalidArgument("読み取り専用で開いたリージョンには書き込めない");
        }
    }

    private void ensureOpen() {
        if (closed) {
            throw SpringNbtException.invalidArgument("既に閉じられたリージョンファイル");
        }
    }

    /**
     * チャンクが存在するか。
     *
     * @param chunkX 絶対チャンクX座標
     * @param chunkZ 絶対チャンクZ座標
     * @return 存在すれば true
     */
    public boolean hasChunk(int chunkX, int chunkZ) {
        ensureOpen();
        return sectorCounts[indexOf(chunkX, chunkZ)] > 0;
    }

    /**
     * 存在するチャンクの座標を、ロケーションテーブルの並び順で返す。
     *
     * @return チャンク座標の一覧
     */
    public List<ChunkPos> chunkPositions() {
        ensureOpen();
        List<ChunkPos> result = new ArrayList<>();

        // 添字の昇順に走査する（localZ が外、localX が内）
        for (int index = 0; index < CHUNK_COUNT; index++) {
            if (sectorCounts[index] == 0) {
                continue;
            }

            int localX = index % 32;
            int localZ = index / 32;
            result.add(new ChunkPos((regionX * 32) + localX, (regionZ * 32) + localZ));
        }

        return result;
    }

    /**
     * チャンクの最終更新時刻（Unix 秒）。存在しなければ 0。
     *
     * @param chunkX 絶対チャンクX座標
     * @param chunkZ 絶対チャンクZ座標
     * @return 時刻
     */
    public int timestamp(int chunkX, int chunkZ) {
        ensureOpen();
        return timestamps[indexOf(chunkX, chunkZ)];
    }

    /**
     * チャンクの最終更新時刻を設定する。
     *
     * @param chunkX 絶対チャンクX座標
     * @param chunkZ 絶対チャンクZ座標
     * @param value  時刻
     */
    public void setTimestamp(int chunkX, int chunkZ, int value) {
        ensureOpen();
        ensureWritable();
        timestamps[indexOf(chunkX, chunkZ)] = value;
        dirty = true;
    }

    /**
     * チャンクを圧縮されたまま取り出す。
     *
     * @param chunkX 絶対チャンクX座標
     * @param chunkZ 絶対チャンクZ座標
     * @return チャンク。存在しなければ null
     */
    public RawChunk readChunkRaw(int chunkX, int chunkZ) {
        ensureOpen();
        int index = indexOf(chunkX, chunkZ);

        if (sectorCounts[index] == 0) {
            return null;
        }

        int start = offsets[index] * SECTOR_SIZE;
        int length = (int) readUnsigned(start, 4);
        int schemeByte = data[start + 4] & 0xFF;

        if (length < 1) {
            throw SpringNbtException.malformed(
                    "チャンク (" + chunkX + ", " + chunkZ + ") の length が不正: " + length);
        }

        if (4 + length > sectorCounts[index] * SECTOR_SIZE) {
            throw SpringNbtException.malformed("チャンク (" + chunkX + ", " + chunkZ
                    + ") の length が確保セクタ数を超えている");
        }

        boolean external = (schemeByte & 0x80) != 0;
        ChunkCompression compression = ChunkCompression.fromId(schemeByte & 0x7F);

        if (external) {
            // 最上位ビットが立っている場合、本体は c.X.Z.mcc にある
            return new RawChunk(compression, readExternalFile(chunkX, chunkZ), true);
        }

        byte[] body = Arrays.copyOfRange(data, start + 5, start + 4 + length);
        return new RawChunk(compression, body, false);
    }

    /**
     * チャンクを NBT として読む。
     *
     * @param chunkX 絶対チャンクX座標
     * @param chunkZ 絶対チャンクZ座標
     * @return チャンク。存在しなければ null
     */
    public NbtCompound readChunk(int chunkX, int chunkZ) {
        RawChunk raw = readChunkRaw(chunkX, chunkZ);

        if (raw == null) {
            return null;
        }

        byte[] plain = ChunkCodec.decompress(raw);
        NbtReadOptions options = NbtReadOptions.defaults().setCompression(Compression.NONE);
        return NbtIo.readBytes(plain, options).tag();
    }

    /**
     * チャンクを NBT として書き込む。圧縮方式は Zlib。
     *
     * @param chunkX 絶対チャンクX座標
     * @param chunkZ 絶対チャンクZ座標
     * @param tag    書き込む内容
     */
    public void writeChunk(int chunkX, int chunkZ, NbtCompound tag) {
        writeChunk(chunkX, chunkZ, tag, ChunkCompression.ZLIB);
    }

    /**
     * チャンクを NBT として、圧縮方式を指定して書き込む。
     *
     * @param chunkX      絶対チャンクX座標
     * @param chunkZ      絶対チャンクZ座標
     * @param tag         書き込む内容
     * @param compression 圧縮方式
     */
    public void writeChunk(int chunkX, int chunkZ, NbtCompound tag, ChunkCompression compression) {
        Objects.requireNonNull(tag, "tag");
        NbtWriteOptions options = NbtWriteOptions.defaults().setCompression(Compression.NONE);
        byte[] plain = NbtIo.writeBytes(new NamedTag("", tag), options);
        writeChunkRaw(chunkX, chunkZ,
                new RawChunk(compression, ChunkCodec.compress(plain, compression)));
    }

    /**
     * 圧縮済みのチャンクをそのまま書き込む。
     *
     * @param chunkX 絶対チャンクX座標
     * @param chunkZ 絶対チャンクZ座標
     * @param raw    書き込む内容
     */
    public void writeChunkRaw(int chunkX, int chunkZ, RawChunk raw) {
        Objects.requireNonNull(raw, "raw");
        ensureOpen();
        ensureWritable();

        int index = indexOf(chunkX, chunkZ);
        boolean useExternal = raw.data().length > MAX_INLINE_PAYLOAD;

        byte[] payload;
        int schemeByte;

        if (useExternal) {
            // 1MiB を超えるチャンクは外部ファイルへ退避し、リージョンには目印だけ残す
            writeExternalFile(chunkX, chunkZ, raw.data());
            payload = new byte[0];
            schemeByte = raw.compression().id() | 0x80;
        } else {
            deleteExternalFile(chunkX, chunkZ);
            payload = raw.data();
            schemeByte = raw.compression().id();
        }

        int totalLength = 4 + 1 + payload.length;
        int needed = (totalLength + SECTOR_SIZE - 1) / SECTOR_SIZE;

        if (needed > MAX_SECTORS) {
            throw SpringNbtException.invalidArgument(
                    "チャンクが大きすぎる: " + needed + " セクタ（上限 " + MAX_SECTORS + "）");
        }

        int start = allocateSectors(index, needed);

        // 確保した領域をゼロで埋めてから書く（前の内容を残さないため）
        Arrays.fill(data, start * SECTOR_SIZE, (start + needed) * SECTOR_SIZE, (byte) 0);

        int position = start * SECTOR_SIZE;
        writeUnsigned(position, 1 + payload.length, 4);
        data[position + 4] = (byte) schemeByte;
        System.arraycopy(payload, 0, data, position + 5, payload.length);

        offsets[index] = start;
        sectorCounts[index] = needed;
        timestamps[index] = (int) Instant.now().getEpochSecond();
        dirty = true;
    }

    /**
     * チャンクを削除する。
     *
     * @param chunkX 絶対チャンクX座標
     * @param chunkZ 絶対チャンクZ座標
     * @return 削除できたら true
     */
    public boolean deleteChunk(int chunkX, int chunkZ) {
        ensureOpen();
        ensureWritable();

        int index = indexOf(chunkX, chunkZ);

        if (sectorCounts[index] == 0) {
            return false;
        }

        deleteExternalFile(chunkX, chunkZ);
        offsets[index] = 0;
        sectorCounts[index] = 0;
        timestamps[index] = 0;
        dirty = true;
        return true;
    }

    /**
     * 必要なセクタ数を確保し、開始セクタ番号を返す。
     *
     * <p>既存の割り当てがちょうど同じ大きさならその場を使い、
     * そうでなければ先頭から空き領域を探し、無ければ末尾へ追加する。
     */
    private int allocateSectors(int index, int needed) {
        // 大きさが変わらないなら動かさない。触っていないチャンクの配置を保つため
        if (sectorCounts[index] == needed) {
            return offsets[index];
        }

        boolean[] used = buildSectorUsage(index);
        int totalSectors = data.length / SECTOR_SIZE;
        int run = 0;

        // 先頭から連続した空き領域を探す
        for (int sector = HEADER_SECTORS; sector < totalSectors; sector++) {
            if (used[sector]) {
                run = 0;
                continue;
            }

            run += 1;

            if (run == needed) {
                return sector - needed + 1;
            }
        }

        // 見つからなければ末尾へ追加する。末尾の空きは再利用できる
        int start = totalSectors - run;
        data = Arrays.copyOf(data, (start + needed) * SECTOR_SIZE);
        return start;
    }

    /** セクタの使用状況を作る。{@code ignoreIndex} のチャンクは空きとして扱う。 */
    private boolean[] buildSectorUsage(int ignoreIndex) {
        int totalSectors = data.length / SECTOR_SIZE;
        boolean[] used = new boolean[totalSectors];

        // ヘッダの 2 セクタは常に使用中
        for (int sector = 0; sector < HEADER_SECTORS && sector < totalSectors; sector++) {
            used[sector] = true;
        }

        // 他のチャンクが占めているセクタに印を付ける
        for (int other = 0; other < CHUNK_COUNT; other++) {
            if (other == ignoreIndex || sectorCounts[other] == 0) {
                continue;
            }

            for (int sector = offsets[other]; sector < offsets[other] + sectorCounts[other]; sector++) {
                if (sector < totalSectors) {
                    used[sector] = true;
                }
            }
        }

        return used;
    }

    /** 全チャンクを隙間なく詰め直す。断片化したファイルを縮めたいときに使う。 */
    public void optimize() {
        ensureOpen();
        ensureWritable();

        List<int[]> indices = new ArrayList<>();
        List<RawChunk> chunks = new ArrayList<>();

        // 先に全チャンクを取り出してから、新しい配置で書き直す
        for (int index = 0; index < CHUNK_COUNT; index++) {
            if (sectorCounts[index] == 0) {
                continue;
            }

            int localX = index % 32;
            int localZ = index / 32;
            RawChunk raw = readChunkRaw((regionX * 32) + localX, (regionZ * 32) + localZ);

            if (raw != null) {
                indices.add(new int[] { index });
                chunks.add(raw);
            }
        }

        int[] savedTimestamps = timestamps.clone();
        data = new byte[HEADER_SECTORS * SECTOR_SIZE];
        Arrays.fill(offsets, 0);
        Arrays.fill(sectorCounts, 0);

        int nextSector = HEADER_SECTORS;

        // 添字の昇順に、先頭から詰めて配置する
        for (int position = 0; position < chunks.size(); position++) {
            int index = indices.get(position)[0];
            RawChunk raw = chunks.get(position);

            byte[] payload;
            int schemeByte;

            if (raw.external()) {
                payload = new byte[0];
                schemeByte = raw.compression().id() | 0x80;
            } else {
                payload = raw.data();
                schemeByte = raw.compression().id();
            }

            int needed = (4 + 1 + payload.length + SECTOR_SIZE - 1) / SECTOR_SIZE;
            data = Arrays.copyOf(data, (nextSector + needed) * SECTOR_SIZE);

            int offset = nextSector * SECTOR_SIZE;
            writeUnsigned(offset, 1 + payload.length, 4);
            data[offset + 4] = (byte) schemeByte;
            System.arraycopy(payload, 0, data, offset + 5, payload.length);

            offsets[index] = nextSector;
            sectorCounts[index] = needed;
            nextSector += needed;
        }

        System.arraycopy(savedTimestamps, 0, timestamps, 0, CHUNK_COUNT);
        dirty = true;
    }

    /** 変更をファイルへ書き出す。 */
    public void flush() {
        ensureOpen();

        if (mode == RegionFileMode.READ_ONLY) {
            return;
        }

        writeHeader();

        try {
            Files.write(path, data);
        } catch (IOException error) {
            throw new SpringNbtException(ErrorCode.IO, "ファイルへ書けない: " + path, error);
        }

        dirty = false;
    }

    /**
     * 現在の内容をバイト列として組み立てる。ファイルには書かない。
     *
     * @return バイト列
     */
    public byte[] toBytes() {
        ensureOpen();
        writeHeader();
        return data.clone();
    }

    /** ロケーションテーブルとタイムスタンプテーブルを先頭 2 セクタへ書き戻す。 */
    private void writeHeader() {
        for (int index = 0; index < CHUNK_COUNT; index++) {
            long entry = ((long) offsets[index] << 8) | (long) sectorCounts[index];
            writeUnsigned(index * 4, entry, 4);
            writeUnsigned(SECTOR_SIZE + (index * 4), timestamps[index] & 0xFFFFFFFFL, 4);
        }
    }

    /** 変更があれば書き出してから閉じる。 */
    @Override
    public void close() {
        if (closed) {
            return;
        }

        if (dirty && mode == RegionFileMode.READ_WRITE) {
            flush();
        }

        closed = true;
    }

    // -- バイト操作 ---------------------------------------------------------

    /** 指定位置からビッグエンディアンで読む。 */
    private long readUnsigned(int position, int count) {
        long value = 0;

        // 上位バイトから順に積み上げる
        for (int offset = 0; offset < count; offset++) {
            value = (value << 8) | (data[position + offset] & 0xFFL);
        }

        return value;
    }

    /** 指定位置へビッグエンディアンで書く。 */
    private void writeUnsigned(int position, long value, int count) {
        // 上位バイトから順に取り出す
        for (int offset = 0; offset < count; offset++) {
            data[position + offset] = (byte) ((value >>> ((count - 1 - offset) * 8)) & 0xFF);
        }
    }

    // -- 外部ファイル (.mcc) ------------------------------------------------

    private Path externalPath(int chunkX, int chunkZ) {
        return directory.resolve("c." + chunkX + "." + chunkZ + ".mcc");
    }

    private byte[] readExternalFile(int chunkX, int chunkZ) {
        Path external = externalPath(chunkX, chunkZ);

        try {
            return Files.readAllBytes(external);
        } catch (NoSuchFileException error) {
            throw new SpringNbtException(
                    ErrorCode.MALFORMED_DATA, "外部チャンクファイルが無い: " + external, error);
        } catch (IOException error) {
            throw new SpringNbtException(
                    ErrorCode.IO, "外部チャンクファイルを読めない: " + external, error);
        }
    }

    private void writeExternalFile(int chunkX, int chunkZ, byte[] payload) {
        Path external = externalPath(chunkX, chunkZ);

        try {
            Files.write(external, payload);
        } catch (IOException error) {
            throw new SpringNbtException(
                    ErrorCode.IO, "外部チャンクファイルへ書けない: " + external, error);
        }
    }

    private void deleteExternalFile(int chunkX, int chunkZ) {
        Path external = externalPath(chunkX, chunkZ);

        // 縮んで内部へ戻ったチャンクの残骸を消す
        try {
            Files.deleteIfExists(external);
        } catch (IOException error) {
            throw new SpringNbtException(
                    ErrorCode.IO, "外部チャンクファイルを削除できない: " + external, error);
        }
    }
}

/** チャンクのペイロードを圧縮方式IDに従って展開・圧縮する。 */
final class ChunkCodec {

    private ChunkCodec() {
        // ユーティリティクラス
    }

    /** 圧縮済みペイロードを展開する。 */
    static byte[] decompress(RawChunk raw) {
        return switch (raw.compression()) {
            case NONE -> raw.data();
            case GZIP, ZLIB -> inflate(raw.data(), raw.compression());
            case LZ4 -> throw SpringNbtException.unsupportedFeature(
                    "LZ4 圧縮のチャンクは扱えない。生バイトAPI (readChunkRaw) を使うこと");
            case CUSTOM -> throw SpringNbtException.unsupportedFeature(
                    "カスタム圧縮のチャンクは扱えない。生バイトAPI (readChunkRaw) を使うこと");
        };
    }

    /** ペイロードを指定の方式で圧縮する。 */
    static byte[] compress(byte[] plain, ChunkCompression compression) {
        if (compression == ChunkCompression.NONE) {
            return plain;
        }

        if (compression != ChunkCompression.GZIP && compression != ChunkCompression.ZLIB) {
            throw SpringNbtException.unsupportedFeature(
                    "この圧縮方式では書き込めない: " + compression.asString());
        }

        try (ByteArrayOutputStream destination = new ByteArrayOutputStream()) {
            // ストリームを閉じてフッタを書かせてから toByteArray する必要がある
            try (OutputStream encoder = createEncoder(destination, compression)) {
                encoder.write(plain);
            }

            return destination.toByteArray();
        } catch (IOException error) {
            throw new SpringNbtException(ErrorCode.IO, "チャンクを圧縮できない", error);
        }
    }

    private static byte[] inflate(byte[] payload, ChunkCompression compression) {
        try (InputStream source = new ByteArrayInputStream(payload);
             InputStream decoder = createDecoder(source, compression);
             ByteArrayOutputStream destination = new ByteArrayOutputStream()) {
            decoder.transferTo(destination);
            return destination.toByteArray();
        } catch (IOException error) {
            throw new SpringNbtException(
                    ErrorCode.MALFORMED_DATA, "チャンクの圧縮データを展開できない", error);
        }
    }

    private static InputStream createDecoder(InputStream source, ChunkCompression compression)
            throws IOException {
        if (compression == ChunkCompression.GZIP) {
            return new GZIPInputStream(source);
        }

        return new InflaterInputStream(source);
    }

    private static OutputStream createEncoder(OutputStream destination, ChunkCompression compression)
            throws IOException {
        if (compression == ChunkCompression.GZIP) {
            return new GZIPOutputStream(destination);
        }

        return new DeflaterOutputStream(destination, new Deflater(Deflater.BEST_COMPRESSION));
    }
}

package io.github.scriptarts.springnbt.anvil;

import io.github.scriptarts.springnbt.ErrorCode;
import io.github.scriptarts.springnbt.SpringNbtException;
import io.github.scriptarts.springnbt.nbt.NbtCompound;
import java.io.IOException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * リージョンファイルが並ぶディレクトリ 1 つ分
 * （{@code region/}、{@code entities/}、{@code poi/} のいずれか）。
 *
 * <p>開いたリージョンファイルはキャッシュし、{@link #close()} でまとめて閉じる。
 * チャンク座標からリージョンを解決するので、利用側はリージョンの存在を意識しなくてよい。
 *
 * <p>仕様: {@code docs/spec/20-anvil-region.md} 5章
 */
public final class RegionFolder implements AutoCloseable {

    private final Map<RegionPos, RegionFile> cache = new HashMap<>();
    private final Path directory;
    private final RegionFileMode mode;
    private boolean closed;

    private RegionFolder(Path directory, RegionFileMode mode) {
        this.directory = directory;
        this.mode = mode;
    }

    /**
     * このフォルダのパス。
     *
     * @return パス
     */
    public Path directory() {
        return directory;
    }

    /**
     * リージョンフォルダを開く。
     *
     * @param directory ディレクトリ
     * @param mode      読み取り専用か読み書きか
     * @return 開いたフォルダ
     * @throws SpringNbtException 読み取り専用でディレクトリが存在しない場合
     */
    public static RegionFolder open(Path directory, RegionFileMode mode) {
        Objects.requireNonNull(directory, "directory");

        if (!Files.isDirectory(directory) && mode == RegionFileMode.READ_ONLY) {
            throw new SpringNbtException(
                    ErrorCode.IO, "リージョンフォルダが存在しない: " + directory);
        }

        return new RegionFolder(directory, mode);
    }

    /**
     * 読み取り専用でリージョンフォルダを開く。
     *
     * @param directory ディレクトリ
     * @return 開いたフォルダ
     */
    public static RegionFolder open(Path directory) {
        return open(directory, RegionFileMode.READ_ONLY);
    }

    /**
     * このフォルダに存在するリージョンの座標を返す。
     *
     * @return リージョン座標の一覧
     */
    public List<RegionPos> regionPositions() {
        ensureOpen();
        List<RegionPos> found = new ArrayList<>();

        if (!Files.isDirectory(directory)) {
            return found;
        }

        try (DirectoryStream<Path> stream = Files.newDirectoryStream(directory, "r.*.mca")) {
            // r.X.Z.mca として解釈できるファイルだけを拾う
            for (Path path : stream) {
                RegionPos position = RegionPos.fromFileName(path.getFileName().toString());

                if (position != null) {
                    found.add(position);
                }
            }
        } catch (IOException error) {
            throw new SpringNbtException(
                    ErrorCode.IO, "リージョンフォルダを走査できない: " + directory, error);
        }

        // 走査順がファイルシステム依存にならないよう、座標で並べる
        found.sort(Comparator.comparingInt(RegionPos::z).thenComparingInt(RegionPos::x));
        return found;
    }

    /**
     * リージョンファイルを取得する。
     *
     * @param regionX リージョンX座標
     * @param regionZ リージョンZ座標
     * @return リージョン。読み取り専用で存在しなければ null
     */
    public RegionFile region(int regionX, int regionZ) {
        ensureOpen();
        RegionPos position = new RegionPos(regionX, regionZ);
        RegionFile cached = cache.get(position);

        if (cached != null) {
            return cached;
        }

        Path path = directory.resolve(position.fileName());

        // 読み取り専用では、存在しないリージョンは「チャンクが無い」として null を返す
        if (!Files.exists(path) && mode == RegionFileMode.READ_ONLY) {
            return null;
        }

        RegionFile opened = RegionFile.open(path, mode);
        cache.put(position, opened);
        return opened;
    }

    /**
     * チャンクが存在するか。
     *
     * @param chunkX 絶対チャンクX座標
     * @param chunkZ 絶対チャンクZ座標
     * @return 存在すれば true
     */
    public boolean hasChunk(int chunkX, int chunkZ) {
        RegionFile file = regionFor(chunkX, chunkZ);

        if (file == null) {
            return false;
        }

        return file.hasChunk(chunkX, chunkZ);
    }

    /**
     * チャンクを NBT として読む。
     *
     * @param chunkX 絶対チャンクX座標
     * @param chunkZ 絶対チャンクZ座標
     * @return チャンク。存在しなければ null
     */
    public NbtCompound readChunk(int chunkX, int chunkZ) {
        RegionFile file = regionFor(chunkX, chunkZ);

        if (file == null) {
            return null;
        }

        return file.readChunk(chunkX, chunkZ);
    }

    /**
     * チャンクを NBT として書き込む。
     *
     * @param chunkX 絶対チャンクX座標
     * @param chunkZ 絶対チャンクZ座標
     * @param tag    書き込む内容
     */
    public void writeChunk(int chunkX, int chunkZ, NbtCompound tag) {
        RegionFile file = regionFor(chunkX, chunkZ);

        if (file == null) {
            throw SpringNbtException.invalidArgument(
                    "読み取り専用のフォルダには書き込めない: " + directory);
        }

        file.writeChunk(chunkX, chunkZ, tag);
    }

    /**
     * チャンクを削除する。
     *
     * @param chunkX 絶対チャンクX座標
     * @param chunkZ 絶対チャンクZ座標
     * @return 削除できたら true
     */
    public boolean deleteChunk(int chunkX, int chunkZ) {
        RegionFile file = regionFor(chunkX, chunkZ);

        if (file == null) {
            return false;
        }

        return file.deleteChunk(chunkX, chunkZ);
    }

    /**
     * このフォルダに存在する全チャンクの座標を返す。
     *
     * @return チャンク座標の一覧
     */
    public List<ChunkPos> chunkPositions() {
        List<ChunkPos> result = new ArrayList<>();

        // リージョンごとに、その中のチャンクを順に集める
        for (RegionPos position : regionPositions()) {
            RegionFile file = region(position.x(), position.z());

            if (file == null) {
                continue;
            }

            result.addAll(file.chunkPositions());
        }

        return result;
    }

    /** 開いている全リージョンの変更を書き出す。 */
    public void flush() {
        ensureOpen();

        for (RegionFile file : cache.values()) {
            file.flush();
        }
    }

    /** 開いている全リージョンを閉じる。 */
    @Override
    public void close() {
        if (closed) {
            return;
        }

        for (RegionFile file : cache.values()) {
            file.close();
        }

        cache.clear();
        closed = true;
    }

    private RegionFile regionFor(int chunkX, int chunkZ) {
        RegionPos position = new ChunkPos(chunkX, chunkZ).region();
        return region(position.x(), position.z());
    }

    private void ensureOpen() {
        if (closed) {
            throw SpringNbtException.invalidArgument("既に閉じられたリージョンフォルダ");
        }
    }
}

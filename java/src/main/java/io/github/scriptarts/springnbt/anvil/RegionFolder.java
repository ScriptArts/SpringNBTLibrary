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
import java.util.LinkedList;
import java.util.Objects;

/**
 * リージョンファイルが並ぶディレクトリ 1 つ分
 * （{@code region/}、{@code entities/}、{@code poi/} のいずれか）
 *
 * <p>開いたリージョンファイルはキャッシュし、{@link #close()} でまとめて閉じる
 * チャンク座標からリージョンを解決するので、利用側はリージョンの存在を意識しなくてよい
 *
 * <p>{@link RegionFile} はファイル全体をメモリへ載せるため、キャッシュには
 * {@link #maxCachedRegions()} 件の上限がある
 * 上限を超えると、最も長く使われていない
 * ものから書き出して閉じる
 * 大きなワールドを端から走査してもメモリを使い切らない
 *
 * <p>このため {@link #region(int, int)} が返した参照は、
 * <b>別のリージョンへアクセスすると閉じられている場合がある</b>
 * 参照を保持せず、必要なたびに取得すること
 *
 * <p>仕様: {@code docs/spec/20-anvil-region.md} 5章
 */
public final class RegionFolder implements AutoCloseable {

    /**
     * 同時に開いておくリージョンファイル数の既定の上限
     *
     * <p>1 リージョンは最大 255 セクタ × 1024 チャンク＝理論上 1GiB になりうる
     * 実データでは数 MB から数十 MB 程度
     * 8 件なら通常のワールドで数百 MB に収まる
     */
    public static final int DEFAULT_MAX_CACHED_REGIONS = 8;

    private final Map<RegionPos, RegionFile> cache = new HashMap<>();

    /**
     * 最近使った順のリージョン座標
     * 末尾がいちばん新しい
     */
    private final LinkedList<RegionPos> recentlyUsed = new LinkedList<>();

    private final Path directory;
    private final RegionFileMode mode;
    private final int maxCachedRegions;
    private boolean closed;

    private RegionFolder(Path directory, RegionFileMode mode, int maxCachedRegions) {
        this.directory = directory;
        this.mode = mode;
        this.maxCachedRegions = maxCachedRegions;
    }

    /**
     * 同時に開いておくリージョンファイル数の上限
     *
     * @return 上限
     */
    public int maxCachedRegions() {
        return maxCachedRegions;
    }

    /**
     * いま開いているリージョンファイル数
     *
     * @return 件数
     */
    public int cachedRegionCount() {
        return cache.size();
    }

    /**
     * このフォルダのパス
     *
     * @return パス
     */
    public Path directory() {
        return directory;
    }

    /**
     * リージョンフォルダを開く
     *
     * @param directory ディレクトリ
     * @param mode      読み取り専用か読み書きか
     * @return 開いたフォルダ
     * @throws SpringNbtException 読み取り専用でディレクトリが存在しない場合
     */
    public static RegionFolder open(Path directory, RegionFileMode mode) {
        return open(directory, mode, DEFAULT_MAX_CACHED_REGIONS);
    }

    /**
     * 上限を指定してリージョンフォルダを開く
     *
     * @param directory        ディレクトリ
     * @param mode             読み取り専用か読み書きか
     * @param maxCachedRegions 同時に開いておくリージョンファイル数の上限
     * @return 開いたフォルダ
     * @throws SpringNbtException 読み取り専用でディレクトリが存在しない場合、
     *                            または上限が 1 未満の場合
     */
    public static RegionFolder open(Path directory, RegionFileMode mode, int maxCachedRegions) {
        Objects.requireNonNull(directory, "directory");

        if (maxCachedRegions < 1) {
            throw SpringNbtException.invalidArgument(
                    "maxCachedRegions は 1 以上でなければならない: " + maxCachedRegions);
        }

        if (!Files.isDirectory(directory) && mode == RegionFileMode.READ_ONLY) {
            throw new SpringNbtException(
                    ErrorCode.IO, "リージョンフォルダが存在しない: " + directory);
        }

        return new RegionFolder(directory, mode, maxCachedRegions);
    }

    /**
     * 読み取り専用でリージョンフォルダを開く
     *
     * @param directory ディレクトリ
     * @return 開いたフォルダ
     */
    public static RegionFolder open(Path directory) {
        return open(directory, RegionFileMode.READ_ONLY);
    }

    /**
     * このフォルダに存在するリージョンの座標を返す
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
     * リージョンファイルを取得する
     *
     * @param regionX リージョンX座標
     * @param regionZ リージョンZ座標
     * @return リージョン
     * 読み取り専用で存在しなければ null
     */
    public RegionFile region(int regionX, int regionZ) {
        ensureOpen();
        RegionPos position = new RegionPos(regionX, regionZ);
        RegionFile cached = cache.get(position);

        if (cached != null) {
            touch(position);
            return cached;
        }

        Path path = directory.resolve(position.fileName());

        // 読み取り専用では、存在しないリージョンは「チャンクが無い」として null を返す
        if (!Files.exists(path) && mode == RegionFileMode.READ_ONLY) {
            return null;
        }

        // 開く前に空きを作る
        // 開いてからだと一瞬だけ上限を超える
        evictUntilBelowLimit();

        RegionFile opened = RegionFile.open(path, mode);
        cache.put(position, opened);
        touch(position);
        return opened;
    }

    /** 使ったリージョンを、最近使った列の末尾へ移す */
    private void touch(RegionPos position) {
        recentlyUsed.remove(position);
        recentlyUsed.addLast(position);
    }

    /** 新しく 1 件開けるよう、上限を下回るまで古いものを閉じる */
    private void evictUntilBelowLimit() {
        // 上限に達している間、いちばん長く使っていないものから閉じる
        while (cache.size() >= maxCachedRegions && !recentlyUsed.isEmpty()) {
            RegionPos oldest = recentlyUsed.removeFirst();
            RegionFile file = cache.remove(oldest);

            if (file != null) {
                // 閉じる前に必ず書き出す
                // 捨てると変更が失われる
                file.close();
            }
        }
    }

    /**
     * チャンクが存在するか
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
     * チャンクを NBT として読む
     *
     * @param chunkX 絶対チャンクX座標
     * @param chunkZ 絶対チャンクZ座標
     * @return チャンク
     * 存在しなければ null
     */
    public NbtCompound readChunk(int chunkX, int chunkZ) {
        RegionFile file = regionFor(chunkX, chunkZ);

        if (file == null) {
            return null;
        }

        return file.readChunk(chunkX, chunkZ);
    }

    /**
     * チャンクを NBT として書き込む
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
     * チャンクを削除する
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
     * このフォルダに存在する全チャンクの座標を返す
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

    /** 開いている全リージョンの変更を書き出す */
    public void flush() {
        ensureOpen();

        // 開いているリージョンをすべて書き出す
        for (RegionFile file : cache.values()) {
            file.flush();
        }
    }

    /** 開いている全リージョンを閉じる */
    @Override
    public void close() {
        if (closed) {
            return;
        }

        // 開いているリージョンをすべて閉じる
        for (RegionFile file : cache.values()) {
            file.close();
        }

        cache.clear();
        recentlyUsed.clear();
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

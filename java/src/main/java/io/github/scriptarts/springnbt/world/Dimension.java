package io.github.scriptarts.springnbt.world;

import io.github.scriptarts.springnbt.SpringNbtException;
import io.github.scriptarts.springnbt.anvil.ChunkPos;
import io.github.scriptarts.springnbt.anvil.RegionFileMode;
import io.github.scriptarts.springnbt.anvil.RegionFolder;
import io.github.scriptarts.springnbt.nbt.NbtCompound;
import io.github.scriptarts.springnbt.nbt.NbtIo;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * ワールド内の次元 1 つ分
 * {@code region/} {@code entities/} {@code poi/} をまとめて扱う
 *
 * <p>ブロックの取得・設定は<strong>絶対ワールド座標</strong>で行い、
 * リージョン・チャンク・セクションの解決は内部で済ませる
 *
 * <p>仕様: {@code docs/spec/40-world-layout.md} 4章
 */
public final class Dimension implements AutoCloseable {

    private final String id;
    private final Path directory;
    private final WorldOpenOptions options;
    private final Map<Long, Chunk> chunkCache = new HashMap<>();
    private final Set<Long> modifiedChunks = new HashSet<>();

    private RegionFolder regions;
    private RegionFolder entities;
    private RegionFolder poi;
    private boolean closed;

    Dimension(String id, Path directory, WorldOpenOptions options) {
        this.id = id;
        this.directory = directory;
        this.options = options;
    }

    /**
     * 次元ID（{@code minecraft:overworld} など）
     *
     * @return 次元ID
     */
    public String id() {
        return id;
    }

    /**
     * この次元のディレクトリ
     *
     * @return パス
     */
    public Path directory() {
        return directory;
    }

    /**
     * 地形のリージョンフォルダ
     * 無ければ null
     *
     * @return フォルダ
     */
    public RegionFolder regionFolder() {
        regions = folder(regions, "region");
        return regions;
    }

    /**
     * エンティティのリージョンフォルダ
     * 無ければ null
     *
     * @return フォルダ
     */
    public RegionFolder entityFolder() {
        entities = folder(entities, "entities");
        return entities;
    }

    /**
     * POI のリージョンフォルダ
     * 無ければ null
     *
     * @return フォルダ
     */
    public RegionFolder poiFolder() {
        poi = folder(poi, "poi");
        return poi;
    }

    /**
     * {@code data/minecraft/<name>.dat} を読む
     *
     * @param name ファイル名（拡張子なし）
     * @return NBT
     * 存在しなければ null
     */
    public NbtCompound dataFile(String name) {
        ensureOpen();
        Path path = directory.resolve("data").resolve("minecraft").resolve(name + ".dat");

        if (!Files.exists(path)) {
            return null;
        }

        return NbtIo.readFile(path, null).tag();
    }

    /**
     * この次元に存在する全チャンクの座標を返す
     *
     * @return チャンク座標の一覧
     */
    public List<ChunkPos> chunkPositions() {
        ensureOpen();
        RegionFolder folder = regionFolder();

        if (folder == null) {
            return new ArrayList<>();
        }

        return folder.chunkPositions();
    }

    /**
     * チャンクを読む
     * 読み込んだチャンクはキャッシュされ、次回は同じインスタンスが返る
     *
     * @param chunkX 絶対チャンクX座標
     * @param chunkZ 絶対チャンクZ座標
     * @return チャンク
     * 存在しなければ null
     */
    public Chunk chunk(int chunkX, int chunkZ) {
        ensureOpen();
        long key = chunkKey(chunkX, chunkZ);
        Chunk cached = chunkCache.get(key);

        if (cached != null) {
            return cached;
        }

        RegionFolder folder = regionFolder();

        if (folder == null) {
            return null;
        }

        NbtCompound nbt = folder.readChunk(chunkX, chunkZ);

        if (nbt == null) {
            return null;
        }

        Chunk chunk = Chunk.fromNbt(nbt, options.chunkRead());
        chunkCache.put(key, chunk);
        return chunk;
    }

    /**
     * チャンクを書き戻す
     *
     * @param chunk チャンク
     */
    public void saveChunk(Chunk chunk) {
        Objects.requireNonNull(chunk, "chunk");
        ensureOpen();
        ensureWritable();

        RegionFolder folder = regionFolder();

        if (folder == null) {
            throw SpringNbtException.invalidArgument("region/ が無い次元には書き込めない: " + id);
        }

        folder.writeChunk(chunk.x(), chunk.z(), chunk.toNbt(options.chunkWrite()));
        modifiedChunks.remove(chunkKey(chunk.x(), chunk.z()));
    }

    /**
     * 絶対座標でブロックを取得する
     *
     * @param x X座標
     * @param y Y座標
     * @param z Z座標
     * @return ブロック
     * チャンクが無ければ null
     */
    public BlockState getBlock(int x, int y, int z) {
        Chunk chunk = chunk(x >> 4, z >> 4);

        if (chunk == null) {
            return null;
        }

        return chunk.getBlock(x & 15, y, z & 15);
    }

    /**
     * 絶対座標でブロックを設定する
     *
     * <p>変更したチャンクは記録され、{@link #flush()} でまとめて書き戻される
     * 本ライブラリはチャンクを新規生成しないので、存在しない座標はエラーになる
     *
     * @param x     X座標
     * @param y     Y座標
     * @param z     Z座標
     * @param state ブロック
     */
    public void setBlock(int x, int y, int z, BlockState state) {
        Objects.requireNonNull(state, "state");
        ensureWritable();

        int chunkX = x >> 4;
        int chunkZ = z >> 4;
        Chunk chunk = chunk(chunkX, chunkZ);

        if (chunk == null) {
            throw SpringNbtException.invalidArgument("チャンク (" + chunkX + ", " + chunkZ
                    + ") が存在しない。本ライブラリはチャンクを生成しない");
        }

        chunk.setBlock(x & 15, y, z & 15, state);
        modifiedChunks.add(chunkKey(chunkX, chunkZ));
    }

    /**
     * 絶対座標でバイオームを取得する
     * 4×4×4 の単位
     *
     * @param x X座標
     * @param y Y座標
     * @param z Z座標
     * @return バイオームID
     * チャンクが無ければ null
     */
    public String getBiome(int x, int y, int z) {
        Chunk chunk = chunk(x >> 4, z >> 4);

        if (chunk == null) {
            return null;
        }

        return chunk.getBiome(x & 15, y, z & 15);
    }

    /**
     * 絶対座標でバイオームを設定する
     * 4×4×4 の単位
     *
     * @param x     X座標
     * @param y     Y座標
     * @param z     Z座標
     * @param biome バイオームID
     */
    public void setBiome(int x, int y, int z, String biome) {
        Objects.requireNonNull(biome, "biome");
        ensureWritable();

        int chunkX = x >> 4;
        int chunkZ = z >> 4;
        Chunk chunk = chunk(chunkX, chunkZ);

        if (chunk == null) {
            throw SpringNbtException.invalidArgument("チャンク (" + chunkX + ", " + chunkZ
                    + ") が存在しない。本ライブラリはチャンクを生成しない");
        }

        chunk.setBiome(x & 15, y, z & 15, biome);
        modifiedChunks.add(chunkKey(chunkX, chunkZ));
    }

    /** 変更したチャンクをすべて書き戻し、リージョンをディスクへ反映する
    /** */
    public void flush() {
        ensureOpen();

        if (!options.writable()) {
            return;
        }

        // 変更のあったチャンクだけを書き戻す
        for (Long key : modifiedChunks) {
            Chunk chunk = chunkCache.get(key);

            if (chunk != null) {
                regionFolder().writeChunk(chunk.x(), chunk.z(), chunk.toNbt(options.chunkWrite()));
            }
        }

        modifiedChunks.clear();

        if (regions != null) {
            regions.flush();
        }

        if (entities != null) {
            entities.flush();
        }

        if (poi != null) {
            poi.flush();
        }
    }

    /** 変更を書き戻してから閉じる
    /** */
    @Override
    public void close() {
        if (closed) {
            return;
        }

        // 書き込みモードなら、閉じる前に変更を反映する
        if (options.writable()) {
            flush();
        }

        if (regions != null) {
            regions.close();
        }

        if (entities != null) {
            entities.close();
        }

        if (poi != null) {
            poi.close();
        }

        chunkCache.clear();
        closed = true;
    }

    /** フォルダを遅延して開く
    /** 存在しなければ null のまま
    /** */
    private RegionFolder folder(RegionFolder slot, String name) {
        ensureOpen();

        if (slot != null) {
            return slot;
        }

        Path path = directory.resolve(name);

        // 生成されていない次元にはディレクトリ自体が無い
        if (!Files.isDirectory(path) && !options.writable()) {
            return null;
        }

        RegionFileMode mode;
        // ワールドを開いたモードに合わせる
        if (options.writable()) {
            mode = RegionFileMode.READ_WRITE;
        } else {
            mode = RegionFileMode.READ_ONLY;
        }

        return RegionFolder.open(path, mode);
    }

    private void ensureWritable() {
        if (!options.writable()) {
            throw SpringNbtException.invalidArgument("読み取り専用で開いたワールドには書き込めない");
        }
    }

    private void ensureOpen() {
        if (closed) {
            throw SpringNbtException.invalidArgument("既に閉じられた次元");
        }
    }

    /** チャンク座標を 1 つの long に詰めてキャッシュの鍵にする
    /** */
    private static long chunkKey(int chunkX, int chunkZ) {
        return ((long) chunkX << 32) | (chunkZ & 0xFFFFFFFFL);
    }
}

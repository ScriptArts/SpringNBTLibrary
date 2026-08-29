using SpringNBTLibrary.Anvil;
using SpringNBTLibrary.Nbt;

namespace SpringNBTLibrary.World;

/// <summary>
/// ワールド内の次元 1 つ分
/// <c>region/</c> <c>entities/</c> <c>poi/</c> をまとめて扱う
/// </summary>
/// <remarks>
/// <para>
/// ブロックの取得・設定は**絶対ワールド座標**で行い、
/// リージョン・チャンク・セクションの解決は内部で済ませる
/// </para>
/// <para>仕様: <c>docs/spec/40-world-layout.md</c> 4章</para>
/// </remarks>
public sealed class Dimension : IDisposable
{
    private readonly WorldOpenOptions options;
    private readonly Dictionary<long, Chunk> chunkCache = new Dictionary<long, Chunk>();
    private readonly HashSet<long> modifiedChunks = new HashSet<long>();

    private RegionFolder? regions;
    private RegionFolder? entities;
    private RegionFolder? poi;
    private bool closed;

    internal Dimension(string id, string directory, WorldOpenOptions options)
    {
        Id = id;
        Directory = directory;
        this.options = options;
    }

    /// <summary>次元ID（<c>minecraft:overworld</c> など）</summary>
    public string Id { get; }

    /// <summary>この次元のディレクトリ</summary>
    public string Directory { get; }

    /// <summary>地形のリージョンフォルダ
    /// 無ければ null</summary>
    public RegionFolder? RegionFolder => Folder(ref regions, "region");

    /// <summary>エンティティのリージョンフォルダ
    /// 無ければ null</summary>
    public RegionFolder? EntityFolder => Folder(ref entities, "entities");

    /// <summary>POI のリージョンフォルダ
    /// 無ければ null</summary>
    public RegionFolder? PoiFolder => Folder(ref poi, "poi");

    /// <summary>
    /// <c>data/minecraft/&lt;name&gt;.dat</c> を読む
    /// 存在しなければ null
    /// </summary>
    /// <remarks>
    /// 次元ごとの <c>world_border</c> / <c>raids</c> / <c>chunk_tickets</c> などが入る
    /// </remarks>
    public NbtCompound? DataFile(string name)
    {
        EnsureOpen();
        string path = Path.Combine(Directory, "data", "minecraft", name + ".dat");

        if (!File.Exists(path))
        {
            return null;
        }

        return NbtIo.ReadFile(path).Tag;
    }

    /// <summary>この次元に存在する全チャンクの座標を列挙する</summary>
    public IEnumerable<ChunkPos> ChunkPositions()
    {
        EnsureOpen();
        RegionFolder? folder = RegionFolder;

        if (folder is null)
        {
            return Array.Empty<ChunkPos>();
        }

        return folder.ChunkPositions();
    }

    /// <summary>
    /// チャンクを読む
    /// 存在しなければ null
    /// </summary>
    /// <remarks>読み込んだチャンクはキャッシュされ、次回は同じインスタンスが返る</remarks>
    public Chunk? Chunk(int chunkX, int chunkZ)
    {
        EnsureOpen();
        long key = ChunkKey(chunkX, chunkZ);

        if (chunkCache.TryGetValue(key, out Chunk? cached))
        {
            return cached;
        }

        RegionFolder? folder = RegionFolder;

        if (folder is null)
        {
            return null;
        }

        NbtCompound? nbt = folder.ReadChunk(chunkX, chunkZ);

        if (nbt is null)
        {
            return null;
        }

        Chunk chunk = World.Chunk.FromNbt(nbt, options.ChunkRead);
        chunkCache[key] = chunk;
        return chunk;
    }

    /// <summary>チャンクを書き戻す</summary>
    public void SaveChunk(Chunk chunk)
    {
        ArgumentNullException.ThrowIfNull(chunk);
        EnsureOpen();
        EnsureWritable();

        RegionFolder? folder = RegionFolder;

        if (folder is null)
        {
            throw SpringNbtException.InvalidArgument($"region/ が無い次元には書き込めない: {Id}");
        }

        folder.WriteChunk(chunk.X, chunk.Z, chunk.ToNbt(options.ChunkWrite));
        modifiedChunks.Remove(ChunkKey(chunk.X, chunk.Z));
    }

    /// <summary>
    /// 絶対座標でブロックを取得する
    /// チャンクが無ければ null
    /// </summary>
    public BlockState? GetBlock(int x, int y, int z)
    {
        Chunk? chunk = Chunk(x >> 4, z >> 4);

        if (chunk is null)
        {
            return null;
        }

        return chunk.GetBlock(x & 15, y, z & 15);
    }

    /// <summary>
    /// 絶対座標でブロックを設定する
    /// </summary>
    /// <remarks>
    /// 変更したチャンクは記録され、<see cref="Flush"/> でまとめて書き戻される
    /// 本ライブラリはチャンクを新規生成しないので、存在しない座標はエラーになる
    /// </remarks>
    public void SetBlock(int x, int y, int z, BlockState state)
    {
        ArgumentNullException.ThrowIfNull(state);
        EnsureWritable();

        int chunkX = x >> 4;
        int chunkZ = z >> 4;
        Chunk? chunk = Chunk(chunkX, chunkZ);

        if (chunk is null)
        {
            throw SpringNbtException.InvalidArgument(
                $"チャンク ({chunkX}, {chunkZ}) が存在しない。本ライブラリはチャンクを生成しない");
        }

        chunk.SetBlock(x & 15, y, z & 15, state);
        modifiedChunks.Add(ChunkKey(chunkX, chunkZ));
    }

    /// <summary>絶対座標でバイオームを取得する
    /// 4×4×4 の単位</summary>
    public string? GetBiome(int x, int y, int z)
    {
        Chunk? chunk = Chunk(x >> 4, z >> 4);

        if (chunk is null)
        {
            return null;
        }

        return chunk.GetBiome(x & 15, y, z & 15);
    }

    /// <summary>絶対座標でバイオームを設定する
    /// 4×4×4 の単位</summary>
    public void SetBiome(int x, int y, int z, string biome)
    {
        ArgumentNullException.ThrowIfNull(biome);
        EnsureWritable();

        int chunkX = x >> 4;
        int chunkZ = z >> 4;
        Chunk? chunk = Chunk(chunkX, chunkZ);

        if (chunk is null)
        {
            throw SpringNbtException.InvalidArgument(
                $"チャンク ({chunkX}, {chunkZ}) が存在しない。本ライブラリはチャンクを生成しない");
        }

        chunk.SetBiome(x & 15, y, z & 15, biome);
        modifiedChunks.Add(ChunkKey(chunkX, chunkZ));
    }

    /// <summary>変更したチャンクをすべて書き戻し、リージョンをディスクへ反映する</summary>
    public void Flush()
    {
        EnsureOpen();

        if (!options.Writable)
        {
            return;
        }

        // 変更のあったチャンクだけを書き戻す
        foreach (long key in modifiedChunks)
        {
            // キャッシュに残っているものだけ書き戻せる
            if (chunkCache.TryGetValue(key, out Chunk? chunk))
            {
                RegionFolder!.WriteChunk(chunk.X, chunk.Z, chunk.ToNbt(options.ChunkWrite));
            }
        }

        modifiedChunks.Clear();
        // 開いているフォルダだけを書き出す
        foreach (RegionFolder? folder in new[] { regions, entities, poi })
        {
            // 開いているフォルダだけを書き出す
            if (folder is not null)
            {
                folder.Flush();
            }
        }
    }

    /// <summary>変更を書き戻してから閉じる</summary>
    public void Close()
    {
        if (closed)
        {
            return;
        }

        // 書き込みモードなら、閉じる前に変更を反映する
        if (options.Writable)
        {
            Flush();
        }

        // 開いているフォルダだけを閉じる
        foreach (RegionFolder? folder in new[] { regions, entities, poi })
        {
            // 開いているフォルダだけを閉じる
            if (folder is not null)
            {
                folder.Close();
            }
        }
        chunkCache.Clear();
        closed = true;
    }

    /// <inheritdoc/>
    public void Dispose() => Close();

    /// <summary>フォルダを遅延して開く
    /// 存在しなければ null のまま</summary>
    private RegionFolder? Folder(ref RegionFolder? slot, string name)
    {
        EnsureOpen();

        if (slot is not null)
        {
            return slot;
        }

        string path = Path.Combine(Directory, name);

        // 生成されていない次元にはディレクトリ自体が無い
        if (!System.IO.Directory.Exists(path) && !options.Writable)
        {
            return null;
        }

        RegionFileMode mode;
        // ワールドを開いたモードに合わせる
        if (options.Writable)
        {
            mode = RegionFileMode.ReadWrite;
        }
        else
        {
            mode = RegionFileMode.ReadOnly;
        }

        slot = Anvil.RegionFolder.Open(path, mode);
        return slot;
    }

    private void EnsureWritable()
    {
        if (!options.Writable)
        {
            throw SpringNbtException.InvalidArgument("読み取り専用で開いたワールドには書き込めない");
        }
    }

    private void EnsureOpen()
    {
        if (closed)
        {
            throw SpringNbtException.InvalidArgument("既に閉じられた次元");
        }
    }

    /// <summary>チャンク座標を 1 つの long に詰めてキャッシュの鍵にする</summary>
    private static long ChunkKey(int chunkX, int chunkZ) =>
        ((long)chunkX << 32) | (uint)chunkZ;
}

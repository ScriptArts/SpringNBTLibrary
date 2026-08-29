using SpringNBTLibrary.Nbt;

namespace SpringNBTLibrary.Anvil;

/// <summary>
/// リージョンファイルが並ぶディレクトリ 1 つ分（<c>region/</c>、<c>entities/</c>、<c>poi/</c> のいずれか）。
/// </summary>
/// <remarks>
/// <para>
/// 開いたリージョンファイルはキャッシュし、<see cref="Close"/> でまとめて閉じる。
/// チャンク座標からリージョンを解決するので、利用側はリージョンの存在を意識しなくてよい。
/// </para>
/// <para>仕様: <c>docs/spec/20-anvil-region.md</c> 5章</para>
/// </remarks>
public sealed class RegionFolder : IDisposable
{
    private readonly Dictionary<RegionPos, RegionFile> cache = new Dictionary<RegionPos, RegionFile>();
    private readonly RegionFileMode mode;
    private bool closed;

    private RegionFolder(string directory, RegionFileMode mode)
    {
        Directory = directory;
        this.mode = mode;
    }

    /// <summary>このフォルダのパス。</summary>
    public string Directory { get; }

    /// <summary>
    /// リージョンフォルダを開く。
    /// </summary>
    /// <exception cref="SpringNbtException">
    /// 読み取り専用でディレクトリが存在しない場合（<see cref="ErrorCode.Io"/>）。
    /// </exception>
    public static RegionFolder Open(string directory, RegionFileMode mode = RegionFileMode.ReadOnly)
    {
        ArgumentNullException.ThrowIfNull(directory);

        if (!System.IO.Directory.Exists(directory) && mode == RegionFileMode.ReadOnly)
        {
            throw new SpringNbtException(
                ErrorCode.Io, $"リージョンフォルダが存在しない: {directory}");
        }

        return new RegionFolder(directory, mode);
    }

    /// <summary>このフォルダに存在するリージョンの座標を列挙する。</summary>
    public IEnumerable<RegionPos> RegionPositions()
    {
        EnsureOpen();

        if (!System.IO.Directory.Exists(Directory))
        {
            yield break;
        }

        List<RegionPos> found = new List<RegionPos>();

        // r.X.Z.mca として解釈できるファイルだけを拾う
        foreach (string path in System.IO.Directory.EnumerateFiles(Directory, "r.*.mca"))
        {
            RegionPos? position = RegionPos.FromFileName(Path.GetFileName(path));

            if (position is not null)
            {
                found.Add(position.Value);
            }
        }

        // 走査順がファイルシステム依存にならないよう、座標で並べる
        found.Sort((left, right) =>
        {
            int compared = left.Z.CompareTo(right.Z);

            if (compared != 0)
            {
                return compared;
            }

            return left.X.CompareTo(right.X);
        });

        foreach (RegionPos position in found)
        {
            yield return position;
        }
    }

    /// <summary>
    /// リージョンファイルを取得する。読み取り専用で存在しなければ null。
    /// </summary>
    public RegionFile? Region(int regionX, int regionZ)
    {
        EnsureOpen();
        RegionPos position = new RegionPos(regionX, regionZ);

        if (cache.TryGetValue(position, out RegionFile? cached))
        {
            return cached;
        }

        string path = Path.Combine(Directory, position.FileName);

        // 読み取り専用では、存在しないリージョンは「チャンクが無い」として null を返す
        if (!File.Exists(path) && mode == RegionFileMode.ReadOnly)
        {
            return null;
        }

        RegionFile opened = RegionFile.Open(path, mode);
        cache[position] = opened;
        return opened;
    }

    /// <summary>チャンクが存在するか。</summary>
    public bool HasChunk(int chunkX, int chunkZ)
    {
        RegionPos region = new ChunkPos(chunkX, chunkZ).Region;
        RegionFile? file = Region(region.X, region.Z);

        if (file is null)
        {
            return false;
        }

        return file.HasChunk(chunkX, chunkZ);
    }

    /// <summary>チャンクを NBT として読む。存在しなければ null。</summary>
    public NbtCompound? ReadChunk(int chunkX, int chunkZ)
    {
        RegionPos region = new ChunkPos(chunkX, chunkZ).Region;
        RegionFile? file = Region(region.X, region.Z);

        if (file is null)
        {
            return null;
        }

        return file.ReadChunk(chunkX, chunkZ);
    }

    /// <summary>チャンクを NBT として書き込む。</summary>
    public void WriteChunk(int chunkX, int chunkZ, NbtCompound tag)
    {
        RegionPos region = new ChunkPos(chunkX, chunkZ).Region;
        RegionFile? file = Region(region.X, region.Z);

        if (file is null)
        {
            throw SpringNbtException.InvalidArgument(
                $"読み取り専用のフォルダには書き込めない: {Directory}");
        }

        file.WriteChunk(chunkX, chunkZ, tag);
    }

    /// <summary>チャンクを削除する。削除できたら true。</summary>
    public bool DeleteChunk(int chunkX, int chunkZ)
    {
        RegionPos region = new ChunkPos(chunkX, chunkZ).Region;
        RegionFile? file = Region(region.X, region.Z);

        if (file is null)
        {
            return false;
        }

        return file.DeleteChunk(chunkX, chunkZ);
    }

    /// <summary>このフォルダに存在する全チャンクの座標を列挙する。</summary>
    public IEnumerable<ChunkPos> ChunkPositions()
    {
        // リージョンごとに、その中のチャンクを順に返す
        foreach (RegionPos position in RegionPositions())
        {
            RegionFile? file = Region(position.X, position.Z);

            if (file is null)
            {
                continue;
            }

            foreach (ChunkPos chunk in file.ChunkPositions())
            {
                yield return chunk;
            }
        }
    }

    /// <summary>開いている全リージョンの変更を書き出す。</summary>
    public void Flush()
    {
        EnsureOpen();

        foreach (RegionFile file in cache.Values)
        {
            file.Flush();
        }
    }

    /// <summary>開いている全リージョンを閉じる。</summary>
    public void Close()
    {
        if (closed)
        {
            return;
        }

        foreach (RegionFile file in cache.Values)
        {
            file.Close();
        }

        cache.Clear();
        closed = true;
    }

    /// <inheritdoc/>
    public void Dispose() => Close();

    private void EnsureOpen()
    {
        if (closed)
        {
            throw SpringNbtException.InvalidArgument("既に閉じられたリージョンフォルダ");
        }
    }
}

using SpringNBTLibrary.Nbt;

namespace SpringNBTLibrary.Anvil;

/// <summary>
/// リージョンファイルが並ぶディレクトリ 1 つ分（<c>region/</c>、<c>entities/</c>、<c>poi/</c> のいずれか）
/// </summary>
/// <remarks>
/// <para>
/// 開いたリージョンファイルはキャッシュし、<see cref="Close"/> でまとめて閉じる
/// チャンク座標からリージョンを解決するので、利用側はリージョンの存在を意識しなくてよい
/// </para>
/// <para>
/// <see cref="RegionFile"/> はファイル全体をメモリへ載せるため、キャッシュには
/// <see cref="MaxCachedRegions"/> 件の上限がある
/// 上限を超えると、最も長く使われていない
/// ものから書き出して閉じる
/// 大きなワールドを端から走査してもメモリを使い切らない
/// </para>
/// <para>
/// このため <see cref="Region(int, int)"/> が返した参照は、
/// **別のリージョンへアクセスすると閉じられている場合がある**
/// 参照を保持せず、必要なたびに取得すること
/// </para>
/// <para>仕様: <c>docs/spec/20-anvil-region.md</c> 5章</para>
/// </remarks>
public sealed class RegionFolder : IDisposable
{
    /// <summary>同時に開いておくリージョンファイル数の既定の上限</summary>
    /// <remarks>
    /// 1 リージョンは最大 255 セクタ × 1024 チャンク＝理論上 1GiB になりうる
    /// 実データでは数 MB から数十 MB 程度
    /// 8 件なら通常のワールドで数百 MB に収まる
    /// </remarks>
    public const int DefaultMaxCachedRegions = 8;

    private readonly Dictionary<RegionPos, RegionFile> cache = new Dictionary<RegionPos, RegionFile>();

    /// <summary>最近使った順のリージョン座標
    /// 末尾がいちばん新しい</summary>
    private readonly LinkedList<RegionPos> recentlyUsed = new LinkedList<RegionPos>();

    private readonly Dictionary<RegionPos, LinkedListNode<RegionPos>> recentlyUsedNodes =
        new Dictionary<RegionPos, LinkedListNode<RegionPos>>();

    private readonly RegionFileMode mode;
    private bool closed;

    private RegionFolder(string directory, RegionFileMode mode, int maxCachedRegions)
    {
        Directory = directory;
        this.mode = mode;
        MaxCachedRegions = maxCachedRegions;
    }

    /// <summary>このフォルダのパス</summary>
    public string Directory { get; }

    /// <summary>同時に開いておくリージョンファイル数の上限</summary>
    public int MaxCachedRegions { get; }

    /// <summary>いま開いているリージョンファイル数</summary>
    public int CachedRegionCount => cache.Count;

    /// <summary>
    /// リージョンフォルダを開く
    /// </summary>
    /// <exception cref="SpringNbtException">
    /// 読み取り専用でディレクトリが存在しない場合（<see cref="ErrorCode.Io"/>）
    /// </exception>
    /// <param name="directory">リージョンファイルが並ぶディレクトリ</param>
    /// <param name="mode">読み取り専用か、読み書きか</param>
    /// <param name="maxCachedRegions">
    /// 同時に開いておくリージョンファイル数の上限
    /// 既定は <see cref="DefaultMaxCachedRegions"/>
    /// </param>
    public static RegionFolder Open(
        string directory,
        RegionFileMode mode = RegionFileMode.ReadOnly,
        int maxCachedRegions = DefaultMaxCachedRegions)
    {
        ArgumentNullException.ThrowIfNull(directory);

        if (maxCachedRegions < 1)
        {
            throw SpringNbtException.InvalidArgument(
                $"maxCachedRegions は 1 以上でなければならない: {maxCachedRegions}");
        }

        if (!System.IO.Directory.Exists(directory) && mode == RegionFileMode.ReadOnly)
        {
            throw new SpringNbtException(
                ErrorCode.Io, $"リージョンフォルダが存在しない: {directory}");
        }

        return new RegionFolder(directory, mode, maxCachedRegions);
    }

    /// <summary>このフォルダに存在するリージョンの座標を列挙する</summary>
    public IEnumerable<RegionPos> RegionPositions()
    {
        EnsureOpen();

        // フォルダがまだ無いなら、リージョンは 1 つも無い
        if (!System.IO.Directory.Exists(Directory))
        {
            yield break;
        }

        List<RegionPos> found = new List<RegionPos>();

        // r.X.Z.mca として解釈できるファイルだけを拾う
        foreach (string path in System.IO.Directory.EnumerateFiles(Directory, "r.*.mca"))
        {
            RegionPos? position = RegionPos.FromFileName(Path.GetFileName(path));

            // r.X.Z.mca として解釈できるファイルだけを拾う
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

        // 座標順に並べたものを、1 件ずつ返す
        foreach (RegionPos position in found)
        {
            yield return position;
        }
    }

    /// <summary>
    /// リージョンファイルを取得する
    /// 読み取り専用で存在しなければ null
    /// </summary>
    public RegionFile? Region(int regionX, int regionZ)
    {
        EnsureOpen();
        RegionPos position = new RegionPos(regionX, regionZ);

        // 既に開いているものは、使った印を付けて使い回す
        if (cache.TryGetValue(position, out RegionFile? cached))
        {
            Touch(position);
            return cached;
        }

        string path = Path.Combine(Directory, position.FileName);

        // 読み取り専用では、存在しないリージョンは「チャンクが無い」として null を返す
        if (!File.Exists(path) && mode == RegionFileMode.ReadOnly)
        {
            return null;
        }

        // 開く前に空きを作る
        // 開いてからだと一瞬だけ上限を超える
        EvictUntilBelowLimit();

        RegionFile opened = RegionFile.Open(path, mode);
        cache[position] = opened;
        Touch(position);
        return opened;
    }

    /// <summary>使ったリージョンを、最近使った列の末尾へ移す</summary>
    private void Touch(RegionPos position)
    {
        // 既に列にあるなら、いったん外してから末尾へ積み直す
        if (recentlyUsedNodes.TryGetValue(position, out LinkedListNode<RegionPos>? node))
        {
            recentlyUsed.Remove(node);
            recentlyUsed.AddLast(node);
            return;
        }

        recentlyUsedNodes[position] = recentlyUsed.AddLast(position);
    }

    /// <summary>新しく 1 件開けるよう、上限を下回るまで古いものを閉じる</summary>
    private void EvictUntilBelowLimit()
    {
        // 上限に達している間、いちばん長く使っていないものから閉じる
        while (cache.Count >= MaxCachedRegions && recentlyUsed.First is not null)
        {
            RegionPos oldest = recentlyUsed.First.Value;
            recentlyUsed.RemoveFirst();
            recentlyUsedNodes.Remove(oldest);

            if (cache.TryGetValue(oldest, out RegionFile? file))
            {
                // 閉じる前に必ず書き出す
                // 捨てると変更が失われる
                file.Close();
                cache.Remove(oldest);
            }
        }
    }

    /// <summary>チャンクが存在するか</summary>
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

    /// <summary>チャンクを NBT として読む
    /// 存在しなければ null</summary>
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

    /// <summary>チャンクを NBT として書き込む</summary>
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

    /// <summary>チャンクを削除する
    /// 削除できたら true</summary>
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

    /// <summary>このフォルダに存在する全チャンクの座標を列挙する</summary>
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

            // リージョンごとに、その中のチャンク座標を順に返す
            foreach (ChunkPos chunk in file.ChunkPositions())
            {
                yield return chunk;
            }
        }
    }

    /// <summary>開いている全リージョンの変更を書き出す</summary>
    public void Flush()
    {
        EnsureOpen();

        // 開いているリージョンをすべて書き出す
        foreach (RegionFile file in cache.Values)
        {
            file.Flush();
        }
    }

    /// <summary>開いている全リージョンを閉じる</summary>
    public void Close()
    {
        if (closed)
        {
            return;
        }

        // 開いているリージョンをすべて閉じる
        foreach (RegionFile file in cache.Values)
        {
            file.Close();
        }

        cache.Clear();
        recentlyUsed.Clear();
        recentlyUsedNodes.Clear();
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

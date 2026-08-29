using SpringNBTLibrary.Anvil;
using SpringNBTLibrary.Nbt;

namespace SpringNBTLibrary.World;

/// <summary>ワールドを開くときの動作。</summary>
public sealed class WorldOpenOptions
{
    /// <summary>既定のオプション。</summary>
    public static WorldOpenOptions Default { get; } = new WorldOpenOptions();

    /// <summary>読み書きで開くか。既定は読み取り専用。</summary>
    public bool Writable { get; set; }

    /// <summary>
    /// <c>session.lock</c> の確認を飛ばすか。
    /// </summary>
    /// <remarks>
    /// Minecraft が起動中のワールドへ書き込むとデータが壊れる。
    /// 既定では書き込みモードで開くときに必ず確認する。
    /// これを立てるのは自己責任。
    /// </remarks>
    public bool IgnoreSessionLock { get; set; }

    /// <summary>チャンク読み込みのオプション。</summary>
    public ChunkReadOptions ChunkRead { get; set; } = ChunkReadOptions.Default;

    /// <summary>チャンク書き込みのオプション。</summary>
    public ChunkWriteOptions ChunkWrite { get; set; } = ChunkWriteOptions.Default;
}

/// <summary>
/// Minecraft Java版のセーブデータ 1 つ分。
/// </summary>
/// <remarks>
/// <para>
/// 26.x では構成が大きく変わっており、標準の3次元も
/// <c>dimensions/&lt;名前空間&gt;/&lt;パス&gt;/</c> の下に並ぶ。
/// </para>
/// <para>仕様: <c>docs/spec/40-world-layout.md</c></para>
/// </remarks>
public sealed class MinecraftWorld : IDisposable
{
    private readonly Dictionary<string, Dimension> dimensions = new Dictionary<string, Dimension>(StringComparer.Ordinal);
    private readonly WorldOpenOptions options;
    private bool closed;

    private MinecraftWorld(string directory, WorldOpenOptions options, NamedTag level)
    {
        Directory = directory;
        this.options = options;
        Level = new LevelData(level);
    }

    /// <summary>ワールドディレクトリのパス。</summary>
    public string Directory { get; }

    /// <summary><c>level.dat</c> の内容。</summary>
    public LevelData Level { get; }

    /// <summary>
    /// ワールドを開く。
    /// </summary>
    /// <exception cref="SpringNbtException">
    /// ディレクトリや <c>level.dat</c> が無い場合、
    /// または書き込みモードで <c>session.lock</c> を取得できない場合。
    /// </exception>
    public static MinecraftWorld Open(string directory, WorldOpenOptions? options = null)
    {
        ArgumentNullException.ThrowIfNull(directory);

        WorldOpenOptions effective;
        // 省略されたら既定のオプションで開く
        if (options is null)
        {
            effective = WorldOpenOptions.Default;
        }
        else
        {
            effective = options;
        }

        if (!System.IO.Directory.Exists(directory))
        {
            throw new SpringNbtException(ErrorCode.Io, $"ワールドディレクトリが無い: {directory}");
        }

        string levelPath = Path.Combine(directory, "level.dat");

        if (!File.Exists(levelPath))
        {
            throw new SpringNbtException(ErrorCode.Io, $"level.dat が無い: {levelPath}");
        }

        // 書き込むなら、Minecraft が起動中でないことを先に確かめる
        if (effective.Writable && !effective.IgnoreSessionLock)
        {
            CheckSessionLock(directory);
        }

        NamedTag level = NbtIo.ReadFile(levelPath);
        return new MinecraftWorld(directory, effective, level);
    }

    /// <summary>
    /// <c>session.lock</c> を排他で開けるか確かめる。
    /// </summary>
    private static void CheckSessionLock(string directory)
    {
        string lockPath = Path.Combine(directory, "session.lock");

        if (!File.Exists(lockPath))
        {
            return;
        }

        try
        {
            using FileStream stream = new FileStream(
                lockPath, FileMode.Open, FileAccess.ReadWrite, FileShare.None);
        }
        catch (IOException error)
        {
            throw new SpringNbtException(
                ErrorCode.Io,
                "session.lock を排他で開けない。Minecraft が起動中の可能性がある。"
                    + "無視するなら WorldOpenOptions.IgnoreSessionLock を立てること",
                error);
        }
    }

    /// <summary>
    /// <c>data/minecraft/&lt;name&gt;.dat</c> を読む。存在しなければ null。
    /// </summary>
    /// <remarks>
    /// 26.x では <c>game_rules</c> / <c>weather</c> / <c>world_gen_settings</c> などが
    /// この形で <c>level.dat</c> から分離されている。
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

    /// <summary>存在する次元のIDを列挙する。</summary>
    public IEnumerable<string> DimensionIds()
    {
        EnsureOpen();
        string root = Path.Combine(Directory, "dimensions");

        // dimensions/ が無いワールドには次元が 1 つも無い
        if (!System.IO.Directory.Exists(root))
        {
            yield break;
        }

        List<string> found = new List<string>();

        // dimensions/<名前空間>/<パス>/ の 2 段を辿る
        foreach (string namespaceDir in System.IO.Directory.EnumerateDirectories(root))
        {
            string namespaceName = Path.GetFileName(namespaceDir);

            // dimensions/<名前空間>/<パス>/ の 2 段目を次元の名前として拾う
            foreach (string pathDir in System.IO.Directory.EnumerateDirectories(namespaceDir))
            {
                found.Add(namespaceName + ":" + Path.GetFileName(pathDir));
            }
        }

        // 走査順がファイルシステム依存にならないよう並べる
        found.Sort(StringComparer.Ordinal);

        // 並べ替えたものを 1 件ずつ返す
        foreach (string id in found)
        {
            yield return id;
        }
    }

    /// <summary>
    /// 次元を得る。ディレクトリが無ければ null。
    /// </summary>
    /// <param name="dimensionId">
    /// <c>minecraft:overworld</c> のような名前空間つきのID。
    /// 名前空間が省略されていたら <c>minecraft:</c> を補う。
    /// </param>
    public Dimension? Dimension(string dimensionId)
    {
        EnsureOpen();
        ArgumentNullException.ThrowIfNull(dimensionId);

        string normalized = NormalizeDimensionId(dimensionId);

        if (dimensions.TryGetValue(normalized, out Dimension? cached))
        {
            return cached;
        }

        int colon = normalized.IndexOf(':', StringComparison.Ordinal);
        string namespaceName = normalized.Substring(0, colon);
        string path = normalized.Substring(colon + 1);
        string directory = Path.Combine(Directory, "dimensions", namespaceName, path);

        if (!System.IO.Directory.Exists(directory))
        {
            return null;
        }

        Dimension opened = new Dimension(normalized, directory, options);
        dimensions[normalized] = opened;
        return opened;
    }

    /// <summary>プレイヤーのUUID一覧。</summary>
    public IEnumerable<string> PlayerIds()
    {
        EnsureOpen();
        string directory = Path.Combine(Directory, "players", "data");

        // players/data/ が無ければプレイヤーは 1 人もいない
        if (!System.IO.Directory.Exists(directory))
        {
            yield break;
        }

        List<string> found = new List<string>();

        // <uuid>.dat の名前部分が UUID にあたる
        foreach (string path in System.IO.Directory.EnumerateFiles(directory, "*.dat"))
        {
            found.Add(Path.GetFileNameWithoutExtension(path));
        }

        found.Sort(StringComparer.Ordinal);

        // 並べ替えたものを 1 件ずつ返す
        foreach (string id in found)
        {
            yield return id;
        }
    }

    /// <summary>プレイヤーデータを読む。存在しなければ null。</summary>
    public NbtCompound? Player(string uuid)
    {
        EnsureOpen();
        ArgumentNullException.ThrowIfNull(uuid);

        string path = Path.Combine(Directory, "players", "data", uuid + ".dat");

        if (!File.Exists(path))
        {
            return null;
        }

        return NbtIo.ReadFile(path).Tag;
    }

    /// <summary>
    /// <c>level.dat</c> を書き戻す。
    /// </summary>
    /// <remarks>
    /// 壊れるとワールド全体が開けなくなるため、
    /// 一時ファイルへ書いてから <c>level.dat_old</c> へ退避し、最後に置き換える。
    /// </remarks>
    public void SaveLevel()
    {
        EnsureOpen();

        if (!options.Writable)
        {
            throw SpringNbtException.InvalidArgument("読み取り専用で開いたワールドには書き込めない");
        }

        string path = Path.Combine(Directory, "level.dat");
        string temporary = path + ".tmp";
        string backup = path + "_old";

        try
        {
            NbtIo.WriteFile(temporary, Level.ToNamedTag());

            // 既存の level.dat は、置き換える前に level.dat_old へ退避する
            if (File.Exists(path))
            {
                File.Copy(path, backup, overwrite: true);
            }

            File.Move(temporary, path, overwrite: true);
        }
        catch (IOException error)
        {
            throw new SpringNbtException(ErrorCode.Io, $"level.dat を書けない: {path}", error);
        }
    }

    /// <summary>開いている次元をすべて閉じる。</summary>
    public void Close()
    {
        if (closed)
        {
            return;
        }

        // 開いている次元をすべて閉じる
        foreach (Dimension dimension in dimensions.Values)
        {
            dimension.Close();
        }

        dimensions.Clear();
        closed = true;
    }

    /// <inheritdoc/>
    public void Dispose() => Close();

    private void EnsureOpen()
    {
        if (closed)
        {
            throw SpringNbtException.InvalidArgument("既に閉じられたワールド");
        }
    }

    /// <summary>名前空間が省略されていたら <c>minecraft:</c> を補う。</summary>
    private static string NormalizeDimensionId(string dimensionId)
    {
        if (dimensionId.Contains(':', StringComparison.Ordinal))
        {
            return dimensionId;
        }

        return "minecraft:" + dimensionId;
    }
}

/// <summary>
/// <c>level.dat</c> の内容。
/// </summary>
/// <remarks>
/// 26.x では大幅に軽量化されており、ゲームルールやワールド生成設定は
/// <c>data/minecraft/</c> 配下の個別ファイルへ分離されている。
///
/// <para>仕様: <c>docs/spec/40-world-layout.md</c> 2章</para>
/// </remarks>
public sealed class LevelData
{
    private readonly string rootName;

    internal LevelData(NamedTag named)
    {
        rootName = named.Name;
        Raw = named.Tag;
        Data = named.Tag.GetCompound("Data");
    }

    /// <summary>ルートの NBT。<c>Data</c> を含む。</summary>
    public NbtCompound Raw { get; }

    /// <summary><c>Data</c> の中身。実際の設定はここに入っている。</summary>
    public NbtCompound Data { get; }

    /// <summary>チャンク構造のバージョン。</summary>
    public int DataVersion => Data.GetInt("DataVersion");

    /// <summary>ワールド名。</summary>
    public string LevelName => Data.GetString("LevelName");

    /// <summary>ワールドの経過時間（tick）。</summary>
    public long Time => Data.GetLong("Time");

    /// <summary>ゲームモード。0=サバイバル 1=クリエイティブ 2=アドベンチャー 3=スペクテイター。</summary>
    public int GameType => Data.GetInt("GameType");

    /// <summary>スポーン地点の <c>[x, y, z]</c>。</summary>
    public int[] SpawnPos => Data.GetCompound("spawn").GetIntArray("pos");

    /// <summary>スポーン地点の次元ID。</summary>
    public string SpawnDimension => Data.GetCompound("spawn").GetString("dimension");

    /// <summary>難易度（<c>normal</c> など）。</summary>
    public string Difficulty => Data.GetCompound("difficulty_settings").GetString("difficulty");

    /// <summary>ハードコアか。</summary>
    public bool IsHardcore => Data.GetCompound("difficulty_settings").GetBool("hardcore");

    /// <summary>バージョン名（<c>26.2</c> など）。</summary>
    public string VersionName => Data.GetCompound("Version").GetString("Name");

    /// <summary>書き出し用の <see cref="NamedTag"/> を作る。</summary>
    public NamedTag ToNamedTag() => new NamedTag(rootName, Raw);
}

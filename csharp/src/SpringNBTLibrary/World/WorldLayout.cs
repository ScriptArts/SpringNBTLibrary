using System.Globalization;
using SpringNBTLibrary.Nbt;

namespace SpringNBTLibrary.World;

/// <summary>
/// ワールドの構成の世代1つ分
/// ライブラリの内部だけで使う
/// </summary>
/// <remarks>
/// 世代ごとの違いはこの表に集める
/// ワールドと<c>level.dat</c>の読み書きは表の値に従い、DataVersionによる分岐をほかの場所に書かない
/// </remarks>
internal sealed class WorldLayout
{
    /// <summary>L2（26.1以降）が始まるDataVersion</summary>
    internal const int L2MinDataVersion = 4786;

    /// <summary>
    /// 標準の次元のIDと、L1でのワールド直下からの相対ディレクトリ
    /// 並びがL1の<c>DimensionIds</c>の並びになる
    /// </summary>
    private static readonly (string Id, string Relative)[] L1StandardDimensions =
    {
        ("minecraft:overworld", string.Empty),
        ("minecraft:the_nether", "DIM-1"),
        ("minecraft:the_end", "DIM1"),
    };

    /// <summary>L1の<c>Difficulty</c>の数値に対応する名前</summary>
    private static readonly string[] L1Difficulties = { "peaceful", "easy", "normal", "hard" };

    /// <summary>L1: 1.13〜1.21.x</summary>
    private static readonly WorldLayout L1 = new WorldLayout(
        legacy: true,
        playerFolder: new[] { "playerdata" },
        dataFolder: new[] { "data" });

    /// <summary>L2: 26.1以降</summary>
    private static readonly WorldLayout L2 = new WorldLayout(
        legacy: false,
        playerFolder: new[] { "players", "data" },
        dataFolder: new[] { "data", "minecraft" });

    private WorldLayout(bool legacy, string[] playerFolder, string[] dataFolder)
    {
        Legacy = legacy;
        PlayerFolder = playerFolder;
        DataFolder = dataFolder;
    }

    /// <summary>標準の次元が直下と<c>DIM-1/</c> <c>DIM1/</c>に置かれ、<c>level.dat</c>にスポーンなどが直に入る構成か</summary>
    internal bool Legacy { get; }

    /// <summary>ワールド直下からプレイヤーデータのフォルダまでの道</summary>
    private string[] PlayerFolder { get; }

    /// <summary>次元のフォルダから付随データのフォルダまでの道</summary>
    private string[] DataFolder { get; }

    /// <summary>
    /// DataVersionから世代を引く
    /// L1より古い値もL1として扱う
    /// </summary>
    internal static WorldLayout ForDataVersion(int dataVersion)
    {
        // 境界以上ならL2、それ未満はL1
        if (dataVersion >= L2MinDataVersion)
        {
            return L2;
        }

        return L1;
    }

    /// <summary>
    /// <c>level.dat</c>の<c>Data</c>と、利用者の指定から世代を決める
    /// </summary>
    /// <remarks>
    /// 指定があればそれを使い、無ければ<c>Data.DataVersion</c>で決める
    /// <c>DataVersion</c>が無い古いワールドはL1として扱う
    /// </remarks>
    /// <exception cref="SpringNbtException">指定が扱える下限より小さい場合</exception>
    internal static WorldLayout Detect(NbtCompound data, int? requested)
    {
        if (requested is not null)
        {
            // 指定は下限より小さいと解釈のしようがない
            if (requested.Value < ChunkFormat.OldestFormatDataVersion)
            {
                throw SpringNbtException.InvalidArgument(string.Create(
                    CultureInfo.InvariantCulture,
                    $"世代を選ぶDataVersionは{ChunkFormat.OldestFormatDataVersion}以上でなければならない: {requested.Value}"));
            }

            return ForDataVersion(requested.Value);
        }

        int? found = data.OptInt("DataVersion");

        // DataVersionが無いのは1.9より前のワールドなのでL1
        if (found is null)
        {
            return L1;
        }

        return ForDataVersion(found.Value);
    }

    /// <summary>
    /// 次元のフォルダのパス
    /// 次元のIDは名前空間つきで渡す
    /// </summary>
    internal string DimensionDirectory(string worldDirectory, string dimensionId)
    {
        // L1の標準の次元は、ワールド直下か<c>DIM-1/</c> <c>DIM1/</c>に置かれる
        if (Legacy)
        {
            foreach ((string id, string relative) in L1StandardDimensions)
            {
                // 標準の次元ならその専用の場所を返す
                if (dimensionId == id)
                {
                    // オーバーワールドはワールドのフォルダそのもの
                    if (relative.Length == 0)
                    {
                        return worldDirectory;
                    }

                    return Path.Combine(worldDirectory, relative);
                }
            }
        }

        int colon = dimensionId.IndexOf(':', StringComparison.Ordinal);
        return Path.Combine(
            worldDirectory, "dimensions", dimensionId.Substring(0, colon), dimensionId.Substring(colon + 1));
    }

    /// <summary>次元が存在するか</summary>
    internal bool HasDimension(string worldDirectory, string dimensionId)
    {
        string directory = DimensionDirectory(worldDirectory, dimensionId);

        // L1のオーバーワールドはワールド直下なので、region/の有無で判断する
        if (Legacy && dimensionId == L1StandardDimensions[0].Id)
        {
            return Directory.Exists(Path.Combine(directory, "region"));
        }

        return Directory.Exists(directory);
    }

    /// <summary>
    /// 存在する次元のIDを返す
    /// L1では標準の3つを固定の順に並べ、そのあとにデータパックの次元をIDの順に並べる
    /// </summary>
    internal List<string> DimensionIds(string worldDirectory)
    {
        List<string> found = new List<string>();

        // L1の標準の次元は固定の順で先に並べる
        if (Legacy)
        {
            foreach ((string id, _) in L1StandardDimensions)
            {
                // 存在する標準の次元だけを数える
                if (HasDimension(worldDirectory, id))
                {
                    found.Add(id);
                }
            }
        }

        List<string> extra = new List<string>();
        string root = Path.Combine(worldDirectory, "dimensions");

        if (Directory.Exists(root))
        {
            // dimensions/<名前空間>/<パス>/の2段を辿る
            foreach (string namespaceDir in Directory.EnumerateDirectories(root))
            {
                string namespaceName = Path.GetFileName(namespaceDir);

                // 2段目のディレクトリが次元のパス
                foreach (string pathDir in Directory.EnumerateDirectories(namespaceDir))
                {
                    string dimensionId = namespaceName + ":" + Path.GetFileName(pathDir);

                    // L1では標準の次元をdimensions/の下からは探さない
                    if (!Legacy || !IsL1Standard(dimensionId))
                    {
                        extra.Add(dimensionId);
                    }
                }
            }
        }

        // 走査順がファイルシステム依存にならないよう並べる
        extra.Sort(StringComparer.Ordinal);
        found.AddRange(extra);
        return found;
    }

    /// <summary>L1の標準の次元のIDか</summary>
    private static bool IsL1Standard(string dimensionId)
    {
        foreach ((string id, _) in L1StandardDimensions)
        {
            // 標準の次元のIDと一致すれば真
            if (dimensionId == id)
            {
                return true;
            }
        }

        return false;
    }

    /// <summary>プレイヤーデータのフォルダのパス</summary>
    internal string PlayerDirectory(string worldDirectory)
    {
        return Path.Combine(worldDirectory, Path.Combine(PlayerFolder));
    }

    /// <summary>次元のフォルダの下の付随データのファイルのパス</summary>
    internal string DataFilePath(string dimensionDirectory, string name)
    {
        return Path.Combine(dimensionDirectory, Path.Combine(DataFolder), name + ".dat");
    }

    /// <summary>スポーン地点の<c>[x, y, z]</c></summary>
    internal int[] SpawnPos(NbtCompound data)
    {
        // L1は3つの整数に分かれて入っている
        if (Legacy)
        {
            return new[] { data.GetInt("SpawnX"), data.GetInt("SpawnY"), data.GetInt("SpawnZ") };
        }

        return data.GetCompound("spawn").GetIntArray("pos");
    }

    /// <summary>
    /// スポーン地点の次元ID
    /// </summary>
    /// <exception cref="SpringNbtException">この世代の<c>level.dat</c>に無い場合（<c>UnsupportedFeature</c>）</exception>
    internal string SpawnDimension(NbtCompound data)
    {
        // L1にはスポーン地点の次元を持つキーが無い
        if (Legacy)
        {
            throw SpringNbtException.UnsupportedFeature("26.1より前のlevel.datにはスポーン地点の次元が無い");
        }

        return data.GetCompound("spawn").GetString("dimension");
    }

    /// <summary>
    /// 難易度（<c>normal</c>など）
    /// </summary>
    /// <exception cref="SpringNbtException">数値が0〜3の外の場合（<c>MalformedData</c>）</exception>
    internal string Difficulty(NbtCompound data)
    {
        // L1は0〜3の数値で入っている
        if (Legacy)
        {
            sbyte number = data.GetByte("Difficulty");

            if (number < 0 || number >= L1Difficulties.Length)
            {
                throw SpringNbtException.Malformed(string.Create(
                    CultureInfo.InvariantCulture, $"Difficultyが0〜3の外: {number}"));
            }

            return L1Difficulties[number];
        }

        return data.GetCompound("difficulty_settings").GetString("difficulty");
    }

    /// <summary>ハードコアか</summary>
    internal bool IsHardcore(NbtCompound data)
    {
        // L1はDataの直下に入っている
        if (Legacy)
        {
            return data.GetBool("hardcore");
        }

        return data.GetCompound("difficulty_settings").GetBool("hardcore");
    }
}

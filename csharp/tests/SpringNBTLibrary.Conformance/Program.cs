using System.Globalization;
using System.Text;
using SpringNBTLibrary;
using SpringNBTLibrary.Anvil;
using SpringNBTLibrary.Nbt;
using SpringNBTLibrary.World;

namespace SpringNBTLibrary.Conformance;

/// <summary>
/// 適合性検証ツール。4言語すべてが同じインターフェースで同じ出力を出す。
/// </summary>
/// <remarks>
/// <para>
/// <c>spec/run-conformance.sh</c> がこのツールを4言語ぶん起動し、
/// 出力を相互に diff することで「4言語が同一に振る舞う」ことを機械的に確かめる。
/// </para>
/// <para>仕様: <c>docs/spec/90-conformance.md</c> 2.3章</para>
/// </remarks>
internal static class Program
{
    private static int Main(string[] args)
    {
        if (args.Length == 0)
        {
            Console.Error.WriteLine(Usage());
            return 2;
        }

        try
        {
            switch (args[0])
            {
                case "decode":
                    return RunDecode(args);
                case "encode":
                    return RunEncode(args);
                case "snbt":
                    return RunSnbt(args);
                case "nbt-list":
                    return RunNbtList(args);
                case "region-list":
                    return RunRegionList(args);
                case "region-rewrite":
                    return RunRegionRewrite(args);
                case "chunk-report":
                    return RunChunkReport(args);
                case "chunk-edit":
                    return RunChunkEdit(args);
                case "version":
                    Console.Out.Write(VersionLine());
                    return 0;
                default:
                    Console.Error.WriteLine(Usage());
                    return 2;
            }
        }
        catch (SpringNbtException error)
        {
            // 4言語で同じ ErrorCode を出すことが検証対象なので、コードを機械可読な形で出す
            Console.Error.Write($"ERROR {error.Code.AsString()} {error.Message}\n");
            return 1;
        }
    }

    /// <summary>入力を読み、正規化JSON を書き出す。</summary>
    private static int RunDecode(string[] args)
    {
        if (args.Length < 3)
        {
            Console.Error.WriteLine(Usage());
            return 2;
        }

        NbtFormat format = ParseFormat(args);
        NbtReadOptions options = new NbtReadOptions { Format = format };
        NamedTag named = NbtIo.ReadFile(args[1], options);

        WriteTextFile(args[2], NormalizedJson.Write(named, format));
        return 0;
    }

    /// <summary>入力を読み、無圧縮で書き直す。ラウンドトリップ検証に使う。</summary>
    private static int RunEncode(string[] args)
    {
        if (args.Length < 3)
        {
            Console.Error.WriteLine(Usage());
            return 2;
        }

        NbtFormat format = ParseFormat(args);
        NamedTag named = NbtIo.ReadFile(args[1], new NbtReadOptions { Format = format });

        NbtWriteOptions write = new NbtWriteOptions
        {
            Format = format,
            Compression = Compression.None,
        };
        File.WriteAllBytes(args[2], NbtIo.WriteBytes(named, write));
        return 0;
    }

    /// <summary>入力を読み、1行の SNBT を書き出す。</summary>
    private static int RunSnbt(string[] args)
    {
        if (args.Length < 3)
        {
            Console.Error.WriteLine(Usage());
            return 2;
        }

        NbtFormat format = ParseFormat(args);
        NamedTag named = NbtIo.ReadFile(args[1], new NbtReadOptions { Format = format });

        WriteTextFile(args[2], Snbt.Write(named.Tag) + "\n");
        return 0;
    }

    /// <summary>連なった NBT を、位置を追いながら一覧として書き出す。</summary>
    private static int RunNbtList(string[] args)
    {
        if (args.Length < 3)
        {
            Console.Error.WriteLine(Usage());
            return 2;
        }

        NbtFormat format = ParseFormat(args);
        NbtReadOptions options = new NbtReadOptions
        {
            Format = format,
            Compression = Compression.None,
        };

        byte[] bytes = File.ReadAllBytes(args[1]);
        IReadOnlyList<NamedTag> all = NbtIo.ReadBytesAll(bytes, options);
        StringBuilder builder = new StringBuilder();
        builder.Append(CultureInfo.InvariantCulture, $"count {all.Count}\n");

        int offset = 0;
        int index = 0;

        // 位置を指定した読み込みでも同じ並びになることを確かめる
        while (offset < bytes.Length)
        {
            NbtReadResult result = NbtIo.ReadBytesAt(bytes, offset, options);
            NbtCompound root = (NbtCompound)result.Tag.Tag;

            builder.Append(CultureInfo.InvariantCulture,
                $"{index} {offset} {result.End} {result.Tag.Name} {root.Count}\n");

            offset = result.End;
            index++;
        }

        builder.Append(CultureInfo.InvariantCulture, $"total {index} {offset}\n");
        WriteTextFile(args[2], builder.ToString());
        return 0;
    }

    /// <summary>リージョンの中身を一覧として書き出す。</summary>
    private static int RunRegionList(string[] args)
    {
        if (args.Length < 3)
        {
            Console.Error.WriteLine(Usage());
            return 2;
        }

        using RegionFile region = RegionFile.Open(args[1], RegionFileMode.ReadOnly);
        WriteTextFile(args[2], RegionReport.List(region));
        return 0;
    }

    /// <summary>リージョンを読み直し、無圧縮で詰め直して書き出す。</summary>
    private static int RunRegionRewrite(string[] args)
    {
        if (args.Length < 3)
        {
            Console.Error.WriteLine(Usage());
            return 2;
        }

        using RegionFile region = RegionFile.Open(args[1], RegionFileMode.ReadOnly);
        RegionReport.Rewrite(region, args[2]);
        return 0;
    }

    /// <summary>チャンクの全ブロック・全バイオームを走査して集計を書き出す。</summary>
    private static int RunChunkReport(string[] args)
    {
        if (args.Length < 3)
        {
            Console.Error.WriteLine(Usage());
            return 2;
        }

        Chunk chunk = ReadChunkFile(args[1]);
        WriteTextFile(args[2], ChunkReport.Describe(chunk));
        return 0;
    }

    /// <summary>決まった手順でチャンクを編集し、無圧縮で書き出す。</summary>
    private static int RunChunkEdit(string[] args)
    {
        if (args.Length < 3)
        {
            Console.Error.WriteLine(Usage());
            return 2;
        }

        Chunk chunk = ReadChunkFile(args[1]);
        ChunkReport.Edit(chunk);

        NbtWriteOptions write = new NbtWriteOptions { Compression = Compression.None };
        File.WriteAllBytes(args[2], NbtIo.WriteBytes(new NamedTag(string.Empty, chunk.ToNbt()), write));
        return 0;
    }

    /// <summary>チャンク NBT のファイルを読む。</summary>
    private static Chunk ReadChunkFile(string path)
    {
        NamedTag named = NbtIo.ReadFile(path);

        // 検証では DataVersion の違いを警告にせず、そのまま読む
        ChunkReadOptions options = new ChunkReadOptions
        {
            OnVersionMismatch = VersionMismatchAction.Ignore,
        };
        return Chunk.FromNbt(named.Tag, options);
    }

    /// <summary><c>--format network</c> が指定されていればネットワーク形式として読む。</summary>
    private static NbtFormat ParseFormat(string[] args)
    {
        // 3 番目以降の引数からオプションを探す
        for (int i = 3; i < args.Length - 1; i++)
        {
            if (args[i] == "--format" && args[i + 1] == "network")
            {
                return NbtFormat.Network;
            }
        }

        return NbtFormat.Java;
    }

    /// <summary>改行を変換せず、BOM も付けずに UTF-8 で書く。</summary>
    private static void WriteTextFile(string path, string content)
    {
        File.WriteAllBytes(path, new UTF8Encoding(false).GetBytes(content));
    }

    private static string VersionLine()
    {
        return string.Create(
            CultureInfo.InvariantCulture,
            $"csharp spring-nbt-library 0.1.0 target_data_version={SpringNbt.TargetDataVersion}\n");
    }

    private static string Usage()
    {
        return """
            使い方:
              springnbt-conformance decode  <入力パス> <出力JSONパス> [--format network]
              springnbt-conformance encode  <入力パス> <出力バイナリパス> [--format network]
              springnbt-conformance snbt    <入力パス> <出力SNBTパス> [--format network]
              springnbt-conformance nbt-list <入力パス> <出力テキストパス> [--format network]
              springnbt-conformance region-list    <入力mcaパス> <出力テキストパス>
              springnbt-conformance region-rewrite <入力mcaパス> <出力mcaパス>
              springnbt-conformance chunk-report   <入力チャンクnbt> <出力テキストパス>
              springnbt-conformance chunk-edit     <入力チャンクnbt> <出力nbtパス>
              springnbt-conformance version
            """;
    }
}

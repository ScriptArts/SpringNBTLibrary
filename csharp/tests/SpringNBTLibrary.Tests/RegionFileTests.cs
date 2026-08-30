using SpringNBTLibrary.Anvil;
using SpringNBTLibrary.Nbt;

namespace SpringNBTLibrary.Tests;

/// <summary>
/// Anvil リージョンファイルの読み書き。仕様: docs/spec/20-anvil-region.md
/// </summary>
public class RegionFileTests : IDisposable
{
    private readonly string workDirectory;

    public RegionFileTests()
    {
        workDirectory = Path.Combine(Path.GetTempPath(), "springnbt-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(workDirectory);
    }

    public void Dispose()
    {
        // テストごとに作った一時ディレクトリを片付ける
        if (Directory.Exists(workDirectory))
        {
            Directory.Delete(workDirectory, recursive: true);
        }

        GC.SuppressFinalize(this);
    }

    /// <summary>共通テストベクタのディレクトリ。</summary>
    private static string VectorDirectory(string name)
    {
        string current = AppContext.BaseDirectory;

        // ビルド出力からリポジトリ直下まで遡って spec/testdata を探す
        while (current is not null)
        {
            string candidate = Path.Combine(current, "spec", "testdata", "anvil", name);

            if (Directory.Exists(candidate))
            {
                return candidate;
            }

            DirectoryInfo? parent = Directory.GetParent(current);

            if (parent is null)
            {
                break;
            }

            current = parent.FullName;
        }

        throw new DirectoryNotFoundException($"テストベクタが見つからない: anvil/{name}");
    }

    /// <summary>ベクタを一時ディレクトリへ複製し、書き込みテストで原本を汚さないようにする。</summary>
    private string CopyVector(string name)
    {
        string source = VectorDirectory(name);
        string destination = Path.Combine(workDirectory, name);
        Directory.CreateDirectory(destination);

        foreach (string file in Directory.EnumerateFiles(source))
        {
            File.Copy(file, Path.Combine(destination, Path.GetFileName(file)));
        }

        return destination;
    }

    private static NbtCompound SampleChunk(int x, int z)
    {
        NbtCompound chunk = new NbtCompound();
        chunk.Set("DataVersion", new NbtInt(SpringNbt.TargetDataVersion));
        chunk.Set("xPos", new NbtInt(x));
        chunk.Set("zPos", new NbtInt(z));
        chunk.Set("yPos", new NbtInt(-4));
        chunk.Set("Status", new NbtString("minecraft:full"));
        return chunk;
    }

    // -- 座標計算 -----------------------------------------------------------

    [Theory]
    [InlineData(0, 0, 0, 0, 0, 0)]
    [InlineData(31, 31, 0, 0, 31, 31)]
    [InlineData(32, 32, 1, 1, 0, 0)]
    [InlineData(-1, -1, -1, -1, 31, 31)]
    [InlineData(-32, -32, -1, -1, 0, 0)]
    [InlineData(-33, -33, -2, -2, 31, 31)]
    public void ChunkPositionMathHandlesNegativeCoordinates(
        int chunkX, int chunkZ, int regionX, int regionZ, int localX, int localZ)
    {
        ChunkPos position = new ChunkPos(chunkX, chunkZ);

        // 算術右シフトなので負の座標でも正しく求まる
        Assert.Equal(regionX, position.Region.X);
        Assert.Equal(regionZ, position.Region.Z);
        Assert.Equal(localX, position.LocalX);
        Assert.Equal(localZ, position.LocalZ);
        Assert.Equal(localX + (localZ * 32), position.Index);
    }

    [Fact]
    public void RegionFileNameRoundtrips()
    {
        Assert.Equal("r.-1.2.mca", new RegionPos(-1, 2).FileName);

        RegionPos? parsed = RegionPos.FromFileName("r.-1.2.mca");
        Assert.NotNull(parsed);
        Assert.Equal(new RegionPos(-1, 2), parsed.Value);

        // 形式が違うものは受け付けない
        Assert.Null(RegionPos.FromFileName("r.0.0.mcr"));
        Assert.Null(RegionPos.FromFileName("region.mca"));
        Assert.Null(RegionPos.FromFileName("r.a.0.mca"));
    }

    // -- 読み込み -----------------------------------------------------------

    [Fact]
    public void EmptyRegionHasNoChunks()
    {
        using RegionFile region = RegionFile.Open(
            Path.Combine(VectorDirectory("empty"), "r.0.0.mca"));

        Assert.Empty(region.ChunkPositions());
        Assert.False(region.HasChunk(0, 0));
        Assert.Null(region.ReadChunk(0, 0));
    }

    [Fact]
    public void ReadsSingleChunk()
    {
        using RegionFile region = RegionFile.Open(
            Path.Combine(VectorDirectory("single_chunk"), "r.0.0.mca"));

        Assert.Equal(new[] { new ChunkPos(0, 0) }, region.ChunkPositions().ToArray());
        Assert.True(region.HasChunk(0, 0));

        NbtCompound? chunk = region.ReadChunk(0, 0);
        Assert.NotNull(chunk);
        Assert.Equal(SpringNbt.TargetDataVersion, chunk.GetInt("DataVersion"));
        Assert.Equal("minecraft:full", chunk.GetString("Status"));
        Assert.Equal(1700000000, region.Timestamp(0, 0));
    }

    [Fact]
    public void ReadsEveryCompressionScheme()
    {
        using RegionFile region = RegionFile.Open(
            Path.Combine(VectorDirectory("mixed_compression"), "r.0.0.mca"));

        Assert.Equal(ChunkCompression.Gzip, region.ReadChunkRaw(0, 0)!.Compression);
        Assert.Equal(ChunkCompression.Zlib, region.ReadChunkRaw(1, 0)!.Compression);
        Assert.Equal(ChunkCompression.None, region.ReadChunkRaw(2, 0)!.Compression);

        // 方式が違っても中身は同じように読める
        for (int x = 0; x < 3; x++)
        {
            Assert.Equal(x, region.ReadChunk(x, 0)!.GetInt("xPos"));
        }
    }

    [Fact]
    public void ReadsLz4Chunks()
    {
        using RegionFile region = RegionFile.Open(
            Path.Combine(VectorDirectory("lz4"), "r.0.0.mca"));

        // 1 ブロック / 2 ブロック連結 / 無圧縮ブロック / 重なりのあるマッチ
        for (int x = 0; x < 4; x++)
        {
            Assert.Equal(ChunkCompression.Lz4, region.ReadChunkRaw(x, 0)!.Compression);
            Assert.Equal(x, region.ReadChunk(x, 0)!.GetInt("xPos"));
        }

        // 同じバイトの繰り返しは、重なりのあるマッチとして詰められている
        Assert.Equal(new string('A', 4000), region.ReadChunk(3, 0)!.GetString("filler"));
    }

    [Fact]
    public void RejectsLz4BlockWithBrokenMagic()
    {
        using RegionFile region = RegionFile.Open(
            Path.Combine(VectorDirectory("lz4_bad_magic"), "r.0.0.mca"));

        SpringNbtException error = Assert.Throws<SpringNbtException>(
            () => region.ReadChunk(0, 0));
        Assert.Equal(ErrorCode.MalformedData, error.Code);
    }

    [Fact]
    public void WritingLz4IsRejected()
    {
        string directory = CopyVector("lz4");
        using RegionFile region = RegionFile.Open(
            Path.Combine(directory, "r.0.0.mca"), RegionFileMode.ReadWrite);

        // LZ4 は読み込みのみ対応なので、圧縮して書き出すことはできない
        NbtCompound chunk = region.ReadChunk(0, 0)!;
        SpringNbtException error = Assert.Throws<SpringNbtException>(
            () => region.WriteChunk(0, 0, chunk, ChunkCompression.Lz4));
        Assert.Equal(ErrorCode.UnsupportedFeature, error.Code);
    }

    [Fact]
    public void UntouchedLz4ChunksKeepTheirCompression()
    {
        string directory = CopyVector("lz4");
        string path = Path.Combine(directory, "r.0.0.mca");
        byte[] before = File.ReadAllBytes(path);

        using (RegionFile region = RegionFile.Open(path, RegionFileMode.ReadWrite))
        {
            // 触らずに閉じるだけ。生バイトを素通しするので LZ4 のまま残る
        }

        Assert.Equal(before, File.ReadAllBytes(path));
    }

    [Fact]
    public void ReadsChunkStoredInExternalFile()
    {
        using RegionFile region = RegionFile.Open(
            Path.Combine(VectorDirectory("external_mcc"), "r.0.0.mca"));

        RawChunk? raw = region.ReadChunkRaw(0, 0);
        Assert.NotNull(raw);
        Assert.True(raw.External);
        Assert.Equal(ChunkCompression.Zlib, raw.Compression);

        Assert.Equal("minecraft:full", region.ReadChunk(0, 0)!.GetString("Status"));
    }

    [Theory]
    [InlineData("bad_offset")]
    [InlineData("overlapping_sectors")]
    [InlineData("unaligned_length")]
    [InlineData("offset_out_of_file")]
    public void BrokenHeadersAreRejected(string vector)
    {
        SpringNbtException error = Assert.Throws<SpringNbtException>(
            () => RegionFile.Open(Path.Combine(VectorDirectory(vector), "r.0.0.mca")));

        Assert.Equal(ErrorCode.MalformedData, error.Code);
    }

    [Fact]
    public void ChunkOutsideTheRegionIsRejected()
    {
        using RegionFile region = RegionFile.Open(
            Path.Combine(VectorDirectory("empty"), "r.0.0.mca"));

        // r.0.0 が担当するのは 0..31 の範囲だけ
        SpringNbtException error = Assert.Throws<SpringNbtException>(() => region.HasChunk(32, 0));
        Assert.Equal(ErrorCode.InvalidArgument, error.Code);
    }

    [Fact]
    public void ReadOnlyRegionRejectsWrites()
    {
        using RegionFile region = RegionFile.Open(
            Path.Combine(VectorDirectory("empty"), "r.0.0.mca"));

        SpringNbtException error = Assert.Throws<SpringNbtException>(
            () => region.WriteChunk(0, 0, SampleChunk(0, 0)));
        Assert.Equal(ErrorCode.InvalidArgument, error.Code);
    }

    // -- 書き込み -----------------------------------------------------------

    [Fact]
    public void OpeningAndFlushingWithoutChangesKeepsBytesIdentical()
    {
        // 触っていないチャンクの配置を保つことが、既存ワールドを壊さない前提になる
        string directory = CopyVector("fragmented");
        string path = Path.Combine(directory, "r.0.0.mca");
        byte[] original = File.ReadAllBytes(path);

        using (RegionFile region = RegionFile.Open(path, RegionFileMode.ReadWrite))
        {
            region.Flush();
        }

        Assert.Equal(original, File.ReadAllBytes(path));
    }

    [Fact]
    public void WritesAndReadsBackAChunk()
    {
        string path = Path.Combine(workDirectory, "r.0.0.mca");

        using (RegionFile region = RegionFile.Open(path, RegionFileMode.ReadWrite))
        {
            region.WriteChunk(3, 4, SampleChunk(3, 4));
            region.Flush();
        }

        using RegionFile reopened = RegionFile.Open(path);
        Assert.True(reopened.HasChunk(3, 4));
        Assert.Equal(3, reopened.ReadChunk(3, 4)!.GetInt("xPos"));

        // 書き出したファイルは必ずセクタ境界に揃う
        Assert.Equal(0, new FileInfo(path).Length % RegionFile.SectorSize);
    }

    [Fact]
    public void RewritingTheSameSizeKeepsTheChunkInPlace()
    {
        string directory = CopyVector("fragmented");
        string path = Path.Combine(directory, "r.0.0.mca");

        long originalLength = new FileInfo(path).Length;

        using (RegionFile region = RegionFile.Open(path, RegionFileMode.ReadWrite))
        {
            // 同じ内容を書き直すので、必要セクタ数は変わらない
            NbtCompound chunk = region.ReadChunk(0, 0)!;
            region.WriteChunk(0, 0, chunk);
            region.Flush();
        }

        // その場で上書きされるので、ファイルは伸びない
        Assert.Equal(originalLength, new FileInfo(path).Length);

        using RegionFile reopened = RegionFile.Open(path);
        Assert.Equal(3, reopened.ChunkPositions().Count());
    }

    [Fact]
    public void GrowingChunkIsRelocatedWithoutBreakingOthers()
    {
        string directory = CopyVector("fragmented");
        string path = Path.Combine(directory, "r.0.0.mca");

        // 5 セクタぶんになる大きなチャンクを作る
        NbtCompound big = SampleChunk(0, 0);
        big.Set("filler", new NbtByteArray(BuildIncompressibleBytes(5 * RegionFile.SectorSize)));

        using (RegionFile region = RegionFile.Open(path, RegionFileMode.ReadWrite))
        {
            region.WriteChunk(0, 0, big);
            region.Flush();
        }

        using RegionFile reopened = RegionFile.Open(path);

        // 動かした結果、他の 2 チャンクが壊れていないこと
        Assert.Equal(3, reopened.ChunkPositions().Count());
        Assert.Equal(5, reopened.ReadChunk(5, 3)!.GetInt("xPos"));
        Assert.Equal(31, reopened.ReadChunk(31, 31)!.GetInt("xPos"));
        Assert.Equal(
            big.GetByteArray("filler").Length,
            reopened.ReadChunk(0, 0)!.GetByteArray("filler").Length);
    }

    [Fact]
    public void DeletedChunkDisappearsAndOthersSurvive()
    {
        string directory = CopyVector("fragmented");
        string path = Path.Combine(directory, "r.0.0.mca");

        using (RegionFile region = RegionFile.Open(path, RegionFileMode.ReadWrite))
        {
            Assert.True(region.DeleteChunk(5, 3));
            Assert.False(region.DeleteChunk(5, 3));
            region.Flush();
        }

        using RegionFile reopened = RegionFile.Open(path);
        Assert.False(reopened.HasChunk(5, 3));
        Assert.Equal(0, reopened.Timestamp(5, 3));
        Assert.Equal(2, reopened.ChunkPositions().Count());
    }

    [Fact]
    public void FreedSectorsAreReused()
    {
        string directory = CopyVector("fragmented");
        string path = Path.Combine(directory, "r.0.0.mca");
        long originalLength = new FileInfo(path).Length;

        using (RegionFile region = RegionFile.Open(path, RegionFileMode.ReadWrite))
        {
            region.DeleteChunk(5, 3);
            region.WriteChunk(7, 7, SampleChunk(7, 7));
            region.Flush();
        }

        // 空いたセクタへ収まるので、ファイルは伸びない
        Assert.Equal(originalLength, new FileInfo(path).Length);

        using RegionFile reopened = RegionFile.Open(path);
        Assert.Equal(7, reopened.ReadChunk(7, 7)!.GetInt("xPos"));
    }

    [Fact]
    public void OptimizeCompactsTheFile()
    {
        string directory = CopyVector("fragmented");
        string path = Path.Combine(directory, "r.0.0.mca");
        long originalLength = new FileInfo(path).Length;

        using (RegionFile region = RegionFile.Open(path, RegionFileMode.ReadWrite))
        {
            region.Optimize();
            region.Flush();
        }

        long optimizedLength = new FileInfo(path).Length;

        // 隙間が詰まるぶん小さくなる
        Assert.True(optimizedLength < originalLength,
            $"詰め直しても縮んでいない: {originalLength} -> {optimizedLength}");
        Assert.Equal(0, optimizedLength % RegionFile.SectorSize);

        using RegionFile reopened = RegionFile.Open(path);
        Assert.Equal(3, reopened.ChunkPositions().Count());
        Assert.Equal(1700000000, reopened.Timestamp(0, 0));
        Assert.Equal(31, reopened.ReadChunk(31, 31)!.GetInt("xPos"));
    }

    [Fact]
    public void HugeChunkGoesToExternalFileAndComesBack()
    {
        string path = Path.Combine(workDirectory, "r.0.0.mca");

        // 1MiB を超えるよう、圧縮の効かないデータを詰める
        NbtCompound huge = SampleChunk(1, 2);
        huge.Set("filler", new NbtByteArray(BuildIncompressibleBytes(1200 * 1024)));

        using (RegionFile region = RegionFile.Open(path, RegionFileMode.ReadWrite))
        {
            region.WriteChunk(1, 2, huge, ChunkCompression.None);
            region.Flush();
        }

        string external = Path.Combine(workDirectory, "c.1.2.mcc");
        Assert.True(File.Exists(external), "外部ファイルへ退避されていない");

        using (RegionFile reopened = RegionFile.Open(path))
        {
            Assert.True(reopened.ReadChunkRaw(1, 2)!.External);
            Assert.Equal(
                huge.GetByteArray("filler").Length,
                reopened.ReadChunk(1, 2)!.GetByteArray("filler").Length);
        }

        // 小さく書き直すと内部へ戻り、外部ファイルは消える
        using (RegionFile region = RegionFile.Open(path, RegionFileMode.ReadWrite))
        {
            region.WriteChunk(1, 2, SampleChunk(1, 2));
            region.Flush();
        }

        Assert.False(File.Exists(external), "内部へ戻ったのに外部ファイルが残っている");

        using RegionFile final = RegionFile.Open(path);
        Assert.False(final.ReadChunkRaw(1, 2)!.External);
    }

    [Fact]
    public void TimestampCanBeSetExplicitly()
    {
        string path = Path.Combine(workDirectory, "r.0.0.mca");

        using (RegionFile region = RegionFile.Open(path, RegionFileMode.ReadWrite))
        {
            region.WriteChunk(0, 0, SampleChunk(0, 0));
            region.SetTimestamp(0, 0, 1234567890);
            region.Flush();
        }

        using RegionFile reopened = RegionFile.Open(path);
        Assert.Equal(1234567890, reopened.Timestamp(0, 0));
    }

    // -- RegionFolder -------------------------------------------------------

    [Fact]
    public void FolderResolvesChunksAcrossRegions()
    {
        using (RegionFolder folder = RegionFolder.Open(workDirectory, RegionFileMode.ReadWrite))
        {
            folder.WriteChunk(0, 0, SampleChunk(0, 0));
            folder.WriteChunk(-1, -1, SampleChunk(-1, -1));
            folder.WriteChunk(40, 40, SampleChunk(40, 40));
            folder.Flush();
        }

        // 3 つの異なるリージョンへ振り分けられる
        Assert.True(File.Exists(Path.Combine(workDirectory, "r.0.0.mca")));
        Assert.True(File.Exists(Path.Combine(workDirectory, "r.-1.-1.mca")));
        Assert.True(File.Exists(Path.Combine(workDirectory, "r.1.1.mca")));

        using RegionFolder reopened = RegionFolder.Open(workDirectory);
        Assert.Equal(3, reopened.RegionPositions().Count());
        Assert.Equal(3, reopened.ChunkPositions().Count());
        Assert.Equal(-1, reopened.ReadChunk(-1, -1)!.GetInt("xPos"));
        Assert.Null(reopened.ReadChunk(100, 100));
        Assert.False(reopened.HasChunk(100, 100));
    }

    [Fact]
    public void FolderKeepsCachedRegionsUnderTheLimit()
    {
        // 上限 2 で 4 リージョンへ書く。古いものは閉じられるが内容は失われない
        using (RegionFolder folder = RegionFolder.Open(
            workDirectory, RegionFileMode.ReadWrite, maxCachedRegions: 2))
        {
            for (int region = 0; region < 4; region++)
            {
                folder.WriteChunk(region * 32, 0, SampleChunk(region * 32, 0));
                Assert.True(folder.CachedRegionCount <= 2);
            }

            folder.Flush();
        }

        // 追い出されたリージョンも、書き出されてから閉じられている
        using RegionFolder reopened = RegionFolder.Open(workDirectory);
        Assert.Equal(4, reopened.RegionPositions().Count());

        for (int region = 0; region < 4; region++)
        {
            Assert.Equal(region * 32, reopened.ReadChunk(region * 32, 0)!.GetInt("xPos"));
        }
    }

    [Fact]
    public void FolderRejectsInvalidCacheLimit()
    {
        SpringNbtException error = Assert.Throws<SpringNbtException>(
            () => RegionFolder.Open(workDirectory, RegionFileMode.ReadOnly, maxCachedRegions: 0));
        Assert.Equal(ErrorCode.InvalidArgument, error.Code);
    }

    /// <summary>圧縮しても縮まないバイト列を作る。サイズの制御が効くようにするため。</summary>
    private static sbyte[] BuildIncompressibleBytes(int length)
    {
        sbyte[] result = new sbyte[length];
        uint state = 0x12345678;

        // 線形合同法で疑似乱数を作る。テストの再現性を保つため固定の種を使う
        for (int index = 0; index < length; index++)
        {
            state = (state * 1664525) + 1013904223;
            result[index] = (sbyte)(state >> 24);
        }

        return result;
    }
}

using System.Globalization;
using SpringNBTLibrary.Nbt;

namespace SpringNBTLibrary.World;

/// <summary>DataVersion が対象と違ったときの動作</summary>
public enum VersionMismatchAction
{
    /// <summary>警告コールバックを呼んで続行する
    /// 既定</summary>
    Warn,

    /// <summary><see cref="ErrorCode.UnsupportedDataVersion"/> の例外にする</summary>
    Error,

    /// <summary>何もしない</summary>
    Ignore,
}

/// <summary>チャンク読み込みのオプション</summary>
/// <remarks>仕様: <c>docs/spec/30-chunk-format.md</c> 5章</remarks>
public sealed class ChunkReadOptions
{
    /// <summary>既定のオプション</summary>
    public static ChunkReadOptions Default { get; } = new ChunkReadOptions();

    /// <summary>DataVersion が <see cref="SpringNbt.TargetDataVersion"/> と違うときの動作</summary>
    public VersionMismatchAction OnVersionMismatch { get; set; } = VersionMismatchAction.Warn;

    /// <summary>警告の通知先
    /// null なら何もしない</summary>
    public Action<string>? OnWarning { get; set; }

    /// <summary>
    /// data の長さが期待値と違うとき、長さからビット幅を逆算して読むか
    /// 第三者ツールが書いたデータの救済用
    /// </summary>
    public bool LenientBitStorage { get; set; }
}

/// <summary>チャンク書き込みのオプション</summary>
public sealed class ChunkWriteOptions
{
    /// <summary>既定のオプション</summary>
    public static ChunkWriteOptions Default { get; } = new ChunkWriteOptions();

    /// <summary>
    /// 対象バージョン以外の DataVersion を持つチャンクの書き戻しを許すか
    /// </summary>
    /// <remarks>
    /// 既定は false
    /// 古いワールドを黙って新形式で上書きし、
    /// 利用者が気づかないうちに壊すことを防ぐため（<c>docs/adr/0003-version-policy.md</c>）
    /// </remarks>
    public bool AllowForeignDataVersion { get; set; }
}

/// <summary>
/// チャンク 1 つ分
/// 地形の読み書きの入口
/// </summary>
/// <remarks>
/// <para>
/// 読んだ NBT をそのまま保持し、変更した部分だけを書き戻す
/// 未知のキーを落とさないので、将来の追加要素があってもデータを壊さない
/// </para>
/// <para>仕様: <c>docs/spec/30-chunk-format.md</c></para>
/// </remarks>
public sealed class Chunk
{
    /// <summary>セクション 1 つに入るブロック数</summary>
    public const int BlocksPerSection = 4096;

    /// <summary>セクション 1 つに入るバイオームのエントリ数（4×4×4 単位）</summary>
    public const int BiomesPerSection = 64;

    /// <summary>
    /// ブロックに紐づく付随データのキー
    /// ブロックを置き換えたら整合が崩れる
    /// </summary>
    private static readonly string[] BlockDataKeys =
        new[] { "block_entities", "block_ticks", "fluid_ticks" };

    private readonly NbtCompound root;
    private readonly SortedDictionary<int, ChunkSection> sections =
        new SortedDictionary<int, ChunkSection>();

    private Chunk(NbtCompound root)
    {
        this.root = root;
    }

    /// <summary>チャンク構造のバージョン</summary>
    public int DataVersion => root.GetInt("DataVersion");

    /// <summary>絶対チャンクX座標</summary>
    public int X => root.GetInt("xPos");

    /// <summary>絶対チャンクZ座標</summary>
    public int Z => root.GetInt("zPos");

    /// <summary>最下段セクションのY位置
    /// オーバーワールドは -4</summary>
    public int MinSectionY => root.GetInt("yPos");

    /// <summary>生成段階（<c>minecraft:full</c> など）</summary>
    public string Status => root.GetString("Status");

    /// <summary>生成が完了しているか
    /// ブロック改変の対象にしてよいのはこれだけ</summary>
    public bool IsFullyGenerated => Status == "minecraft:full";

    /// <summary>
    /// このチャンクに変更が加わったか
    /// </summary>
    /// <remarks>
    /// <para>
    /// ブロックやバイオームを書き換えると立つ
    /// <see cref="Dimension.Flush"/> はこれが立っているチャンクだけを書き戻す
    /// </para>
    /// <para>
    /// <see cref="Raw"/> を直接いじった場合はここが立たないので、
    /// 自分で true にすること
    /// </para>
    /// </remarks>
    public bool IsModified { get; set; }

    /// <summary>存在するセクションのY位置
    /// 昇順</summary>
    public IEnumerable<int> SectionYs => sections.Keys;

    /// <summary>元の NBT
    /// 解釈していないキーもここに残っている</summary>
    public NbtCompound Raw => root;

    /// <summary>
    /// NBT からチャンクを読む
    /// </summary>
    /// <exception cref="SpringNbtException">
    /// 必須のキーが無い、または構造が想定と違う場合
    /// </exception>
    public static Chunk FromNbt(NbtCompound nbt, ChunkReadOptions? options = null)
    {
        ArgumentNullException.ThrowIfNull(nbt);

        ChunkReadOptions effective;
        // 省略されたら既定のオプションで読む
        if (options is null)
        {
            effective = ChunkReadOptions.Default;
        }
        else
        {
            effective = options;
        }

        Chunk chunk = new Chunk(nbt);
        chunk.CheckDataVersion(effective);

        NbtList? sectionList = nbt.OptList("sections");

        if (sectionList is null)
        {
            return chunk;
        }

        // 並び順に依存しないよう、Y から索引を作る
        foreach (NbtTag entry in sectionList)
        {
            if (entry is not NbtCompound sectionTag)
            {
                throw SpringNbtException.UnexpectedTagType(
                    $"sections の要素が compound でない: {entry.Type.AsString()}");
            }

            ChunkSection section = ChunkSection.FromNbt(sectionTag, effective);
            chunk.sections[section.Y] = section;
        }

        return chunk;
    }

    /// <summary>DataVersion を検査し、オプションに従って警告またはエラーにする</summary>
    private void CheckDataVersion(ChunkReadOptions options)
    {
        int version = DataVersion;

        if (version == SpringNbt.TargetDataVersion)
        {
            return;
        }

        string message = string.Create(
            CultureInfo.InvariantCulture,
            $"DataVersion が対象と違う: {version}（対象は {SpringNbt.TargetDataVersion}）");

        if (options.OnVersionMismatch == VersionMismatchAction.Error)
        {
            throw new SpringNbtException(ErrorCode.UnsupportedDataVersion, message);
        }

        if (options.OnVersionMismatch == VersionMismatchAction.Warn)
        {
            // 通知先が設定されているときだけ知らせる
            if (options.OnWarning is not null)
            {
                options.OnWarning.Invoke(message);
            }
        }
    }

    /// <summary>
    /// NBT へ書き戻す
    /// 変更したセクションだけを反映し、他のキーはそのまま残す
    /// </summary>
    /// <exception cref="SpringNbtException">
    /// DataVersion が対象と違い、かつ
    /// <see cref="ChunkWriteOptions.AllowForeignDataVersion"/> が false の場合
    /// </exception>
    public NbtCompound ToNbt(ChunkWriteOptions? options = null)
    {
        ChunkWriteOptions effective;
        // 省略されたら既定のオプションで書く
        if (options is null)
        {
            effective = ChunkWriteOptions.Default;
        }
        else
        {
            effective = options;
        }

        int version = DataVersion;

        // 対象バージョン以外のチャンクは、明示的に許可されない限り書き戻さない
        if (version != SpringNbt.TargetDataVersion && !effective.AllowForeignDataVersion)
        {
            string message = string.Create(
                CultureInfo.InvariantCulture,
                $"DataVersion {version} のチャンクは書き戻せない（対象は {SpringNbt.TargetDataVersion}）");
            throw new SpringNbtException(
                ErrorCode.UnsupportedDataVersion,
                message + "。許可するなら ChunkWriteOptions.AllowForeignDataVersion を立てること");
        }

        // 常に対象バージョンを書く
        root.Set("DataVersion", new NbtInt(SpringNbt.TargetDataVersion));

        if (sections.Count == 0)
        {
            return root;
        }

        NbtList sectionList = new NbtList(TagType.Compound);

        // Y の昇順で書き出す
        foreach (ChunkSection section in sections.Values)
        {
            sectionList.Add(section.ToNbt());
        }

        root.Set("sections", sectionList);
        return root;
    }

    /// <summary>Y位置からセクションを得る
    /// 無ければ null</summary>
    public ChunkSection? Section(int sectionY)
    {
        if (sections.TryGetValue(sectionY, out ChunkSection? section))
        {
            return section;
        }

        return null;
    }

    /// <summary>
    /// ブロックを取得する
    /// </summary>
    /// <param name="x">チャンク内相対X座標 (0..15)</param>
    /// <param name="y">絶対Y座標</param>
    /// <param name="z">チャンク内相対Z座標 (0..15)</param>
    /// <returns>ブロック
    /// セクションが無い、または block_states を持たない場合は null</returns>
    public BlockState? GetBlock(int x, int y, int z)
    {
        CheckLocalCoordinates(x, z);
        ChunkSection? section = Section(y >> 4);

        if (section is null || !section.HasBlockStates)
        {
            return null;
        }

        NbtTag entry = section.BlockStates!.Get(BlockIndex(x, y, z));

        if (entry is not NbtCompound compound)
        {
            throw SpringNbtException.UnexpectedTagType(
                $"ブロックのパレット要素が compound でない: {entry.Type.AsString()}");
        }

        return BlockState.FromNbt(compound);
    }

    /// <summary>
    /// ブロックを設定する
    /// <c>minecraft:oak_stairs[facing=north]</c> の形の文字列で指定する
    /// </summary>
    /// <exception cref="SpringNbtException">
    /// 文字列を解釈できない場合（<see cref="ErrorCode.InvalidArgument"/>）
    /// </exception>
    public void SetBlock(int x, int y, int z, string state)
    {
        ArgumentNullException.ThrowIfNull(state);
        SetBlock(x, y, z, BlockState.Parse(state));
    }

    /// <summary>
    /// ブロックを設定する
    /// </summary>
    /// <remarks>
    /// 置き換えによって不整合になる付随データ（<c>block_entities</c> /
    /// <c>block_ticks</c> / <c>fluid_ticks</c> のうち、その座標を指すもの）は
    /// 同時に取り除く
    /// 残すとブロックと中身が食い違い、
    /// Minecraft 側で予期しない挙動になるため
    /// 仕様: <c>docs/spec/30-chunk-format.md</c> 2.4章
    /// </remarks>
    /// <exception cref="SpringNbtException">
    /// 対象のセクションが無い、または block_states を持たない場合
    /// （<see cref="ErrorCode.InvalidArgument"/>）
    /// </exception>
    public void SetBlock(int x, int y, int z, BlockState state)
    {
        ArgumentNullException.ThrowIfNull(state);
        CheckLocalCoordinates(x, z);

        int sectionY = y >> 4;
        ChunkSection? section = Section(sectionY);

        // 本ライブラリはセクションを新規生成しないので、無ければ書き込めない
        if (section is null || !section.HasBlockStates)
        {
            string message = string.Create(
                CultureInfo.InvariantCulture,
                $"Y={y} を含むセクション（Y={sectionY}）が無いか、ブロックを持たない");
            throw SpringNbtException.InvalidArgument(
                message + "。本ライブラリはセクションを新規生成しない");
        }

        // 同じ状態を置き直すだけなら、付随データを触る理由がない
        // プロパティの並び順に左右されないよう、NBT ではなく BlockState として比べる
        BlockState? current = GetBlock(x, y, z);

        if (current is not null && current.Equals(state))
        {
            return;
        }

        section.BlockStates!.Set(BlockIndex(x, y, z), state.ToNbt());
        RemoveBlockData(x, y, z);
        IsModified = true;
    }

    /// <summary>
    /// その座標を指す付随データを取り除く
    /// </summary>
    /// <remarks>
    /// <c>block_entities</c> / <c>block_ticks</c> / <c>fluid_ticks</c> の要素は
    /// いずれも <c>x</c> <c>y</c> <c>z</c> を**絶対座標**で持つ
    /// </remarks>
    private void RemoveBlockData(int x, int y, int z)
    {
        int absoluteX = (X * 16) + x;
        int absoluteZ = (Z * 16) + z;

        // 3 つのリストは形が同じなので、まとめて同じ処理をかける
        foreach (string key in BlockDataKeys)
        {
            NbtList? list = root.OptList(key);

            if (list is null || list.Count == 0)
            {
                continue;
            }

            // 後ろから削ると、削除しても残りの添字がずれない
            for (int position = list.Count - 1; position >= 0; position--)
            {
                // 座標を持つ要素のうち、指定の位置を指すものだけを取り除く
                if (list[position] is NbtCompound entry
                    && MatchesPosition(entry, absoluteX, y, absoluteZ))
                {
                    list.RemoveAt(position);
                }
            }
        }
    }

    /// <summary>付随データの要素が、指定の絶対座標を指しているか</summary>
    private static bool MatchesPosition(NbtCompound entry, int x, int y, int z)
    {
        int? entryX = entry.OptInt("x");
        int? entryY = entry.OptInt("y");
        int? entryZ = entry.OptInt("z");

        // 座標を持たない要素は、対象かどうか判断できないので触らない
        if (entryX is null || entryY is null || entryZ is null)
        {
            return false;
        }

        return entryX.Value == x && entryY.Value == y && entryZ.Value == z;
    }

    /// <summary>
    /// バイオームを取得する
    /// 4×4×4 の単位なので、座標は自動的に丸められる
    /// </summary>
    /// <returns>バイオームID
    /// セクションが無い場合は null</returns>
    public string? GetBiome(int x, int y, int z)
    {
        CheckLocalCoordinates(x, z);
        ChunkSection? section = Section(y >> 4);

        if (section is null || !section.HasBiomes)
        {
            return null;
        }

        NbtTag entry = section.Biomes!.Get(BiomeIndex(x, y, z));

        if (entry is not NbtString text)
        {
            throw SpringNbtException.UnexpectedTagType(
                $"バイオームのパレット要素が string でない: {entry.Type.AsString()}");
        }

        return text.Value;
    }

    /// <summary>バイオームを設定する
    /// 4×4×4 の単位</summary>
    public void SetBiome(int x, int y, int z, string biome)
    {
        ArgumentNullException.ThrowIfNull(biome);
        CheckLocalCoordinates(x, z);

        int sectionY = y >> 4;
        ChunkSection? section = Section(sectionY);

        if (section is null || !section.HasBiomes)
        {
            throw SpringNbtException.InvalidArgument(string.Create(
                CultureInfo.InvariantCulture,
                $"Y={y} を含むセクション（Y={sectionY}）が無いか、バイオームを持たない"));
        }

        section.Biomes!.Set(BiomeIndex(x, y, z), new NbtString(biome));
        IsModified = true;
    }

    /// <summary>
    /// <c>Heightmaps</c> を削除し、Minecraft に再計算させる
    /// </summary>
    /// <remarks>
    /// 本ライブラリは高さマップを再計算しない
    /// ブロックを改変したら呼ぶこと
    /// （<c>docs/adr/0004-defer-heightmap-recalc.md</c>）
    /// </remarks>
    public void ClearHeightmaps()
    {
        root.Remove("Heightmaps");
        IsModified = true;
    }

    /// <summary>
    /// <c>isLightOn</c> を 0 にし、光源の再計算を促す
    /// </summary>
    public void InvalidateLighting()
    {
        root.SetByte("isLightOn", 0);
        IsModified = true;
    }

    /// <summary>使われていないパレット要素を全セクションから取り除く</summary>
    public void Compact()
    {
        // 全セクションのパレットをまとめて掃除する
        foreach (ChunkSection section in sections.Values)
        {
            section.Compact();
        }
    }

    /// <summary>セクション内のブロック添字</summary>
    /// <remarks><c>&amp; 15</c> により負のY座標でも正しく求まる</remarks>
    public static int BlockIndex(int x, int y, int z) =>
        ((y & 15) * 256) + ((z & 15) * 16) + (x & 15);

    /// <summary>セクション内のバイオーム添字
    /// 1 エントリが 4×4×4 ブロック</summary>
    public static int BiomeIndex(int x, int y, int z) =>
        (((y & 15) / 4) * 16) + (((z & 15) / 4) * 4) + ((x & 15) / 4);

    private static void CheckLocalCoordinates(int x, int z)
    {
        // チャンク内相対座標は 0..15 でなければならない
        if (x < 0 || x > 15 || z < 0 || z > 15)
        {
            throw SpringNbtException.InvalidArgument(string.Create(
                CultureInfo.InvariantCulture,
                $"チャンク内相対座標が範囲外: ({x}, {z})。X も Z も 0..15 であること"));
        }
    }
}

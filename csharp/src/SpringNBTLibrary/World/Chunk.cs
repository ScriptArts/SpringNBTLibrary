using System.Globalization;
using SpringNBTLibrary.Nbt;

namespace SpringNBTLibrary.World;

/// <summary>DataVersionが扱える形式より古いときの動作</summary>
public enum VersionMismatchAction
{
    /// <summary>警告コールバックを呼んで続行する
    /// 既定</summary>
    Warn,

    /// <summary><see cref="ErrorCode.UnsupportedDataVersion"/>の例外にする</summary>
    Error,

    /// <summary>何もしない</summary>
    Ignore,
}

/// <summary>チャンク読み込みのオプション</summary>
public sealed class ChunkReadOptions
{
    /// <summary>既定のオプション</summary>
    public static ChunkReadOptions Default { get; } = new ChunkReadOptions();

    /// <summary>DataVersionが扱える形式より古いときの動作</summary>
    public VersionMismatchAction OnVersionMismatch { get; set; } = VersionMismatchAction.Warn;

    /// <summary>警告の通知先
    /// nullなら何もしない</summary>
    public Action<string>? OnWarning { get; set; }

    /// <summary>
    /// dataの長さが期待値と違うとき、長さからビット幅を逆算して読むか
    /// 第三者ツールが書いたデータの救済用
    /// </summary>
    public bool LenientBitStorage { get; set; }

    /// <summary>
    /// チャンクの形式の世代を選ぶDataVersion
    /// </summary>
    /// <remarks>
    /// nullなら、チャンク自身のDataVersionで選ぶ
    /// 1519以上でなければならない
    /// 扱える形式の下限との比較には使わず、常にチャンク自身のDataVersionで比べる
    /// </remarks>
    public int? FormatDataVersion { get; set; }
}

/// <summary>チャンク書き込みのオプション</summary>
public sealed class ChunkWriteOptions
{
    /// <summary>既定のオプション</summary>
    public static ChunkWriteOptions Default { get; } = new ChunkWriteOptions();

    /// <summary>
    /// 扱える形式より古いDataVersionを持つチャンクの書き戻しを許すか
    /// </summary>
    /// <remarks>
    /// 既定はfalse
    /// エラーを出さずに古いワールドを新形式で上書きし、
    /// 利用者が気づかないうちに使えなくすることを防ぐため
    /// </remarks>
    public bool AllowForeignDataVersion { get; set; }
}

/// <summary>
/// チャンク1つ分
/// 地形の読み書きはここから行う
/// </summary>
/// <remarks>
/// <para>
/// 読んだNBTをそのまま保持し、書き戻すときに作り直すのはセクションだけにする
/// 未知のキーを落とさないので、将来の追加要素があってもデータをおかしくしない
/// </para>
/// </remarks>
public sealed class Chunk
{
    /// <summary>セクション1つに入るブロック数</summary>
    public const int BlocksPerSection = 4096;

    /// <summary>セクション1つに入るバイオームのエントリ数（4×4×4単位）</summary>
    public const int BiomesPerSection = 64;

    /// <summary>1.15から1.17までの形式で、チャンクの<c>Biomes</c>が持つ数値のバイオームIDの数（4×4×4単位で高さ256まで）</summary>
    private const int BiomeIds3DLength = 1024;

    /// <summary>1.14までの形式で、チャンクの<c>Biomes</c>が持つ数値のバイオームIDの数（列ごと）</summary>
    private const int BiomeIds2DLength = 256;

    /// <summary>DataVersionの無いチャンクで、世代の指定も無いときの<see cref="FormatDataVersion"/></summary>
    private const int MissingDataVersion = -1;

    /// <summary>1.17までの形式で、バイオームIDを持つ最も高いY座標</summary>
    private const int BiomeIdsMaxY = 255;

    /// <summary>生成段階の名前空間</summary>
    private const string MinecraftNamespace = "minecraft:";

    private readonly NbtCompound root;
    private readonly SortedDictionary<int, ChunkSection> sections =
        new SortedDictionary<int, ChunkSection>();

    /// <summary>
    /// セクションのYを読んだ順に並べたもの
    /// 書き戻しで読んだときと同じ並びにするため
    /// </summary>
    private readonly List<int> readOrder = new List<int>();

    /// <summary>
    /// チャンクの形式の世代
    /// 引けなかったチャンクはnullのままで、元のNBTだけを持つ
    /// </summary>
    private ChunkFormat? format;

    private Chunk(NbtCompound root)
    {
        this.root = root;
    }

    /// <summary>チャンク構造のバージョン</summary>
    /// <exception cref="SpringNbtException"><c>DataVersion</c>の無いチャンク（1.9より前）の場合</exception>
    public int DataVersion => root.GetInt("DataVersion");

    /// <summary>
    /// チャンクの形式の世代を選ぶのに使ったDataVersion
    /// </summary>
    /// <remarks>
    /// 読み込みのオプションで指定していればその値、指定が無ければ<see cref="DataVersion"/>
    /// <see cref="DataVersion"/>が1519未満のチャンクでは、世代を選ばずに指定の値をそのまま返す
    /// <c>DataVersion</c>の無いチャンクで指定も無ければ-1
    /// </remarks>
    public int FormatDataVersion { get; private set; }

    /// <summary>絶対チャンクX座標</summary>
    public int X => Body().GetInt("xPos");

    /// <summary>絶対チャンクZ座標</summary>
    public int Z => Body().GetInt("zPos");

    /// <summary>
    /// 最下段セクションのY位置
    /// オーバーワールドは-4
    /// 1.17までの形式では0
    /// </summary>
    /// <exception cref="SpringNbtException">
    /// 元のNBTだけを持つチャンクの場合（<see cref="ErrorCode.UnsupportedDataVersion"/>）
    /// </exception>
    public int MinSectionY
    {
        get
        {
            ChunkFormat chunkFormat = RequireFormat();

            // 1.17までの形式はyPosを持たず、セクションは0段目から始まる
            if (!chunkFormat.HasYPos)
            {
                return 0;
            }

            return root.GetInt("yPos");
        }
    }

    /// <summary>
    /// 生成段階（<c>minecraft:full</c>など）
    /// 1.19までは名前空間の無い<c>full</c>などで入る
    /// </summary>
    public string Status => Body().GetString("Status");

    /// <summary>生成が完了しているか
    /// ブロック改変の対象にしてよいのはこれだけ</summary>
    /// <remarks>1.14までの形式では、1.13の<c>postprocessed</c>と<c>fullchunk</c>も生成済みとみなす
    /// <c>Status</c>が無いか文字列でないチャンク（1.13より前のものなど）は生成済みとみなさない</remarks>
    public bool IsFullyGenerated
    {
        get
        {
            string status;

            // 1.13より前のチャンクなど、Statusを文字列として読めないものは生成済みとみなさない
            try
            {
                status = Status;
            }
            catch (SpringNbtException)
            {
                return false;
            }

            // 名前空間の有無はバージョンで違うので、外してから比べる
            if (status.StartsWith(MinecraftNamespace, StringComparison.Ordinal))
            {
                status = status.Substring(MinecraftNamespace.Length);
            }

            IReadOnlyList<string> fullStatuses = ChunkFormat.DefaultFullStatuses;
            // 生成済みとみなす値は世代で違う
            if (format is not null)
            {
                fullStatuses = format.FullStatuses;
            }

            return fullStatuses.Contains(status);
        }
    }

    /// <summary>
    /// このチャンクに変更が加わったか
    /// </summary>
    /// <remarks>
    /// <para>
    /// ブロックやバイオームを書き換えると立つ
    /// <see cref="Dimension.Flush"/>はこれが立っているチャンクだけを書き戻す
    /// </para>
    /// <para>
    /// <see cref="Raw"/>を直接いじった場合は立たないので、自分でtrueにすること
    /// </para>
    /// </remarks>
    public bool IsModified { get; set; }

    /// <summary>存在するセクションのY位置
    /// 昇順</summary>
    public IEnumerable<int> SectionYs => sections.Keys;

    /// <summary>元のNBT
    /// 解釈していないキーもここに残っている</summary>
    public NbtCompound Raw => root;

    /// <summary>
    /// NBTからチャンクを読む
    /// </summary>
    /// <remarks>
    /// 形式の世代は、オプションで指定したDataVersionか、チャンク自身のDataVersionで選ぶ
    /// DataVersionが1519未満のチャンクは、指定があってもどの世代でも解釈せず、元のNBTだけを持つ
    /// </remarks>
    /// <exception cref="SpringNbtException">
    /// 世代を選ぶDataVersionが1519未満の場合（<see cref="ErrorCode.InvalidArgument"/>）、
    /// 選んだ世代とチャンクの構造が合わない場合（<see cref="ErrorCode.MalformedData"/>）、
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

        int? requested = effective.FormatDataVersion;

        // 1.13より前の形式は、どの世代の部品でも読めない
        if (requested is not null && requested.Value < ChunkFormat.OldestFormatDataVersion)
        {
            throw SpringNbtException.InvalidArgument(string.Create(
                CultureInfo.InvariantCulture,
                $"世代を選ぶDataVersionは{ChunkFormat.OldestFormatDataVersion}以上でなければならない: {requested.Value}"));
        }

        Chunk chunk = new Chunk(nbt);
        chunk.CheckDataVersion(effective);
        int? dataVersion = chunk.OwnDataVersion();
        chunk.FormatDataVersion = MissingDataVersion;
        // DataVersionを持つチャンクは、指定が無ければそれで世代を選ぶ
        if (dataVersion is not null)
        {
            chunk.FormatDataVersion = dataVersion.Value;
        }

        // 指定があれば、チャンク自身のDataVersionの代わりにその値で世代を選ぶ
        if (requested is not null)
        {
            chunk.FormatDataVersion = requested.Value;
        }

        // 1.13より前のチャンクはブロックが数値IDで、どの世代で読んでも誤った値になる
        // DataVersionの無いチャンクは1.9より前のものなので、同じく解釈しない
        if (dataVersion is null || dataVersion.Value < ChunkFormat.OldestFormatDataVersion)
        {
            return chunk;
        }

        ChunkFormat? format = ChunkFormat.ForDataVersion(chunk.FormatDataVersion);

        // 表に無い世代のチャンクは、解釈せずに元のNBTだけを持つ
        if (format is null)
        {
            return chunk;
        }

        chunk.format = format;
        bool hasLevel = nbt.OptCompound("Level") is not null;

        // 選んだ世代と本体の包み方が食い違うなら、空のチャンクとして読み進めずにエラーにする
        if (hasLevel != format.WrappedInLevel)
        {
            throw SpringNbtException.Malformed(string.Create(
                CultureInfo.InvariantCulture,
                $"DataVersion {chunk.FormatDataVersion}で選んだ形式と、ルートのLevelの有無が合わない"));
        }

        NbtList? sectionList = chunk.Body().OptList(format.SectionsKey);

        if (sectionList is null)
        {
            return chunk;
        }

        // 並び順に依存しないよう、Yから索引を作る
        foreach (NbtTag entry in sectionList)
        {
            if (entry is not NbtCompound sectionTag)
            {
                throw SpringNbtException.UnexpectedTagType(
                    $"sections の要素が compound でない: {entry.Type.AsString()}");
            }

            // セクションのブロックの持ち方は世代で違う
            ChunkSection section = ChunkSection.FromNbtForFormat(sectionTag, effective, format);

            // 書き戻しの並びのため、初めて出たYだけを読んだ順に覚える
            if (!chunk.sections.ContainsKey(section.Y))
            {
                chunk.readOrder.Add(section.Y);
            }

            chunk.sections[section.Y] = section;
        }

        return chunk;
    }

    /// <summary>
    /// チャンク自身のDataVersion
    /// 無ければnull
    /// </summary>
    private int? OwnDataVersion() => root.OptInt("DataVersion");

    /// <summary>エラーや警告の文で、チャンクをDataVersionで言い表す</summary>
    private static string DescribeChunk(int? dataVersion)
    {
        // 1.9より前のチャンクはDataVersionを持たない
        if (dataVersion is null)
        {
            return "DataVersionの無いチャンク";
        }

        return string.Create(CultureInfo.InvariantCulture, $"DataVersion {dataVersion.Value}のチャンク");
    }

    /// <summary>DataVersionを検査し、オプションに従って警告またはエラーにする</summary>
    private void CheckDataVersion(ChunkReadOptions options)
    {
        int? version = OwnDataVersion();

        // 形式が同じであれば、新しいバージョンでもそのまま読める
        if (version is not null && version.Value >= SpringNbt.MinSupportedDataVersion)
        {
            return;
        }

        string message = string.Create(
            CultureInfo.InvariantCulture,
            $"{DescribeChunk(version)}はこのライブラリが扱う形式より古い"
                + $"（{SpringNbt.MinSupportedDataVersion}以降が対象）");

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
    /// NBTへ書き戻す
    /// 全セクションを読んだときの世代の形式で、読んだときの並びのまま書き戻し、他のキーはそのまま残す
    /// </summary>
    /// <exception cref="SpringNbtException">
    /// DataVersionが扱える形式より古く、かつ
    /// <see cref="ChunkWriteOptions.AllowForeignDataVersion"/>がfalseの場合
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

        int? version = OwnDataVersion();
        bool supported = version is not null && version.Value >= SpringNbt.MinSupportedDataVersion;

        // 形式の違う古いチャンクは、書き戻すと使えなくなりかねない
        if (!supported && !effective.AllowForeignDataVersion)
        {
            string message = string.Create(
                CultureInfo.InvariantCulture,
                $"{DescribeChunk(version)}は書き戻せない"
                    + $"（{SpringNbt.MinSupportedDataVersion}以降が対象）");
            throw new SpringNbtException(
                ErrorCode.UnsupportedDataVersion,
                message + "。許可するなら ChunkWriteOptions.AllowForeignDataVersion を立てること");
        }

        // DataVersionは読んだ値のまま残す
        // 書き換えると、そのワールドを開くゲーム側の判断を誤らせる

        // 元のNBTだけを持つチャンクは、セクションも読んでいないのでそのまま返す
        if (format is null || sections.Count == 0)
        {
            return root;
        }

        NbtList sectionList = new NbtList(TagType.Compound);

        // 読んだときの並びで書き出す
        foreach (int sectionY in readOrder)
        {
            sectionList.Add(sections[sectionY].ToNbt());
        }

        Body().Set(format.SectionsKey, sectionList);
        return root;
    }

    /// <summary>
    /// チャンクの本体
    /// 1.17までの形式では<c>Level</c>の中、1.18以降はルート
    /// </summary>
    private NbtCompound Body()
    {
        NbtCompound? level = root.OptCompound("Level");

        // 世代とLevelの有無は読み込みで突き合わせてあるので、Levelがあればその中が本体
        if (level is not null)
        {
            return level;
        }

        return root;
    }

    /// <summary>
    /// チャンクの形式の世代を返す
    /// </summary>
    /// <exception cref="SpringNbtException">
    /// 世代を引けず、元のNBTだけを持つチャンクの場合（<see cref="ErrorCode.UnsupportedDataVersion"/>）
    /// </exception>
    private ChunkFormat RequireFormat()
    {
        // 世代を引けなかったチャンクは、ブロックなどの場所が分からない
        if (format is null)
        {
            throw new SpringNbtException(
                ErrorCode.UnsupportedDataVersion,
                DescribeChunk(OwnDataVersion()) + "は形式を解釈せず元のNBTだけを持つので、この操作はできない");
        }

        return format;
    }

    /// <summary>
    /// バイオームを名前で読み書きできる世代を返す
    /// </summary>
    /// <exception cref="SpringNbtException">
    /// 元のNBTだけを持つチャンクの場合（<see cref="ErrorCode.UnsupportedDataVersion"/>）、
    /// バイオームを数値のIDで持つ世代の場合（<see cref="ErrorCode.UnsupportedFeature"/>）
    /// </exception>
    private ChunkFormat RequireNamedBiomes()
    {
        ChunkFormat chunkFormat = RequireFormat();

        // 1.17まではバイオームを数値のIDで持ち、名前では読み書きできない
        if (chunkFormat.BiomeStorage != BiomeStorage.Paletted)
        {
            throw SpringNbtException.UnsupportedFeature(string.Create(
                CultureInfo.InvariantCulture,
                $"DataVersion {FormatDataVersion}のチャンクはバイオームを数値のIDで持つ。GetBiomeId / SetBiomeIdを使うこと"));
        }

        return chunkFormat;
    }

    /// <summary>
    /// バイオームを数値のIDで読み書きできる世代を返す
    /// </summary>
    /// <exception cref="SpringNbtException">
    /// 元のNBTだけを持つチャンクの場合（<see cref="ErrorCode.UnsupportedDataVersion"/>）、
    /// バイオームを名前で持つ世代の場合（<see cref="ErrorCode.UnsupportedFeature"/>）
    /// </exception>
    private ChunkFormat RequireBiomeIds()
    {
        ChunkFormat chunkFormat = RequireFormat();

        // 1.18以降はバイオームを名前で持ち、数値のIDでは読み書きできない
        if (chunkFormat.BiomeStorage == BiomeStorage.Paletted)
        {
            throw SpringNbtException.UnsupportedFeature(string.Create(
                CultureInfo.InvariantCulture,
                $"DataVersion {FormatDataVersion}のチャンクはバイオームを名前で持つ。GetBiome / SetBiomeを使うこと"));
        }

        return chunkFormat;
    }

    /// <summary>
    /// 本体の<c>Biomes</c>を返す
    /// 無い、IntArrayでない、長さが世代と合わない場合はnull
    /// </summary>
    private int[]? BiomeIds(ChunkFormat chunkFormat)
    {
        // 生成途中のチャンクなどは、Biomesを持たないか別の形で持つ
        if (Body().Opt("Biomes") is not NbtIntArray biomes
            || biomes.Value.Length != BiomeIdsLength(chunkFormat))
        {
            return null;
        }

        return biomes.Value;
    }

    /// <summary>世代の<c>Biomes</c>が持つ数値のバイオームIDの数</summary>
    private static int BiomeIdsLength(ChunkFormat chunkFormat)
    {
        // 列ごとに持つ形式は256個
        if (chunkFormat.BiomeStorage == BiomeStorage.Ids2D)
        {
            return BiomeIds2DLength;
        }

        return BiomeIds3DLength;
    }

    /// <summary>Y位置からセクションを得る
    /// 無ければnull</summary>
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
    /// セクションが無い、またはblock_statesを持たない場合はnull</returns>
    /// <exception cref="SpringNbtException">
    /// 元のNBTだけを持つチャンクの場合（<see cref="ErrorCode.UnsupportedDataVersion"/>）
    /// </exception>
    public BlockState? GetBlock(int x, int y, int z)
    {
        ChunkFormat chunkFormat = RequireFormat();
        CheckLocalCoordinates(x, z);
        ChunkSection? section = Section(y >> 4);

        if (section is null || !section.HasBlockStates)
        {
            return null;
        }

        // パレットの要素の形は世代で違うので、世代ごとに決めたDataVersionで読む
        return BlockState.FromNbtForDataVersion(
            section.BlockStates!.Get(BlockIndex(x, y, z)), chunkFormat.PaletteDataVersion);
    }

    /// <summary>
    /// ブロックを設定する
    /// <c>minecraft:oak_stairs[facing=north]</c>の形の文字列で指定する
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
    /// <para>
    /// 置き換えによって不整合になる付随データ（<c>block_entities</c> /
    /// <c>block_ticks</c> / <c>fluid_ticks</c>のうち、その座標を指すもの）は同時に取り除く
    /// 1.17までの形式では、<c>Level</c>の中の<c>TileEntities</c> / <c>TileTicks</c> / <c>LiquidTicks</c>から取り除く
    /// 残すとブロックと中身が食い違い、Minecraft側で予期しない挙動になるため
    /// </para>
    /// <para>
    /// パレットには、チャンクを読んだときの世代の形式で入れる
    /// </para>
    /// </remarks>
    /// <exception cref="SpringNbtException">
    /// 対象のセクションが無い、またはblock_statesを持たない場合
    /// （<see cref="ErrorCode.InvalidArgument"/>）、
    /// 元のNBTだけを持つチャンクの場合（<see cref="ErrorCode.UnsupportedDataVersion"/>）
    /// </exception>
    public void SetBlock(int x, int y, int z, BlockState state)
    {
        ArgumentNullException.ThrowIfNull(state);
        ChunkFormat chunkFormat = RequireFormat();
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
        // プロパティの並び順に左右されないよう、NBTではなくBlockStateとして比べる
        BlockState? current = GetBlock(x, y, z);

        if (current is not null && current.Equals(state))
        {
            return;
        }

        // 書き戻すときに読んだときと同じ形式になるよう、世代ごとに決めたDataVersionで読み書きする
        NbtTag entry = PaletteEntryFor(section.BlockStates!, state, chunkFormat.PaletteDataVersion);
        section.BlockStates!.Set(BlockIndex(x, y, z), entry);
        RemoveBlockData(chunkFormat, x, y, z);
        IsModified = true;
    }

    /// <summary>
    /// ブロック状態を置くときに使うパレット要素を決める
    /// </summary>
    /// <remarks>
    /// 同じ状態の要素がパレットにあれば、キーやプロパティの並びが違ってもそれを使う
    /// 無ければ世代の形式で作る
    /// </remarks>
    private static NbtTag PaletteEntryFor(PalettedContainer container, BlockState state, int dataVersion)
    {
        // 実データの{Properties, Name}の並びの要素も、状態として比べて使い回す
        foreach (NbtTag entry in container.Palette)
        {
            // 状態が同じ要素が見つかれば、パレットを増やさずにそれを置く
            if (BlockState.FromNbtForDataVersion(entry, dataVersion).Equals(state))
            {
                return entry;
            }
        }

        return state.ToNbtForDataVersion(dataVersion);
    }

    /// <summary>
    /// その座標を指す付随データを取り除く
    /// </summary>
    /// <remarks>
    /// <c>block_entities</c> / <c>block_ticks</c> / <c>fluid_ticks</c>の要素は
    /// いずれも<c>x</c> <c>y</c> <c>z</c>を**絶対座標**で持つ
    /// 1.17までの形式の<c>TileEntities</c> / <c>TileTicks</c> / <c>LiquidTicks</c>も同じ
    /// </remarks>
    private void RemoveBlockData(ChunkFormat chunkFormat, int x, int y, int z)
    {
        int absoluteX = (X * 16) + x;
        int absoluteZ = (Z * 16) + z;
        NbtCompound body = Body();

        // 3つのリストは形が同じなので、まとめて同じ処理をかける
        foreach (string key in chunkFormat.BlockDataKeys)
        {
            NbtList? list = body.OptList(key);

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
    /// 4×4×4の単位なので、座標は自動的に丸められる
    /// </summary>
    /// <returns>バイオームID
    /// セクションが無い場合はnull</returns>
    /// <exception cref="SpringNbtException">
    /// 元のNBTだけを持つチャンクの場合（<see cref="ErrorCode.UnsupportedDataVersion"/>）、
    /// バイオームを数値のIDで持つ1.17までの形式の場合（<see cref="ErrorCode.UnsupportedFeature"/>）
    /// </exception>
    public string? GetBiome(int x, int y, int z)
    {
        RequireNamedBiomes();
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
    /// 4×4×4の単位</summary>
    /// <exception cref="SpringNbtException">
    /// 対象のセクションが無い、またはバイオームを持たない場合（<see cref="ErrorCode.InvalidArgument"/>）、
    /// 元のNBTだけを持つチャンクの場合（<see cref="ErrorCode.UnsupportedDataVersion"/>）、
    /// バイオームを数値のIDで持つ1.17までの形式の場合（<see cref="ErrorCode.UnsupportedFeature"/>）
    /// </exception>
    public void SetBiome(int x, int y, int z, string biome)
    {
        ArgumentNullException.ThrowIfNull(biome);
        RequireNamedBiomes();
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
    /// 数値のバイオームIDを取得する（1.17までの形式）
    /// 1.15以降の形式は4×4×4の単位なので、座標は自動的に丸められる
    /// 1.14までの形式は列ごとに持つので、Yは見ない
    /// </summary>
    /// <remarks>
    /// IDは名前に直さない
    /// 1.16.2以降はデータパックで独自のバイオームを足せるので、固定の表では正しく引けないため
    /// </remarks>
    /// <param name="x">チャンク内相対X座標 (0..15)</param>
    /// <param name="y">絶対Y座標</param>
    /// <param name="z">チャンク内相対Z座標 (0..15)</param>
    /// <returns>バイオームID
    /// 1.15以降の形式でYが0..255の外の場合と、<c>Biomes</c>が無いか形が違う場合はnull</returns>
    /// <exception cref="SpringNbtException">
    /// 元のNBTだけを持つチャンクの場合（<see cref="ErrorCode.UnsupportedDataVersion"/>）、
    /// バイオームを名前で持つ1.18以降の形式の場合（<see cref="ErrorCode.UnsupportedFeature"/>）
    /// </exception>
    public int? GetBiomeId(int x, int y, int z)
    {
        ChunkFormat chunkFormat = RequireBiomeIds();
        CheckLocalCoordinates(x, z);
        int[]? biomes = BiomeIds(chunkFormat);

        // Biomesを読めないチャンクは値を持たない
        if (biomes is null)
        {
            return null;
        }

        // 列ごとに持つ形式は高さを見ない
        if (chunkFormat.BiomeStorage == BiomeStorage.Ids2D)
        {
            return biomes[BiomeId2DIndex(x, z)];
        }

        // 高さの範囲外は値を持たない
        if (y < 0 || y > BiomeIdsMaxY)
        {
            return null;
        }

        return biomes[BiomeIdIndex(x, y, z)];
    }

    /// <summary>
    /// 数値のバイオームIDを設定する（1.17までの形式）
    /// 1.15以降の形式は4×4×4の単位
    /// 1.14までの形式は列ごとに持つので、Yは見ない
    /// </summary>
    /// <exception cref="SpringNbtException">
    /// 1.15以降の形式でYが0..255の外の場合、
    /// <c>Biomes</c>が無いか形が違う場合（<see cref="ErrorCode.InvalidArgument"/>）、
    /// 元のNBTだけを持つチャンクの場合（<see cref="ErrorCode.UnsupportedDataVersion"/>）、
    /// バイオームを名前で持つ1.18以降の形式の場合（<see cref="ErrorCode.UnsupportedFeature"/>）
    /// </exception>
    public void SetBiomeId(int x, int y, int z, int biomeId)
    {
        ChunkFormat chunkFormat = RequireBiomeIds();
        CheckLocalCoordinates(x, z);
        int index = BiomeId2DIndex(x, z);
        // 4×4×4ごとに持つ形式は、高さ0..255の分だけある
        if (chunkFormat.BiomeStorage == BiomeStorage.Ids3D)
        {
            // 範囲外の高さはどの値にも当たらない
            if (y < 0 || y > BiomeIdsMaxY)
            {
                throw SpringNbtException.InvalidArgument(string.Create(
                    CultureInfo.InvariantCulture,
                    $"Y={y}はバイオームIDを持つ高さ（0..{BiomeIdsMaxY}）の外"));
            }

            index = BiomeIdIndex(x, y, z);
        }

        int[]? biomes = BiomeIds(chunkFormat);

        // 読めないBiomesを作り直すと元のデータを失うので、書き込まない
        if (biomes is null)
        {
            throw SpringNbtException.InvalidArgument(string.Create(
                CultureInfo.InvariantCulture,
                $"Biomesが無いか、int[{BiomeIdsLength(chunkFormat)}]でない"));
        }

        biomes[index] = biomeId;
        IsModified = true;
    }

    /// <summary>
    /// <c>Heightmaps</c>を削除し、Minecraftに再計算させる
    /// </summary>
    /// <remarks>
    /// 本ライブラリは高さマップを再計算しない
    /// ブロックを改変したら呼ぶこと
    /// </remarks>
    /// <exception cref="SpringNbtException">
    /// 元のNBTだけを持つチャンクの場合（<see cref="ErrorCode.UnsupportedDataVersion"/>）
    /// </exception>
    public void ClearHeightmaps()
    {
        RequireFormat();
        Body().Remove("Heightmaps");
        IsModified = true;
    }

    /// <summary>
    /// <c>isLightOn</c>を0にし、光源の再計算を促す
    /// </summary>
    /// <exception cref="SpringNbtException">
    /// 元のNBTだけを持つチャンクの場合（<see cref="ErrorCode.UnsupportedDataVersion"/>）、
    /// <c>isLightOn</c>の無い1.17までの形式のチャンクの場合（<see cref="ErrorCode.UnsupportedFeature"/>）
    /// </exception>
    public void InvalidateLighting()
    {
        ChunkFormat chunkFormat = RequireFormat();
        NbtCompound body = Body();

        // 書き足さない世代では、isLightOnの無いチャンクは光源の印を持たない
        if (!chunkFormat.AddsLightFlag && !body.ContainsKey("isLightOn"))
        {
            throw SpringNbtException.UnsupportedFeature(string.Create(
                CultureInfo.InvariantCulture,
                $"DataVersion {FormatDataVersion}のチャンクはisLightOnを持たない"));
        }

        body.SetByte("isLightOn", 0);
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
    /// <remarks><c>&amp; 15</c>により負のY座標でも正しく求まる</remarks>
    public static int BlockIndex(int x, int y, int z) =>
        ((y & 15) * 256) + ((z & 15) * 16) + (x & 15);

    /// <summary>セクション内のバイオーム添字
    /// 1エントリが4×4×4ブロック</summary>
    public static int BiomeIndex(int x, int y, int z) =>
        (((y & 15) / 4) * 16) + (((z & 15) / 4) * 4) + ((x & 15) / 4);

    /// <summary>1.15から1.17までの形式の<c>Biomes</c>の添字
    /// 1エントリが4×4×4ブロック</summary>
    private static int BiomeIdIndex(int x, int y, int z) =>
        (((y >> 2) & 63) * 16) + ((z >> 2) * 4) + (x >> 2);

    /// <summary>1.14までの形式の<c>Biomes</c>の添字
    /// 1エントリが1列</summary>
    private static int BiomeId2DIndex(int x, int z) => (z * 16) + x;

    private static void CheckLocalCoordinates(int x, int z)
    {
        // チャンク内相対座標は0..15でなければならない
        if (x < 0 || x > 15 || z < 0 || z > 15)
        {
            throw SpringNbtException.InvalidArgument(string.Create(
                CultureInfo.InvariantCulture,
                $"チャンク内相対座標が範囲外: ({x}, {z})。X も Z も 0..15 であること"));
        }
    }
}

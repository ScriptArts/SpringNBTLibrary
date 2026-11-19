namespace SpringNBTLibrary.World;

/// <summary>
/// バイオームの持ち方
/// ライブラリの内部だけで使う
/// </summary>
internal enum BiomeStorage
{
    /// <summary>セクションごとのパレット付きコンテナ</summary>
    Paletted,

    /// <summary>チャンクの列ごとの数値のバイオームID（<c>int[256]</c>）</summary>
    Ids2D,

    /// <summary>4×4×4ブロックごとの数値のバイオームID（<c>int[1024]</c>）</summary>
    Ids3D,
}

/// <summary>
/// チャンクの形式の世代1つ分
/// ライブラリの内部だけで使う
/// </summary>
/// <remarks>
/// 世代ごとの違いはこの表に集める
/// チャンクの読み書きは表の値に従い、DataVersionによる分岐をほかの場所に書かない
/// </remarks>
internal sealed class ChunkFormat
{
    /// <summary>
    /// ブロックのパレット要素が<c>id</c> / <c>properties</c>の形式になるDataVersion（26.3）
    /// これ未満は<c>Name</c> / <c>Properties</c>の形式
    /// </summary>
    internal const int PaletteIdFormatDataVersion = 5006;

    /// <summary>DataVersionを指定して読み書きできる最も古いDataVersion（1.13の正式版）</summary>
    internal const int OldestFormatDataVersion = 1519;

    /// <summary>ルートの直下に置かれる、ブロックに紐づく付随データのキー（1.18以降）</summary>
    private static readonly string[] RootBlockDataKeys =
        new[] { "block_entities", "block_ticks", "fluid_ticks" };

    /// <summary>
    /// 世代の表
    /// 境界のDataVersionの昇順に並べる
    /// </summary>
    private static readonly ChunkFormat[] Formats = new[]
    {
        // C4: 1.18〜26.2
        // Levelが無くなり、パレットの要素はName / Properties
        new ChunkFormat(
            minDataVersion: 2844,
            wrappedInLevel: false,
            sectionsKey: "sections",
            paletteDataVersion: 2844,
            spanningBitStorage: false,
            biomeStorage: BiomeStorage.Paletted,
            blockDataKeys: RootBlockDataKeys),

        // C5: 26.3以降
        // パレットの要素は文字列かid / properties
        new ChunkFormat(
            minDataVersion: PaletteIdFormatDataVersion,
            wrappedInLevel: false,
            sectionsKey: "sections",
            paletteDataVersion: PaletteIdFormatDataVersion,
            spanningBitStorage: false,
            biomeStorage: BiomeStorage.Paletted,
            blockDataKeys: RootBlockDataKeys),
    };

    private ChunkFormat(
        int minDataVersion,
        bool wrappedInLevel,
        string sectionsKey,
        int paletteDataVersion,
        bool spanningBitStorage,
        BiomeStorage biomeStorage,
        IReadOnlyList<string> blockDataKeys)
    {
        MinDataVersion = minDataVersion;
        WrappedInLevel = wrappedInLevel;
        SectionsKey = sectionsKey;
        PaletteDataVersion = paletteDataVersion;
        SpanningBitStorage = spanningBitStorage;
        BiomeStorage = biomeStorage;
        BlockDataKeys = blockDataKeys;
    }

    /// <summary>この世代が始まるDataVersion</summary>
    internal int MinDataVersion { get; }

    /// <summary>チャンクの本体が<c>Level</c>の中にあるか</summary>
    internal bool WrappedInLevel { get; }

    /// <summary>セクションの一覧のキー</summary>
    internal string SectionsKey { get; }

    /// <summary>パレットの要素と<see cref="BlockState"/>の変換に渡すDataVersion</summary>
    internal int PaletteDataVersion { get; }

    /// <summary>ビット詰めで値が64bitの境目をまたぐか</summary>
    internal bool SpanningBitStorage { get; }

    /// <summary>バイオームの持ち方</summary>
    internal BiomeStorage BiomeStorage { get; }

    /// <summary>ブロックを置き換えたときに取り除く付随データのキー</summary>
    internal IReadOnlyList<string> BlockDataKeys { get; }

    /// <summary>
    /// DataVersionから世代を引く
    /// 表にあるどの世代よりも古ければnull
    /// </summary>
    internal static ChunkFormat? ForDataVersion(int dataVersion)
    {
        ChunkFormat? result = null;

        // 表は境界の昇順に並ぶので、境界以上の最後の世代が当てはまる
        foreach (ChunkFormat format in Formats)
        {
            // 境界に届いた世代だけを候補にする
            if (dataVersion >= format.MinDataVersion)
            {
                result = format;
            }
        }

        return result;
    }
}

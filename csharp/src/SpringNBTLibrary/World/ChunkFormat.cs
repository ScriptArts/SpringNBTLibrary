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
/// セクションのブロックの持ち方
/// ライブラリの内部だけで使う
/// </summary>
internal enum BlockStorage
{
    /// <summary>
    /// セクションの<c>block_states</c>にあるパレット付きコンテナ（<c>palette</c> / <c>data</c>）
    /// パレットが1要素なら<c>data</c>を持たない
    /// </summary>
    Container,

    /// <summary>
    /// セクションの直下の<c>Palette</c>と<c>BlockStates</c>
    /// <c>BlockStates</c>はパレットが1要素でも必ずある
    /// </summary>
    SectionPalette,
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

    /// <summary><c>Level</c>の中に置かれる、ブロックに紐づく付随データのキー（1.17まで）</summary>
    private static readonly string[] LevelBlockDataKeys =
        new[] { "TileEntities", "TileTicks", "LiquidTicks" };

    /// <summary>
    /// 生成済みとみなす<c>Status</c>の値（名前空間を外した形）
    /// 世代を引けないチャンクもこれで判定する
    /// </summary>
    internal static readonly IReadOnlyList<string> DefaultFullStatuses = new[] { "full" };

    /// <summary>
    /// 1.14までの形式で生成済みとみなす<c>Status</c>の値
    /// 1.13は生成を終えたチャンクを<c>fullchunk</c>や<c>postprocessed</c>で保存する
    /// </summary>
    private static readonly string[] FullStatuses1_13 = new[] { "full", "postprocessed", "fullchunk" };

    /// <summary>
    /// 世代の表
    /// 境界のDataVersionの昇順に並べる
    /// </summary>
    private static readonly ChunkFormat[] Formats = new[]
    {
        // C1: 1.13〜1.14.x
        // C2と同じで、バイオームは列ごとの数値のID
        // 1.13の生成済みのチャンクはStatusがfullchunkかpostprocessed
        new ChunkFormat(
            minDataVersion: OldestFormatDataVersion,
            wrappedInLevel: true,
            sectionsKey: "Sections",
            paletteDataVersion: OldestFormatDataVersion,
            spanningBitStorage: true,
            blockStorage: BlockStorage.SectionPalette,
            biomeStorage: BiomeStorage.Ids2D,
            blockDataKeys: LevelBlockDataKeys,
            hasYPos: false,
            addsLightFlag: false,
            fullStatuses: FullStatuses1_13),

        // C2: 1.15〜1.15.2
        // C3と同じで、ビット詰めが値を64bitの境目でまたぐ
        new ChunkFormat(
            minDataVersion: 2203,
            wrappedInLevel: true,
            sectionsKey: "Sections",
            paletteDataVersion: 2203,
            spanningBitStorage: true,
            blockStorage: BlockStorage.SectionPalette,
            biomeStorage: BiomeStorage.Ids3D,
            blockDataKeys: LevelBlockDataKeys,
            hasYPos: false,
            addsLightFlag: false,
            fullStatuses: DefaultFullStatuses),

        // C3: 1.16〜1.17.x
        // 本体はLevelの中で、ブロックはセクションの直下のPalette / BlockStates
        // バイオームは4×4×4ブロックごとの数値のID
        new ChunkFormat(
            minDataVersion: 2529,
            wrappedInLevel: true,
            sectionsKey: "Sections",
            paletteDataVersion: 2529,
            spanningBitStorage: false,
            blockStorage: BlockStorage.SectionPalette,
            biomeStorage: BiomeStorage.Ids3D,
            blockDataKeys: LevelBlockDataKeys,
            hasYPos: false,
            addsLightFlag: false,
            fullStatuses: DefaultFullStatuses),

        // C4: 1.18〜26.2
        // Levelが無くなり、パレットの要素はName / Properties
        new ChunkFormat(
            minDataVersion: 2844,
            wrappedInLevel: false,
            sectionsKey: "sections",
            paletteDataVersion: 2844,
            spanningBitStorage: false,
            blockStorage: BlockStorage.Container,
            biomeStorage: BiomeStorage.Paletted,
            blockDataKeys: RootBlockDataKeys,
            hasYPos: true,
            addsLightFlag: true,
            fullStatuses: DefaultFullStatuses),

        // C5: 26.3以降
        // パレットの要素は文字列かid / properties
        new ChunkFormat(
            minDataVersion: PaletteIdFormatDataVersion,
            wrappedInLevel: false,
            sectionsKey: "sections",
            paletteDataVersion: PaletteIdFormatDataVersion,
            spanningBitStorage: false,
            blockStorage: BlockStorage.Container,
            biomeStorage: BiomeStorage.Paletted,
            blockDataKeys: RootBlockDataKeys,
            hasYPos: true,
            addsLightFlag: true,
            fullStatuses: DefaultFullStatuses),
    };

    private ChunkFormat(
        int minDataVersion,
        bool wrappedInLevel,
        string sectionsKey,
        int paletteDataVersion,
        bool spanningBitStorage,
        BlockStorage blockStorage,
        BiomeStorage biomeStorage,
        IReadOnlyList<string> blockDataKeys,
        bool hasYPos,
        bool addsLightFlag,
        IReadOnlyList<string> fullStatuses)
    {
        MinDataVersion = minDataVersion;
        WrappedInLevel = wrappedInLevel;
        SectionsKey = sectionsKey;
        PaletteDataVersion = paletteDataVersion;
        SpanningBitStorage = spanningBitStorage;
        BlockStorage = blockStorage;
        BiomeStorage = biomeStorage;
        BlockDataKeys = blockDataKeys;
        HasYPos = hasYPos;
        AddsLightFlag = addsLightFlag;
        FullStatuses = fullStatuses;
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

    /// <summary>セクションのブロックの持ち方</summary>
    internal BlockStorage BlockStorage { get; }

    /// <summary>バイオームの持ち方</summary>
    internal BiomeStorage BiomeStorage { get; }

    /// <summary>ブロックを置き換えたときに取り除く付随データのキー</summary>
    internal IReadOnlyList<string> BlockDataKeys { get; }

    /// <summary>
    /// ルートに最下段セクションのY位置（<c>yPos</c>）があるか
    /// 無い世代では、セクションは0段目から始まる
    /// </summary>
    internal bool HasYPos { get; }

    /// <summary>
    /// <c>isLightOn</c>の無いチャンクで光源を無効化するとき、<c>isLightOn</c>を書き足すか
    /// 1.17までは生成途中のチャンクに<c>isLightOn</c>が無く（1.13はどのチャンクにも無い）、
    /// 書き足すと元に無いキーが増えるので足さない
    /// </summary>
    internal bool AddsLightFlag { get; }

    /// <summary>生成済みとみなす<c>Status</c>の値（名前空間を外した形）</summary>
    internal IReadOnlyList<string> FullStatuses { get; }

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

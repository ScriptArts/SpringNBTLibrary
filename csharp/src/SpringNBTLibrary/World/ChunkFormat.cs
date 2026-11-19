namespace SpringNBTLibrary.World;

/// <summary>
/// チャンクの形式の世代の境界
/// ライブラリの内部だけで使う
/// </summary>
internal static class ChunkFormat
{
    /// <summary>
    /// ブロックのパレット要素が<c>id</c> / <c>properties</c>の形式になるDataVersion（26.3）
    /// これ未満は<c>Name</c> / <c>Properties</c>の形式
    /// </summary>
    internal const int PaletteIdFormatDataVersion = 5006;

    /// <summary>DataVersionを指定して読み書きできる最も古いDataVersion（1.13の正式版）</summary>
    internal const int OldestFormatDataVersion = 1519;
}

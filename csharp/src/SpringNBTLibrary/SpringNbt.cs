namespace SpringNBTLibrary;

/// <summary>
/// SpringNBTLibraryのライブラリ全体に関わる定数
/// </summary>
/// <remarks>
/// 対象は26.3で導入されたワールド形式 (DataVersion 5006以降)
/// </remarks>
public static class SpringNbt
{
    /// <summary>
    /// このライブラリが扱えるワールド形式の下限となるDataVersion (26.3)
    /// </summary>
    /// <remarks>
    /// <para>
    /// 26.3でブロックのパレットの形式が変わり、いまの形式になった
    /// 5006はMinecraftがこの形式へ変換するDataVersionで、26.3 Snapshot 7で入った
    /// これ以降のバージョンは、形式が同じであればそのまま読み書きできる
    /// </para>
    /// <para>
    /// これより古いワールドはパレットの書き方が違う
    /// そうしたチャンクは、読み込み時は既定で警告を出し、書き戻しは既定で<see cref="ErrorCode.UnsupportedDataVersion"/>にする
    /// </para>
    /// </remarks>
    public const int MinSupportedDataVersion = 5006;

    /// <summary>動作を確かめたMinecraft Java版のDataVersion (26.3)</summary>
    public const int TargetDataVersion = 5023;
}

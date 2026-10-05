namespace SpringNBTLibrary;

/// <summary>
/// SpringNBTLibraryのライブラリ全体に関わる定数
/// </summary>
/// <remarks>
/// 対象は26.1で導入されたワールド形式 (DataVersion 4786以降)
/// </remarks>
public static class SpringNbt
{
    /// <summary>
    /// このライブラリが扱えるワールド形式の下限となるDataVersion (26.1)
    /// </summary>
    /// <remarks>
    /// <para>
    /// 26.1で次元とプレイヤーデータの置き場が変わり、いまの形式になった
    /// これ以降のバージョンは、形式が同じであればそのまま読み書きできる
    /// </para>
    /// <para>
    /// これより古いワールドは構成そのものが違う
    /// そうしたチャンクは、読み込み時は既定で警告を出し、書き戻しは既定で<see cref="ErrorCode.UnsupportedDataVersion"/>にする
    /// </para>
    /// </remarks>
    public const int MinSupportedDataVersion = 4786;

    /// <summary>動作を確かめたMinecraft Java版のDataVersion (26.2)</summary>
    public const int TargetDataVersion = 4903;
}

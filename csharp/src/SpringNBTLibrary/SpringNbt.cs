namespace SpringNBTLibrary;

/// <summary>
/// SpringNBTLibrary のライブラリ全体に関わる定数
/// </summary>
/// <remarks>
/// 仕様は <c>docs/spec/</c> を唯一の正とする
/// 対象バージョンは Java版 26.2 (DataVersion 4903)
/// </remarks>
public static class SpringNbt
{
    /// <summary>
    /// このライブラリが扱えるワールド形式の下限となる DataVersion (26.1)
    /// </summary>
    /// <remarks>
    /// <para>
    /// 26.1 で次元とプレイヤーデータの置き場が変わり、いまの形式になった
    /// これ以降のバージョンは、形式が同じであればそのまま読み書きできる
    /// </para>
    /// <para>
    /// これより古いワールドは構成そのものが違うので、
    /// 読み込み時に <see cref="ErrorCode.UnsupportedDataVersion"/> の対象になる
    /// </para>
    /// </remarks>
    public const int MinSupportedDataVersion = 4786;

    /// <summary>動作を確かめた Minecraft Java版の DataVersion (26.2)</summary>
    public const int TargetDataVersion = 4903;
}

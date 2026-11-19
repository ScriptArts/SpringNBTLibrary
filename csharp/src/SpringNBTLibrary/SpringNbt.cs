namespace SpringNBTLibrary;

/// <summary>
/// SpringNBTLibraryのライブラリ全体に関わる定数
/// </summary>
/// <remarks>
/// 対象は1.13以降のワールド形式 (DataVersion 1519以降)
/// </remarks>
public static class SpringNbt
{
    /// <summary>
    /// このライブラリが扱えるワールド形式の下限となるDataVersion (1.13)
    /// </summary>
    /// <remarks>
    /// <para>
    /// 1.13でブロックの持ち方が数値のIDからパレットへ変わった
    /// 1519は1.13の正式版のDataVersion
    /// これ以降のチャンクは、読んだときの形式のまま読み書きできる
    /// 1.16（DataVersion 2529）でビット詰めが値を64bitの境目でまたがない形に変わり、
    /// 1.18（DataVersion 2844）でチャンクの本体が<c>Level</c>の外へ出て、
    /// 26.3（DataVersion 5006）でパレットの要素の形が変わったが、どの形式も扱う
    /// </para>
    /// <para>
    /// これより古いチャンクと、DataVersionの無いチャンク（1.9より前）は形式が違う
    /// そうしたチャンクは、読み込み時は既定で警告を出し、書き戻しは既定で<see cref="ErrorCode.UnsupportedDataVersion"/>にする
    /// </para>
    /// </remarks>
    public const int MinSupportedDataVersion = 1519;

    /// <summary>動作を確かめたMinecraft Java版のDataVersion (26.3)</summary>
    public const int TargetDataVersion = 5023;
}

namespace SpringNBTLibrary;

/// <summary>
/// SpringNBTLibraryのライブラリ全体に関わる定数
/// </summary>
/// <remarks>
/// 対象は1.18以降のワールド形式 (DataVersion 2844以降)
/// </remarks>
public static class SpringNbt
{
    /// <summary>
    /// このライブラリが扱えるワールド形式の下限となるDataVersion (1.18)
    /// </summary>
    /// <remarks>
    /// <para>
    /// 1.18でチャンクの本体が<c>Level</c>の外へ出て、セクションがパレット付きのコンテナになった
    /// 2844はMinecraftがこの形式へ変換するDataVersionで、1.18の開発版で入った
    /// これ以降のチャンクは、読んだときの形式のまま読み書きできる
    /// 26.3（DataVersion 5006）でパレットの要素の形が変わったが、どちらの形式も扱う
    /// </para>
    /// <para>
    /// これより古いチャンクは形式が違う
    /// そうしたチャンクは、読み込み時は既定で警告を出し、書き戻しは既定で<see cref="ErrorCode.UnsupportedDataVersion"/>にする
    /// </para>
    /// </remarks>
    public const int MinSupportedDataVersion = 2844;

    /// <summary>動作を確かめたMinecraft Java版のDataVersion (26.3)</summary>
    public const int TargetDataVersion = 5023;
}

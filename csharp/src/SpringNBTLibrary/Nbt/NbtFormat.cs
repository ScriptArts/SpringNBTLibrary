namespace SpringNBTLibrary.Nbt;

/// <summary>
/// NBTのルートタグの並び方
/// </summary>
public enum NbtFormat
{
    /// <summary>
    /// ファイル形式
    /// ルートは「タグID + 名前長 + 名前 + ペイロード」の順に並ぶ
    /// <c>level.dat</c>やチャンクなど、保存されるデータはすべてこちら
    /// </summary>
    Java,

    /// <summary>
    /// ネットワーク形式 (1.20.2以降)
    /// ルートに名前が付かない
    /// </summary>
    Network,
}

/// <summary>
/// 圧縮方式
/// </summary>
public enum Compression
{
    /// <summary>無圧縮</summary>
    None,

    /// <summary>GZip (RFC 1952)</summary>
    Gzip,

    /// <summary>Zlib (RFC 1950)</summary>
    Zlib,

    /// <summary>
    /// 先頭バイトから自動判定する
    /// 読み込み時のみ指定できる
    /// </summary>
    Auto,
}

/// <summary>
/// ルート名とルートタグの組
/// </summary>
/// <remarks>
/// <see cref="NbtFormat.Java"/>ではルート名は通常空文字列だが、
/// 読んだ値をそのまま保持し、書き出しでも同じ値を出力する
/// </remarks>
public sealed class NamedTag
{
    /// <summary>ルート名とルートタグを指定して作る</summary>
    public NamedTag(string name, NbtCompound tag)
    {
        ArgumentNullException.ThrowIfNull(name);
        ArgumentNullException.ThrowIfNull(tag);
        Name = name;
        Tag = tag;
    }

    /// <summary>ルート名</summary>
    public string Name { get; }

    /// <summary>ルートタグ</summary>
    public NbtCompound Tag { get; }

    /// <inheritdoc/>
    public override string ToString() => $"NamedTag(\"{Name}\", {Tag})";
}

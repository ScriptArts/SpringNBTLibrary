namespace SpringNBTLibrary.Nbt;

/// <summary>
/// NBT読み込みのオプション
/// </summary>
public sealed class NbtReadOptions
{
    /// <summary>既定のオプション</summary>
    public static NbtReadOptions Default { get; } = new NbtReadOptions();

    /// <summary>ルートタグの並び方
    /// 既定は<see cref="NbtFormat.Java"/></summary>
    public NbtFormat Format { get; set; } = NbtFormat.Java;

    /// <summary>圧縮方式
    /// 既定は<see cref="Compression.Auto"/>（先頭バイトから判定）</summary>
    public Compression Compression { get; set; } = Compression.Auto;

    /// <summary>ネストの深さ上限
    /// 既定は512</summary>
    public int MaxDepth { get; set; } = 512;

    /// <summary>展開後の総バイト数の上限
    /// 負値なら無制限
    /// 既定は-1</summary>
    public long MaxDecompressedSize { get; set; } = -1;
}

/// <summary>
/// NBT書き込みのオプション
/// </summary>
public sealed class NbtWriteOptions
{
    /// <summary>既定のオプション</summary>
    public static NbtWriteOptions Default { get; } = new NbtWriteOptions();

    /// <summary>無圧縮で書き出すオプション</summary>
    public static NbtWriteOptions Uncompressed { get; } =
        new NbtWriteOptions { Compression = Compression.None };

    /// <summary>ルートタグの並び方
    /// 既定は<see cref="NbtFormat.Java"/></summary>
    public NbtFormat Format { get; set; } = NbtFormat.Java;

    /// <summary>圧縮方式
    /// 既定は<see cref="Compression.Gzip"/></summary>
    public Compression Compression { get; set; } = Compression.Gzip;
}

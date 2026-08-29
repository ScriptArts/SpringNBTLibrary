using System.Globalization;

namespace SpringNBTLibrary.Anvil;

/// <summary>
/// チャンクの絶対座標
/// </summary>
/// <remarks>仕様: <c>docs/spec/20-anvil-region.md</c> 1章</remarks>
public readonly struct ChunkPos : IEquatable<ChunkPos>
{
    /// <summary>座標を指定して作る</summary>
    public ChunkPos(int x, int z)
    {
        X = x;
        Z = z;
    }

    /// <summary>絶対チャンクX座標</summary>
    public int X { get; }

    /// <summary>絶対チャンクZ座標</summary>
    public int Z { get; }

    /// <summary>このチャンクを含むリージョンの座標</summary>
    /// <remarks>算術右シフトなので負の座標でも正しく求まる</remarks>
    public RegionPos Region => new RegionPos(X >> 5, Z >> 5);

    /// <summary>リージョン内でのX位置 (0..31)</summary>
    public int LocalX => X & 31;

    /// <summary>リージョン内でのZ位置 (0..31)</summary>
    public int LocalZ => Z & 31;

    /// <summary>ロケーションテーブル内の添字 (0..1023)</summary>
    public int Index => LocalX + (LocalZ * 32);

    /// <inheritdoc/>
    public bool Equals(ChunkPos other) => other.X == X && other.Z == Z;

    /// <inheritdoc/>
    public override bool Equals(object? obj) => obj is ChunkPos other && Equals(other);

    /// <inheritdoc/>
    public override int GetHashCode() => HashCode.Combine(X, Z);

    /// <summary>2つの座標が等しいか</summary>
    public static bool operator ==(ChunkPos left, ChunkPos right) => left.Equals(right);

    /// <summary>2つの座標が異なるか</summary>
    public static bool operator !=(ChunkPos left, ChunkPos right) => !left.Equals(right);

    /// <inheritdoc/>
    public override string ToString() =>
        string.Create(CultureInfo.InvariantCulture, $"ChunkPos({X}, {Z})");
}

/// <summary>
/// リージョンの座標
/// 1リージョンは 32×32 チャンクを担当する
/// </summary>
public readonly struct RegionPos : IEquatable<RegionPos>
{
    /// <summary>座標を指定して作る</summary>
    public RegionPos(int x, int z)
    {
        X = x;
        Z = z;
    }

    /// <summary>リージョンX座標</summary>
    public int X { get; }

    /// <summary>リージョンZ座標</summary>
    public int Z { get; }

    /// <summary>このリージョンのファイル名（<c>r.X.Z.mca</c>）</summary>
    public string FileName =>
        string.Create(CultureInfo.InvariantCulture, $"r.{X}.{Z}.mca");

    /// <summary>
    /// <c>r.X.Z.mca</c> 形式のファイル名から座標を得る
    /// 解釈できなければ null
    /// </summary>
    public static RegionPos? FromFileName(string fileName)
    {
        ArgumentNullException.ThrowIfNull(fileName);

        string[] parts = fileName.Split('.');

        // "r" "<x>" "<z>" "mca" の 4 つに分かれるはず
        if (parts.Length != 4 || parts[0] != "r" || parts[3] != "mca")
        {
            return null;
        }

        if (!int.TryParse(parts[1], NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out int x))
        {
            return null;
        }

        if (!int.TryParse(parts[2], NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out int z))
        {
            return null;
        }

        return new RegionPos(x, z);
    }

    /// <inheritdoc/>
    public bool Equals(RegionPos other) => other.X == X && other.Z == Z;

    /// <inheritdoc/>
    public override bool Equals(object? obj) => obj is RegionPos other && Equals(other);

    /// <inheritdoc/>
    public override int GetHashCode() => HashCode.Combine(X, Z);

    /// <summary>2つの座標が等しいか</summary>
    public static bool operator ==(RegionPos left, RegionPos right) => left.Equals(right);

    /// <summary>2つの座標が異なるか</summary>
    public static bool operator !=(RegionPos left, RegionPos right) => !left.Equals(right);

    /// <inheritdoc/>
    public override string ToString() =>
        string.Create(CultureInfo.InvariantCulture, $"RegionPos({X}, {Z})");
}

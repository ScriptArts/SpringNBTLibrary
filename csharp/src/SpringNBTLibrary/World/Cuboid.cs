using System.Globalization;

namespace SpringNBTLibrary.World;

/// <summary>
/// ブロック座標の直方体の範囲
/// </summary>
/// <remarks>
/// <para>両端を含む</para>
/// <para><c>Of(0, 0, 0, 0, 0, 0)</c>は1ブロック</para>
/// <para>範囲内のブロックを順に処理したいときに使う</para>
/// </remarks>
public sealed class Cuboid : IEquatable<Cuboid>
{
    /// <summary>両端の座標から作る</summary>
    /// <remarks>大小の順序は問わない
    /// 内部で小さいほうを最小に揃える</remarks>
    public Cuboid(BlockPos first, BlockPos second)
    {
        ArgumentNullException.ThrowIfNull(first);
        ArgumentNullException.ThrowIfNull(second);

        MinX = Math.Min(first.X, second.X);
        MinY = Math.Min(first.Y, second.Y);
        MinZ = Math.Min(first.Z, second.Z);
        MaxX = Math.Max(first.X, second.X);
        MaxY = Math.Max(first.Y, second.Y);
        MaxZ = Math.Max(first.Z, second.Z);
    }

    /// <summary>両端の座標から作る</summary>
    public static Cuboid Of(int x1, int y1, int z1, int x2, int y2, int z2) =>
        new Cuboid(new BlockPos(x1, y1, z1), new BlockPos(x2, y2, z2));

    /// <summary>Xの最小値</summary>
    public int MinX { get; }

    /// <summary>Yの最小値</summary>
    public int MinY { get; }

    /// <summary>Zの最小値</summary>
    public int MinZ { get; }

    /// <summary>Xの最大値（含む）</summary>
    public int MaxX { get; }

    /// <summary>Yの最大値（含む）</summary>
    public int MaxY { get; }

    /// <summary>Zの最大値（含む）</summary>
    public int MaxZ { get; }

    /// <summary>X方向の長さ</summary>
    public int SizeX => MaxX - MinX + 1;

    /// <summary>Y方向の長さ</summary>
    public int SizeY => MaxY - MinY + 1;

    /// <summary>Z方向の長さ</summary>
    public int SizeZ => MaxZ - MinZ + 1;

    /// <summary>含まれるブロックの個数</summary>
    public long Volume => (long)SizeX * SizeY * SizeZ;

    /// <summary>その座標が範囲に含まれるか</summary>
    public bool Contains(int x, int y, int z) =>
        x >= MinX && x <= MaxX && y >= MinY && y <= MaxY && z >= MinZ && z <= MaxZ;

    /// <summary>
    /// 範囲内の座標を順に返す
    /// </summary>
    /// <remarks>並びはY、Z、Xの順で、Xがいちばん内側で動く</remarks>
    public IEnumerable<BlockPos> Positions()
    {
        // Xがいちばん内側で動くので、同じチャンクの並びを続けて扱える
        for (int y = MinY; y <= MaxY; y++)
        {
            // Zを進めながら、その行のXを端から端まで返す
            for (int z = MinZ; z <= MaxZ; z++)
            {
                // Xはチャンク内で連続するので、まとめて扱える
                for (int x = MinX; x <= MaxX; x++)
                {
                    yield return new BlockPos(x, y, z);
                }
            }
        }
    }

    /// <inheritdoc/>
    public bool Equals(Cuboid? other)
    {
        if (other is null)
        {
            return false;
        }

        return other.MinX == MinX && other.MinY == MinY && other.MinZ == MinZ
            && other.MaxX == MaxX && other.MaxY == MaxY && other.MaxZ == MaxZ;
    }

    /// <inheritdoc/>
    public override bool Equals(object? obj) => Equals(obj as Cuboid);

    /// <inheritdoc/>
    public override int GetHashCode() => HashCode.Combine(MinX, MinY, MinZ, MaxX, MaxY, MaxZ);

    /// <inheritdoc/>
    public override string ToString() => string.Create(
        CultureInfo.InvariantCulture, $"({MinX}, {MinY}, {MinZ})-({MaxX}, {MaxY}, {MaxZ})");
}

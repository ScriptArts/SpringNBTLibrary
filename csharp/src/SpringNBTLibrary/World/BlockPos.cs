using System.Globalization;
using SpringNBTLibrary.Anvil;

namespace SpringNBTLibrary.World;

/// <summary>
/// ブロックの絶対座標
/// </summary>
/// <remarks>仕様: <c>docs/spec/30-chunk-format.md</c> 5章</remarks>
public sealed class BlockPos : IEquatable<BlockPos>
{
    /// <summary>座標を指定して作る</summary>
    public BlockPos(int x, int y, int z)
    {
        X = x;
        Y = y;
        Z = z;
    }

    /// <summary>X座標</summary>
    public int X { get; }

    /// <summary>Y座標</summary>
    public int Y { get; }

    /// <summary>Z座標</summary>
    public int Z { get; }

    /// <summary>この座標を含むチャンクの座標</summary>
    /// <remarks>算術右シフトなので負の座標でも正しく求まる</remarks>
    public ChunkPos ChunkPos => new ChunkPos(X >> 4, Z >> 4);

    /// <summary>チャンク内でのX位置 (0..15)</summary>
    public int LocalX => X & 15;

    /// <summary>チャンク内でのZ位置 (0..15)</summary>
    public int LocalZ => Z & 15;

    /// <summary>各軸へずらした座標を返す</summary>
    public BlockPos Offset(int dx, int dy, int dz) => new BlockPos(X + dx, Y + dy, Z + dz);

    /// <inheritdoc/>
    public bool Equals(BlockPos? other)
    {
        if (other is null)
        {
            return false;
        }

        return other.X == X && other.Y == Y && other.Z == Z;
    }

    /// <inheritdoc/>
    public override bool Equals(object? obj) => Equals(obj as BlockPos);

    /// <inheritdoc/>
    public override int GetHashCode() => HashCode.Combine(X, Y, Z);

    /// <inheritdoc/>
    public override string ToString() =>
        string.Create(CultureInfo.InvariantCulture, $"({X}, {Y}, {Z})");
}

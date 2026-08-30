using SpringNBTLibrary.Anvil;
using SpringNBTLibrary.World;

namespace SpringNBTLibrary.Tests;

/// <summary>
/// ブロック座標と範囲。仕様: docs/spec/30-chunk-format.md 5章
/// </summary>
public class BlockPosTests
{
    [Fact]
    public void ResolvesChunkAndLocalCoordinates()
    {
        BlockPos pos = new BlockPos(100, 64, -200);

        // 算術右シフトなので負の座標でも正しく求まる
        Assert.Equal(new ChunkPos(6, -13), pos.ChunkPos);
        Assert.Equal(4, pos.LocalX);
        Assert.Equal(8, pos.LocalZ);
    }

    [Fact]
    public void OffsetsEachAxis()
    {
        BlockPos moved = new BlockPos(1, 2, 3).Offset(10, -20, 30);

        Assert.Equal(new BlockPos(11, -18, 33), moved);
        Assert.False(moved.Equals(new BlockPos(11, -18, 34)));
    }

    [Fact]
    public void NormalizesTheOrderOfTheTwoCorners()
    {
        // 端の順序は問わない
        Cuboid box = Cuboid.Of(10, 20, 30, 0, 5, 15);

        Assert.Equal(0, box.MinX);
        Assert.Equal(10, box.MaxX);
        Assert.Equal(11, box.SizeX);
        Assert.Equal(16, box.SizeY);
        Assert.Equal(16, box.SizeZ);
    }

    [Fact]
    public void ContainsOnlyThePositionsInside()
    {
        Cuboid box = Cuboid.Of(0, 0, 0, 1, 1, 1);

        Assert.True(box.Contains(0, 0, 0));
        Assert.True(box.Contains(1, 1, 1));
        Assert.False(box.Contains(2, 0, 0));
        Assert.False(box.Contains(0, -1, 0));
    }

    [Fact]
    public void WalksEveryPositionInside()
    {
        Cuboid box = Cuboid.Of(0, 0, 0, 1, 2, 3);
        List<BlockPos> positions = box.Positions().ToList();

        Assert.Equal(box.Volume, positions.Count);
        Assert.Equal(2 * 3 * 4, positions.Count);

        // 並びは Y、Z、X の順で、X がいちばん内側で動く
        Assert.Equal(new BlockPos(0, 0, 0), positions[0]);
        Assert.Equal(new BlockPos(1, 0, 0), positions[1]);
        Assert.Equal(new BlockPos(0, 0, 1), positions[2]);
        Assert.Equal(new BlockPos(1, 2, 3), positions[^1]);
    }

    [Fact]
    public void OneBlockBoxHasVolumeOne()
    {
        Cuboid box = Cuboid.Of(5, 5, 5, 5, 5, 5);

        Assert.Equal(1, box.Volume);
        Assert.Single(box.Positions());
    }
}

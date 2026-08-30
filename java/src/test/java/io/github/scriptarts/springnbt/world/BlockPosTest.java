package io.github.scriptarts.springnbt.world;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import io.github.scriptarts.springnbt.anvil.ChunkPos;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** ブロック座標と範囲。仕様: {@code docs/spec/30-chunk-format.md} 5章 */
class BlockPosTest {

    @Test
    @DisplayName("チャンク座標とチャンク内位置を求められる")
    void resolvesChunkAndLocalCoordinates() {
        BlockPos pos = new BlockPos(100, 64, -200);

        // 算術右シフトなので負の座標でも正しく求まる
        assertEquals(new ChunkPos(6, -13), pos.chunkPos());
        assertEquals(4, pos.localX());
        assertEquals(8, pos.localZ());
    }

    @Test
    @DisplayName("各軸へずらせる")
    void offsetsEachAxis() {
        BlockPos moved = new BlockPos(1, 2, 3).offset(10, -20, 30);

        assertEquals(new BlockPos(11, -18, 33), moved);
        assertFalse(moved.equals(new BlockPos(11, -18, 34)));
    }

    @Test
    @DisplayName("両端の順序は問わない")
    void normalizesTheOrderOfTheTwoCorners() {
        Cuboid box = Cuboid.of(10, 20, 30, 0, 5, 15);

        assertEquals(0, box.minX());
        assertEquals(10, box.maxX());
        assertEquals(11, box.sizeX());
        assertEquals(16, box.sizeY());
        assertEquals(16, box.sizeZ());
    }

    @Test
    @DisplayName("範囲の内側だけを含む")
    void containsOnlyThePositionsInside() {
        Cuboid box = Cuboid.of(0, 0, 0, 1, 1, 1);

        assertTrue(box.contains(0, 0, 0));
        assertTrue(box.contains(1, 1, 1));
        assertFalse(box.contains(2, 0, 0));
        assertFalse(box.contains(0, -1, 0));
    }

    @Test
    @DisplayName("範囲内の座標をすべて返す")
    void walksEveryPositionInside() {
        Cuboid box = Cuboid.of(0, 0, 0, 1, 2, 3);
        List<BlockPos> positions = new ArrayList<>();

        // 範囲内の座標を順に集める
        for (BlockPos pos : box.positions()) {
            positions.add(pos);
        }

        assertEquals(box.volume(), positions.size());
        assertEquals(2 * 3 * 4, positions.size());

        // 並びは Y、Z、X の順で、X がいちばん内側で動く
        assertEquals(new BlockPos(0, 0, 0), positions.get(0));
        assertEquals(new BlockPos(1, 0, 0), positions.get(1));
        assertEquals(new BlockPos(0, 0, 1), positions.get(2));
        assertEquals(new BlockPos(1, 2, 3), positions.get(positions.size() - 1));
    }

    @Test
    @DisplayName("1ブロックの範囲は体積 1")
    void oneBlockBoxHasVolumeOne() {
        Cuboid box = Cuboid.of(5, 5, 5, 5, 5, 5);
        assertEquals(1, box.volume());

        int count = 0;

        // 1 つだけ返ることを数えて確かめる
        for (BlockPos pos : box.positions()) {
            count++;
        }

        assertEquals(1, count);
    }
}

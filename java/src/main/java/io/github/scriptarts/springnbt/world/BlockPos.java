package io.github.scriptarts.springnbt.world;

import io.github.scriptarts.springnbt.anvil.ChunkPos;

/**
 * ブロックの絶対座標
 *
 * <p>仕様: {@code docs/spec/30-chunk-format.md} 5章
 *
 * @param x X座標
 * @param y Y座標
 * @param z Z座標
 */
public record BlockPos(int x, int y, int z) {

    /**
     * この座標を含むチャンクの座標
     *
     * <p>算術右シフトなので負の座標でも正しく求まる
     *
     * @return チャンク座標
     */
    public ChunkPos chunkPos() {
        return new ChunkPos(x >> 4, z >> 4);
    }

    /**
     * チャンク内でのX位置 (0..15)
     *
     * @return 位置
     */
    public int localX() {
        return x & 15;
    }

    /**
     * チャンク内でのZ位置 (0..15)
     *
     * @return 位置
     */
    public int localZ() {
        return z & 15;
    }

    /**
     * 各軸へずらした座標を返す
     *
     * @param dx X方向のずれ
     * @param dy Y方向のずれ
     * @param dz Z方向のずれ
     * @return ずらした座標
     */
    public BlockPos offset(int dx, int dy, int dz) {
        return new BlockPos(x + dx, y + dy, z + dz);
    }

    @Override
    public String toString() {
        return "(" + x + ", " + y + ", " + z + ")";
    }
}

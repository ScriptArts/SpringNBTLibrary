package io.github.scriptarts.springnbt.anvil;

/**
 * チャンクの絶対座標。
 *
 * <p>仕様: {@code docs/spec/20-anvil-region.md} 1章
 *
 * @param x 絶対チャンクX座標
 * @param z 絶対チャンクZ座標
 */
public record ChunkPos(int x, int z) {

    /**
     * このチャンクを含むリージョンの座標。
     *
     * <p>算術右シフトなので負の座標でも正しく求まる。
     *
     * @return リージョン座標
     */
    public RegionPos region() {
        return new RegionPos(x >> 5, z >> 5);
    }

    /**
     * リージョン内でのX位置 (0..31)。
     *
     * @return 位置
     */
    public int localX() {
        return x & 31;
    }

    /**
     * リージョン内でのZ位置 (0..31)。
     *
     * @return 位置
     */
    public int localZ() {
        return z & 31;
    }

    /**
     * ロケーションテーブル内の添字 (0..1023)。
     *
     * @return 添字
     */
    public int index() {
        return localX() + (localZ() * 32);
    }
}

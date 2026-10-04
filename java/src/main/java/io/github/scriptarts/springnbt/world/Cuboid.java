package io.github.scriptarts.springnbt.world;

import java.util.Iterator;
import java.util.NoSuchElementException;
import java.util.Objects;

/**
 * ブロック座標の直方体の範囲
 *
 * <p>両端を含む
 * {@code of(0, 0, 0, 0, 0, 0)}は1ブロック
 *
 * <p>範囲内のブロックを順に処理したいときに使う
 */
public final class Cuboid {

    private final int minX;
    private final int minY;
    private final int minZ;
    private final int maxX;
    private final int maxY;
    private final int maxZ;

    /**
     * 両端の座標から作る
     *
     * <p>大小の順序は問わない
     * 内部で小さいほうを最小に揃える
     *
     * @param first 端の座標
     * @param second もう一方の端の座標
     */
    public Cuboid(BlockPos first, BlockPos second) {
        Objects.requireNonNull(first, "first");
        Objects.requireNonNull(second, "second");

        minX = Math.min(first.x(), second.x());
        minY = Math.min(first.y(), second.y());
        minZ = Math.min(first.z(), second.z());
        maxX = Math.max(first.x(), second.x());
        maxY = Math.max(first.y(), second.y());
        maxZ = Math.max(first.z(), second.z());
    }

    /**
     * 両端の座標から作る
     *
     * @param x1 一方の端のX座標
     * @param y1 一方の端のY座標
     * @param z1 一方の端のZ座標
     * @param x2 もう一方の端のX座標
     * @param y2 もう一方の端のY座標
     * @param z2 もう一方の端のZ座標
     * @return 範囲
     */
    public static Cuboid of(int x1, int y1, int z1, int x2, int y2, int z2) {
        return new Cuboid(new BlockPos(x1, y1, z1), new BlockPos(x2, y2, z2));
    }

    /**
     * Xの最小値
     *
     * @return 座標
     */
    public int minX() {
        return minX;
    }

    /**
     * Yの最小値
     *
     * @return 座標
     */
    public int minY() {
        return minY;
    }

    /**
     * Zの最小値
     *
     * @return 座標
     */
    public int minZ() {
        return minZ;
    }

    /**
     * Xの最大値（含む）
     *
     * @return 座標
     */
    public int maxX() {
        return maxX;
    }

    /**
     * Yの最大値（含む）
     *
     * @return 座標
     */
    public int maxY() {
        return maxY;
    }

    /**
     * Zの最大値（含む）
     *
     * @return 座標
     */
    public int maxZ() {
        return maxZ;
    }

    /**
     * X方向の長さ
     *
     * @return 長さ
     */
    public int sizeX() {
        return maxX - minX + 1;
    }

    /**
     * Y方向の長さ
     *
     * @return 長さ
     */
    public int sizeY() {
        return maxY - minY + 1;
    }

    /**
     * Z方向の長さ
     *
     * @return 長さ
     */
    public int sizeZ() {
        return maxZ - minZ + 1;
    }

    /**
     * 含まれるブロックの個数
     *
     * @return 個数
     */
    public long volume() {
        return (long) sizeX() * sizeY() * sizeZ();
    }

    /**
     * その座標が範囲に含まれるか
     *
     * @param x X座標
     * @param y Y座標
     * @param z Z座標
     * @return 含まれればtrue
     */
    public boolean contains(int x, int y, int z) {
        return x >= minX && x <= maxX && y >= minY && y <= maxY && z >= minZ && z <= maxZ;
    }

    /**
     * 範囲内の座標を順に返す
     *
     * <p>並びはY、Z、Xの順で、Xがいちばん内側で動く
     *
     * @return 座標の並び
     */
    public Iterable<BlockPos> positions() {
        return () -> new Iterator<BlockPos>() {
            private int x = minX;
            private int y = minY;
            private int z = minZ;
            private boolean done = volume() == 0;

            @Override
            public boolean hasNext() {
                return !done;
            }

            @Override
            public BlockPos next() {
                if (done) {
                    throw new NoSuchElementException();
                }

                BlockPos current = new BlockPos(x, y, z);
                x++;

                // Xがいちばん内側で動くので、同じチャンクの並びを続けて扱える
                if (x > maxX) {
                    x = minX;
                    z++;

                    if (z > maxZ) {
                        z = minZ;
                        y++;

                        if (y > maxY) {
                            done = true;
                        }
                    }
                }

                return current;
            }
        };
    }

    @Override
    public boolean equals(Object other) {
        if (!(other instanceof Cuboid box)) {
            return false;
        }

        return box.minX == minX && box.minY == minY && box.minZ == minZ
                && box.maxX == maxX && box.maxY == maxY && box.maxZ == maxZ;
    }

    @Override
    public int hashCode() {
        return Objects.hash(minX, minY, minZ, maxX, maxY, maxZ);
    }

    @Override
    public String toString() {
        return "(" + minX + ", " + minY + ", " + minZ + ")-("
                + maxX + ", " + maxY + ", " + maxZ + ")";
    }
}

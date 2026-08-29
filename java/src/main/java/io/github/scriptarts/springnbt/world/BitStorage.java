package io.github.scriptarts.springnbt.world;

import io.github.scriptarts.springnbt.SpringNbtException;
import java.util.Objects;

/**
 * 添字を 64bit 整数の配列へ詰めた表現
 * 1.16 以降の<strong>跨ぎなし</strong>パッキング
 *
 * <p>1 つの {@code long} に入りきらない分は、その {@code long} の残りビットを未使用のまま捨て、
 * 次の {@code long} の最下位ビットから始める
 *
 * <p>仕様: {@code docs/spec/31-paletted-container.md} 2章
 */
public final class BitStorage {

    private final long[] data;
    private final int bitsPerEntry;
    private final int entryCount;

    private BitStorage(long[] data, int bitsPerEntry, int entryCount) {
        this.data = data;
        this.bitsPerEntry = bitsPerEntry;
        this.entryCount = entryCount;
    }

    /**
     * 1 エントリあたりのビット数
     *
     * @return ビット数
     */
    public int bitsPerEntry() {
        return bitsPerEntry;
    }

    /**
     * エントリ数
     * ブロックなら 4096、バイオームなら 64
     *
     * @return エントリ数
     */
    public int entryCount() {
        return entryCount;
    }

    /**
     * 1 つの {@code long} に入るエントリ数
     *
     * @return エントリ数
     */
    public int valuesPerLong() {
        return 64 / bitsPerEntry;
    }

    /**
     * すべてゼロで初期化した記憶域を作る
     *
     * @param bitsPerEntry ビット幅
     * @param entryCount   エントリ数
     * @return 記憶域
     */
    public static BitStorage create(int bitsPerEntry, int entryCount) {
        if (bitsPerEntry < 1 || bitsPerEntry > 32) {
            throw SpringNbtException.invalidArgument("ビット幅が範囲外: " + bitsPerEntry);
        }

        return new BitStorage(new long[longCount(bitsPerEntry, entryCount)], bitsPerEntry, entryCount);
    }

    /**
     * 既存の {@code long} 配列から作る
     *
     * @param data         packed な配列
     * @param bitsPerEntry パレット長から求めたビット幅
     * @param entryCount   エントリ数
     * @param lenient      true なら配列長からビット幅を逆算して読む（第三者ツール由来の救済）
     * @return 記憶域
     * @throws SpringNbtException 配列長が期待値と一致しない場合
     */
    public static BitStorage fromLongs(long[] data, int bitsPerEntry, int entryCount, boolean lenient) {
        Objects.requireNonNull(data, "data");
        int expected = longCount(bitsPerEntry, entryCount);

        if (data.length == expected) {
            return new BitStorage(data, bitsPerEntry, entryCount);
        }

        if (!lenient) {
            throw SpringNbtException.malformed("bits=" + bitsPerEntry + " なら data は "
                    + expected + " long のはずだが " + data.length + " long");
        }

        // 配列長からビット幅を逆算する
        // 合致する幅が無ければ諦める
        for (int candidate = 1; candidate <= 32; candidate++) {
            if (longCount(candidate, entryCount) == data.length) {
                return new BitStorage(data, candidate, entryCount);
            }
        }

        throw SpringNbtException.malformed("data の長さ " + data.length
                + " long に合うビット幅が無い（エントリ数 " + entryCount + "）");
    }

    /**
     * 必要な {@code long} の個数を求める
     *
     * @param bitsPerEntry ビット幅
     * @param entryCount   エントリ数
     * @return 個数
     */
    public static int longCount(int bitsPerEntry, int entryCount) {
        int valuesPerLong = 64 / bitsPerEntry;
        return (entryCount + valuesPerLong - 1) / valuesPerLong;
    }

    /**
     * 添字の値を取り出す
     *
     * @param index 添字
     * @return 値
     */
    public int get(int index) {
        checkIndex(index);

        int perLong = valuesPerLong();
        int longIndex = index / perLong;
        int bitOffset = (index % perLong) * bitsPerEntry;
        long mask = (1L << bitsPerEntry) - 1;

        // 算術シフトだと上位ビットが伸びるので、必ず論理右シフトを使う
        return (int) ((data[longIndex] >>> bitOffset) & mask);
    }

    /**
     * 添字の値を書き換える
     *
     * @param index 添字
     * @param value 値
     */
    public void set(int index, int value) {
        checkIndex(index);
        long limit = 1L << bitsPerEntry;

        if (value < 0 || value >= limit) {
            throw SpringNbtException.invalidArgument(
                    "値がビット幅に収まらない: " + value + " (0.." + (limit - 1) + ")");
        }

        int perLong = valuesPerLong();
        int longIndex = index / perLong;
        int bitOffset = (index % perLong) * bitsPerEntry;
        long mask = ((1L << bitsPerEntry) - 1) << bitOffset;

        data[longIndex] = (data[longIndex] & ~mask) | (((long) value << bitOffset) & mask);
    }

    /**
     * packed な配列を返す
     * 内部の配列をそのまま返す（コピーしない）
     *
     * @return 配列
     */
    public long[] toLongs() {
        return data;
    }

    /**
     * 別のビット幅へ詰め直した新しい記憶域を返す
     *
     * @param newBitsPerEntry 新しいビット幅
     * @return 記憶域
     */
    public BitStorage resize(int newBitsPerEntry) {
        BitStorage result = create(newBitsPerEntry, entryCount);

        // 全エントリを読み直して新しい幅で詰める
        for (int index = 0; index < entryCount; index++) {
            result.set(index, get(index));
        }

        return result;
    }

    private void checkIndex(int index) {
        if (index < 0 || index >= entryCount) {
            throw SpringNbtException.invalidArgument(
                    "添字が範囲外: " + index + " (0.." + (entryCount - 1) + ")");
        }
    }
}

package io.github.scriptarts.springnbt.world;

import io.github.scriptarts.springnbt.SpringNbtException;
import java.util.Objects;

/**
 * 添字を64bit整数の配列へ詰めた表現
 * 公開の入口は1.16以降の<strong>跨ぎなし</strong>パッキング
 *
 * <p>1つの{@code long}に入りきらない分は、その{@code long}の残りビットを未使用のまま捨て、
 * 次の{@code long}の最下位ビットから始める
 *
 * <p>DataVersionが2529より前（1.13から1.15）の形式は、値が64bitの境目をまたぐ詰め方で、
 * 内部の入口からだけ使う
 */
public final class BitStorage {

    private final long[] data;
    private final int bitsPerEntry;
    private final int entryCount;
    private final boolean spanning;

    private BitStorage(long[] data, int bitsPerEntry, int entryCount, boolean spanning) {
        this.data = data;
        this.bitsPerEntry = bitsPerEntry;
        this.entryCount = entryCount;
        this.spanning = spanning;
    }

    /**
     * 1エントリあたりのビット数
     *
     * @return ビット数
     */
    public int bitsPerEntry() {
        return bitsPerEntry;
    }

    /**
     * エントリ数
     * ブロックなら4096、バイオームなら64
     *
     * @return エントリ数
     */
    public int entryCount() {
        return entryCount;
    }

    /**
     * 1つの{@code long}に入るエントリ数
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
        return create(bitsPerEntry, entryCount, false);
    }

    /**
     * 詰め方を指定して、すべてゼロで初期化した記憶域を作る
     *
     * @param bitsPerEntry ビット幅
     * @param entryCount   エントリ数
     * @param spanning     64bitの境目をまたいで詰めるか
     * @return 記憶域
     */
    static BitStorage create(int bitsPerEntry, int entryCount, boolean spanning) {
        if (bitsPerEntry < 1 || bitsPerEntry > 32) {
            throw SpringNbtException.invalidArgument("ビット幅が範囲外: " + bitsPerEntry);
        }

        return new BitStorage(new long[longCount(bitsPerEntry, entryCount, spanning)], bitsPerEntry, entryCount, spanning);
    }

    /**
     * 既存の{@code long}配列から作る
     *
     * @param data         packedな配列
     * @param bitsPerEntry パレット長から求めたビット幅
     * @param entryCount   エントリ数
     * @param lenient      trueなら、配列長が期待値と違う場合に配列長からビット幅を逆算して読む
     * 第三者ツールが書いたデータの救済用
     * @return 記憶域
     * @throws SpringNbtException 配列長が期待値と一致しない場合
     */
    public static BitStorage fromLongs(long[] data, int bitsPerEntry, int entryCount, boolean lenient) {
        return fromLongs(data, bitsPerEntry, entryCount, lenient, false);
    }

    /**
     * 詰め方を指定して、既存の{@code long}配列から作る
     *
     * @param data         packedな配列
     * @param bitsPerEntry パレット長から求めたビット幅
     * @param entryCount   エントリ数
     * @param lenient      trueなら、配列長が期待値と違う場合に配列長からビット幅を逆算して読む
     * @param spanning     64bitの境目をまたいで詰めるか
     * @return 記憶域
     * @throws SpringNbtException 配列長が期待値と一致しない場合
     */
    static BitStorage fromLongs(
            long[] data, int bitsPerEntry, int entryCount, boolean lenient, boolean spanning) {
        Objects.requireNonNull(data, "data");
        int expected = longCount(bitsPerEntry, entryCount, spanning);

        if (data.length == expected) {
            return new BitStorage(data, bitsPerEntry, entryCount, spanning);
        }

        if (!lenient) {
            throw SpringNbtException.malformed("bits=" + bitsPerEntry + " なら data は "
                    + expected + " long のはずだが " + data.length + " long");
        }

        // 配列長からビット幅を逆算する
        // 合致する幅が無ければ諦める
        for (int candidate = 1; candidate <= 32; candidate++) {
            if (longCount(candidate, entryCount, spanning) == data.length) {
                return new BitStorage(data, candidate, entryCount, spanning);
            }
        }

        throw SpringNbtException.malformed("data の長さ " + data.length
                + " long に合うビット幅が無い（エントリ数 " + entryCount + "）");
    }

    /**
     * 必要な{@code long}の個数を求める
     *
     * @param bitsPerEntry ビット幅
     * @param entryCount   エントリ数
     * @return 個数
     */
    public static int longCount(int bitsPerEntry, int entryCount) {
        return longCount(bitsPerEntry, entryCount, false);
    }

    /**
     * 詰め方を指定して、必要な{@code long}の個数を求める
     *
     * @param bitsPerEntry ビット幅
     * @param entryCount   エントリ数
     * @param spanning     64bitの境目をまたいで詰めるか
     * @return 個数
     */
    static int longCount(int bitsPerEntry, int entryCount, boolean spanning) {
        // またぐ詰め方なら、全ビットを隙間なく並べた長さになる
        if (spanning) {
            return (int) (((long) entryCount * bitsPerEntry + 63) / 64);
        }

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

        long mask = (1L << bitsPerEntry) - 1;

        // またぐ詰め方なら、隣のlongへ続く分を上位ビットとして足す
        if (spanning) {
            long bitIndex = (long) index * bitsPerEntry;
            int spanLongIndex = (int) (bitIndex >> 6);
            int spanOffset = (int) (bitIndex & 63);
            long spanValue = data[spanLongIndex] >>> spanOffset;

            // 次のlongへ続く場合は、続き分を左へずらして重ねる
            if (spanOffset + bitsPerEntry > 64) {
                spanValue |= data[spanLongIndex + 1] << (64 - spanOffset);
            }

            return (int) (spanValue & mask);
        }

        int perLong = valuesPerLong();
        int longIndex = index / perLong;
        int bitOffset = (index % perLong) * bitsPerEntry;

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

        // またぐ詰め方なら、隣のlongへ続く分も書き込む
        if (spanning) {
            long bitIndex = (long) index * bitsPerEntry;
            int spanLongIndex = (int) (bitIndex >> 6);
            int spanOffset = (int) (bitIndex & 63);
            long spanMask = (1L << bitsPerEntry) - 1;

            data[spanLongIndex] = (data[spanLongIndex] & ~(spanMask << spanOffset))
                    | ((long) value << spanOffset);

            // 次のlongへ続く場合は、続き分の下位ビットを書き換える
            if (spanOffset + bitsPerEntry > 64) {
                int shift = 64 - spanOffset;
                long highMask = spanMask >>> shift;
                data[spanLongIndex + 1] = (data[spanLongIndex + 1] & ~highMask)
                        | ((long) value >>> shift);
            }

            return;
        }

        int perLong = valuesPerLong();
        int longIndex = index / perLong;
        int bitOffset = (index % perLong) * bitsPerEntry;
        long mask = ((1L << bitsPerEntry) - 1) << bitOffset;

        data[longIndex] = (data[longIndex] & ~mask) | (((long) value << bitOffset) & mask);
    }

    /**
     * packedな配列を返す
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
        BitStorage result = create(newBitsPerEntry, entryCount, spanning);

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

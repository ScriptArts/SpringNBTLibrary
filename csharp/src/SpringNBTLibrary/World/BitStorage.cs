namespace SpringNBTLibrary.World;

/// <summary>
/// 添字を64bit整数の配列へ詰めた表現
/// 公開の入口は1.16以降の**跨ぎなし**パッキング
/// </summary>
/// <remarks>
/// <para>
/// 1つの<c>i64</c>に入りきらない分は、その<c>i64</c>の残りビットを未使用のまま捨て、
/// 次の<c>i64</c>の最下位ビットから始める
/// </para>
/// <para>
/// DataVersionが2529より前（1.13から1.15）の形式は、値が64bitの境目をまたぐ詰め方で、
/// 内部の入口からだけ使う
/// </para>
/// </remarks>
public sealed class BitStorage
{
    private readonly long[] data;

    private BitStorage(long[] data, int bitsPerEntry, int entryCount, bool spanning)
    {
        this.data = data;
        BitsPerEntry = bitsPerEntry;
        EntryCount = entryCount;
        Spanning = spanning;
    }

    /// <summary>64bitの境目をまたいで詰めるか
    /// 1.13から1.15までの形式ならtrue</summary>
    internal bool Spanning { get; }

    /// <summary>1エントリあたりのビット数</summary>
    public int BitsPerEntry { get; }

    /// <summary>エントリ数
    /// ブロックなら4096、バイオームなら64</summary>
    public int EntryCount { get; }

    /// <summary>1つの<c>i64</c>に入るエントリ数</summary>
    public int ValuesPerLong => 64 / BitsPerEntry;

    /// <summary>すべてゼロで初期化した記憶域を作る</summary>
    public static BitStorage Create(int bitsPerEntry, int entryCount)
    {
        return Create(bitsPerEntry, entryCount, false);
    }

    /// <summary>詰め方を指定して、すべてゼロで初期化した記憶域を作る</summary>
    internal static BitStorage Create(int bitsPerEntry, int entryCount, bool spanning)
    {
        if (bitsPerEntry < 1 || bitsPerEntry > 32)
        {
            throw SpringNbtException.InvalidArgument($"ビット幅が範囲外: {bitsPerEntry}");
        }

        return new BitStorage(new long[LongCount(bitsPerEntry, entryCount, spanning)], bitsPerEntry, entryCount, spanning);
    }

    /// <summary>
    /// 既存の<c>i64</c>配列から作る
    /// </summary>
    /// <param name="data">packedな配列</param>
    /// <param name="bitsPerEntry">パレット長から求めたビット幅</param>
    /// <param name="entryCount">エントリ数</param>
    /// <param name="lenient">
    /// trueなら、配列長が期待値と違う場合に配列長からビット幅を逆算して読む
    /// 第三者ツールが書いたデータの救済用
    /// </param>
    /// <exception cref="SpringNbtException">
    /// 配列長が期待値と一致しない場合（<see cref="ErrorCode.MalformedData"/>）
    /// </exception>
    public static BitStorage FromLongs(long[] data, int bitsPerEntry, int entryCount, bool lenient = false)
    {
        return FromLongs(data, bitsPerEntry, entryCount, lenient, false);
    }

    /// <summary>詰め方を指定して、既存の<c>i64</c>配列から作る</summary>
    internal static BitStorage FromLongs(long[] data, int bitsPerEntry, int entryCount, bool lenient, bool spanning)
    {
        ArgumentNullException.ThrowIfNull(data);
        int expected = LongCount(bitsPerEntry, entryCount, spanning);

        if (data.Length == expected)
        {
            return new BitStorage(data, bitsPerEntry, entryCount, spanning);
        }

        if (!lenient)
        {
            throw SpringNbtException.Malformed(
                $"bits={bitsPerEntry} なら data は {expected} long のはずだが {data.Length} long");
        }

        // 配列長からビット幅を逆算する
        // 合致する幅が無ければ諦める
        for (int candidate = 1; candidate <= 32; candidate++)
        {
            if (LongCount(candidate, entryCount, spanning) == data.Length)
            {
                return new BitStorage(data, candidate, entryCount, spanning);
            }
        }

        throw SpringNbtException.Malformed(
            $"data の長さ {data.Length} long に合うビット幅が無い（エントリ数 {entryCount}）");
    }

    /// <summary>必要な<c>i64</c>の個数を求める</summary>
    public static int LongCount(int bitsPerEntry, int entryCount)
    {
        return LongCount(bitsPerEntry, entryCount, false);
    }

    /// <summary>詰め方を指定して、必要な<c>i64</c>の個数を求める</summary>
    internal static int LongCount(int bitsPerEntry, int entryCount, bool spanning)
    {
        // またぐ詰め方なら、全ビットを隙間なく並べた長さになる
        if (spanning)
        {
            return (int)(((long)entryCount * bitsPerEntry + 63) / 64);
        }

        int valuesPerLong = 64 / bitsPerEntry;
        return (entryCount + valuesPerLong - 1) / valuesPerLong;
    }

    /// <summary>添字の値を取り出す</summary>
    public int Get(int index)
    {
        if (index < 0 || index >= EntryCount)
        {
            throw SpringNbtException.InvalidArgument($"添字が範囲外: {index} (0..{EntryCount - 1})");
        }

        long mask = (1L << BitsPerEntry) - 1;

        // またぐ詰め方なら、隣のlongへ続く分を上位ビットとして足す
        if (Spanning)
        {
            long bitIndex = (long)index * BitsPerEntry;
            int spanLongIndex = (int)(bitIndex >> 6);
            int spanOffset = (int)(bitIndex & 63);
            ulong spanValue = (ulong)data[spanLongIndex] >> spanOffset;

            // 次のlongへ続く場合は、続き分を左へずらして重ねる
            if (spanOffset + BitsPerEntry > 64)
            {
                spanValue |= (ulong)data[spanLongIndex + 1] << (64 - spanOffset);
            }

            return (int)(spanValue & (ulong)mask);
        }

        int valuesPerLong = ValuesPerLong;
        int longIndex = index / valuesPerLong;
        int bitOffset = (index % valuesPerLong) * BitsPerEntry;

        // 符号付きの算術シフトだと上位ビットが伸びるので、いったんulongにして論理シフトする
        return (int)(((ulong)data[longIndex] >> bitOffset) & (ulong)mask);
    }

    /// <summary>添字の値を書き換える</summary>
    public void Set(int index, int value)
    {
        if (index < 0 || index >= EntryCount)
        {
            throw SpringNbtException.InvalidArgument($"添字が範囲外: {index} (0..{EntryCount - 1})");
        }

        long limit = 1L << BitsPerEntry;

        if (value < 0 || value >= limit)
        {
            throw SpringNbtException.InvalidArgument(
                $"値がビット幅に収まらない: {value} (0..{limit - 1})");
        }

        // またぐ詰め方なら、隣のlongへ続く分も書き込む
        if (Spanning)
        {
            long bitIndex = (long)index * BitsPerEntry;
            int spanLongIndex = (int)(bitIndex >> 6);
            int spanOffset = (int)(bitIndex & 63);
            long spanMask = (1L << BitsPerEntry) - 1;

            data[spanLongIndex] = (data[spanLongIndex] & ~(spanMask << spanOffset))
                | ((long)value << spanOffset);

            // 次のlongへ続く場合は、続き分の下位ビットを書き換える
            if (spanOffset + BitsPerEntry > 64)
            {
                int shift = 64 - spanOffset;
                long highMask = spanMask >> shift;
                data[spanLongIndex + 1] = (data[spanLongIndex + 1] & ~highMask)
                    | ((long)value >> shift);
            }

            return;
        }

        int valuesPerLong = ValuesPerLong;
        int longIndex = index / valuesPerLong;
        int bitOffset = (index % valuesPerLong) * BitsPerEntry;
        long mask = ((1L << BitsPerEntry) - 1) << bitOffset;

        data[longIndex] = (data[longIndex] & ~mask) | ((long)value << bitOffset & mask);
    }

    /// <summary>packedな配列を返す
    /// 内部の配列をそのまま返す（コピーしない）</summary>
    public long[] ToLongs() => data;

    /// <summary>
    /// 別のビット幅へ詰め直した新しい記憶域を返す
    /// </summary>
    public BitStorage Resize(int newBitsPerEntry)
    {
        BitStorage result = Create(newBitsPerEntry, EntryCount, Spanning);

        // 全エントリを読み直して新しい幅で詰める
        for (int index = 0; index < EntryCount; index++)
        {
            result.Set(index, Get(index));
        }

        return result;
    }
}

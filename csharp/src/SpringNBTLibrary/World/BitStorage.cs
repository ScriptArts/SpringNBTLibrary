namespace SpringNBTLibrary.World;

/// <summary>
/// 添字を 64bit 整数の配列へ詰めた表現
/// 1.16 以降の**跨ぎなし**パッキング
/// </summary>
/// <remarks>
/// <para>
/// 1 つの <c>i64</c> に入りきらない分は、その <c>i64</c> の残りビットを未使用のまま捨て、
/// 次の <c>i64</c> の最下位ビットから始める
/// </para>
/// <para>仕様: <c>docs/spec/31-paletted-container.md</c> 2章</para>
/// </remarks>
public sealed class BitStorage
{
    private readonly long[] data;

    private BitStorage(long[] data, int bitsPerEntry, int entryCount)
    {
        this.data = data;
        BitsPerEntry = bitsPerEntry;
        EntryCount = entryCount;
    }

    /// <summary>1 エントリあたりのビット数</summary>
    public int BitsPerEntry { get; }

    /// <summary>エントリ数
    /// ブロックなら 4096、バイオームなら 64</summary>
    public int EntryCount { get; }

    /// <summary>1 つの <c>i64</c> に入るエントリ数</summary>
    public int ValuesPerLong => 64 / BitsPerEntry;

    /// <summary>すべてゼロで初期化した記憶域を作る</summary>
    public static BitStorage Create(int bitsPerEntry, int entryCount)
    {
        if (bitsPerEntry < 1 || bitsPerEntry > 32)
        {
            throw SpringNbtException.InvalidArgument($"ビット幅が範囲外: {bitsPerEntry}");
        }

        return new BitStorage(new long[LongCount(bitsPerEntry, entryCount)], bitsPerEntry, entryCount);
    }

    /// <summary>
    /// 既存の <c>i64</c> 配列から作る
    /// </summary>
    /// <param name="data">packed な配列</param>
    /// <param name="bitsPerEntry">パレット長から求めたビット幅</param>
    /// <param name="entryCount">エントリ数</param>
    /// <param name="lenient">
    /// true なら、配列長が期待値と違う場合に配列長からビット幅を逆算して読む
    /// 第三者ツールが書いたデータの救済用
    /// </param>
    /// <exception cref="SpringNbtException">
    /// 配列長が期待値と一致しない場合（<see cref="ErrorCode.MalformedData"/>）
    /// </exception>
    public static BitStorage FromLongs(long[] data, int bitsPerEntry, int entryCount, bool lenient = false)
    {
        ArgumentNullException.ThrowIfNull(data);
        int expected = LongCount(bitsPerEntry, entryCount);

        if (data.Length == expected)
        {
            return new BitStorage(data, bitsPerEntry, entryCount);
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
            if (LongCount(candidate, entryCount) == data.Length)
            {
                return new BitStorage(data, candidate, entryCount);
            }
        }

        throw SpringNbtException.Malformed(
            $"data の長さ {data.Length} long に合うビット幅が無い（エントリ数 {entryCount}）");
    }

    /// <summary>必要な <c>i64</c> の個数を求める</summary>
    public static int LongCount(int bitsPerEntry, int entryCount)
    {
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

        int valuesPerLong = ValuesPerLong;
        int longIndex = index / valuesPerLong;
        int bitOffset = (index % valuesPerLong) * BitsPerEntry;
        long mask = (1L << BitsPerEntry) - 1;

        // 符号付きの算術シフトだと上位ビットが伸びるので、いったん ulong にして論理シフトする
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

        int valuesPerLong = ValuesPerLong;
        int longIndex = index / valuesPerLong;
        int bitOffset = (index % valuesPerLong) * BitsPerEntry;
        long mask = ((1L << BitsPerEntry) - 1) << bitOffset;

        data[longIndex] = (data[longIndex] & ~mask) | ((long)value << bitOffset & mask);
    }

    /// <summary>packed な配列を返す
    /// 内部の配列をそのまま返す（コピーしない）</summary>
    public long[] ToLongs() => data;

    /// <summary>
    /// 別のビット幅へ詰め直した新しい記憶域を返す
    /// </summary>
    public BitStorage Resize(int newBitsPerEntry)
    {
        BitStorage result = Create(newBitsPerEntry, EntryCount);

        // 全エントリを読み直して新しい幅で詰める
        for (int index = 0; index < EntryCount; index++)
        {
            result.Set(index, Get(index));
        }

        return result;
    }
}

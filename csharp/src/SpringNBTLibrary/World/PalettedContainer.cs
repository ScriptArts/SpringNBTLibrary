using SpringNBTLibrary.Nbt;

namespace SpringNBTLibrary.World;

/// <summary>
/// パレットとビットストレージの組。セクション内のブロック状態やバイオームを格納する。
/// </summary>
/// <remarks>
/// <para>
/// パレットの要素は**生の <see cref="NbtTag"/> のまま**持つ。
/// こうすると、触っていないブロックについては Minecraft が書き出したときの
/// プロパティの並び順まで含めてそのまま書き戻せる。
/// </para>
/// <para>仕様: <c>docs/spec/31-paletted-container.md</c></para>
/// </remarks>
public sealed class PalettedContainer
{
    private readonly List<NbtTag> palette = new List<NbtTag>();
    private BitStorage? storage;

    private PalettedContainer(int entryCount, int minBits)
    {
        EntryCount = entryCount;
        MinBits = minBits;
    }

    /// <summary>エントリ数。ブロックなら 4096、バイオームなら 64。</summary>
    public int EntryCount { get; }

    /// <summary>ビット幅の下限。ブロックなら 4、バイオームなら 1。</summary>
    public int MinBits { get; }

    /// <summary>パレット。読み取り専用。</summary>
    public IReadOnlyList<NbtTag> Palette => palette;

    /// <summary>現在のビット幅。パレットが 1 要素なら 0（記憶域を持たない）。</summary>
    public int BitsPerEntry
    {
        get
        {
            if (storage is null)
            {
                return 0;
            }

            return storage.BitsPerEntry;
        }
    }

    /// <summary>
    /// 単一の値で埋めたコンテナを作る。
    /// </summary>
    public static PalettedContainer Filled(NbtTag value, int entryCount, int minBits)
    {
        ArgumentNullException.ThrowIfNull(value);
        PalettedContainer result = new PalettedContainer(entryCount, minBits);
        result.palette.Add(value);
        return result;
    }

    /// <summary>
    /// NBT から読み込む。
    /// </summary>
    /// <exception cref="SpringNbtException">
    /// パレットが空、data の長さが合わない、添字がパレット範囲外のいずれか。
    /// </exception>
    public static PalettedContainer FromNbt(
        NbtCompound nbt, int entryCount, int minBits, bool lenientBitStorage = false)
    {
        ArgumentNullException.ThrowIfNull(nbt);
        PalettedContainer result = new PalettedContainer(entryCount, minBits);

        NbtList? paletteTag = nbt.OptList("palette");

        if (paletteTag is null || paletteTag.Count == 0)
        {
            throw SpringNbtException.Malformed("palette が無いか空");
        }

        foreach (NbtTag entry in paletteTag)
        {
            result.palette.Add(entry);
        }

        long[]? data = nbt.OptLongArray("data");

        if (data is null)
        {
            // パレットが 1 要素なら data は無くてよい
            if (result.palette.Count != 1)
            {
                throw SpringNbtException.Malformed(
                    $"palette が {result.palette.Count} 要素なのに data が無い");
            }

            return result;
        }

        int bits = Math.Max(minBits, CeilLog2(result.palette.Count));
        result.storage = BitStorage.FromLongs(data, bits, entryCount, lenientBitStorage);

        // 取り出した添字がパレットの範囲に収まっているか確かめる。
        // 黙って 0 番目で代替すると、壊れたデータをそうと分からない形で書き戻してしまう
        for (int index = 0; index < entryCount; index++)
        {
            int value = result.storage.Get(index);

            if (value >= result.palette.Count)
            {
                throw SpringNbtException.Malformed(
                    $"添字 {index} の値 {value} がパレット（{result.palette.Count} 要素）の範囲外");
            }
        }

        return result;
    }

    /// <summary>NBT へ変換する。</summary>
    public NbtCompound ToNbt()
    {
        NbtCompound result = new NbtCompound();
        NbtList paletteTag = new NbtList();

        foreach (NbtTag entry in palette)
        {
            paletteTag.Add(entry);
        }

        // パレットが 1 要素なら data は書かない。Minecraft と同じ振る舞い
        if (storage is not null && palette.Count > 1)
        {
            result.Set("data", new NbtLongArray(storage.ToLongs()));
        }

        result.Set("palette", paletteTag);
        return result;
    }

    /// <summary>添字の値を取り出す。</summary>
    public NbtTag Get(int index)
    {
        if (index < 0 || index >= EntryCount)
        {
            throw SpringNbtException.InvalidArgument($"添字が範囲外: {index} (0..{EntryCount - 1})");
        }

        // 記憶域が無いということは、全エントリがパレットの 0 番目
        if (storage is null)
        {
            return palette[0];
        }

        return palette[storage.Get(index)];
    }

    /// <summary>添字の値を書き換える。パレットに無ければ追加する。</summary>
    public void Set(int index, NbtTag value)
    {
        ArgumentNullException.ThrowIfNull(value);

        if (index < 0 || index >= EntryCount)
        {
            throw SpringNbtException.InvalidArgument($"添字が範囲外: {index} (0..{EntryCount - 1})");
        }

        int paletteIndex = IndexOfOrAdd(value);

        // 記憶域が無く、書き込む値も 0 番目なら何もしなくてよい
        if (storage is null && paletteIndex == 0)
        {
            return;
        }

        EnsureStorage();
        storage!.Set(index, paletteIndex);
    }

    /// <summary>全エントリを 1 つの値で埋める。パレットもその 1 要素だけにする。</summary>
    public void Fill(NbtTag value)
    {
        ArgumentNullException.ThrowIfNull(value);
        palette.Clear();
        palette.Add(value);
        storage = null;
    }

    /// <summary>
    /// どのエントリからも参照されていないパレット要素を取り除き、添字を振り直す。
    /// </summary>
    /// <remarks>
    /// 大量の <c>Set</c> を行う用途で遅くならないよう、明示的に呼んだときだけ実行する。
    /// </remarks>
    public void Compact()
    {
        if (storage is null)
        {
            return;
        }

        bool[] usedEntries = new bool[palette.Count];

        // どのパレット要素が実際に使われているかを数える
        for (int index = 0; index < EntryCount; index++)
        {
            usedEntries[storage.Get(index)] = true;
        }

        List<NbtTag> compacted = new List<NbtTag>();
        int[] remap = new int[palette.Count];

        for (int old = 0; old < palette.Count; old++)
        {
            if (!usedEntries[old])
            {
                remap[old] = -1;
                continue;
            }

            remap[old] = compacted.Count;
            compacted.Add(palette[old]);
        }

        if (compacted.Count == palette.Count)
        {
            return;
        }

        int newBits = Math.Max(MinBits, CeilLog2(compacted.Count));
        BitStorage rebuilt = BitStorage.Create(newBits, EntryCount);

        // 新しい添字へ置き換えながら詰め直す
        for (int index = 0; index < EntryCount; index++)
        {
            rebuilt.Set(index, remap[storage.Get(index)]);
        }

        palette.Clear();
        palette.AddRange(compacted);

        if (compacted.Count == 1)
        {
            // 1 要素になったら記憶域を捨てる
            storage = null;
        }
        else
        {
            storage = rebuilt;
        }
    }

    /// <summary>パレット内の位置を返す。無ければ末尾へ追加する。</summary>
    private int IndexOfOrAdd(NbtTag value)
    {
        // パレットは高々 4096 要素なので線形探索で足りる
        for (int index = 0; index < palette.Count; index++)
        {
            if (palette[index].Equals(value))
            {
                return index;
            }
        }

        palette.Add(value);
        return palette.Count - 1;
    }

    /// <summary>現在のパレット長に合うビット幅の記憶域を用意する。</summary>
    private void EnsureStorage()
    {
        int required = Math.Max(MinBits, CeilLog2(palette.Count));

        if (storage is null)
        {
            // これまで単一値だったので、全エントリが 0 番目のまま始まる
            storage = BitStorage.Create(required, EntryCount);
            return;
        }

        if (storage.BitsPerEntry >= required)
        {
            return;
        }

        // パレットが増えてビット幅が足りなくなったら、全体を詰め直す
        storage = storage.Resize(required);
    }

    /// <summary><paramref name="count"/> 個の値を表すのに必要な最小ビット数。1 なら 0。</summary>
    public static int CeilLog2(int count)
    {
        int bits = 0;

        // 1 を超える分だけシフトして数える
        while ((1 << bits) < count)
        {
            bits += 1;
        }

        return bits;
    }
}

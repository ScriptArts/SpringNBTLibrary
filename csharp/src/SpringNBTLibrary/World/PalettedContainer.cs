using SpringNBTLibrary.Nbt;

namespace SpringNBTLibrary.World;

/// <summary>
/// パレットとビットストレージの組
/// セクション内のブロック状態やバイオームを格納する
/// </summary>
/// <remarks>
/// <para>
/// パレットの要素は**生の<see cref="NbtTag"/>のまま**持つ
/// こうすると、触っていないブロックについてはMinecraftが書き出したときの
/// プロパティの並び順まで含めてそのまま書き戻せる
/// </para>
/// <para>
/// 26.3からは、ブロックのパレットに文字列とCompoundが混ざる
/// Minecraftはこうした異種リストをCompoundのリストとして保存し、Compoundでない要素を<c>{"": &lt;値&gt;}</c>で包む
/// 読むときにこの包みを外して持ち、書くときに要素の型を見て包み直す
/// </para>
/// </remarks>
public sealed class PalettedContainer
{
    private readonly List<NbtTag> palette = new List<NbtTag>();
    private readonly bool spanning;
    private readonly bool alwaysHasData;
    private BitStorage? storage;

    private PalettedContainer(int entryCount, int minBits, bool spanning, bool alwaysHasData)
    {
        EntryCount = entryCount;
        MinBits = minBits;
        this.spanning = spanning;
        this.alwaysHasData = alwaysHasData;
    }

    /// <summary>エントリ数
    /// ブロックなら4096、バイオームなら64</summary>
    public int EntryCount { get; }

    /// <summary>ビット幅の下限
    /// ブロックなら4、バイオームなら1</summary>
    public int MinBits { get; }

    /// <summary>パレット
    /// 読み取り専用</summary>
    public IReadOnlyList<NbtTag> Palette => palette;

    /// <summary>現在のビット幅
    /// パレットが1要素なら0（記憶域を持たない）</summary>
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
    /// 単一の値で埋めたコンテナを作る
    /// </summary>
    public static PalettedContainer Filled(NbtTag value, int entryCount, int minBits)
    {
        ArgumentNullException.ThrowIfNull(value);
        PalettedContainer result = new PalettedContainer(entryCount, minBits, false, false);
        result.palette.Add(value);
        return result;
    }

    /// <summary>
    /// NBTから読み込む
    /// </summary>
    /// <exception cref="SpringNbtException">
    /// パレットが空、dataの長さが合わない、添字がパレット範囲外のいずれか
    /// </exception>
    public static PalettedContainer FromNbt(
        NbtCompound nbt, int entryCount, int minBits, bool lenientBitStorage = false)
    {
        ArgumentNullException.ThrowIfNull(nbt);
        NbtList? paletteTag = nbt.OptList("palette");

        if (paletteTag is null || paletteTag.Count == 0)
        {
            throw SpringNbtException.Malformed("palette が無いか空");
        }

        // パレットの要素は生のNbtTagのまま持つ
        // 並び順まで元どおりに書き戻すため
        // 異種リストの包みだけは外しておき、書くときに包み直す
        List<NbtTag> entries = new List<NbtTag>();

        // 包みを外しながら、パレットの要素を順に集める
        foreach (NbtTag entry in paletteTag)
        {
            entries.Add(UnwrapListElement(entry));
        }

        return FromParts(entries, nbt.OptLongArray("data"), entryCount, minBits, false, false, lenientBitStorage);
    }

    /// <summary>
    /// パレットとdataから作る
    /// 1.13から1.15までの詰め方や、dataが必ず書かれる形式を読むための入口
    /// </summary>
    /// <param name="palette">パレットの要素（異種リストの包みは外してあること）</param>
    /// <param name="data">packedな配列（無ければnull）</param>
    /// <param name="entryCount">エントリ数</param>
    /// <param name="minBits">ビット幅の下限</param>
    /// <param name="spanning">64bitの境目をまたいで詰めるか</param>
    /// <param name="alwaysHasData">パレットが1要素でもdataを書く形式か</param>
    /// <param name="lenientBitStorage">dataの長さが合わないとき、長さからビット幅を逆算して読むか</param>
    internal static PalettedContainer FromParts(
        IReadOnlyList<NbtTag> palette, long[]? data, int entryCount, int minBits,
        bool spanning, bool alwaysHasData, bool lenientBitStorage)
    {
        ArgumentNullException.ThrowIfNull(palette);

        if (palette.Count == 0)
        {
            throw SpringNbtException.Malformed("palette が無いか空");
        }

        PalettedContainer result = new PalettedContainer(entryCount, minBits, spanning, alwaysHasData);
        result.palette.AddRange(palette);

        if (data is null)
        {
            // dataが必ず書かれる形式で無いなら、壊れたデータとして扱う
            // 書き戻しで元に無いdataを作ってしまわないため
            if (alwaysHasData)
            {
                throw SpringNbtException.Malformed("data が必ず書かれる形式なのに data が無い");
            }

            // パレットが1要素ならdataは無くてよい
            if (result.palette.Count != 1)
            {
                throw SpringNbtException.Malformed(
                    $"palette が {result.palette.Count} 要素なのに data が無い");
            }

            return result;
        }

        int bits = Math.Max(minBits, CeilLog2(result.palette.Count));
        result.storage = BitStorage.FromLongs(data, bits, entryCount, lenientBitStorage, spanning);

        // 取り出した添字がパレットの範囲に収まっているか確かめる
        // エラーを出さずに0番目で代替すると、おかしくなったデータをそうと分からない形で書き戻してしまう
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

    /// <summary>
    /// パレットとdataに分けて返す
    /// パレットの要素は異種リストの包みを掛けないまま返す
    /// dataは、パレットが1要素なら（<c>alwaysHasData</c>でない限り）null
    /// </summary>
    internal (List<NbtTag> Palette, long[]? Data) ToParts()
    {
        List<NbtTag> entries = new List<NbtTag>(palette);

        // パレットが2要素以上なら、記憶域をそのまま返す
        if (storage is not null && palette.Count > 1)
        {
            return (entries, storage.ToLongs());
        }

        // 1要素でもdataを書く形式なら、記憶域が無くてもゼロで埋めた配列を作る
        if (alwaysHasData)
        {
            int bits = Math.Max(MinBits, CeilLog2(palette.Count));
            BitStorage zeroed = BitStorage.Create(bits, EntryCount, spanning);
            return (entries, zeroed.ToLongs());
        }

        return (entries, null);
    }

    /// <summary>NBTへ変換する</summary>
    public NbtCompound ToNbt()
    {
        NbtCompound result = new NbtCompound();

        // パレットの要素は読んだときのまま書き出す
        // 型が混ざっていれば、Minecraftと同じく包んでCompoundのリストにする
        NbtList paletteTag = PaletteToList(palette);

        // パレットが1要素ならdataは書かない
        // Minecraftと同じ振る舞い
        if (storage is not null && palette.Count > 1)
        {
            result.Set("data", new NbtLongArray(storage.ToLongs()));
        }

        result.Set("palette", paletteTag);
        return result;
    }

    /// <summary>異種リストの包みを外す
    /// 包みでなければそのまま返す</summary>
    internal static NbtTag UnwrapListElement(NbtTag tag)
    {
        if (IsListWrapper(tag))
        {
            return ((NbtCompound)tag).Get("");
        }

        return tag;
    }

    /// <summary>異種リストの要素を包むCompoundか
    /// 空のキー1つだけを持つものがそれに当たる（MinecraftのListTagと同じ判定）</summary>
    private static bool IsListWrapper(NbtTag tag)
    {
        if (tag is not NbtCompound compound)
        {
            return false;
        }

        return compound.Count == 1 && compound.ContainsKey("");
    }

    /// <summary>パレットの要素をリストへ詰める</summary>
    /// <remarks>
    /// 要素の型がすべて同じならその型のリストにする
    /// 1つでも違えば、Minecraftと同じくCompoundのリストにして、Compoundでない要素と包みに見える要素を包む
    /// </remarks>
    private static NbtList PaletteToList(List<NbtTag> entries)
    {
        TagType elementType = entries[0].Type;

        // 先頭と型の違う要素があるか調べる
        foreach (NbtTag entry in entries)
        {
            // 1つでも違えば、異種リストとしてCompoundのリストにする
            if (entry.Type != elementType)
            {
                elementType = TagType.Compound;
                break;
            }
        }

        NbtList result = new NbtList(elementType);

        // 要素を順にリストへ入れる
        foreach (NbtTag entry in entries)
        {
            // Compoundのリストでは、Compoundでない要素と包みに見える要素を包む
            if (elementType == TagType.Compound && (entry is not NbtCompound || IsListWrapper(entry)))
            {
                NbtCompound wrapper = new NbtCompound();
                wrapper.Set("", entry);
                result.Add(wrapper);
            }
            else
            {
                result.Add(entry);
            }
        }

        return result;
    }

    /// <summary>添字の値を取り出す</summary>
    public NbtTag Get(int index)
    {
        if (index < 0 || index >= EntryCount)
        {
            throw SpringNbtException.InvalidArgument($"添字が範囲外: {index} (0..{EntryCount - 1})");
        }

        // 記憶域が無いということは、全エントリがパレットの0番目
        if (storage is null)
        {
            return palette[0];
        }

        return palette[storage.Get(index)];
    }

    /// <summary>添字の値を書き換える
    /// パレットに無ければ追加する</summary>
    public void Set(int index, NbtTag value)
    {
        ArgumentNullException.ThrowIfNull(value);

        if (index < 0 || index >= EntryCount)
        {
            throw SpringNbtException.InvalidArgument($"添字が範囲外: {index} (0..{EntryCount - 1})");
        }

        int paletteIndex = IndexOfOrAdd(value);

        // 記憶域が無く、書き込む値も0番目なら何もしなくてよい
        if (storage is null && paletteIndex == 0)
        {
            return;
        }

        EnsureStorage();
        storage!.Set(index, paletteIndex);
    }

    /// <summary>全エントリを1つの値で埋める
    /// パレットもその1要素だけにする</summary>
    public void Fill(NbtTag value)
    {
        ArgumentNullException.ThrowIfNull(value);
        palette.Clear();
        palette.Add(value);
        storage = null;
    }

    /// <summary>
    /// どのエントリからも参照されていないパレット要素を取り除き、添字を振り直す
    /// </summary>
    /// <remarks>
    /// 大量の<c>Set</c>を行う用途で遅くならないよう、明示的に呼んだときだけ実行する
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

        // 使われている要素だけを詰め直し、新しい添字を割り当てる
        for (int old = 0; old < palette.Count; old++)
        {
            // 参照されていない要素は捨てる
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
        BitStorage rebuilt = BitStorage.Create(newBits, EntryCount, spanning);

        // 新しい添字へ置き換えながら詰め直す
        for (int index = 0; index < EntryCount; index++)
        {
            rebuilt.Set(index, remap[storage.Get(index)]);
        }

        palette.Clear();
        palette.AddRange(compacted);

        if (compacted.Count == 1)
        {
            // 1要素になったら記憶域を捨てる
            storage = null;
        }
        else
        {
            storage = rebuilt;
        }
    }

    /// <summary>パレット内の位置を返す
    /// 無ければ末尾へ追加する</summary>
    private int IndexOfOrAdd(NbtTag value)
    {
        // パレットは高々4096要素なので線形探索で足りる
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

    /// <summary>現在のパレット長に合うビット幅の記憶域を用意する</summary>
    private void EnsureStorage()
    {
        int required = Math.Max(MinBits, CeilLog2(palette.Count));

        if (storage is null)
        {
            // これまで単一値だったので、全エントリが0番目のまま始まる
            storage = BitStorage.Create(required, EntryCount, spanning);
            return;
        }

        if (storage.BitsPerEntry >= required)
        {
            return;
        }

        // パレットが増えてビット幅が足りなくなったら、全体を詰め直す
        storage = storage.Resize(required);
    }

    /// <summary><paramref name="count"/>個の値を表すのに必要な最小ビット数
    /// 1なら0</summary>
    public static int CeilLog2(int count)
    {
        int bits = 0;

        // 1を超える分だけシフトして数える
        while ((1 << bits) < count)
        {
            bits += 1;
        }

        return bits;
    }
}

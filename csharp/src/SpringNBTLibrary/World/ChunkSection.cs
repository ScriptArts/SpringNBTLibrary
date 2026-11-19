using SpringNBTLibrary.Nbt;

namespace SpringNBTLibrary.World;

/// <summary>
/// チャンクをY方向に16ブロックずつ区切った16×16×16の立方体
/// </summary>
/// <remarks>
/// <para>
/// <c>BlockLight</c> / <c>SkyLight</c>などの解釈していないキーは元のNBTに残り、
/// 書き戻しでそのまま出力される
/// </para>
/// </remarks>
public sealed class ChunkSection
{
    private readonly NbtCompound raw;

    /// <summary>
    /// ブロックの持ち方
    /// 書き戻すときに読んだときと同じキーへ書くため、覚えておく
    /// </summary>
    private BlockStorage blockStorage = BlockStorage.Container;

    private ChunkSection(NbtCompound raw, int y)
    {
        this.raw = raw;
        Y = y;
    }

    /// <summary>セクションのY位置
    /// オーバーワールドは-5..20</summary>
    public int Y { get; }

    /// <summary>ブロック状態
    /// 持たないセクション（光源専用）ではnull</summary>
    public PalettedContainer? BlockStates { get; private set; }

    /// <summary>バイオーム
    /// 持たないセクションではnull</summary>
    public PalettedContainer? Biomes { get; private set; }

    /// <summary>ブロック状態を持つか</summary>
    public bool HasBlockStates => BlockStates is not null;

    /// <summary>バイオームを持つか</summary>
    public bool HasBiomes => Biomes is not null;

    /// <summary>元のNBT
    /// 解釈していないキーもここに残っている</summary>
    public NbtCompound Raw => raw;

    /// <summary>
    /// NBTからセクションを読む
    /// 1.18以降の形式（<c>block_states</c> / <c>biomes</c>）として読む
    /// </summary>
    public static ChunkSection FromNbt(NbtCompound nbt, ChunkReadOptions options)
    {
        ArgumentNullException.ThrowIfNull(nbt);
        ChunkSection section = new ChunkSection(nbt, nbt.GetByte("Y"));

        NbtCompound? blockStates = nbt.OptCompound("block_states");

        // 光源専用のセクションはblock_statesを持たない
        if (blockStates is not null)
        {
            section.BlockStates = PalettedContainer.FromNbt(
                blockStates, Chunk.BlocksPerSection, 4, options.LenientBitStorage);
        }

        NbtCompound? biomes = nbt.OptCompound("biomes");

        // 光源だけを持つセクションにはバイオームが無い
        if (biomes is not null)
        {
            section.Biomes = PalettedContainer.FromNbt(
                biomes, Chunk.BiomesPerSection, 1, options.LenientBitStorage);
        }

        return section;
    }

    /// <summary>世代の持ち方に従ってNBTからセクションを読む</summary>
    internal static ChunkSection FromNbtForFormat(
        NbtCompound nbt, ChunkReadOptions options, ChunkFormat format)
    {
        // 1.18以降の形式は公開の読み込みと同じ
        if (format.BlockStorage == BlockStorage.Container)
        {
            return FromNbt(nbt, options);
        }

        ChunkSection section = new ChunkSection(nbt, nbt.GetByte("Y"));
        section.blockStorage = format.BlockStorage;
        NbtList? palette = nbt.OptList("Palette");

        // Paletteの無いセクション（光源だけを持つものなど）はブロックを持たない
        if (palette is null)
        {
            return section;
        }

        List<NbtTag> entries = new List<NbtTag>(palette.Count);

        // 書き戻すときにCompoundのリストとして書くので、要素の型をここで確かめる
        foreach (NbtTag entry in palette)
        {
            // Compound以外の要素は1.17までの形式に無い
            if (entry is not NbtCompound)
            {
                throw SpringNbtException.UnexpectedTagType(
                    $"Palette の要素が compound でない: {entry.Type.AsString()}");
            }

            entries.Add(entry);
        }

        // BlockStatesはパレットが1要素でも必ず書かれる
        section.BlockStates = PalettedContainer.FromParts(
            entries, nbt.OptLongArray("BlockStates"), Chunk.BlocksPerSection, 4,
            format.SpanningBitStorage, true, options.LenientBitStorage);
        return section;
    }

    /// <summary>NBTへ書き戻す
    /// 解釈していないキーはそのまま残る</summary>
    public NbtCompound ToNbt()
    {
        // 1.17までの形式は、セクションの直下のPaletteとBlockStatesへ書き戻す
        if (BlockStates is not null && blockStorage == BlockStorage.SectionPalette)
        {
            (List<NbtTag> palette, long[]? data) = BlockStates.ToParts();
            NbtList paletteTag = new NbtList(TagType.Compound);

            // 要素は読んだときのまま並べる
            foreach (NbtTag entry in palette)
            {
                paletteTag.Add(entry);
            }

            // 既存のキーへ書くので、キーの並びは読んだときのまま残る
            raw.SetLongArray("BlockStates", data!);
            raw.Set("Palette", paletteTag);
            return raw;
        }

        // 解釈したコンテナだけを書き戻す
        // 持たないキーは元のまま残す
        if (BlockStates is not null)
        {
            raw.Set("block_states", BlockStates.ToNbt());
        }

        // 解釈したコンテナだけを書き戻す
        // 持たないキーは元のまま残す
        if (Biomes is not null)
        {
            raw.Set("biomes", Biomes.ToNbt());
        }

        return raw;
    }

    /// <summary>使われていないパレット要素を取り除く</summary>
    public void Compact()
    {
        // 持っているコンテナだけを掃除する
        if (BlockStates is not null)
        {
            BlockStates.Compact();
        }

        // 持っているコンテナだけを掃除する
        if (Biomes is not null)
        {
            Biomes.Compact();
        }
    }
}

using SpringNBTLibrary.Nbt;

namespace SpringNBTLibrary.World;

/// <summary>
/// チャンクを Y 方向に 16 ブロックずつ区切った 16×16×16 の立方体。
/// </summary>
/// <remarks>
/// <para>
/// <c>BlockLight</c> / <c>SkyLight</c> などの解釈していないキーは元の NBT に残り、
/// 書き戻しでそのまま出力される。
/// </para>
/// <para>仕様: <c>docs/spec/30-chunk-format.md</c> 2章</para>
/// </remarks>
public sealed class ChunkSection
{
    private readonly NbtCompound raw;

    private ChunkSection(NbtCompound raw, int y)
    {
        this.raw = raw;
        Y = y;
    }

    /// <summary>セクションのY位置。オーバーワールドは -5..20。</summary>
    public int Y { get; }

    /// <summary>ブロック状態。持たないセクション（光源専用）では null。</summary>
    public PalettedContainer? BlockStates { get; private set; }

    /// <summary>バイオーム。持たないセクションでは null。</summary>
    public PalettedContainer? Biomes { get; private set; }

    /// <summary>ブロック状態を持つか。</summary>
    public bool HasBlockStates => BlockStates is not null;

    /// <summary>バイオームを持つか。</summary>
    public bool HasBiomes => Biomes is not null;

    /// <summary>元の NBT。解釈していないキーもここに残っている。</summary>
    public NbtCompound Raw => raw;

    /// <summary>NBT からセクションを読む。</summary>
    public static ChunkSection FromNbt(NbtCompound nbt, ChunkReadOptions options)
    {
        ArgumentNullException.ThrowIfNull(nbt);
        ChunkSection section = new ChunkSection(nbt, nbt.GetByte("Y"));

        NbtCompound? blockStates = nbt.OptCompound("block_states");

        // 光源専用のセクションは block_states を持たない
        if (blockStates is not null)
        {
            section.BlockStates = PalettedContainer.FromNbt(
                blockStates, Chunk.BlocksPerSection, 4, options.LenientBitStorage);
        }

        NbtCompound? biomes = nbt.OptCompound("biomes");

        if (biomes is not null)
        {
            section.Biomes = PalettedContainer.FromNbt(
                biomes, Chunk.BiomesPerSection, 1, options.LenientBitStorage);
        }

        return section;
    }

    /// <summary>NBT へ書き戻す。解釈していないキーはそのまま残る。</summary>
    public NbtCompound ToNbt()
    {
        if (BlockStates is not null)
        {
            raw.Set("block_states", BlockStates.ToNbt());
        }

        if (Biomes is not null)
        {
            raw.Set("biomes", Biomes.ToNbt());
        }

        return raw;
    }

    /// <summary>使われていないパレット要素を取り除く。</summary>
    public void Compact()
    {
        BlockStates?.Compact();
        Biomes?.Compact();
    }
}

package io.github.scriptarts.springnbt.world;

import io.github.scriptarts.springnbt.nbt.NbtCompound;
import java.util.Objects;

/**
 * チャンクをY方向に16ブロックずつ区切った16×16×16の立方体
 *
 * <p>{@code BlockLight} / {@code SkyLight}などの解釈していないキーは元のNBTに残り、
 * 書き戻しでそのまま出力される
 */
public final class ChunkSection {

    private final NbtCompound raw;
    private final int y;

    private PalettedContainer blockStates;
    private PalettedContainer biomes;

    private ChunkSection(NbtCompound raw, int y) {
        this.raw = raw;
        this.y = y;
    }

    /**
     * セクションのY位置
     * オーバーワールドは-5..20
     *
     * @return Y位置
     */
    public int y() {
        return y;
    }

    /**
     * ブロック状態
     * 持たないセクション（光源専用）ではnull
     *
     * @return ブロック状態
     */
    public PalettedContainer blockStates() {
        return blockStates;
    }

    /**
     * バイオーム
     * 持たないセクションではnull
     *
     * @return バイオーム
     */
    public PalettedContainer biomes() {
        return biomes;
    }

    /**
     * ブロック状態を持つか
     *
     * @return 持つならtrue
     */
    public boolean hasBlockStates() {
        return blockStates != null;
    }

    /**
     * バイオームを持つか
     *
     * @return 持つならtrue
     */
    public boolean hasBiomes() {
        return biomes != null;
    }

    /**
     * 元のNBT
     * 解釈していないキーもここに残っている
     *
     * @return NBT
     */
    public NbtCompound raw() {
        return raw;
    }

    /**
     * NBTからセクションを読む
     *
     * @param nbt     セクションのNBT
     * @param options 読み込みオプション
     * @return セクション
     */
    public static ChunkSection fromNbt(NbtCompound nbt, ChunkReadOptions options) {
        Objects.requireNonNull(nbt, "nbt");
        ChunkSection section = new ChunkSection(nbt, nbt.getByte("Y"));
        NbtCompound blockStatesTag = nbt.optCompound("block_states");

        // 光源専用のセクションはblock_statesを持たない
        if (blockStatesTag != null) {
            section.blockStates = PalettedContainer.fromNbt(
                    blockStatesTag, Chunk.BLOCKS_PER_SECTION, 4, options.lenientBitStorage());
        }

        NbtCompound biomesTag = nbt.optCompound("biomes");

        if (biomesTag != null) {
            section.biomes = PalettedContainer.fromNbt(
                    biomesTag, Chunk.BIOMES_PER_SECTION, 1, options.lenientBitStorage());
        }

        return section;
    }

    /**
     * NBTへ書き戻す
     * 解釈していないキーはそのまま残る
     *
     * @return NBT
     */
    public NbtCompound toNbt() {
        if (blockStates != null) {
            raw.set("block_states", blockStates.toNbt());
        }

        if (biomes != null) {
            raw.set("biomes", biomes.toNbt());
        }

        return raw;
    }

    /** 使われていないパレット要素を取り除く */
    public void compact() {
        if (blockStates != null) {
            blockStates.compact();
        }

        if (biomes != null) {
            biomes.compact();
        }
    }
}

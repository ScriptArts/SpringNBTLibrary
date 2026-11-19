package io.github.scriptarts.springnbt.world;

import io.github.scriptarts.springnbt.SpringNbtException;
import io.github.scriptarts.springnbt.nbt.NbtCompound;
import io.github.scriptarts.springnbt.nbt.NbtList;
import io.github.scriptarts.springnbt.nbt.NbtTag;
import io.github.scriptarts.springnbt.nbt.TagType;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
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

    /**
     * ブロックの持ち方
     * 書き戻すときに読んだときと同じキーへ書くため、覚えておく
     */
    private ChunkFormat.BlockStorage blockStorage = ChunkFormat.BlockStorage.CONTAINER;

    /**
     * パレット付きコンテナを読んだときのキーの並び
     * 書き戻しで同じ並びにするため、コンテナのキーごとに覚えておく
     */
    private final Map<String, List<String>> containerKeys = new HashMap<>();

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
     * 1.18以降の形式（{@code block_states} / {@code biomes}）として読む
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
            section.containerKeys.put("block_states", new ArrayList<>(blockStatesTag.keys()));
        }

        NbtCompound biomesTag = nbt.optCompound("biomes");

        // 光源だけを持つセクションにはバイオームが無い
        if (biomesTag != null) {
            section.biomes = PalettedContainer.fromNbt(
                    biomesTag, Chunk.BIOMES_PER_SECTION, 1, options.lenientBitStorage());
            section.containerKeys.put("biomes", new ArrayList<>(biomesTag.keys()));
        }

        return section;
    }

    /**
     * 世代の持ち方に従ってNBTからセクションを読む
     *
     * @param nbt     セクションのNBT
     * @param options 読み込みオプション
     * @param format  チャンクの形式の世代
     * @return セクション
     */
    static ChunkSection fromNbtForFormat(NbtCompound nbt, ChunkReadOptions options, ChunkFormat format) {
        // 1.18以降の形式は公開の読み込みと同じ
        if (format.blockStorage() == ChunkFormat.BlockStorage.CONTAINER) {
            return fromNbt(nbt, options);
        }

        ChunkSection section = new ChunkSection(nbt, nbt.getByte("Y"));
        section.blockStorage = format.blockStorage();
        NbtList palette = nbt.optList("Palette");
        long[] blockStatesData = nbt.optLongArray("BlockStates");

        // Minecraftも両方がそろったセクションだけを読むので、
        // 片方しか無いセクション（光源だけを持つものなど）はブロックを持たない
        if (palette == null || blockStatesData == null) {
            return section;
        }

        List<NbtTag> entries = new ArrayList<>(palette.size());

        // 書き戻すときにCompoundのリストとして書くので、要素の型をここで確かめる
        for (NbtTag entry : palette) {
            // Compound以外の要素は1.17までの形式に無い
            if (!(entry instanceof NbtCompound)) {
                throw SpringNbtException.unexpectedTagType(
                        "Palette の要素が compound でない: " + entry.type().asString());
            }

            entries.add(entry);
        }

        // BlockStatesはパレットが1要素でも必ず書かれる
        section.blockStates = PalettedContainer.fromParts(
                entries, blockStatesData, Chunk.BLOCKS_PER_SECTION, 4,
                format.spanningBitStorage(), true, options.lenientBitStorage());
        return section;
    }

    /**
     * NBTへ書き戻す
     * 解釈していないキーはそのまま残る
     *
     * @return NBT
     */
    public NbtCompound toNbt() {
        // 1.17までの形式は、セクションの直下のPaletteとBlockStatesへ書き戻す
        if (blockStates != null && blockStorage == ChunkFormat.BlockStorage.SECTION_PALETTE) {
            PalettedContainer.Parts parts = blockStates.toParts();
            NbtList paletteTag = new NbtList(TagType.COMPOUND);

            // 要素は読んだときのまま並べる
            for (NbtTag entry : parts.palette()) {
                paletteTag.add(entry);
            }

            // 既存のキーへ書くので、キーの並びは読んだときのまま残る
            raw.setLongArray("BlockStates", parts.data());
            raw.set("Palette", paletteTag);
            return raw;
        }

        // 解釈したコンテナだけを書き戻す
        // 持たないキーは元のまま残す
        if (blockStates != null) {
            writeContainer(raw, "block_states", blockStates.toNbt(), containerKeys.get("block_states"));
        }

        // 解釈したコンテナだけを書き戻す
        // 持たないキーは元のまま残す
        if (biomes != null) {
            writeContainer(raw, "biomes", biomes.toNbt(), containerKeys.get("biomes"));
        }

        return raw;
    }

    /**
     * パレット付きコンテナを、読んだときのキーの並びを保ってセクションへ書き戻す
     *
     * <p>読んだときにあったキーはその並びで置き、要らなくなった{@code data}は落とす
     * 読んだときに無かった{@code data}を足すときだけ、ライブラリの並び（{@code data}、{@code palette}の順）を先に置く
     * どちらの場合も、読んだときにあったほかのキーは残す
     * 並びは読んだときのキーで決めるので、何度書き戻しても同じ結果になる
     *
     * @param section セクションのNBT
     * @param key コンテナのキー
     * @param written 書き出したコンテナ
     * @param readKeys 読んだときのキーの並び（読んでいなければnull）
     */
    private static void writeContainer(
            NbtCompound section, String key, NbtCompound written, List<String> readKeys) {
        NbtCompound current = section.optCompound(key);

        // 読んだときにコンテナが無ければ、書き出した形をそのまま置く
        if (current == null || readKeys == null) {
            section.set(key, written);
            return;
        }

        List<String> order = new ArrayList<>();
        // 読んだときに無かったdataを足すときだけ、ライブラリの並びを先に置く
        if (written.containsKey("data") && !readKeys.contains("data")) {
            order.addAll(written.keys());
        }

        // 読んだときの並びで、残すキーを後ろに続ける
        for (String name : readKeys) {
            // 先に並べたキーは二度入れない
            if (order.contains(name)) {
                continue;
            }

            // 要らなくなったdataは落とす
            if (name.equals("data") && !written.containsKey("data")) {
                continue;
            }

            order.add(name);
        }

        NbtCompound result = new NbtCompound();

        // 書き出した形にあるキーはその値で、ほかのキーは元の値で並べる
        for (String name : order) {
            // コンテナの中身は書き出した形の値にする
            if (written.containsKey(name)) {
                result.set(name, written.get(name));
            } else {
                result.set(name, current.get(name));
            }
        }

        section.set(key, result);
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

package io.github.scriptarts.springnbt.world;

import io.github.scriptarts.springnbt.ErrorCode;
import io.github.scriptarts.springnbt.SpringNbt;
import io.github.scriptarts.springnbt.SpringNbtException;
import io.github.scriptarts.springnbt.nbt.NbtByte;
import io.github.scriptarts.springnbt.nbt.NbtCompound;
import io.github.scriptarts.springnbt.nbt.NbtInt;
import io.github.scriptarts.springnbt.nbt.NbtList;
import io.github.scriptarts.springnbt.nbt.NbtString;
import io.github.scriptarts.springnbt.nbt.NbtTag;
import io.github.scriptarts.springnbt.nbt.TagType;
import java.util.Collection;
import java.util.Objects;
import java.util.Set;
import java.util.SortedMap;
import java.util.TreeMap;

/**
 * チャンク 1 つ分。地形の読み書きの入口。
 *
 * <p><strong>読んだ NBT をそのまま保持し、変更した部分だけを書き戻す。</strong>
 * 未知のキーを落とさないので、将来の追加要素があってもデータを壊さない。
 *
 * <p>仕様: {@code docs/spec/30-chunk-format.md}
 */
public final class Chunk {

    /** セクション 1 つに入るブロック数。 */
    public static final int BLOCKS_PER_SECTION = 4096;

    /** セクション 1 つに入るバイオームのエントリ数（4×4×4 単位）。 */
    public static final int BIOMES_PER_SECTION = 64;

    /** ブロックに紐づく付随データのキー。ブロックを置き換えたら整合が崩れる。 */
    private static final String[] BLOCK_DATA_KEYS = {"block_entities", "block_ticks", "fluid_ticks"};

    private final NbtCompound root;
    private final SortedMap<Integer, ChunkSection> sections = new TreeMap<>();

    private Chunk(NbtCompound root) {
        this.root = root;
    }

    /**
     * チャンク構造のバージョン。
     *
     * @return バージョン
     */
    public int dataVersion() {
        return root.getInt("DataVersion");
    }

    /**
     * 絶対チャンクX座標。
     *
     * @return 座標
     */
    public int x() {
        return root.getInt("xPos");
    }

    /**
     * 絶対チャンクZ座標。
     *
     * @return 座標
     */
    public int z() {
        return root.getInt("zPos");
    }

    /**
     * 最下段セクションのY位置。オーバーワールドは -4。
     *
     * @return Y位置
     */
    public int minSectionY() {
        return root.getInt("yPos");
    }

    /**
     * 生成段階（{@code minecraft:full} など）。
     *
     * @return 生成段階
     */
    public String status() {
        return root.getString("Status");
    }

    /**
     * 生成が完了しているか。ブロック改変の対象にしてよいのはこれだけ。
     *
     * @return 完了していれば true
     */
    public boolean isFullyGenerated() {
        return "minecraft:full".equals(status());
    }

    /**
     * 存在するセクションのY位置。昇順。
     *
     * @return Y位置の集合
     */
    public Set<Integer> sectionYs() {
        return sections.keySet();
    }

    /**
     * 元の NBT。解釈していないキーもここに残っている。
     *
     * @return NBT
     */
    public NbtCompound raw() {
        return root;
    }

    /**
     * NBT からチャンクを読む。
     *
     * @param nbt     チャンクの NBT
     * @param options 読み込みオプション。null なら既定値
     * @return チャンク
     * @throws SpringNbtException 必須のキーが無い、または構造が想定と違う場合
     */
    public static Chunk fromNbt(NbtCompound nbt, ChunkReadOptions options) {
        Objects.requireNonNull(nbt, "nbt");

        ChunkReadOptions effective;
        if (options == null) {
            effective = ChunkReadOptions.defaults();
        } else {
            effective = options;
        }

        Chunk chunk = new Chunk(nbt);
        chunk.checkDataVersion(effective);
        NbtList sectionList = nbt.optList("sections");

        if (sectionList == null) {
            return chunk;
        }

        // 並び順に依存しないよう、Y から索引を作る
        for (NbtTag entry : sectionList) {
            if (!(entry instanceof NbtCompound sectionTag)) {
                throw SpringNbtException.unexpectedTagType(
                        "sections の要素が compound でない: " + entry.type().asString());
            }

            ChunkSection section = ChunkSection.fromNbt(sectionTag, effective);
            chunk.sections.put(section.y(), section);
        }

        return chunk;
    }

    /** DataVersion を検査し、オプションに従って警告またはエラーにする。 */
    private void checkDataVersion(ChunkReadOptions options) {
        int version = dataVersion();

        if (version == SpringNbt.TARGET_DATA_VERSION) {
            return;
        }

        String message = "DataVersion が対象と違う: " + version
                + "（対象は " + SpringNbt.TARGET_DATA_VERSION + "）";

        if (options.onVersionMismatch() == VersionMismatchAction.ERROR) {
            throw new SpringNbtException(ErrorCode.UNSUPPORTED_DATA_VERSION, message);
        }

        if (options.onVersionMismatch() == VersionMismatchAction.WARN
                && options.onWarning() != null) {
            options.onWarning().accept(message);
        }
    }

    /**
     * NBT へ書き戻す。変更したセクションだけを反映し、他のキーはそのまま残す。
     *
     * @param options 書き込みオプション。null なら既定値
     * @return NBT
     * @throws SpringNbtException DataVersion が対象と違い、かつ書き戻しが許可されていない場合
     */
    public NbtCompound toNbt(ChunkWriteOptions options) {
        ChunkWriteOptions effective;
        if (options == null) {
            effective = ChunkWriteOptions.defaults();
        } else {
            effective = options;
        }

        int version = dataVersion();

        if (version != SpringNbt.TARGET_DATA_VERSION && !effective.allowForeignDataVersion()) {
            throw new SpringNbtException(ErrorCode.UNSUPPORTED_DATA_VERSION,
                    "DataVersion " + version + " のチャンクは書き戻せない（対象は "
                            + SpringNbt.TARGET_DATA_VERSION
                            + "）。許可するなら ChunkWriteOptions.setAllowForeignDataVersion(true)");
        }

        // 常に対象バージョンを書く
        root.set("DataVersion", new NbtInt(SpringNbt.TARGET_DATA_VERSION));

        if (sections.isEmpty()) {
            return root;
        }

        NbtList sectionList = new NbtList(TagType.COMPOUND);

        // Y の昇順で書き出す
        for (ChunkSection section : sections.values()) {
            sectionList.add(section.toNbt());
        }

        root.set("sections", sectionList);
        return root;
    }

    /**
     * Y位置からセクションを得る。
     *
     * @param sectionY セクションのY位置
     * @return セクション。無ければ null
     */
    public ChunkSection section(int sectionY) {
        return sections.get(sectionY);
    }

    /**
     * ブロックを取得する。
     *
     * @param x チャンク内相対X座標 (0..15)
     * @param y 絶対Y座標
     * @param z チャンク内相対Z座標 (0..15)
     * @return ブロック。セクションが無い、または block_states を持たない場合は null
     */
    public BlockState getBlock(int x, int y, int z) {
        checkLocalCoordinates(x, z);
        ChunkSection section = section(y >> 4);

        if (section == null || !section.hasBlockStates()) {
            return null;
        }

        NbtTag entry = section.blockStates().get(blockIndex(x, y, z));

        if (!(entry instanceof NbtCompound compound)) {
            throw SpringNbtException.unexpectedTagType(
                    "ブロックのパレット要素が compound でない: " + entry.type().asString());
        }

        return BlockState.fromNbt(compound);
    }

    /**
     * ブロックを設定する。
     *
     * @param x     チャンク内相対X座標 (0..15)
     * @param y     絶対Y座標
     * @param z     チャンク内相対Z座標 (0..15)
     * @param state ブロック
     * @throws SpringNbtException 対象のセクションが無い、または block_states を持たない場合
     */
    public void setBlock(int x, int y, int z, BlockState state) {
        Objects.requireNonNull(state, "state");
        checkLocalCoordinates(x, z);

        int sectionY = y >> 4;
        ChunkSection section = section(sectionY);

        if (section == null || !section.hasBlockStates()) {
            throw SpringNbtException.invalidArgument("Y=" + y + " を含むセクション（Y=" + sectionY
                    + "）が無いか、ブロックを持たない。本ライブラリはセクションを新規生成しない");
        }

        // 同じ状態を置き直すだけなら、付随データを触る理由がない。
        // プロパティの並び順に左右されないよう、NBT ではなく BlockState として比べる
        BlockState current = getBlock(x, y, z);

        if (current != null && current.equals(state)) {
            return;
        }

        section.blockStates().set(blockIndex(x, y, z), state.toNbt());
        removeBlockData(x, y, z);
    }

    /**
     * その座標を指す付随データを取り除く。
     *
     * <p>{@code block_entities} / {@code block_ticks} / {@code fluid_ticks} の要素は
     * いずれも {@code x} {@code y} {@code z} を<b>絶対座標</b>で持つ。
     */
    private void removeBlockData(int x, int y, int z) {
        int absoluteX = (x() * 16) + x;
        int absoluteZ = (z() * 16) + z;

        // 3 つのリストは形が同じなので、まとめて同じ処理をかける
        for (String key : BLOCK_DATA_KEYS) {
            NbtList list = root.optList(key);

            if (list == null || list.size() == 0) {
                continue;
            }

            // 後ろから削ると、削除しても残りの添字がずれない
            for (int position = list.size() - 1; position >= 0; position--) {
                NbtTag element = list.get(position);

                if (element instanceof NbtCompound entry
                        && matchesPosition(entry, absoluteX, y, absoluteZ)) {
                    list.removeAt(position);
                }
            }
        }
    }

    /** 付随データの要素が、指定の絶対座標を指しているか。 */
    private static boolean matchesPosition(NbtCompound entry, int x, int y, int z) {
        Integer entryX = entry.optInt("x");
        Integer entryY = entry.optInt("y");
        Integer entryZ = entry.optInt("z");

        // 座標を持たない要素は、対象かどうか判断できないので触らない
        if (entryX == null || entryY == null || entryZ == null) {
            return false;
        }

        return entryX == x && entryY == y && entryZ == z;
    }

    /**
     * バイオームを取得する。4×4×4 の単位なので、座標は自動的に丸められる。
     *
     * @param x チャンク内相対X座標 (0..15)
     * @param y 絶対Y座標
     * @param z チャンク内相対Z座標 (0..15)
     * @return バイオームID。セクションが無い場合は null
     */
    public String getBiome(int x, int y, int z) {
        checkLocalCoordinates(x, z);
        ChunkSection section = section(y >> 4);

        if (section == null || !section.hasBiomes()) {
            return null;
        }

        NbtTag entry = section.biomes().get(biomeIndex(x, y, z));

        if (!(entry instanceof NbtString text)) {
            throw SpringNbtException.unexpectedTagType(
                    "バイオームのパレット要素が string でない: " + entry.type().asString());
        }

        return text.value();
    }

    /**
     * バイオームを設定する。4×4×4 の単位。
     *
     * @param x     チャンク内相対X座標 (0..15)
     * @param y     絶対Y座標
     * @param z     チャンク内相対Z座標 (0..15)
     * @param biome バイオームID
     */
    public void setBiome(int x, int y, int z, String biome) {
        Objects.requireNonNull(biome, "biome");
        checkLocalCoordinates(x, z);

        int sectionY = y >> 4;
        ChunkSection section = section(sectionY);

        if (section == null || !section.hasBiomes()) {
            throw SpringNbtException.invalidArgument("Y=" + y + " を含むセクション（Y=" + sectionY
                    + "）が無いか、バイオームを持たない");
        }

        section.biomes().set(biomeIndex(x, y, z), new NbtString(biome));
    }

    /**
     * {@code Heightmaps} を削除し、Minecraft に再計算させる。
     *
     * <p>本ライブラリは高さマップを再計算しない。ブロックを改変したら呼ぶこと
     * （{@code docs/adr/0004-defer-heightmap-recalc.md}）。
     */
    public void clearHeightmaps() {
        root.remove("Heightmaps");
    }

    /** {@code isLightOn} を 0 にし、光源の再計算を促す。 */
    public void invalidateLighting() {
        root.set("isLightOn", new NbtByte((byte) 0));
    }

    /** 使われていないパレット要素を全セクションから取り除く。 */
    public void compact() {
        Collection<ChunkSection> values = sections.values();

        for (ChunkSection section : values) {
            section.compact();
        }
    }

    /**
     * セクション内のブロック添字。
     *
     * <p>{@code & 15} により負のY座標でも正しく求まる。
     *
     * @param x X座標
     * @param y Y座標
     * @param z Z座標
     * @return 添字
     */
    public static int blockIndex(int x, int y, int z) {
        return ((y & 15) * 256) + ((z & 15) * 16) + (x & 15);
    }

    /**
     * セクション内のバイオーム添字。1 エントリが 4×4×4 ブロック。
     *
     * @param x X座標
     * @param y Y座標
     * @param z Z座標
     * @return 添字
     */
    public static int biomeIndex(int x, int y, int z) {
        return (((y & 15) / 4) * 16) + (((z & 15) / 4) * 4) + ((x & 15) / 4);
    }

    private static void checkLocalCoordinates(int x, int z) {
        // チャンク内相対座標は 0..15 でなければならない
        if (x < 0 || x > 15 || z < 0 || z > 15) {
            throw SpringNbtException.invalidArgument(
                    "チャンク内相対座標が範囲外: (" + x + ", " + z + ")。X も Z も 0..15 であること");
        }
    }
}

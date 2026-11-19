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
 * チャンク1つ分
 * 地形の読み書きはここから行う
 *
 * <p><strong>読んだNBTをそのまま保持し、書き戻すときに作り直すのはセクションだけにする</strong>
 * 未知のキーを落とさないので、将来の追加要素があってもデータをおかしくしない
 */
public final class Chunk {

    /** セクション1つに入るブロック数 */
    public static final int BLOCKS_PER_SECTION = 4096;

    /** セクション1つに入るバイオームのエントリ数（4×4×4単位） */
    public static final int BIOMES_PER_SECTION = 64;

    private final NbtCompound root;
    private boolean modified;
    private final SortedMap<Integer, ChunkSection> sections = new TreeMap<>();

    /**
     * チャンクの形式の世代
     * 引けなかったチャンクはnullのままで、元のNBTだけを持つ
     */
    private ChunkFormat format;
    private int formatDataVersion;

    private Chunk(NbtCompound root) {
        this.root = root;
    }

    /**
     * チャンク構造のバージョン
     *
     * @return バージョン
     */
    public int dataVersion() {
        return root.getInt("DataVersion");
    }

    /**
     * チャンクの形式の世代を選ぶのに使ったDataVersion
     *
     * <p>読み込みのオプションで指定していればその値、指定が無ければ{@link #dataVersion()}
     *
     * @return DataVersion
     */
    public int formatDataVersion() {
        return formatDataVersion;
    }

    /**
     * 絶対チャンクX座標
     *
     * @return 座標
     */
    public int x() {
        return body().getInt("xPos");
    }

    /**
     * 絶対チャンクZ座標
     *
     * @return 座標
     */
    public int z() {
        return body().getInt("zPos");
    }

    /**
     * 最下段セクションのY位置
     * オーバーワールドは-4
     *
     * @return Y位置
     */
    public int minSectionY() {
        return root.getInt("yPos");
    }

    /**
     * 生成段階（{@code minecraft:full}など）
     *
     * @return 生成段階
     */
    public String status() {
        return body().getString("Status");
    }

    /**
     * 生成が完了しているか
     * ブロック改変の対象にしてよいのはこれだけ
     *
     * @return 完了していればtrue
     */
    public boolean isFullyGenerated() {
        return "minecraft:full".equals(status());
    }

    /**
     * このチャンクに変更が加わったか
     *
     * <p>ブロックやバイオームを書き換えると立つ
     * {@link Dimension#flush()}はこれが立っているチャンクだけを書き戻す
     *
     * <p>{@link #raw()}を直接いじった場合は立たないので、自分で{@link #setIsModified(boolean)}を呼ぶこと
     *
     * @return 変更があればtrue
     */
    public boolean isModified() {
        return modified;
    }

    /**
     * 変更の印を付け外しする
     *
     * @param value 立てるならtrue
     */
    public void setIsModified(boolean value) {
        modified = value;
    }

    /**
     * 存在するセクションのY位置
     * 昇順
     *
     * @return Y位置の集合
     */
    public Set<Integer> sectionYs() {
        return sections.keySet();
    }

    /**
     * 元のNBT
     * 解釈していないキーもここに残っている
     *
     * @return NBT
     */
    public NbtCompound raw() {
        return root;
    }

    /**
     * NBTからチャンクを読む
     *
     * <p>形式の世代は、オプションで指定したDataVersionか、チャンク自身のDataVersionで選ぶ
     * DataVersionが1519未満のチャンクは、指定があってもどの世代でも解釈せず、元のNBTだけを持つ
     *
     * @param nbt     チャンクのNBT
     * @param options 読み込みオプション
     * nullなら既定値
     * @return チャンク
     * @throws SpringNbtException 世代を選ぶDataVersionが1519未満の場合（INVALID_ARGUMENT）、
     * 選んだ世代とチャンクの構造が合わない場合（MALFORMED_DATA）、
     * 必須のキーが無い、または構造が想定と違う場合
     */
    public static Chunk fromNbt(NbtCompound nbt, ChunkReadOptions options) {
        Objects.requireNonNull(nbt, "nbt");

        ChunkReadOptions effective;
        if (options == null) {
            effective = ChunkReadOptions.defaults();
        } else {
            effective = options;
        }

        Integer requested = effective.formatDataVersion();

        // 1.13より前の形式は、どの世代の部品でも読めない
        if (requested != null && requested < ChunkFormat.OLDEST_FORMAT_DATA_VERSION) {
            throw SpringNbtException.invalidArgument("世代を選ぶDataVersionは"
                    + ChunkFormat.OLDEST_FORMAT_DATA_VERSION + "以上でなければならない: " + requested);
        }

        Chunk chunk = new Chunk(nbt);
        chunk.checkDataVersion(effective);
        int dataVersion = chunk.dataVersion();
        chunk.formatDataVersion = dataVersion;

        // 指定があれば、チャンク自身のDataVersionの代わりにその値で世代を選ぶ
        if (requested != null) {
            chunk.formatDataVersion = requested;
        }

        // 1.13より前のチャンクはブロックが数値IDで、どの世代で読んでも誤った値になる
        if (dataVersion < ChunkFormat.OLDEST_FORMAT_DATA_VERSION) {
            return chunk;
        }

        ChunkFormat format = ChunkFormat.forDataVersion(chunk.formatDataVersion);

        // 表に無い世代のチャンクは、解釈せずに元のNBTだけを持つ
        if (format == null) {
            return chunk;
        }

        chunk.format = format;
        boolean hasLevel = nbt.optCompound("Level") != null;

        // 選んだ世代と本体の包み方が食い違うなら、黙って空のチャンクとして読まずに弾く
        if (hasLevel != format.wrappedInLevel()) {
            throw SpringNbtException.malformed("DataVersion " + chunk.formatDataVersion
                    + "で選んだ形式と、ルートのLevelの有無が合わない");
        }

        NbtList sectionList = chunk.body().optList(format.sectionsKey());

        if (sectionList == null) {
            return chunk;
        }

        // 並び順に依存しないよう、Yから索引を作る
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

    /** DataVersionを検査し、オプションに従って警告またはエラーにする */
    private void checkDataVersion(ChunkReadOptions options) {
        int version = dataVersion();

        // 形式が同じであれば、新しいバージョンでもそのまま読める
        if (version >= SpringNbt.MIN_SUPPORTED_DATA_VERSION) {
            return;
        }

        String message = "DataVersion " + version + " はこのライブラリが扱う形式より古い（"
                + SpringNbt.MIN_SUPPORTED_DATA_VERSION + " 以降が対象）";

        if (options.onVersionMismatch() == VersionMismatchAction.ERROR) {
            throw new SpringNbtException(ErrorCode.UNSUPPORTED_DATA_VERSION, message);
        }

        // 警告として扱う設定で、通知先があるときだけ知らせる
        if (options.onVersionMismatch() == VersionMismatchAction.WARN
                && options.onWarning() != null) {
            options.onWarning().accept(message);
        }
    }

    /**
     * NBTへ書き戻す
     * 全セクションを読んだときの世代の形式で書き戻し、他のキーはそのまま残す
     *
     * @param options 書き込みオプション
     * nullなら既定値
     * @return NBT
     * @throws SpringNbtException DataVersionが扱える形式より古く、かつ書き戻しが許可されていない場合
     */
    public NbtCompound toNbt(ChunkWriteOptions options) {
        ChunkWriteOptions effective;
        if (options == null) {
            effective = ChunkWriteOptions.defaults();
        } else {
            effective = options;
        }

        int version = dataVersion();

        // 形式の違う古いチャンクは、書き戻すと使えなくなりかねない
        if (version < SpringNbt.MIN_SUPPORTED_DATA_VERSION && !effective.allowForeignDataVersion()) {
            throw new SpringNbtException(ErrorCode.UNSUPPORTED_DATA_VERSION,
                    "DataVersion " + version + " のチャンクは書き戻せない（"
                            + SpringNbt.MIN_SUPPORTED_DATA_VERSION
                            + " 以降が対象）。許可するなら"
                            + " ChunkWriteOptions.setAllowForeignDataVersion(true)");
        }

        // DataVersionは読んだ値のまま残す
        // 書き換えると、そのワールドを開くゲーム側の判断を誤らせる

        // 元のNBTだけを持つチャンクは、セクションも読んでいないのでそのまま返す
        if (format == null || sections.isEmpty()) {
            return root;
        }

        NbtList sectionList = new NbtList(TagType.COMPOUND);

        // Yの昇順で書き出す
        for (ChunkSection section : sections.values()) {
            sectionList.add(section.toNbt());
        }

        body().set(format.sectionsKey(), sectionList);
        return root;
    }

    /**
     * チャンクの本体
     * 1.17までの形式では{@code Level}の中、1.18以降はルート
     */
    private NbtCompound body() {
        NbtCompound level = root.optCompound("Level");

        // 世代とLevelの有無は読み込みで突き合わせてあるので、Levelがあればその中が本体
        if (level != null) {
            return level;
        }

        return root;
    }

    /**
     * チャンクの形式の世代を返す
     *
     * @throws SpringNbtException 世代を引けず、元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）
     */
    private ChunkFormat requireFormat() {
        if (format == null) {
            throw new SpringNbtException(ErrorCode.UNSUPPORTED_DATA_VERSION,
                    "DataVersion " + dataVersion() + "のチャンクは形式を解釈せず元のNBTだけを持つので、この操作はできない");
        }

        return format;
    }

    /**
     * Y位置からセクションを得る
     *
     * @param sectionY セクションのY位置
     * @return セクション
     * 無ければnull
     */
    public ChunkSection section(int sectionY) {
        return sections.get(sectionY);
    }

    /**
     * ブロックを取得する
     *
     * @param x チャンク内相対X座標 (0..15)
     * @param y 絶対Y座標
     * @param z チャンク内相対Z座標 (0..15)
     * @return ブロック
     * セクションが無い、またはblock_statesを持たない場合はnull
     * @throws SpringNbtException 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）
     */
    public BlockState getBlock(int x, int y, int z) {
        ChunkFormat chunkFormat = requireFormat();
        checkLocalCoordinates(x, z);
        ChunkSection section = section(y >> 4);

        if (section == null || !section.hasBlockStates()) {
            return null;
        }

        // パレットの要素の形は世代で違うので、世代ごとに決めたDataVersionで読む
        return BlockState.fromNbtForDataVersion(
                section.blockStates().get(blockIndex(x, y, z)), chunkFormat.paletteDataVersion());
    }

    /**
     * ブロックを設定する
     *
     * @param x     チャンク内相対X座標 (0..15)
     * @param y     絶対Y座標
     * @param z     チャンク内相対Z座標 (0..15)
     * @param state ブロック
     * @throws SpringNbtException 対象のセクションが無い、またはblock_statesを持たない場合
     */
    public void setBlock(int x, int y, int z, String state) {
        Objects.requireNonNull(state, "state");
        setBlock(x, y, z, BlockState.parse(state));
    }

    /**
     * ブロックを設定する
     *
     * <p>置き換えによって不整合になる付随データ（{@code block_entities} /
     * {@code block_ticks} / {@code fluid_ticks}のうち、その座標を指すもの）は同時に取り除く
     * 残すとブロックと中身が食い違い、Minecraft側で予期しない挙動になるため
     *
     * <p>パレットには、チャンクを読んだときの世代の形式で入れる
     *
     * @param x     チャンク内相対X座標 (0..15)
     * @param y     絶対Y座標
     * @param z     チャンク内相対Z座標 (0..15)
     * @param state ブロック
     * @throws SpringNbtException 対象のセクションが無い、またはblock_statesを持たない場合、
     * 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）
     */
    public void setBlock(int x, int y, int z, BlockState state) {
        Objects.requireNonNull(state, "state");
        ChunkFormat chunkFormat = requireFormat();
        checkLocalCoordinates(x, z);

        int sectionY = y >> 4;
        ChunkSection section = section(sectionY);

        if (section == null || !section.hasBlockStates()) {
            throw SpringNbtException.invalidArgument("Y=" + y + " を含むセクション（Y=" + sectionY
                    + "）が無いか、ブロックを持たない。本ライブラリはセクションを新規生成しない");
        }

        // 同じ状態を置き直すだけなら、付随データを触る理由がない
        // プロパティの並び順に左右されないよう、NBTではなくBlockStateとして比べる
        BlockState current = getBlock(x, y, z);

        if (current != null && current.equals(state)) {
            return;
        }

        // 書き戻すときに読んだときと同じ形式になるよう、世代ごとに決めたDataVersionで変換する
        section.blockStates().set(
                blockIndex(x, y, z), state.toNbtForDataVersion(chunkFormat.paletteDataVersion()));
        removeBlockData(chunkFormat, x, y, z);
        modified = true;
    }

    /**
     * その座標を指す付随データを取り除く
     *
     * <p>{@code block_entities} / {@code block_ticks} / {@code fluid_ticks}の要素は
     * いずれも{@code x} {@code y} {@code z}を<b>絶対座標</b>で持つ
     */
    private void removeBlockData(ChunkFormat chunkFormat, int x, int y, int z) {
        int absoluteX = (x() * 16) + x;
        int absoluteZ = (z() * 16) + z;
        NbtCompound body = body();

        // 3つのリストは形が同じなので、まとめて同じ処理をかける
        for (String key : chunkFormat.blockDataKeys()) {
            NbtList list = body.optList(key);

            if (list == null || list.size() == 0) {
                continue;
            }

            // 後ろから削ると、削除しても残りの添字がずれない
            for (int position = list.size() - 1; position >= 0; position--) {
                NbtTag element = list.get(position);

                // 座標を持つ要素のうち、指定の位置を指すものだけを取り除く
                if (element instanceof NbtCompound entry
                        && matchesPosition(entry, absoluteX, y, absoluteZ)) {
                    list.removeAt(position);
                }
            }
        }
    }

    /** 付随データの要素が、指定の絶対座標を指しているか */
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
     * バイオームを取得する
     * 4×4×4の単位なので、座標は自動的に丸められる
     *
     * @param x チャンク内相対X座標 (0..15)
     * @param y 絶対Y座標
     * @param z チャンク内相対Z座標 (0..15)
     * @return バイオームID
     * セクションが無い場合はnull
     * @throws SpringNbtException 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）
     */
    public String getBiome(int x, int y, int z) {
        requireFormat();
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
     * バイオームを設定する
     * 4×4×4の単位
     *
     * @param x     チャンク内相対X座標 (0..15)
     * @param y     絶対Y座標
     * @param z     チャンク内相対Z座標 (0..15)
     * @param biome バイオームID
     * @throws SpringNbtException 対象のセクションが無い、またはバイオームを持たない場合、
     * 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）
     */
    public void setBiome(int x, int y, int z, String biome) {
        Objects.requireNonNull(biome, "biome");
        requireFormat();
        checkLocalCoordinates(x, z);

        int sectionY = y >> 4;
        ChunkSection section = section(sectionY);

        if (section == null || !section.hasBiomes()) {
            throw SpringNbtException.invalidArgument("Y=" + y + " を含むセクション（Y=" + sectionY
                    + "）が無いか、バイオームを持たない");
        }

        section.biomes().set(biomeIndex(x, y, z), new NbtString(biome));
        modified = true;
    }

    /**
     * {@code Heightmaps}を削除し、Minecraftに再計算させる
     *
     * <p>本ライブラリは高さマップを再計算しない
     * ブロックを改変したら呼ぶこと
     *
     * @throws SpringNbtException 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）
     */
    public void clearHeightmaps() {
        requireFormat();
        body().remove("Heightmaps");
        modified = true;
    }

    /**
     * {@code isLightOn}を0にし、光源の再計算を促す
     *
     * @throws SpringNbtException 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）
     */
    public void invalidateLighting() {
        requireFormat();
        body().setByte("isLightOn", (byte) 0);
        modified = true;
    }

    /** 使われていないパレット要素を全セクションから取り除く */
    public void compact() {
        Collection<ChunkSection> values = sections.values();

        // 全セクションのパレットをまとめて掃除する
        for (ChunkSection section : values) {
            section.compact();
        }
    }

    /**
     * セクション内のブロック添字
     *
     * <p>{@code & 15}により負のY座標でも正しく求まる
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
     * セクション内のバイオーム添字
     * 1エントリが4×4×4ブロック
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
        // チャンク内相対座標は0..15でなければならない
        if (x < 0 || x > 15 || z < 0 || z > 15) {
            throw SpringNbtException.invalidArgument(
                    "チャンク内相対座標が範囲外: (" + x + ", " + z + ")。X も Z も 0..15 であること");
        }
    }
}

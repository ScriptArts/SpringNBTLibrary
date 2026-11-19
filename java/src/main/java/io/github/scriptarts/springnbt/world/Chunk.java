package io.github.scriptarts.springnbt.world;

import io.github.scriptarts.springnbt.ErrorCode;
import io.github.scriptarts.springnbt.SpringNbt;
import io.github.scriptarts.springnbt.SpringNbtException;
import io.github.scriptarts.springnbt.nbt.NbtByte;
import io.github.scriptarts.springnbt.nbt.NbtCompound;
import io.github.scriptarts.springnbt.nbt.NbtInt;
import io.github.scriptarts.springnbt.nbt.NbtIntArray;
import io.github.scriptarts.springnbt.nbt.NbtList;
import io.github.scriptarts.springnbt.nbt.NbtString;
import io.github.scriptarts.springnbt.nbt.NbtTag;
import io.github.scriptarts.springnbt.nbt.TagType;
import java.util.Collection;
import java.util.List;
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

    /** 1.15から1.17までの形式で、チャンクの{@code Biomes}が持つ数値のバイオームIDの数（4×4×4単位で高さ256まで） */
    private static final int BIOME_IDS_3D_LENGTH = 1024;

    /** 1.14までの形式で、チャンクの{@code Biomes}が持つ数値のバイオームIDの数（列ごと） */
    private static final int BIOME_IDS_2D_LENGTH = 256;

    /** DataVersionの無いチャンクで、世代の指定も無いときの{@link #formatDataVersion()} */
    private static final int MISSING_DATA_VERSION = -1;

    /** 1.17までの形式で、バイオームIDを持つ最も高いY座標 */
    private static final int BIOME_IDS_MAX_Y = 255;

    /** 生成段階の名前空間 */
    private static final String MINECRAFT_NAMESPACE = "minecraft:";

    private final NbtCompound root;
    private boolean modified;
    private final SortedMap<Integer, ChunkSection> sections = new TreeMap<>();

    /**
     * チャンクの形式の世代
     * 引けなかったチャンクはnullのままで、元のNBTだけを持つ
     */
    private ChunkFormat format;

    /**
     * チャンクの形式の世代を選ぶのに使ったDataVersion
     * 読み込みのオプションで指定していればその値、指定が無ければチャンク自身のDataVersion
     */
    private int formatDataVersion;

    private Chunk(NbtCompound root) {
        this.root = root;
    }

    /**
     * チャンク構造のバージョン
     *
     * @return バージョン
     * @throws SpringNbtException {@code DataVersion}の無いチャンク（1.9より前）の場合
     */
    public int dataVersion() {
        return root.getInt("DataVersion");
    }

    /**
     * チャンク自身のDataVersion
     *
     * @return DataVersion
     * 無ければnull
     */
    private Integer ownDataVersion() {
        return root.optInt("DataVersion");
    }

    /**
     * エラーや警告の文で、チャンクをDataVersionで言い表す
     *
     * @param dataVersion チャンク自身のDataVersion
     * 無ければnull
     * @return チャンクを言い表す文
     */
    private static String describeChunk(Integer dataVersion) {
        // 1.9より前のチャンクはDataVersionを持たない
        if (dataVersion == null) {
            return "DataVersionの無いチャンク";
        }

        return "DataVersion " + dataVersion + "のチャンク";
    }

    /**
     * チャンクの形式の世代を選ぶのに使ったDataVersion
     *
     * <p>読み込みのオプションで指定していればその値、指定が無ければ{@link #dataVersion()}
     * {@link #dataVersion()}が1519未満のチャンクでは、世代を選ばずに指定の値をそのまま返す
     * {@code DataVersion}の無いチャンクで指定も無ければ-1
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
     * 1.17までの形式では0
     *
     * @return Y位置
     * @throws SpringNbtException 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）
     */
    public int minSectionY() {
        ChunkFormat chunkFormat = requireFormat();

        // 1.17までの形式はyPosを持たず、セクションは0段目から始まる
        if (!chunkFormat.hasYPos()) {
            return 0;
        }

        return root.getInt("yPos");
    }

    /**
     * 生成段階（{@code minecraft:full}など）
     * 1.19までは名前空間の無い{@code full}などで入る
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
     * <p>1.14までの形式では、1.13の{@code postprocessed}と{@code fullchunk}も生成済みとみなす
     * {@code Status}が無いか文字列でないチャンク（1.13より前のものなど）は生成済みとみなさない
     *
     * @return 完了していればtrue
     */
    public boolean isFullyGenerated() {
        String status;

        // 1.13より前のチャンクなど、Statusを文字列として読めないものは生成済みとみなさない
        try {
            status = status();
        } catch (SpringNbtException error) {
            return false;
        }

        // 名前空間の有無はバージョンで違うので、外してから比べる
        if (status.startsWith(MINECRAFT_NAMESPACE)) {
            status = status.substring(MINECRAFT_NAMESPACE.length());
        }

        List<String> fullStatuses = ChunkFormat.DEFAULT_FULL_STATUSES;

        // 生成済みとみなす値は世代で違う
        if (format != null) {
            fullStatuses = format.fullStatuses();
        }

        return fullStatuses.contains(status);
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
        Integer dataVersion = chunk.ownDataVersion();
        chunk.formatDataVersion = MISSING_DATA_VERSION;

        // DataVersionを持つチャンクは、指定が無ければそれで世代を選ぶ
        if (dataVersion != null) {
            chunk.formatDataVersion = dataVersion;
        }

        // 指定があれば、チャンク自身のDataVersionの代わりにその値で世代を選ぶ
        if (requested != null) {
            chunk.formatDataVersion = requested;
        }

        // 1.13より前のチャンクはブロックが数値IDで、どの世代で読んでも誤った値になる
        // DataVersionの無いチャンクは1.9より前のものなので、同じく解釈しない
        if (dataVersion == null || dataVersion < ChunkFormat.OLDEST_FORMAT_DATA_VERSION) {
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

            // セクションのブロックの持ち方は世代で違う
            ChunkSection section = ChunkSection.fromNbtForFormat(sectionTag, effective, format);
            chunk.sections.put(section.y(), section);
        }

        return chunk;
    }

    /** DataVersionを検査し、オプションに従って警告またはエラーにする */
    private void checkDataVersion(ChunkReadOptions options) {
        Integer version = ownDataVersion();

        // 形式が同じであれば、新しいバージョンでもそのまま読める
        if (version != null && version >= SpringNbt.MIN_SUPPORTED_DATA_VERSION) {
            return;
        }

        String message = describeChunk(version) + "はこのライブラリが扱う形式より古い（"
                + SpringNbt.MIN_SUPPORTED_DATA_VERSION + "以降が対象）";

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

        Integer version = ownDataVersion();
        boolean supported = version != null && version >= SpringNbt.MIN_SUPPORTED_DATA_VERSION;

        // 形式の違う古いチャンクは、書き戻すと使えなくなりかねない
        if (!supported && !effective.allowForeignDataVersion()) {
            throw new SpringNbtException(ErrorCode.UNSUPPORTED_DATA_VERSION,
                    describeChunk(version) + "は書き戻せない（"
                            + SpringNbt.MIN_SUPPORTED_DATA_VERSION
                            + "以降が対象）。許可するなら"
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
        // 世代を引けなかったチャンクは、ブロックなどの場所が分からない
        if (format == null) {
            throw new SpringNbtException(ErrorCode.UNSUPPORTED_DATA_VERSION,
                    describeChunk(ownDataVersion()) + "は形式を解釈せず元のNBTだけを持つので、この操作はできない");
        }

        return format;
    }

    /**
     * バイオームを名前で読み書きできる世代を返す
     *
     * @throws SpringNbtException 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）、
     * バイオームを数値のIDで持つ世代の場合（UNSUPPORTED_FEATURE）
     */
    private ChunkFormat requireNamedBiomes() {
        ChunkFormat chunkFormat = requireFormat();

        // 1.17まではバイオームを数値のIDで持ち、名前では読み書きできない
        if (chunkFormat.biomeStorage() != ChunkFormat.BiomeStorage.PALETTED) {
            throw SpringNbtException.unsupportedFeature("DataVersion " + formatDataVersion
                    + "のチャンクはバイオームを数値のIDで持つ。getBiomeId / setBiomeIdを使うこと");
        }

        return chunkFormat;
    }

    /**
     * バイオームを数値のIDで読み書きできる世代を返す
     *
     * @throws SpringNbtException 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）、
     * バイオームを名前で持つ世代の場合（UNSUPPORTED_FEATURE）
     */
    private ChunkFormat requireBiomeIds() {
        ChunkFormat chunkFormat = requireFormat();

        // 1.18以降はバイオームを名前で持ち、数値のIDでは読み書きできない
        if (chunkFormat.biomeStorage() == ChunkFormat.BiomeStorage.PALETTED) {
            throw SpringNbtException.unsupportedFeature("DataVersion " + formatDataVersion
                    + "のチャンクはバイオームを名前で持つ。getBiome / setBiomeを使うこと");
        }

        return chunkFormat;
    }

    /**
     * 本体の{@code Biomes}を返す
     * 無い、IntArrayでない、長さが世代と合わない場合はnull
     */
    private int[] biomeIds(ChunkFormat chunkFormat) {
        // 生成途中のチャンクなどは、Biomesを持たないか別の形で持つ
        if (!(body().opt("Biomes") instanceof NbtIntArray biomes)
                || biomes.value().length != biomeIdsLength(chunkFormat)) {
            return null;
        }

        return biomes.value();
    }

    /** 世代の{@code Biomes}が持つ数値のバイオームIDの数 */
    private static int biomeIdsLength(ChunkFormat chunkFormat) {
        // 列ごとに持つ形式は256個
        if (chunkFormat.biomeStorage() == ChunkFormat.BiomeStorage.IDS_2D) {
            return BIOME_IDS_2D_LENGTH;
        }

        return BIOME_IDS_3D_LENGTH;
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

        // 書き戻すときに読んだときと同じ形式になるよう、世代ごとに決めたDataVersionで読み書きする
        NbtTag entry = paletteEntryFor(section.blockStates(), state, chunkFormat.paletteDataVersion());
        section.blockStates().set(blockIndex(x, y, z), entry);
        removeBlockData(chunkFormat, x, y, z);
        modified = true;
    }

    /**
     * ブロック状態を置くときに使うパレット要素を決める
     *
     * <p>同じ状態の要素がパレットにあれば、キーやプロパティの並びが違ってもそれを使う
     * 無ければ世代の形式で作る
     */
    private static NbtTag paletteEntryFor(PalettedContainer container, BlockState state, int dataVersion) {
        // 実データの{Properties, Name}の並びの要素も、状態として比べて使い回す
        for (NbtTag entry : container.palette()) {
            // 状態が同じ要素が見つかれば、パレットを増やさずにそれを置く
            if (BlockState.fromNbtForDataVersion(entry, dataVersion).equals(state)) {
                return entry;
            }
        }

        return state.toNbtForDataVersion(dataVersion);
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
     * @throws SpringNbtException 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）、
     * バイオームを数値のIDで持つ1.17までの形式の場合（UNSUPPORTED_FEATURE）
     */
    public String getBiome(int x, int y, int z) {
        requireNamedBiomes();
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
     * 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）、
     * バイオームを数値のIDで持つ1.17までの形式の場合（UNSUPPORTED_FEATURE）
     */
    public void setBiome(int x, int y, int z, String biome) {
        Objects.requireNonNull(biome, "biome");
        requireNamedBiomes();
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
     * 数値のバイオームIDを取得する（1.17までの形式）
     * 1.15以降の形式は4×4×4の単位なので、座標は自動的に丸められる
     * 1.14までの形式は列ごとに持つので、Yは見ない
     *
     * <p>IDは名前に直さない
     * 1.16.2以降はデータパックで独自のバイオームを足せるので、固定の表では正しく引けないため
     *
     * @param x チャンク内相対X座標 (0..15)
     * @param y 絶対Y座標
     * @param z チャンク内相対Z座標 (0..15)
     * @return バイオームID
     * 1.15以降の形式でYが0..255の外の場合と、{@code Biomes}が無いか形が違う場合はnull
     * @throws SpringNbtException 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）、
     * バイオームを名前で持つ1.18以降の形式の場合（UNSUPPORTED_FEATURE）
     */
    public Integer getBiomeId(int x, int y, int z) {
        ChunkFormat chunkFormat = requireBiomeIds();
        checkLocalCoordinates(x, z);
        int[] biomes = biomeIds(chunkFormat);

        // Biomesを読めないチャンクは値を持たない
        if (biomes == null) {
            return null;
        }

        // 列ごとに持つ形式は高さを見ない
        if (chunkFormat.biomeStorage() == ChunkFormat.BiomeStorage.IDS_2D) {
            return biomes[biomeId2DIndex(x, z)];
        }

        // 高さの範囲外は値を持たない
        if (y < 0 || y > BIOME_IDS_MAX_Y) {
            return null;
        }

        return biomes[biomeIdIndex(x, y, z)];
    }

    /**
     * 数値のバイオームIDを設定する（1.17までの形式）
     * 1.15以降の形式は4×4×4の単位
     * 1.14までの形式は列ごとに持つので、Yは見ない
     *
     * @param x       チャンク内相対X座標 (0..15)
     * @param y       絶対Y座標
     * @param z       チャンク内相対Z座標 (0..15)
     * @param biomeId バイオームID
     * @throws SpringNbtException 1.15以降の形式でYが0..255の外の場合、
     * {@code Biomes}が無いか形が違う場合（INVALID_ARGUMENT）、
     * 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）、
     * バイオームを名前で持つ1.18以降の形式の場合（UNSUPPORTED_FEATURE）
     */
    public void setBiomeId(int x, int y, int z, int biomeId) {
        ChunkFormat chunkFormat = requireBiomeIds();
        checkLocalCoordinates(x, z);
        int index = biomeId2DIndex(x, z);

        // 4×4×4ごとに持つ形式は、高さ0..255の分だけある
        if (chunkFormat.biomeStorage() == ChunkFormat.BiomeStorage.IDS_3D) {
            // 範囲外の高さはどの値にも当たらない
            if (y < 0 || y > BIOME_IDS_MAX_Y) {
                throw SpringNbtException.invalidArgument(
                        "Y=" + y + " はバイオームIDを持つ高さ（0.." + BIOME_IDS_MAX_Y + "）の外");
            }

            index = biomeIdIndex(x, y, z);
        }

        int[] biomes = biomeIds(chunkFormat);

        // 読めないBiomesを作り直すと元のデータを失うので、書き込まない
        if (biomes == null) {
            throw SpringNbtException.invalidArgument(
                    "Biomes が無いか、int[" + biomeIdsLength(chunkFormat) + "] でない");
        }

        biomes[index] = biomeId;
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
     * @throws SpringNbtException 元のNBTだけを持つチャンクの場合（UNSUPPORTED_DATA_VERSION）、
     * {@code isLightOn}の無い1.17までの形式のチャンクの場合（UNSUPPORTED_FEATURE）
     */
    public void invalidateLighting() {
        ChunkFormat chunkFormat = requireFormat();
        NbtCompound body = body();

        // 書き足さない世代では、isLightOnの無いチャンクは光源の印を持たない
        if (!chunkFormat.addsLightFlag() && !body.containsKey("isLightOn")) {
            throw SpringNbtException.unsupportedFeature(
                    "DataVersion " + formatDataVersion + "のチャンクは isLightOn を持たない");
        }

        body.setByte("isLightOn", (byte) 0);
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

    /**
     * 1.15から1.17までの形式の{@code Biomes}の添字
     * 1エントリが4×4×4ブロック
     */
    private static int biomeIdIndex(int x, int y, int z) {
        return (((y >> 2) & 63) * 16) + ((z >> 2) * 4) + (x >> 2);
    }

    /**
     * 1.14までの形式の{@code Biomes}の添字
     * 1エントリが1列
     */
    private static int biomeId2DIndex(int x, int z) {
        return (z * 16) + x;
    }

    private static void checkLocalCoordinates(int x, int z) {
        // チャンク内相対座標は0..15でなければならない
        if (x < 0 || x > 15 || z < 0 || z > 15) {
            throw SpringNbtException.invalidArgument(
                    "チャンク内相対座標が範囲外: (" + x + ", " + z + ")。X も Z も 0..15 であること");
        }
    }
}

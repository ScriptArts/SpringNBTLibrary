package io.github.scriptarts.springnbt.world;

import java.util.List;

/**
 * チャンクの形式の世代1つ分
 * ライブラリの内部だけで使う
 *
 * <p>世代ごとの違いはこの表に集める
 * チャンクの読み書きは表の値に従い、DataVersionによる分岐をほかの場所に書かない
 */
final class ChunkFormat {

    /**
     * ブロックのパレット要素が{@code id} / {@code properties}の形式になるDataVersion（26.3）
     * これ未満は{@code Name} / {@code Properties}の形式
     */
    static final int PALETTE_ID_FORMAT_DATA_VERSION = 5006;

    /** DataVersionを指定して読み書きできる最も古いDataVersion（1.13の正式版） */
    static final int OLDEST_FORMAT_DATA_VERSION = 1519;

    /** セクションのブロックの持ち方 */
    enum BlockStorage {
        /**
         * セクションの{@code block_states}にあるパレット付きコンテナ（{@code palette} / {@code data}）
         * パレットが1要素なら{@code data}を持たない
         */
        CONTAINER,

        /**
         * セクションの直下の{@code Palette}と{@code BlockStates}
         * {@code BlockStates}はパレットが1要素でも必ずある
         */
        SECTION_PALETTE,
    }

    /** バイオームの持ち方 */
    enum BiomeStorage {
        /** セクションごとのパレット付きコンテナ */
        PALETTED,

        /** チャンクの列ごとの数値のバイオームID（{@code int[256]}） */
        IDS_2D,

        /** 4×4×4ブロックごとの数値のバイオームID（{@code int[1024]}） */
        IDS_3D,
    }

    /** ルートの直下に置かれる、ブロックに紐づく付随データのキー（1.18以降） */
    private static final List<String> ROOT_BLOCK_DATA_KEYS =
            List.of("block_entities", "block_ticks", "fluid_ticks");

    /** {@code Level}の中に置かれる、ブロックに紐づく付随データのキー（1.17まで） */
    private static final List<String> LEVEL_BLOCK_DATA_KEYS =
            List.of("TileEntities", "TileTicks", "LiquidTicks");

    /**
     * 世代の表
     * 境界のDataVersionの昇順に並べる
     */
    private static final List<ChunkFormat> FORMATS = List.of(
            // C3: 1.16〜1.17.x
            // 本体はLevelの中で、ブロックはセクションの直下のPalette / BlockStates
            // バイオームは4×4×4ブロックごとの数値のID
            new ChunkFormat(
                    2529,
                    true,
                    "Sections",
                    2529,
                    false,
                    BlockStorage.SECTION_PALETTE,
                    BiomeStorage.IDS_3D,
                    LEVEL_BLOCK_DATA_KEYS,
                    false,
                    false),
            // C4: 1.18〜26.2
            // Levelが無くなり、パレットの要素はName / Properties
            new ChunkFormat(
                    2844,
                    false,
                    "sections",
                    2844,
                    false,
                    BlockStorage.CONTAINER,
                    BiomeStorage.PALETTED,
                    ROOT_BLOCK_DATA_KEYS,
                    true,
                    true),
            // C5: 26.3以降
            // パレットの要素は文字列かid / properties
            new ChunkFormat(
                    PALETTE_ID_FORMAT_DATA_VERSION,
                    false,
                    "sections",
                    PALETTE_ID_FORMAT_DATA_VERSION,
                    false,
                    BlockStorage.CONTAINER,
                    BiomeStorage.PALETTED,
                    ROOT_BLOCK_DATA_KEYS,
                    true,
                    true));

    private final int minDataVersion;
    private final boolean wrappedInLevel;
    private final String sectionsKey;
    private final int paletteDataVersion;
    private final boolean spanningBitStorage;
    private final BlockStorage blockStorage;
    private final BiomeStorage biomeStorage;
    private final List<String> blockDataKeys;
    private final boolean hasYPos;
    private final boolean addsLightFlag;

    private ChunkFormat(
            int minDataVersion,
            boolean wrappedInLevel,
            String sectionsKey,
            int paletteDataVersion,
            boolean spanningBitStorage,
            BlockStorage blockStorage,
            BiomeStorage biomeStorage,
            List<String> blockDataKeys,
            boolean hasYPos,
            boolean addsLightFlag) {
        this.minDataVersion = minDataVersion;
        this.wrappedInLevel = wrappedInLevel;
        this.sectionsKey = sectionsKey;
        this.paletteDataVersion = paletteDataVersion;
        this.spanningBitStorage = spanningBitStorage;
        this.blockStorage = blockStorage;
        this.biomeStorage = biomeStorage;
        this.blockDataKeys = blockDataKeys;
        this.hasYPos = hasYPos;
        this.addsLightFlag = addsLightFlag;
    }

    /**
     * DataVersionから世代を引く
     * 表にあるどの世代よりも古ければnull
     *
     * @param dataVersion 世代を選ぶDataVersion
     * @return 世代
     */
    static ChunkFormat forDataVersion(int dataVersion) {
        ChunkFormat result = null;

        // 表は境界の昇順に並ぶので、境界以上の最後の世代が当てはまる
        for (ChunkFormat format : FORMATS) {
            // 境界に届いた世代だけを候補にする
            if (dataVersion >= format.minDataVersion) {
                result = format;
            }
        }

        return result;
    }

    /**
     * この世代が始まるDataVersion
     *
     * @return DataVersion
     */
    int minDataVersion() {
        return minDataVersion;
    }

    /**
     * チャンクの本体が{@code Level}の中にあるか
     *
     * @return {@code Level}の中にあればtrue
     */
    boolean wrappedInLevel() {
        return wrappedInLevel;
    }

    /**
     * セクションの一覧のキー
     *
     * @return キー
     */
    String sectionsKey() {
        return sectionsKey;
    }

    /**
     * パレットの要素と{@link BlockState}の変換に渡すDataVersion
     *
     * @return DataVersion
     */
    int paletteDataVersion() {
        return paletteDataVersion;
    }

    /**
     * ビット詰めで値が64bitの境目をまたぐか
     *
     * @return またぐならtrue
     */
    boolean spanningBitStorage() {
        return spanningBitStorage;
    }

    /**
     * セクションのブロックの持ち方
     *
     * @return 持ち方
     */
    BlockStorage blockStorage() {
        return blockStorage;
    }

    /**
     * バイオームの持ち方
     *
     * @return 持ち方
     */
    BiomeStorage biomeStorage() {
        return biomeStorage;
    }

    /**
     * ブロックを置き換えたときに取り除く付随データのキー
     *
     * @return キー
     */
    List<String> blockDataKeys() {
        return blockDataKeys;
    }

    /**
     * ルートに最下段セクションのY位置（{@code yPos}）があるか
     * 無い世代では、セクションは0段目から始まる
     *
     * @return あればtrue
     */
    boolean hasYPos() {
        return hasYPos;
    }

    /**
     * {@code isLightOn}の無いチャンクで光源を無効化するとき、{@code isLightOn}を書き足すか
     * 1.17までは生成途中のチャンクに{@code isLightOn}が無く、書き足すと元に無いキーが増えるので足さない
     *
     * @return 書き足すならtrue
     */
    boolean addsLightFlag() {
        return addsLightFlag;
    }
}

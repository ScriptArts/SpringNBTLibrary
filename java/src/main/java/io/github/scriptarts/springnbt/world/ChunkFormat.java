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

    /**
     * 世代の表
     * 境界のDataVersionの昇順に並べる
     */
    private static final List<ChunkFormat> FORMATS = List.of(
            // C4: 1.18〜26.2
            // Levelが無くなり、パレットの要素はName / Properties
            new ChunkFormat(
                    2844,
                    false,
                    "sections",
                    2844,
                    false,
                    BiomeStorage.PALETTED,
                    ROOT_BLOCK_DATA_KEYS),
            // C5: 26.3以降
            // パレットの要素は文字列かid / properties
            new ChunkFormat(
                    PALETTE_ID_FORMAT_DATA_VERSION,
                    false,
                    "sections",
                    PALETTE_ID_FORMAT_DATA_VERSION,
                    false,
                    BiomeStorage.PALETTED,
                    ROOT_BLOCK_DATA_KEYS));

    private final int minDataVersion;
    private final boolean wrappedInLevel;
    private final String sectionsKey;
    private final int paletteDataVersion;
    private final boolean spanningBitStorage;
    private final BiomeStorage biomeStorage;
    private final List<String> blockDataKeys;

    private ChunkFormat(
            int minDataVersion,
            boolean wrappedInLevel,
            String sectionsKey,
            int paletteDataVersion,
            boolean spanningBitStorage,
            BiomeStorage biomeStorage,
            List<String> blockDataKeys) {
        this.minDataVersion = minDataVersion;
        this.wrappedInLevel = wrappedInLevel;
        this.sectionsKey = sectionsKey;
        this.paletteDataVersion = paletteDataVersion;
        this.spanningBitStorage = spanningBitStorage;
        this.biomeStorage = biomeStorage;
        this.blockDataKeys = blockDataKeys;
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
}

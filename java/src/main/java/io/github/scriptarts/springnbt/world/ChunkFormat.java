package io.github.scriptarts.springnbt.world;

/**
 * チャンクの形式の世代の境界
 * ライブラリの内部だけで使う
 */
final class ChunkFormat {

    /**
     * ブロックのパレット要素が{@code id} / {@code properties}の形式になるDataVersion（26.3）
     * これ未満は{@code Name} / {@code Properties}の形式
     */
    static final int PALETTE_ID_FORMAT_DATA_VERSION = 5006;

    /** DataVersionを指定して読み書きできる最も古いDataVersion（1.13の正式版） */
    static final int OLDEST_FORMAT_DATA_VERSION = 1519;

    private ChunkFormat() {
    }
}

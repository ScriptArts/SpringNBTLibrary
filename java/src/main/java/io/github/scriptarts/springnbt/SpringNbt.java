package io.github.scriptarts.springnbt;

/**
 * SpringNBTLibrary のライブラリ全体に関わる定数
 *
 * <p>仕様は {@code docs/spec/} を唯一の正とする
 * 対象は 26.1 で導入されたワールド形式 (DataVersion 4786 以降)
 */
public final class SpringNbt {

    /**
     * このライブラリが扱えるワールド形式の下限となる DataVersion (26.1)
     *
     * <p>26.1 で次元とプレイヤーデータの置き場が変わり、いまの形式になった
     * これ以降のバージョンは、形式が同じであればそのまま読み書きできる
     *
     * <p>これより古いワールドは構成そのものが違うので、
     * 読み込み時に {@code UNSUPPORTED_DATA_VERSION} の対象になる
     */
    public static final int MIN_SUPPORTED_DATA_VERSION = 4786;

    /** 動作を確かめた Minecraft Java版の DataVersion (26.2) */
    public static final int TARGET_DATA_VERSION = 4903;

    private SpringNbt() {
        // インスタンス化を禁止する定数ホルダ
    }
}

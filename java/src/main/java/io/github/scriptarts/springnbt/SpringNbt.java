package io.github.scriptarts.springnbt;

/**
 * SpringNBTLibraryのライブラリ全体に関わる定数
 *
 * 対象は26.1で導入されたワールド形式 (DataVersion 4786以降)
 */
public final class SpringNbt {

    /**
     * このライブラリが扱えるワールド形式の下限となるDataVersion (26.1)
     *
     * <p>26.1で次元とプレイヤーデータの置き場が変わり、いまの形式になった
     * これ以降のバージョンは、形式が同じであればそのまま読み書きできる
     *
     * <p>これより古いワールドは構成そのものが違う
     * そうしたチャンクは、読み込み時は既定で警告を出し、書き戻しは既定で{@code UNSUPPORTED_DATA_VERSION}にする
     */
    public static final int MIN_SUPPORTED_DATA_VERSION = 4786;

    /** 動作を確かめたMinecraft Java版のDataVersion (26.2) */
    public static final int TARGET_DATA_VERSION = 4903;

    private SpringNbt() {
        // インスタンス化を禁止する定数ホルダ
    }
}

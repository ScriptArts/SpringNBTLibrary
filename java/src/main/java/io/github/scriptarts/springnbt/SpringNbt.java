package io.github.scriptarts.springnbt;

/**
 * SpringNBTLibraryのライブラリ全体に関わる定数
 *
 * 対象は26.3で導入されたワールド形式 (DataVersion 5006以降)
 */
public final class SpringNbt {

    /**
     * このライブラリが扱えるワールド形式の下限となるDataVersion (26.3)
     *
     * <p>26.3でブロックのパレットの形式が変わり、いまの形式になった
     * 5006はMinecraftがこの形式へ変換するDataVersionで、26.3 Snapshot 7で入った
     * これ以降のバージョンは、形式が同じであればそのまま読み書きできる
     *
     * <p>これより古いワールドはパレットの書き方が違う
     * そうしたチャンクは、読み込み時は既定で警告を出し、書き戻しは既定で{@code UNSUPPORTED_DATA_VERSION}にする
     */
    public static final int MIN_SUPPORTED_DATA_VERSION = 5006;

    /** 動作を確かめたMinecraft Java版のDataVersion (26.3) */
    public static final int TARGET_DATA_VERSION = 5023;

    private SpringNbt() {
        // インスタンス化を禁止する定数ホルダ
    }
}

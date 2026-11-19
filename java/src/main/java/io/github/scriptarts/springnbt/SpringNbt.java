package io.github.scriptarts.springnbt;

/**
 * SpringNBTLibraryのライブラリ全体に関わる定数
 *
 * 対象は1.18以降のワールド形式 (DataVersion 2844以降)
 */
public final class SpringNbt {

    /**
     * このライブラリが扱えるワールド形式の下限となるDataVersion (1.18)
     *
     * <p>1.18でチャンクの本体が{@code Level}の外へ出て、セクションがパレット付きのコンテナになった
     * 2844はMinecraftがこの形式へ変換するDataVersionで、1.18の開発版で入った
     * これ以降のチャンクは、読んだときの形式のまま読み書きできる
     * 26.3（DataVersion 5006）でパレットの要素の形が変わったが、どちらの形式も扱う
     *
     * <p>これより古いチャンクは形式が違う
     * そうしたチャンクは、読み込み時は既定で警告を出し、書き戻しは既定で{@code UNSUPPORTED_DATA_VERSION}にする
     */
    public static final int MIN_SUPPORTED_DATA_VERSION = 2844;

    /** 動作を確かめたMinecraft Java版のDataVersion (26.3) */
    public static final int TARGET_DATA_VERSION = 5023;

    private SpringNbt() {
        // インスタンス化を禁止する定数ホルダ
    }
}

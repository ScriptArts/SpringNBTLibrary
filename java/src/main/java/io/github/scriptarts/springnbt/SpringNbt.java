package io.github.scriptarts.springnbt;

/**
 * SpringNBTLibrary のライブラリ全体に関わる定数
 *
 * <p>仕様は {@code docs/spec/} を唯一の正とする
 * 対象バージョンは Java版 26.2 (DataVersion 4903)
 */
public final class SpringNbt {

    /** 本ライブラリが対象とする Minecraft Java版の DataVersion (26.2)
    /** */
    public static final int TARGET_DATA_VERSION = 4903;

    private SpringNbt() {
        // インスタンス化を禁止する定数ホルダ
    }
}

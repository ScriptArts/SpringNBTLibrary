package io.github.scriptarts.springnbt.world;

/** チャンク書き込みのオプション */
public final class ChunkWriteOptions {

    private boolean allowForeignDataVersion;

    /**
     * 既定のオプションを作る
     *
     * @return オプション
     */
    public static ChunkWriteOptions defaults() {
        return new ChunkWriteOptions();
    }

    /**
     * 扱える形式より古いDataVersionを持つチャンクの書き戻しを許すか
     *
     * <p>既定はfalse
     * エラーを出さずに古いワールドを新形式で上書きし、
     * 利用者が気づかないうちに使えなくすることを防ぐため
     *
     * @return 許すならtrue
     */
    public boolean allowForeignDataVersion() {
        return allowForeignDataVersion;
    }

    /**
     * 扱える形式より古いDataVersionを持つチャンクの書き戻しを許すかを設定する
     *
     * @param value 許すならtrue
     * @return このオブジェクト
     */
    public ChunkWriteOptions setAllowForeignDataVersion(boolean value) {
        this.allowForeignDataVersion = value;
        return this;
    }
}

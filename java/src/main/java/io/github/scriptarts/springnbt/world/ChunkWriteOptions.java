package io.github.scriptarts.springnbt.world;

/** チャンク書き込みのオプション。 */
public final class ChunkWriteOptions {

    private boolean allowForeignDataVersion;

    /**
     * 既定のオプションを作る。
     *
     * @return オプション
     */
    public static ChunkWriteOptions defaults() {
        return new ChunkWriteOptions();
    }

    /**
     * 対象バージョン以外の DataVersion を持つチャンクの書き戻しを許すか。
     *
     * <p>既定は false。古いワールドを黙って新形式で上書きし、
     * 利用者が気づかないうちに壊すことを防ぐため（{@code docs/adr/0003-version-policy.md}）。
     *
     * @return 許すなら true
     */
    public boolean allowForeignDataVersion() {
        return allowForeignDataVersion;
    }

    /**
     * 対象バージョン以外の書き戻しを許すかを設定する。
     *
     * @param value 許すなら true
     * @return このオブジェクト
     */
    public ChunkWriteOptions setAllowForeignDataVersion(boolean value) {
        this.allowForeignDataVersion = value;
        return this;
    }
}

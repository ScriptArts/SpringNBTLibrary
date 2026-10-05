package io.github.scriptarts.springnbt.world;

import java.util.function.Consumer;

/**
 * チャンク読み込みのオプション
 */
public final class ChunkReadOptions {

    private VersionMismatchAction onVersionMismatch = VersionMismatchAction.WARN;
    private Consumer<String> onWarning;
    private boolean lenientBitStorage;

    /**
     * 既定のオプションを作る
     *
     * @return オプション
     */
    public static ChunkReadOptions defaults() {
        return new ChunkReadOptions();
    }

    /**
     * DataVersionが扱える形式より古いときの動作
     *
     * @return 動作
     */
    public VersionMismatchAction onVersionMismatch() {
        return onVersionMismatch;
    }

    /**
     * DataVersionが扱える形式より古いときの動作を設定する
     *
     * @param value 動作
     * @return このオブジェクト
     */
    public ChunkReadOptions setOnVersionMismatch(VersionMismatchAction value) {
        this.onVersionMismatch = value;
        return this;
    }

    /**
     * 警告の通知先
     * nullなら何もしない
     *
     * @return 通知先
     */
    public Consumer<String> onWarning() {
        return onWarning;
    }

    /**
     * 警告の通知先を設定する
     *
     * @param value 通知先
     * @return このオブジェクト
     */
    public ChunkReadOptions setOnWarning(Consumer<String> value) {
        this.onWarning = value;
        return this;
    }

    /**
     * dataの長さが期待値と違うとき、長さからビット幅を逆算して読むか
     *
     * @return 逆算するならtrue
     */
    public boolean lenientBitStorage() {
        return lenientBitStorage;
    }

    /**
     * dataの長さから逆算するかを設定する
     *
     * @param value 逆算するならtrue
     * @return このオブジェクト
     */
    public ChunkReadOptions setLenientBitStorage(boolean value) {
        this.lenientBitStorage = value;
        return this;
    }
}

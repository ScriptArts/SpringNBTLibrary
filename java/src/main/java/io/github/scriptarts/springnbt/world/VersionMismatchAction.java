package io.github.scriptarts.springnbt.world;

/** DataVersionが扱える形式より古いときの動作 */
public enum VersionMismatchAction {

    /**
     * 警告コールバックを呼んで続行する
     * 既定
     */
    WARN,

    /** {@link io.github.scriptarts.springnbt.ErrorCode#UNSUPPORTED_DATA_VERSION}の例外にする */
    ERROR,

    /** 何もしない */
    IGNORE
}

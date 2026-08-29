package io.github.scriptarts.springnbt.nbt;

/**
 * 圧縮方式。
 *
 * <p>仕様: {@code docs/spec/10-nbt-binary.md} 4章
 */
public enum Compression {

    /** 無圧縮。 */
    NONE,

    /** GZip (RFC 1952)。 */
    GZIP,

    /** Zlib (RFC 1950)。 */
    ZLIB,

    /** 先頭バイトから自動判定する。読み込み時のみ指定できる。 */
    AUTO
}

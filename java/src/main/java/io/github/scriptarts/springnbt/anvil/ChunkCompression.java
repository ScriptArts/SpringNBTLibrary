package io.github.scriptarts.springnbt.anvil;

import io.github.scriptarts.springnbt.SpringNbtException;

/**
 * リージョンファイル内でチャンクに使われる圧縮方式
 * {@link #id()} は仕様が定める圧縮方式IDと一致する
 *
 * <p>NBT 層の {@link io.github.scriptarts.springnbt.nbt.Compression} とは別物であることに注意
 * あちらはファイル全体の圧縮を表し、こちらはリージョン内の 1 チャンクに付く 1 バイトのIDを表す
 *
 * <p>仕様: {@code docs/spec/20-anvil-region.md} 3.1章
 */
public enum ChunkCompression {

    /**
     * GZip (RFC 1952)
     * ID=1
     * 実データではほぼ使われない
     */
    GZIP(1, "gzip"),

    /**
     * Zlib (RFC 1950)
     * ID=2
     * Minecraft が実際に書き出す方式
     */
    ZLIB(2, "zlib"),

    /**
     * 無圧縮
     * ID=3
     */
    NONE(3, "none"),

    /**
     * LZ4（ブロック形式）
     * ID=4
     * 任意依存
     */
    LZ4(4, "lz4"),

    /**
     * サードパーティ製サーバのカスタム方式
     * ID=127
     * 中身は解釈できない
     */
    CUSTOM(127, "custom");

    private final int id;
    private final String label;

    ChunkCompression(int id, String label) {
        this.id = id;
        this.label = label;
    }

    /**
     * 仕様が定める圧縮方式ID
     *
     * @return ID
     */
    public int id() {
        return id;
    }

    /**
     * 適合性テストで言語間比較に使う識別子
     *
     * @return 識別子
     */
    public String asString() {
        return label;
    }

    /**
     * 圧縮方式IDから {@link ChunkCompression} を得る
     *
     * @param id 圧縮方式ID
     * @return 圧縮方式
     * @throws SpringNbtException 未知のIDの場合
     */
    public static ChunkCompression fromId(int id) {
        // 仕様が定めるのは 1・2・3・4・127 の 5 種類だけ
        for (ChunkCompression candidate : values()) {
            if (candidate.id == id) {
                return candidate;
            }
        }

        throw SpringNbtException.malformed("未知の圧縮方式ID: " + id);
    }
}

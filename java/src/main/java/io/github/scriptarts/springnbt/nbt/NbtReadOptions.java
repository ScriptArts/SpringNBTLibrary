package io.github.scriptarts.springnbt.nbt;

/**
 * NBT 読み込みのオプション。
 *
 * <p>仕様: {@code docs/spec/10-nbt-binary.md} 6章 / {@code docs/spec/00-conventions.md} 5章
 */
public final class NbtReadOptions {

    /** ネストの深さ上限の既定値。 */
    public static final int DEFAULT_MAX_DEPTH = 512;

    private NbtFormat format = NbtFormat.JAVA;
    private Compression compression = Compression.AUTO;
    private int maxDepth = DEFAULT_MAX_DEPTH;
    private long maxDecompressedSize = -1;

    /**
     * 既定のオプションを作る。
     *
     * @return 既定のオプション
     */
    public static NbtReadOptions defaults() {
        return new NbtReadOptions();
    }

    /**
     * ルートタグの並び方。
     *
     * @return 並び方
     */
    public NbtFormat format() {
        return format;
    }

    /**
     * ルートタグの並び方を設定する。
     *
     * @param value 並び方
     * @return このオブジェクト
     */
    public NbtReadOptions setFormat(NbtFormat value) {
        this.format = value;
        return this;
    }

    /**
     * 圧縮方式。既定は {@link Compression#AUTO}。
     *
     * @return 圧縮方式
     */
    public Compression compression() {
        return compression;
    }

    /**
     * 圧縮方式を設定する。
     *
     * @param value 圧縮方式
     * @return このオブジェクト
     */
    public NbtReadOptions setCompression(Compression value) {
        this.compression = value;
        return this;
    }

    /**
     * ネストの深さ上限。既定は 512。
     *
     * @return 深さ上限
     */
    public int maxDepth() {
        return maxDepth;
    }

    /**
     * ネストの深さ上限を設定する。
     *
     * @param value 深さ上限
     * @return このオブジェクト
     */
    public NbtReadOptions setMaxDepth(int value) {
        this.maxDepth = value;
        return this;
    }

    /**
     * 展開後の総バイト数の上限。負値なら無制限。
     *
     * @return 上限
     */
    public long maxDecompressedSize() {
        return maxDecompressedSize;
    }

    /**
     * 展開後の総バイト数の上限を設定する。
     *
     * @param value 上限。負値なら無制限
     * @return このオブジェクト
     */
    public NbtReadOptions setMaxDecompressedSize(long value) {
        this.maxDecompressedSize = value;
        return this;
    }
}

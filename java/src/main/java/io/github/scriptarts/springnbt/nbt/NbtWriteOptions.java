package io.github.scriptarts.springnbt.nbt;

/**
 * NBT 書き込みのオプション
 *
 * <p>仕様: {@code docs/spec/10-nbt-binary.md} 6章
 */
public final class NbtWriteOptions {

    private NbtFormat format = NbtFormat.JAVA;
    private Compression compression = Compression.GZIP;

    /**
     * 既定のオプションを作る
     *
     * @return 既定のオプション
     */
    public static NbtWriteOptions defaults() {
        return new NbtWriteOptions();
    }

    /**
     * 無圧縮で書き出すオプションを作る
     *
     * @return オプション
     */
    public static NbtWriteOptions uncompressed() {
        return new NbtWriteOptions().setCompression(Compression.NONE);
    }

    /**
     * ルートタグの並び方
     *
     * @return 並び方
     */
    public NbtFormat format() {
        return format;
    }

    /**
     * ルートタグの並び方を設定する
     *
     * @param value 並び方
     * @return このオブジェクト
     */
    public NbtWriteOptions setFormat(NbtFormat value) {
        this.format = value;
        return this;
    }

    /**
     * 圧縮方式
     * 既定は {@link Compression#GZIP}
     *
     * @return 圧縮方式
     */
    public Compression compression() {
        return compression;
    }

    /**
     * 圧縮方式を設定する
     *
     * @param value 圧縮方式
     * @return このオブジェクト
     */
    public NbtWriteOptions setCompression(Compression value) {
        this.compression = value;
        return this;
    }
}

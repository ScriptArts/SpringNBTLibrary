package io.github.scriptarts.springnbt.nbt;

/**
 * NBT のルートタグの並び方。
 *
 * <p>仕様: {@code docs/spec/10-nbt-binary.md} 3章
 */
public enum NbtFormat {

    /**
     * ファイル形式。ルートは「タグID + 名前長 + 名前 + ペイロード」の順に並ぶ。
     * {@code level.dat} やチャンクなど、保存されるデータはすべてこちら。
     */
    JAVA,

    /** ネットワーク形式 (1.20.2 以降)。ルートに名前が付かない。 */
    NETWORK
}

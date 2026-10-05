package io.github.scriptarts.springnbt.nbt;

/**
 * NBTのルートタグの並び方
 */
public enum NbtFormat {

    /**
     * ファイル形式
     * ルートは「タグID + 名前長 + 名前 + ペイロード」の順に並ぶ
     * {@code level.dat}やチャンクなど、保存されるデータはすべてこちら
     */
    JAVA,

    /**
     * ネットワーク形式 (1.20.2以降)
     * ルートに名前が付かない
     */
    NETWORK
}

package io.github.scriptarts.springnbt.nbt;

/**
 * NBTのタグ
 *
 * <p>{@code sealed}なので{@code switch}のパターンマッチで網羅的に分岐できる
 */
public sealed interface NbtTag
        permits NbtByte, NbtShort, NbtInt, NbtLong, NbtFloat, NbtDouble,
                NbtByteArray, NbtString, NbtList, NbtCompound, NbtIntArray, NbtLongArray {

    /**
     * このタグの型
     *
     * @return タグ型
     */
    TagType type();

    /**
     * このタグの深いコピーを作る
     *
     * @return コピー
     */
    NbtTag copy();
}

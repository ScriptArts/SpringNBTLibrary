package io.github.scriptarts.springnbt.nbt;

/**
 * NBT のタグ
 *
 * <p>{@code sealed} なので {@code switch} のパターンマッチで網羅的に分岐できる
 *
 * <p>仕様: {@code docs/spec/10-nbt-binary.md} 1章
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

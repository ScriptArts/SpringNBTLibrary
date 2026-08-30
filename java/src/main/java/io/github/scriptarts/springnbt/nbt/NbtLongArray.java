package io.github.scriptarts.springnbt.nbt;

import java.util.Arrays;
import java.util.Objects;

/**
 * TAG_Long_Array
 * 64bit 符号付き整数の配列
 */
public final class NbtLongArray implements NbtTag {

    private long[] value;

    /**
     * 配列を指定して作る
     * 渡した配列をそのまま保持する（コピーしない）
     *
     * @param value 配列
     */
    public NbtLongArray(long[] value) {
        this.value = Objects.requireNonNull(value, "value");
    }

    /**
     * 保持している配列
     *
     * @return 配列
     */
    public long[] value() {
        return value;
    }

    /**
     * 配列を設定する
     *
     * @param newValue 新しい配列
     */
    public void setValue(long[] newValue) {
        this.value = Objects.requireNonNull(newValue, "value");
    }

    @Override
    public TagType type() {
        return TagType.LONG_ARRAY;
    }

    @Override
    public NbtTag copy() {
        return new NbtLongArray(value.clone());
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof NbtLongArray tag && Arrays.equals(tag.value, value);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(value);
    }

    @Override
    public String toString() {
        return "[L; " + value.length + " 要素]";
    }
}

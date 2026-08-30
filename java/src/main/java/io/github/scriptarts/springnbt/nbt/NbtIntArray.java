package io.github.scriptarts.springnbt.nbt;

import java.util.Arrays;
import java.util.Objects;

/**
 * TAG_Int_Array
 * 32bit 符号付き整数の配列
 */
public final class NbtIntArray implements NbtTag {

    private int[] value;

    /**
     * 配列を指定して作る
     * 渡した配列をそのまま保持する（コピーしない）
     *
     * @param value 配列
     */
    public NbtIntArray(int[] value) {
        this.value = Objects.requireNonNull(value, "value");
    }

    /**
     * 保持している配列
     *
     * @return 配列
     */
    public int[] value() {
        return value;
    }

    /**
     * 配列を設定する
     *
     * @param newValue 新しい配列
     */
    public void setValue(int[] newValue) {
        this.value = Objects.requireNonNull(newValue, "value");
    }

    @Override
    public TagType type() {
        return TagType.INT_ARRAY;
    }

    @Override
    public NbtTag copy() {
        return new NbtIntArray(value.clone());
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof NbtIntArray tag && Arrays.equals(tag.value, value);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(value);
    }

    @Override
    public String toString() {
        return "[I; " + value.length + " 要素]";
    }
}

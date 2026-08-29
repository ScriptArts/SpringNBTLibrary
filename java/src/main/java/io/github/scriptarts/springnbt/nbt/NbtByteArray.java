package io.github.scriptarts.springnbt.nbt;

import java.util.Arrays;
import java.util.Objects;

/** TAG_Byte_Array。8bit 符号付き整数の配列。 */
public final class NbtByteArray implements NbtTag {

    private byte[] value;

    /**
     * 配列を指定して作る。渡した配列をそのまま保持する（コピーしない）。
     *
     * @param value 配列
     */
    public NbtByteArray(byte[] value) {
        this.value = Objects.requireNonNull(value, "value");
    }

    /**
     * 保持している配列。
     *
     * @return 配列
     */
    public byte[] value() {
        return value;
    }

    /**
     * 配列を設定する。
     *
     * @param newValue 新しい配列
     */
    public void setValue(byte[] newValue) {
        this.value = Objects.requireNonNull(newValue, "value");
    }

    @Override
    public TagType type() {
        return TagType.BYTE_ARRAY;
    }

    @Override
    public NbtTag copy() {
        return new NbtByteArray(value.clone());
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof NbtByteArray tag && Arrays.equals(tag.value, value);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(value);
    }

    @Override
    public String toString() {
        return "[B; " + value.length + " 要素]";
    }
}

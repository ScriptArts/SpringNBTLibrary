package io.github.scriptarts.springnbt.nbt;

/**
 * TAG_Short
 * 16bit 符号付き整数
 */
public final class NbtShort implements NbtTag {

    private short value;

    /**
     * 値を指定して作る
     *
     * @param value 値
     */
    public NbtShort(short value) {
        this.value = value;
    }

    /**
     * 保持している値
     *
     * @return 値
     */
    public short value() {
        return value;
    }

    /**
     * 値を設定する
     *
     * @param newValue 新しい値
     */
    public void setValue(short newValue) {
        this.value = newValue;
    }

    @Override
    public TagType type() {
        return TagType.SHORT;
    }

    @Override
    public NbtTag copy() {
        return new NbtShort(value);
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof NbtShort tag && tag.value == value;
    }

    @Override
    public int hashCode() {
        return Short.hashCode(value);
    }

    @Override
    public String toString() {
        return value + "s";
    }
}

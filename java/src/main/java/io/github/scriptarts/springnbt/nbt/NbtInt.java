package io.github.scriptarts.springnbt.nbt;

/**
 * TAG_Int
 * 32bit 符号付き整数
 */
public final class NbtInt implements NbtTag {

    private int value;

    /**
     * 値を指定して作る
     *
     * @param value 値
     */
    public NbtInt(int value) {
        this.value = value;
    }

    /**
     * 保持している値
     *
     * @return 値
     */
    public int value() {
        return value;
    }

    /**
     * 値を設定する
     *
     * @param newValue 新しい値
     */
    public void setValue(int newValue) {
        this.value = newValue;
    }

    @Override
    public TagType type() {
        return TagType.INT;
    }

    @Override
    public NbtTag copy() {
        return new NbtInt(value);
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof NbtInt tag && tag.value == value;
    }

    @Override
    public int hashCode() {
        return Integer.hashCode(value);
    }

    @Override
    public String toString() {
        return Integer.toString(value);
    }
}

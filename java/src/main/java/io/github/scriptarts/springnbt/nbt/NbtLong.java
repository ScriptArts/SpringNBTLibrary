package io.github.scriptarts.springnbt.nbt;

/** TAG_Long
/** 64bit 符号付き整数
/** */
public final class NbtLong implements NbtTag {

    private long value;

    /**
     * 値を指定して作る
     *
     * @param value 値
     */
    public NbtLong(long value) {
        this.value = value;
    }

    /**
     * 保持している値
     *
     * @return 値
     */
    public long value() {
        return value;
    }

    /**
     * 値を設定する
     *
     * @param newValue 新しい値
     */
    public void setValue(long newValue) {
        this.value = newValue;
    }

    @Override
    public TagType type() {
        return TagType.LONG;
    }

    @Override
    public NbtTag copy() {
        return new NbtLong(value);
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof NbtLong tag && tag.value == value;
    }

    @Override
    public int hashCode() {
        return Long.hashCode(value);
    }

    @Override
    public String toString() {
        return value + "L";
    }
}

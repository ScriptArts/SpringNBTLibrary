package io.github.scriptarts.springnbt.nbt;

/**
 * TAG_Byte
 * 8bit 符号付き整数
 */
public final class NbtByte implements NbtTag {

    private byte value;

    /**
     * 値を指定して作る
     *
     * @param value 値
     */
    public NbtByte(byte value) {
        this.value = value;
    }

    /**
     * 保持している値
     *
     * @return 値
     */
    public byte value() {
        return value;
    }

    /**
     * 値を設定する
     *
     * @param newValue 新しい値
     */
    public void setValue(byte newValue) {
        this.value = newValue;
    }

    @Override
    public TagType type() {
        return TagType.BYTE;
    }

    @Override
    public NbtTag copy() {
        return new NbtByte(value);
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof NbtByte tag && tag.value == value;
    }

    @Override
    public int hashCode() {
        return Byte.hashCode(value);
    }

    @Override
    public String toString() {
        return value + "b";
    }
}

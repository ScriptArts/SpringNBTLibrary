package io.github.scriptarts.springnbt.nbt;

/** TAG_Float。IEEE 754 binary32。 */
public final class NbtFloat implements NbtTag {

    private float value;

    /**
     * 値を指定して作る。
     *
     * @param value 値
     */
    public NbtFloat(float value) {
        this.value = value;
    }

    /**
     * 保持している値。
     *
     * @return 値
     */
    public float value() {
        return value;
    }

    /**
     * 値を設定する。
     *
     * @param newValue 新しい値
     */
    public void setValue(float newValue) {
        this.value = newValue;
    }

    @Override
    public TagType type() {
        return TagType.FLOAT;
    }

    @Override
    public NbtTag copy() {
        return new NbtFloat(value);
    }

    @Override
    public boolean equals(Object other) {
        // NaN や -0.0 を区別するため、値ではなくビットパターンで比較する
        return other instanceof NbtFloat tag
                && Float.floatToRawIntBits(tag.value) == Float.floatToRawIntBits(value);
    }

    @Override
    public int hashCode() {
        return Float.floatToRawIntBits(value);
    }

    @Override
    public String toString() {
        return value + "f";
    }
}

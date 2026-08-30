package io.github.scriptarts.springnbt.nbt;

/**
 * TAG_Double
 * IEEE 754 binary64
 */
public final class NbtDouble implements NbtTag {

    private double value;

    /**
     * 値を指定して作る
     *
     * @param value 値
     */
    public NbtDouble(double value) {
        this.value = value;
    }

    /**
     * 保持している値
     *
     * @return 値
     */
    public double value() {
        return value;
    }

    /**
     * 値を設定する
     *
     * @param newValue 新しい値
     */
    public void setValue(double newValue) {
        this.value = newValue;
    }

    @Override
    public TagType type() {
        return TagType.DOUBLE;
    }

    @Override
    public NbtTag copy() {
        return new NbtDouble(value);
    }

    @Override
    public boolean equals(Object other) {
        // NaN や -0.0 を区別するため、値ではなくビットパターンで比較する
        return other instanceof NbtDouble tag
                && Double.doubleToRawLongBits(tag.value) == Double.doubleToRawLongBits(value);
    }

    @Override
    public int hashCode() {
        return Long.hashCode(Double.doubleToRawLongBits(value));
    }

    @Override
    public String toString() {
        return value + "d";
    }
}

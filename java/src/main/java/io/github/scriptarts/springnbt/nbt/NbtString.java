package io.github.scriptarts.springnbt.nbt;

import io.github.scriptarts.springnbt.SpringNbtException;
import java.util.Objects;

/** TAG_String
/** MUTF-8 で符号化される文字列
/** */
public final class NbtString implements NbtTag {

    private String value;

    /**
     * 値を指定して作る
     *
     * @param value 値
     * @throws SpringNbtException MUTF-8 に符号化すると 65535 バイトを超える場合
     */
    public NbtString(String value) {
        this.value = validate(value);
    }

    /**
     * 保持している値
     *
     * @return 値
     */
    public String value() {
        return value;
    }

    /**
     * 値を設定する
     *
     * @param newValue 新しい値
     * @throws SpringNbtException MUTF-8 に符号化すると 65535 バイトを超える場合
     */
    public void setValue(String newValue) {
        this.value = validate(newValue);
    }

    @Override
    public TagType type() {
        return TagType.STRING;
    }

    @Override
    public NbtTag copy() {
        return new NbtString(value);
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof NbtString tag && tag.value.equals(value);
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }

    @Override
    public String toString() {
        return value;
    }

    /** 長さフィールドが u16 のため、符号化後 65535 バイトを超える文字列は保持できない
    /** */
    private static String validate(String candidate) {
        Objects.requireNonNull(candidate, "value");
        int byteLength = Mutf8.byteLength(candidate);

        // 長さフィールドは u16
        // 65535 を超えると書き出せない
        if (byteLength > Mutf8.MAX_BYTE_LENGTH) {
            throw SpringNbtException.invalidArgument(
                    "文字列が長すぎる: MUTF-8 で " + byteLength + " バイト (上限 "
                            + Mutf8.MAX_BYTE_LENGTH + ")");
        }

        return candidate;
    }
}

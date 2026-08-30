package io.github.scriptarts.springnbt.nbt;

import io.github.scriptarts.springnbt.SpringNbtException;
import java.io.ByteArrayOutputStream;
import java.util.Map;

/**
 * NBT を展開済みのバイト列へ書き出す
 *
 * <p>出力は一意でなければならない（ラウンドトリップ検証が成立するため）
 * Compound は挿入順のまま、浮動小数点はビットパターンのまま書き出す
 *
 * <p>仕様: {@code docs/spec/10-nbt-binary.md} 5章
 */
final class NbtBinaryWriter {

    private final ByteArrayOutputStream buffer = new ByteArrayOutputStream();

    /** ルートタグを書き出し、結果のバイト列を返す */
    byte[] writeRoot(NamedTag named, NbtFormat format) {
        buffer.write(TagType.COMPOUND.id());

        if (format == NbtFormat.JAVA) {
            // ファイル形式のルートには名前が付く
            writeString(named.name());
        }

        writeCompoundPayload(named.tag());
        return buffer.toByteArray();
    }

    private void writePayload(NbtTag tag) {
        switch (tag) {
            case NbtByte value -> buffer.write(value.value());
            case NbtShort value -> writeUnsigned(value.value(), 2);
            case NbtInt value -> writeUnsigned(value.value(), 4);
            case NbtLong value -> writeUnsigned(value.value(), 8);
            // NaN や -0.0 を保つため、ビットパターンをそのまま書く
            case NbtFloat value -> writeUnsigned(Float.floatToRawIntBits(value.value()), 4);
            case NbtDouble value -> writeUnsigned(Double.doubleToRawLongBits(value.value()), 8);
            case NbtByteArray value -> writeByteArrayPayload(value.value());
            case NbtString value -> writeString(value.value());
            case NbtList value -> writeListPayload(value);
            case NbtCompound value -> writeCompoundPayload(value);
            case NbtIntArray value -> writeIntArrayPayload(value.value());
            case NbtLongArray value -> writeLongArrayPayload(value.value());
        }
    }

    private void writeCompoundPayload(NbtCompound compound) {
        // 挿入順のまま「タグID + 名前 + ペイロード」を並べる
        for (Map.Entry<String, NbtTag> entry : compound) {
            buffer.write(entry.getValue().type().id());
            writeString(entry.getKey());
            writePayload(entry.getValue());
        }

        buffer.write(TagType.END.id());
    }

    private void writeListPayload(NbtList list) {
        buffer.write(list.elementType().id());
        writeUnsigned(list.size(), 4);

        // 要素型は共通なので、ペイロードだけを並べる
        for (NbtTag item : list) {
            writePayload(item);
        }
    }

    private void writeByteArrayPayload(byte[] values) {
        writeUnsigned(values.length, 4);
        buffer.writeBytes(values);
    }

    private void writeIntArrayPayload(int[] values) {
        writeUnsigned(values.length, 4);

        // 4 バイトずつビッグエンディアンで書く
        for (int value : values) {
            writeUnsigned(value, 4);
        }
    }

    private void writeLongArrayPayload(long[] values) {
        writeUnsigned(values.length, 4);

        // 8 バイトずつビッグエンディアンで書く
        for (long value : values) {
            writeUnsigned(value, 8);
        }
    }

    private void writeString(String text) {
        byte[] encoded = Mutf8.encode(text);

        // 長さフィールドは u16
        // キー名は素の String なのでここでも検査する
        if (encoded.length > Mutf8.MAX_BYTE_LENGTH) {
            throw SpringNbtException.invalidArgument(
                    "文字列が長すぎる: MUTF-8 で " + encoded.length + " バイト (上限 "
                            + Mutf8.MAX_BYTE_LENGTH + ")");
        }

        writeUnsigned(encoded.length, 2);
        buffer.writeBytes(encoded);
    }

    /** 値をビッグエンディアンで指定バイト数ぶん書く */
    private void writeUnsigned(long value, int count) {
        // 上位バイトから順に取り出す
        for (int index = count - 1; index >= 0; index--) {
            buffer.write((int) ((value >>> (index * 8)) & 0xFF));
        }
    }
}

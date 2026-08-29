package io.github.scriptarts.springnbt.conformance;

import io.github.scriptarts.springnbt.nbt.Mutf8;
import io.github.scriptarts.springnbt.nbt.NamedTag;
import io.github.scriptarts.springnbt.nbt.NbtByte;
import io.github.scriptarts.springnbt.nbt.NbtByteArray;
import io.github.scriptarts.springnbt.nbt.NbtCompound;
import io.github.scriptarts.springnbt.nbt.NbtDouble;
import io.github.scriptarts.springnbt.nbt.NbtFloat;
import io.github.scriptarts.springnbt.nbt.NbtFormat;
import io.github.scriptarts.springnbt.nbt.NbtInt;
import io.github.scriptarts.springnbt.nbt.NbtIntArray;
import io.github.scriptarts.springnbt.nbt.NbtList;
import io.github.scriptarts.springnbt.nbt.NbtLong;
import io.github.scriptarts.springnbt.nbt.NbtLongArray;
import io.github.scriptarts.springnbt.nbt.NbtShort;
import io.github.scriptarts.springnbt.nbt.NbtString;
import io.github.scriptarts.springnbt.nbt.NbtTag;
import java.util.Map;

/**
 * NBT を、言語をまたいで文字列として完全一致する JSON へ写す。
 *
 * <p>浮動小数点をビットパターンで、64bit 整数を10進文字列で表すのが要。
 * 10進表記の丸めや JSON 数値の精度は処理系ごとに差が出るため、
 * そのまま出すと4言語の出力が一致しない。
 *
 * <p>仕様: {@code docs/spec/00-conventions.md} 6章 / {@code docs/spec/90-conformance.md}
 */
final class NormalizedJson {

    private NormalizedJson() {
        // ユーティリティクラス
    }

    /** ルートを含む全体を JSON 文字列へ変換する。末尾に改行を1つ付ける。 */
    static String write(NamedTag named, NbtFormat format) {
        StringBuilder builder = new StringBuilder();
        builder.append("{\"format\":");
        appendString(builder, formatName(format));
        builder.append(",\"root_name\":");
        appendString(builder, named.name());
        builder.append(",\"root\":");
        appendTag(builder, named.tag());
        builder.append("}\n");
        return builder.toString();
    }

    private static String formatName(NbtFormat format) {
        if (format == NbtFormat.NETWORK) {
            return "network";
        }

        return "java";
    }

    private static void appendTag(StringBuilder builder, NbtTag tag) {
        builder.append("{\"type\":");
        appendString(builder, tag.type().asString());

        // list だけは value の前に element_type が入る（仕様が定めるキー順）
        if (tag instanceof NbtList listTag) {
            builder.append(",\"element_type\":");
            appendString(builder, listTag.elementType().asString());
        }

        builder.append(",\"value\":");

        switch (tag) {
            case NbtByte value -> builder.append(value.value());
            case NbtShort value -> builder.append(value.value());
            case NbtInt value -> builder.append(value.value());
            // 64bit 整数は JSON 数値だと処理系によって精度が落ちるため10進文字列で表す
            case NbtLong value -> appendString(builder, Long.toString(value.value()));
            case NbtFloat value -> appendString(builder,
                    String.format("0x%08x", Float.floatToRawIntBits(value.value())));
            case NbtDouble value -> appendString(builder,
                    String.format("0x%016x", Double.doubleToRawLongBits(value.value())));
            case NbtString value -> {
                appendString(builder, value.value());

                // MUTF-8 のバイト列も併記する。孤立サロゲートなど UTF-8 に写せない値を厳密に比較するため
                builder.append(",\"mutf8\":");
                appendString(builder, toHex(Mutf8.encode(value.value())));
            }
            case NbtByteArray value -> appendByteArray(builder, value.value());
            case NbtIntArray value -> appendIntArray(builder, value.value());
            case NbtLongArray value -> appendLongArray(builder, value.value());
            case NbtList value -> appendList(builder, value);
            case NbtCompound value -> appendCompound(builder, value);
        }

        builder.append('}');
    }

    private static void appendList(StringBuilder builder, NbtList list) {
        builder.append('[');
        boolean first = true;

        // 要素を順に書き出す
        for (NbtTag item : list) {
            if (!first) {
                builder.append(',');
            }

            first = false;
            appendTag(builder, item);
        }

        builder.append(']');
    }

    private static void appendCompound(StringBuilder builder, NbtCompound compound) {
        // JSON オブジェクトだと挿入順の保持が処理系依存になるため、組の配列で表す
        builder.append('[');
        boolean first = true;

        for (Map.Entry<String, NbtTag> entry : compound) {
            if (!first) {
                builder.append(',');
            }

            first = false;
            builder.append('[');
            appendString(builder, entry.getKey());
            builder.append(',');
            appendTag(builder, entry.getValue());
            builder.append(']');
        }

        builder.append(']');
    }

    private static void appendByteArray(StringBuilder builder, byte[] values) {
        builder.append('[');

        for (int index = 0; index < values.length; index++) {
            if (index > 0) {
                builder.append(',');
            }

            builder.append(values[index]);
        }

        builder.append(']');
    }

    private static void appendIntArray(StringBuilder builder, int[] values) {
        builder.append('[');

        for (int index = 0; index < values.length; index++) {
            if (index > 0) {
                builder.append(',');
            }

            builder.append(values[index]);
        }

        builder.append(']');
    }

    private static void appendLongArray(StringBuilder builder, long[] values) {
        builder.append('[');

        // 64bit 整数は10進文字列の配列で表す
        for (int index = 0; index < values.length; index++) {
            if (index > 0) {
                builder.append(',');
            }

            appendString(builder, Long.toString(values[index]));
        }

        builder.append(']');
    }

    private static String toHex(byte[] bytes) {
        StringBuilder builder = new StringBuilder(bytes.length * 2);

        for (byte value : bytes) {
            builder.append(String.format("%02x", value & 0xFF));
        }

        return builder.toString();
    }

    /**
     * JSON 文字列を書き出す。非 ASCII は必ず {@code \\uXXXX} へ逃がす。
     *
     * <p>言語ごとに既定のエスケープ方針が違うため、ここで一律に固定しないと出力が一致しない。
     */
    private static void appendString(StringBuilder builder, String text) {
        builder.append('"');

        for (int index = 0; index < text.length(); index++) {
            char c = text.charAt(index);

            switch (c) {
                case '"' -> builder.append("\\\"");
                case '\\' -> builder.append("\\\\");
                case '\b' -> builder.append("\\b");
                case '\f' -> builder.append("\\f");
                case '\n' -> builder.append("\\n");
                case '\r' -> builder.append("\\r");
                case '\t' -> builder.append("\\t");
                default -> {
                    // ASCII の印字可能文字だけ生で出し、それ以外は \\uXXXX にする
                    if (c >= 0x20 && c <= 0x7E) {
                        builder.append(c);
                    } else {
                        builder.append(String.format("\\u%04x", (int) c));
                    }
                }
            }
        }

        builder.append('"');
    }
}

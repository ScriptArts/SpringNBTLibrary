package io.github.scriptarts.springnbt.nbt;

import io.github.scriptarts.springnbt.SpringNbtException;
import java.util.Map;
import java.util.Objects;

/**
 * SNBT (Stringified NBT) のパースと出力
 *
 * <p>対応範囲は「バイナリ NBT へ損失なく写せる部分集合」
 * 1.21.5 以降の異種リスト（{@code [1, "a"]}）は受理しない
 *
 * <p>仕様: {@code docs/spec/11-snbt.md} / {@code docs/adr/0006-snbt-scope.md}
 */
public final class Snbt {

    private static final String INDENT_UNIT = "    ";

    private Snbt() {
        // ユーティリティクラス
    }

    /**
     * SNBT 文字列をタグへ変換する
     *
     * @param text SNBT 文字列
     * @return タグ
     * @throws SpringNbtException 構文が不正な場合
     */
    public static NbtTag parse(String text) {
        Objects.requireNonNull(text, "text");
        return new SnbtParser(text).parseWhole();
    }

    /**
     * SNBT 文字列を Compound へ変換する
     *
     * @param text SNBT 文字列
     * @return Compound
     * @throws SpringNbtException 構文が不正、またはルートが Compound でない場合
     */
    public static NbtCompound parseCompound(String text) {
        NbtTag tag = parse(text);

        if (tag instanceof NbtCompound compound) {
            return compound;
        }

        throw SpringNbtException.unexpectedTagType("ルートが compound でない: " + tag.type().asString());
    }

    /**
     * タグを 1 行の SNBT へ変換する
     *
     * @param tag タグ
     * @return SNBT 文字列
     */
    public static String write(NbtTag tag) {
        Objects.requireNonNull(tag, "tag");
        StringBuilder builder = new StringBuilder();
        writeTag(builder, tag, -1);
        return builder.toString();
    }

    /**
     * タグを整形した SNBT へ変換する
     * インデントは空白 4 個
     *
     * @param tag タグ
     * @return SNBT 文字列
     */
    public static String writePretty(NbtTag tag) {
        Objects.requireNonNull(tag, "tag");
        StringBuilder builder = new StringBuilder();
        writeTag(builder, tag, 0);
        return builder.toString();
    }

    /**
     * タグを書き出す
     * {@code depth} が負なら 1 行、0 以上なら整形して出力する
     */
    private static void writeTag(StringBuilder builder, NbtTag tag, int depth) {
        switch (tag) {
            case NbtByte value -> builder.append(value.value()).append('b');
            case NbtShort value -> builder.append(value.value()).append('s');
            case NbtInt value -> builder.append(value.value());
            case NbtLong value -> builder.append(value.value()).append('L');
            case NbtFloat value -> builder.append(CanonicalDecimal.fromFloat(value.value())).append('f');
            case NbtDouble value -> builder.append(CanonicalDecimal.fromDouble(value.value())).append('d');
            case NbtString value -> builder.append(quoteString(value.value()));
            case NbtByteArray value -> writeByteArray(builder, value.value());
            case NbtIntArray value -> writeIntArray(builder, value.value());
            case NbtLongArray value -> writeLongArray(builder, value.value());
            case NbtList value -> writeList(builder, value, depth);
            case NbtCompound value -> writeCompound(builder, value, depth);
        }
    }

    private static void writeCompound(StringBuilder builder, NbtCompound compound, int depth) {
        // 空の compound は改行もインデントも入れず {} と書く
        if (compound.size() == 0) {
            builder.append("{}");
            return;
        }

        builder.append('{');
        boolean first = true;

        // 挿入順のまま「キー: 値」を並べる
        for (Map.Entry<String, NbtTag> entry : compound) {
            if (!first) {
                builder.append(',');
            }

            first = false;
            appendSeparator(builder, nextDepth(depth));
            builder.append(quoteKey(entry.getKey()));
            builder.append(':');

            // 整形時はコロンの後に空白を入れて読みやすくする
            if (depth >= 0) {
                builder.append(' ');
            }

            writeTag(builder, entry.getValue(), nextDepth(depth));
        }

        appendSeparator(builder, depth);
        builder.append('}');
    }

    private static void writeList(StringBuilder builder, NbtList list, int depth) {
        // 空のリストは改行もインデントも入れず [] と書く
        if (list.size() == 0) {
            builder.append("[]");
            return;
        }

        builder.append('[');
        boolean first = true;

        // 要素型は共通なので値だけを並べる
        for (NbtTag item : list) {
            if (!first) {
                builder.append(',');
            }

            first = false;
            appendSeparator(builder, nextDepth(depth));
            writeTag(builder, item, nextDepth(depth));
        }

        appendSeparator(builder, depth);
        builder.append(']');
    }

    private static void writeByteArray(StringBuilder builder, byte[] values) {
        builder.append("[B;");

        // 型付き配列は 1 行に収める
        // 要素には接尾辞を付ける
        for (int index = 0; index < values.length; index++) {
            if (index > 0) {
                builder.append(',');
            }

            builder.append(values[index]).append('B');
        }

        builder.append(']');
    }

    private static void writeIntArray(StringBuilder builder, int[] values) {
        builder.append("[I;");

        // IntArray の要素は接尾辞なし
        for (int index = 0; index < values.length; index++) {
            if (index > 0) {
                builder.append(',');
            }

            builder.append(values[index]);
        }

        builder.append(']');
    }

    private static void writeLongArray(StringBuilder builder, long[] values) {
        builder.append("[L;");

        // LongArray の要素には L 接尾辞を付ける
        for (int index = 0; index < values.length; index++) {
            if (index > 0) {
                builder.append(',');
            }

            builder.append(values[index]).append('L');
        }

        builder.append(']');
    }

    /** 整形出力なら改行とインデントを、1 行出力なら何も入れない */
    private static void appendSeparator(StringBuilder builder, int depth) {
        if (depth < 0) {
            return;
        }

        builder.append('\n');

        // 深さぶんインデントを積む
        for (int index = 0; index < depth; index++) {
            builder.append(INDENT_UNIT);
        }
    }

    /** 整形出力のときだけ深さを 1 段進める */
    private static int nextDepth(int depth) {
        if (depth < 0) {
            return -1;
        }

        return depth + 1;
    }

    /**
     * キーを出力する
     * 引用符なしで書ける場合はそのまま出す
     */
    private static String quoteKey(String key) {
        if (isBareWritable(key)) {
            return key;
        }

        return quoteString(key);
    }

    private static boolean isBareWritable(String text) {
        if (text.isEmpty()) {
            return false;
        }

        // 引用符なしで書ける文字だけで構成されているか調べる
        for (int index = 0; index < text.length(); index++) {
            if (!SnbtParser.isBareChar(text.charAt(index))) {
                return false;
            }
        }

        return true;
    }

    /** 文字列を二重引用符で囲み、必要な文字だけエスケープする */
    private static String quoteString(String text) {
        StringBuilder builder = new StringBuilder(text.length() + 2);
        builder.append('"');

        // 1 文字ずつ見てエスケープが要るものだけ置き換える
        for (int index = 0; index < text.length(); index++) {
            char c = text.charAt(index);

            switch (c) {
                case '"' -> builder.append("\\\"");
                case '\\' -> builder.append("\\\\");
                case '\b' -> builder.append("\\b");
                case '\t' -> builder.append("\\t");
                case '\n' -> builder.append("\\n");
                case '\f' -> builder.append("\\f");
                case '\r' -> builder.append("\\r");
                default -> {
                    // 正しいサロゲートペアはそのまま出す
                    // ここでエスケープすると、コードポイント単位の言語（Python / Rust）と出力が食い違う
                    if (Character.isHighSurrogate(c)
                            && index + 1 < text.length()
                            && Character.isLowSurrogate(text.charAt(index + 1))) {
                        builder.append(c);
                        builder.append(text.charAt(index + 1));
                        index += 1;
                    } else if (c < 0x20 || c == 0x7F || Character.isSurrogate(c)) {
                        // 制御文字と孤立サロゲートは \\uXXXX で表す
                        builder.append(String.format("\\u%04x", (int) c));
                    } else {
                        builder.append(c);
                    }
                }
            }
        }

        builder.append('"');
        return builder.toString();
    }
}

package io.github.scriptarts.springnbt.nbt;

import io.github.scriptarts.springnbt.ErrorCode;
import io.github.scriptarts.springnbt.SpringNbtException;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/**
 * SNBT (Stringified NBT) のパーサ
 *
 * <p>仕様: {@code docs/spec/11-snbt.md}
 */
final class SnbtParser {

    private static final String WIDTH_SUFFIXES = "bBsSlLfFdD";

    private final String text;
    private int position;

    SnbtParser(String text) {
        this.text = text;
        this.position = 0;
    }

    /**
     * 入力全体を 1 つの値として読む
     * 末尾に余りがあれば例外
     */
    NbtTag parseWhole() {
        NbtTag value = parseValue();
        skipWhitespace();

        // 値の後に余分な文字が残っていたら、書き手の意図と違う解釈をしている
        if (position < text.length()) {
            throw malformed("値の後に余分な文字がある: '" + text.charAt(position) + "'");
        }

        return value;
    }

    private NbtTag parseValue() {
        skipWhitespace();

        if (position >= text.length()) {
            throw malformed("値が来るべき位置で入力が尽きた");
        }

        char c = text.charAt(position);

        if (c == '{') {
            return parseCompound();
        }

        if (c == '[') {
            return parseListOrArray();
        }

        if (c == '"' || c == '\'') {
            return new NbtString(parseQuotedString());
        }

        return parseUnquoted();
    }

    private NbtCompound parseCompound() {
        expect('{');
        NbtCompound compound = new NbtCompound();
        skipWhitespace();

        // 空の Compound
        if (peek() == '}') {
            position += 1;
            return compound;
        }

        // 要素を 1 つずつ読む
        while (true) {
            skipWhitespace();

            // 末尾カンマの直後に閉じ括弧が来る形を許す
            if (peek() == '}') {
                position += 1;
                return compound;
            }

            String key = parseKey();
            skipWhitespace();
            expect(':');
            compound.set(key, parseValue());

            skipWhitespace();
            char next = peek();

            if (next == ',') {
                position += 1;
            } else if (next == '}') {
                position += 1;
                return compound;
            } else {
                throw malformed("Compound の区切りが不正: '" + next + "'");
            }
        }
    }

    private NbtTag parseListOrArray() {
        expect('[');

        // "[B;" のような型付き配列かどうかを先に判定する
        if (position + 1 < text.length() && text.charAt(position + 1) == ';') {
            char marker = text.charAt(position);

            if (marker == 'B' || marker == 'I' || marker == 'L') {
                position += 2;
                return parseTypedArray(marker);
            }
        }

        return parseList();
    }

    private NbtList parseList() {
        NbtList list = new NbtList();
        skipWhitespace();

        // 空のリスト
        if (peek() == ']') {
            position += 1;
            return list;
        }

        // 要素を 1 つずつ読む
        while (true) {
            skipWhitespace();

            // 末尾カンマの直後に閉じ括弧が来る形を許す
            if (peek() == ']') {
                position += 1;
                return list;
            }

            NbtTag value = parseValue();

            // 異種リストはバイナリ NBT へ写せないため受理しない (adr/0006)
            if (list.elementType() != TagType.END && list.elementType() != value.type()) {
                throw malformed("リストに異なる型が混在している: "
                        + list.elementType().asString() + " と " + value.type().asString());
            }

            list.add(value);

            skipWhitespace();
            char next = peek();

            if (next == ',') {
                position += 1;
            } else if (next == ']') {
                position += 1;
                return list;
            } else {
                throw malformed("リストの区切りが不正: '" + next + "'");
            }
        }
    }

    private NbtTag parseTypedArray(char marker) {
        List<Long> values = new ArrayList<>();
        skipWhitespace();

        // 空でなければ要素を読む
        if (peek() == ']') {
            position += 1;
        } else {
            // 閉じ括弧が来るまで要素を読み続ける
            while (true) {
                skipWhitespace();

                // 末尾カンマの直後に閉じ括弧が来る形を許す
                if (peek() == ']') {
                    position += 1;
                    break;
                }

                values.add(toIntegral(parseValue()));

                skipWhitespace();
                char next = peek();

                if (next == ',') {
                    position += 1;
                } else if (next == ']') {
                    position += 1;
                    break;
                } else {
                    throw malformed("配列の区切りが不正: '" + next + "'");
                }
            }
        }

        if (marker == 'B') {
            byte[] result = new byte[values.size()];

            // 各要素が Byte の範囲に収まるか確認しながら詰める
            for (int i = 0; i < values.size(); i++) {
                long value = values.get(i);

                if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
                    throw malformed("ByteArray の要素が範囲外: " + value);
                }

                result[i] = (byte) value;
            }

            return new NbtByteArray(result);
        }

        if (marker == 'I') {
            int[] result = new int[values.size()];

            // 各要素が Int の範囲に収まるか確認しながら詰める
            for (int i = 0; i < values.size(); i++) {
                long value = values.get(i);

                if (value < Integer.MIN_VALUE || value > Integer.MAX_VALUE) {
                    throw malformed("IntArray の要素が範囲外: " + value);
                }

                result[i] = (int) value;
            }

            return new NbtIntArray(result);
        }

        long[] result = new long[values.size()];

        // 読み取った値を配列へ移す
        for (int i = 0; i < values.size(); i++) {
            result[i] = values.get(i);
        }

        return new NbtLongArray(result);
    }

    /**
     * 整数タグから値を取り出す
     * 整数以外なら例外
     */
    private long toIntegral(NbtTag tag) {
        return switch (tag) {
            case NbtByte value -> value.value();
            case NbtShort value -> value.value();
            case NbtInt value -> value.value();
            case NbtLong value -> value.value();
            default -> throw malformed("型付き配列の要素が整数でない: " + tag.type().asString());
        };
    }

    private String parseKey() {
        char c = peek();

        if (c == '"' || c == '\'') {
            return parseQuotedString();
        }

        String bare = readBareToken();

        if (bare.isEmpty()) {
            throw malformed("Compound のキーが空");
        }

        return bare;
    }

    private String parseQuotedString() {
        char quote = text.charAt(position);
        position += 1;
        StringBuilder builder = new StringBuilder();

        // 閉じ引用符が来るまで読む
        while (true) {
            if (position >= text.length()) {
                throw malformed("文字列が閉じられていない");
            }

            char c = text.charAt(position);

            if (c == quote) {
                position += 1;
                return builder.toString();
            }

            if (c == '\\') {
                position += 1;
                appendEscape(builder);
            } else {
                builder.append(c);
                position += 1;
            }
        }
    }

    private void appendEscape(StringBuilder builder) {
        if (position >= text.length()) {
            throw malformed("エスケープが途中で切れている");
        }

        char c = text.charAt(position);
        position += 1;

        switch (c) {
            case '\\' -> builder.append('\\');
            case '"' -> builder.append('"');
            case '\'' -> builder.append('\'');
            case 'b' -> builder.append('\b');
            case 's' -> builder.append(' ');
            case 't' -> builder.append('\t');
            case 'n' -> builder.append('\n');
            case 'f' -> builder.append('\f');
            case 'r' -> builder.append('\r');
            case 'x' -> builder.append((char) readHexDigits(2));
            case 'u' -> builder.append((char) readHexDigits(4));
            case 'U' -> appendCodePoint(builder, readHexDigits(8));
            case 'N' -> appendNamedCharacter(builder);
            default -> throw malformed("未知のエスケープ: '\\" + c + "'");
        }
    }

    private long readHexDigits(int count) {
        if (position + count > text.length()) {
            throw malformed("エスケープの16進数字が足りない");
        }

        long value = 0;

        // 指定桁数ぶん 16進数字を読む
        for (int i = 0; i < count; i++) {
            char c = text.charAt(position + i);
            int digit = hexDigitValue(c);

            if (digit < 0) {
                throw malformed("エスケープに16進数字でない文字がある: '" + c + "'");
            }

            value = (value * 16) + digit;
        }

        position += count;
        return value;
    }

    private void appendCodePoint(StringBuilder builder, long codePoint) {
        // Unicode のコードポイント範囲を外れていないか確認する
        if (codePoint < 0 || codePoint > 0x10FFFF) {
            throw malformed(String.format("コードポイントが範囲外: U+%X", codePoint));
        }

        builder.appendCodePoint((int) codePoint);
    }

    /** Unicode 文字名によるエスケープ {@code \N{...}} を読む */
    private void appendNamedCharacter(StringBuilder builder) {
        expect('{');
        int start = position;

        // 閉じ波括弧まで名前を読む
        while (position < text.length() && text.charAt(position) != '}') {
            position += 1;
        }

        if (position >= text.length()) {
            throw malformed("文字名エスケープが閉じられていない");
        }

        String name = text.substring(start, position);
        position += 1;

        // 実装間で Unicode 文字名の表が揃わないため対応しない（C# / Rust には表が無い）
        throw new SpringNbtException(
                ErrorCode.UNSUPPORTED_FEATURE,
                "文字名によるエスケープには対応していない: \\N{" + name + "}");
    }

    private NbtTag parseUnquoted() {
        String token = readBareToken();

        if (token.isEmpty()) {
            throw malformed("値が来るべき位置に解釈できない文字がある: '" + peekOrNul() + "'");
        }

        // bool(...) / uuid(...) の関数呼び出し
        skipWhitespace();
        if (peekOrNul() == '(' && (token.equals("bool") || token.equals("uuid"))) {
            return parseFunction(token);
        }

        if (token.equals("true")) {
            return new NbtByte((byte) 1);
        }

        if (token.equals("false")) {
            return new NbtByte((byte) 0);
        }

        NbtTag number = tryParseNumber(token);

        if (number != null) {
            return number;
        }

        return new NbtString(token);
    }

    private NbtTag parseFunction(String name) {
        expect('(');
        NbtTag argument = parseValue();
        skipWhitespace();
        expect(')');

        if (name.equals("bool")) {
            // 0 以外を真とする
            if (toIntegral(argument) != 0) {
                return new NbtByte((byte) 1);
            }

            return new NbtByte((byte) 0);
        }

        return uuidToIntArray(argument);
    }

    private NbtIntArray uuidToIntArray(NbtTag argument) {
        if (!(argument instanceof NbtString stringTag)) {
            throw malformed("uuid() の引数は文字列でなければならない");
        }

        UUID parsed;
        try {
            parsed = UUID.fromString(stringTag.value());
        } catch (IllegalArgumentException error) {
            throw malformed("UUID として解釈できない: " + stringTag.value());
        }

        // UUID を上位から 32bit ずつ 4 要素の IntArray へ写す
        long high = parsed.getMostSignificantBits();
        long low = parsed.getLeastSignificantBits();

        return new NbtIntArray(new int[] {
            (int) (high >>> 32), (int) high, (int) (low >>> 32), (int) low,
        });
    }

    /**
     * 数値トークンを解釈する
     * 数値として読めなければ null を返す（文字列として扱われる）
     */
    private NbtTag tryParseNumber(String token) {
        boolean negative = false;
        int start = 0;

        // 先頭の符号を取り除き、数字の並びだけを残す
        if (token.charAt(0) == '+' || token.charAt(0) == '-') {
            negative = token.charAt(0) == '-';
            start = 1;
        }

        String body = token.substring(start);

        if (body.isEmpty()) {
            return null;
        }

        char widthSuffix = '\0';
        boolean unsignedSuffix = false;

        boolean isHex = isHexBody(body);

        // 幅接尾辞を末尾から剥がす
        // 16進では b/d/f が数字と紛れるため s/l だけを認める
        char last = body.charAt(body.length() - 1);
        boolean suffixAllowed;

        if (isHex) {
            suffixAllowed = last == 's' || last == 'S' || last == 'l' || last == 'L';
        } else {
            suffixAllowed = WIDTH_SUFFIXES.indexOf(last) >= 0;
        }

        // 末尾 1 文字が型の印なら切り離す
        // 1 文字だけの token は数字そのもの
        if (suffixAllowed && body.length() >= 2) {
            widthSuffix = Character.toLowerCase(last);
            body = body.substring(0, body.length() - 1);

            // 符号接尾辞 u / s は幅接尾辞の手前に置かれる
            if (body.length() >= 2) {
                char signChar = body.charAt(body.length() - 1);

                if (signChar == 'u' || signChar == 'U') {
                    unsignedSuffix = true;
                    body = body.substring(0, body.length() - 1);
                } else if (signChar == 's' || signChar == 'S') {
                    body = body.substring(0, body.length() - 1);
                }
            }
        }

        body = body.replace("_", "");

        if (body.isEmpty()) {
            return null;
        }

        // 特殊な浮動小数点値
        if (body.equals("Infinity")) {
            return makeFloating(Double.POSITIVE_INFINITY, negative, widthSuffix);
        }

        if (body.equals("NaN")) {
            return makeFloating(Double.NaN, negative, widthSuffix);
        }

        if (isHexBody(body)) {
            return parseRadix(body.substring(2), 16, negative, widthSuffix, unsignedSuffix);
        }

        if (isBinaryBody(body)) {
            return parseRadix(body.substring(2), 2, negative, widthSuffix, unsignedSuffix);
        }

        boolean looksFloating = body.indexOf('.') >= 0
                || body.indexOf('e') >= 0 || body.indexOf('E') >= 0;

        if (looksFloating || widthSuffix == 'f' || widthSuffix == 'd') {
            double parsed;
            try {
                parsed = Double.parseDouble(body);
            } catch (NumberFormatException error) {
                return null;
            }

            return makeFloating(parsed, negative, widthSuffix);
        }

        return parseRadix(body, 10, negative, widthSuffix, unsignedSuffix);
    }

    private static boolean isHexBody(String body) {
        return body.length() > 2 && body.charAt(0) == '0'
                && (body.charAt(1) == 'x' || body.charAt(1) == 'X');
    }

    private static boolean isBinaryBody(String body) {
        // 0b / 0B で始まり、続きがある場合だけ 2 進リテラルとみなす
        if (!(body.length() > 2 && body.charAt(0) == '0'
                && (body.charAt(1) == 'b' || body.charAt(1) == 'B'))) {
            return false;
        }

        // 2進リテラルの本体は 0 と 1 だけ
        for (int index = 2; index < body.length(); index++) {
            char c = body.charAt(index);

            if (c != '0' && c != '1') {
                return false;
            }
        }

        return true;
    }

    private NbtTag makeFloating(double value, boolean negative, char widthSuffix) {
        double signed;

        if (negative) {
            signed = -value;
        } else {
            signed = value;
        }

        if (widthSuffix == 'f') {
            return new NbtFloat((float) signed);
        }

        // 接尾辞なしの小数は Double
        if (widthSuffix == '\0' || widthSuffix == 'd') {
            return new NbtDouble(signed);
        }

        throw malformed("小数に整数の接尾辞 '" + widthSuffix + "' は付けられない");
    }

    private NbtTag parseRadix(String digits, int radix, boolean negative,
            char widthSuffix, boolean unsignedSuffix) {
        if (digits.isEmpty()) {
            return null;
        }

        long magnitude = 0;

        // 桁を1つずつ積み上げる
        // 桁あふれはその場で検出する
        for (int index = 0; index < digits.length(); index++) {
            int digit = digitValue(digits.charAt(index), radix);

            if (digit < 0) {
                return null;
            }

            long next = (magnitude * radix) + digit;

            if (Long.compareUnsigned(next, magnitude) < 0) {
                throw malformed("整数が大きすぎる: " + digits);
            }

            magnitude = next;
        }

        return makeIntegral(magnitude, negative, widthSuffix, unsignedSuffix);
    }

    private NbtTag makeIntegral(long magnitude, boolean negative,
            char widthSuffix, boolean unsignedSuffix) {
        if (unsignedSuffix) {
            // 符号なし指定は、その幅の符号なし最大値までを受け付けて符号付きへ読み替える
            return switch (widthSuffix) {
                case 'b' -> new NbtByte((byte) checkUnsigned(magnitude, 0xFFL));
                case 's' -> new NbtShort((short) checkUnsigned(magnitude, 0xFFFFL));
                case 'l' -> new NbtLong(magnitude);
                default -> new NbtInt((int) checkUnsigned(magnitude, 0xFFFFFFFFL));
            };
        }

        long value = toSigned(magnitude, negative);

        return switch (widthSuffix) {
            case 'b' -> new NbtByte((byte) checkRange(value, Byte.MIN_VALUE, Byte.MAX_VALUE, "byte"));
            case 's' -> new NbtShort(
                    (short) checkRange(value, Short.MIN_VALUE, Short.MAX_VALUE, "short"));
            case 'l' -> new NbtLong(value);
            case 'f' -> new NbtFloat((float) value);
            case 'd' -> new NbtDouble(value);
            // 接尾辞なしの整数は Int
            // 暗黙に Long へ格上げしない
            default -> new NbtInt(
                    (int) checkRange(value, Integer.MIN_VALUE, Integer.MAX_VALUE, "int"));
        };
    }

    private long checkUnsigned(long magnitude, long max) {
        if (Long.compareUnsigned(magnitude, max) > 0) {
            throw malformed("符号なし整数が範囲外: " + Long.toUnsignedString(magnitude)
                    + " (上限 " + max + ")");
        }

        return magnitude;
    }

    private long toSigned(long magnitude, boolean negative) {
        if (negative) {
            // Long.MIN_VALUE の絶対値は long に収まらないため個別に扱う
            if (magnitude == Long.MIN_VALUE) {
                return Long.MIN_VALUE;
            }

            if (magnitude < 0) {
                throw malformed("整数が小さすぎる: -" + Long.toUnsignedString(magnitude));
            }

            return -magnitude;
        }

        if (magnitude < 0) {
            throw malformed("整数が大きすぎる: " + Long.toUnsignedString(magnitude));
        }

        return magnitude;
    }

    private long checkRange(long value, long min, long max, String typeName) {
        if (value < min || value > max) {
            throw malformed(typeName + " の範囲外: " + value);
        }

        return value;
    }

    private static int digitValue(char c, int radix) {
        int value = hexDigitValue(c);

        if (value < 0 || value >= radix) {
            return -1;
        }

        return value;
    }

    private static int hexDigitValue(char c) {
        if (c >= '0' && c <= '9') {
            return c - '0';
        }

        if (c >= 'a' && c <= 'f') {
            return (c - 'a') + 10;
        }

        if (c >= 'A' && c <= 'F') {
            return (c - 'A') + 10;
        }

        return -1;
    }

    private String readBareToken() {
        int start = position;

        // 引用符なしトークンに使える文字を読み進める
        while (position < text.length() && isBareChar(text.charAt(position))) {
            position += 1;
        }

        return text.substring(start, position);
    }

    /** 引用符なしで書ける文字か */
    static boolean isBareChar(char c) {
        if (c >= 'a' && c <= 'z') {
            return true;
        }

        if (c >= 'A' && c <= 'Z') {
            return true;
        }

        if (c >= '0' && c <= '9') {
            return true;
        }

        return c == '_' || c == '-' || c == '.' || c == '+';
    }

    private void skipWhitespace() {
        // 空白・改行・タブを読み飛ばす
        while (position < text.length() && Character.isWhitespace(text.charAt(position))) {
            position += 1;
        }
    }

    private char peek() {
        if (position >= text.length()) {
            throw malformed("入力が途中で尽きた");
        }

        return text.charAt(position);
    }

    /**
     * 末尾でも例外にしない先読み
     * 入力が尽きていれば NUL を返す
     */
    private char peekOrNul() {
        if (position >= text.length()) {
            return '\0';
        }

        return text.charAt(position);
    }

    private void expect(char expected) {
        skipWhitespace();

        if (position >= text.length()) {
            throw malformed("'" + expected + "' が来るべき位置で入力が尽きた");
        }

        if (text.charAt(position) != expected) {
            throw malformed("'" + expected + "' を期待したが '" + text.charAt(position) + "' だった");
        }

        position += 1;
    }

    private SpringNbtException malformed(String message) {
        return SpringNbtException.malformed("SNBT (" + position + " 文字目): " + message);
    }
}

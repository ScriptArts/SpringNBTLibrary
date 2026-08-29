package io.github.scriptarts.springnbt.nbt;

import java.util.Locale;

/**
 * 浮動小数点の正準10進表記。
 *
 * <p>各言語の標準の数値書式は互いに一致しない。指数表記へ切り替わる閾値も、
 * 指数部の桁数も、E の大文字小文字も処理系ごとに違う。
 * そのままでは SNBT 出力の言語間一致が成立しないため、書式をここで固定する。
 *
 * <p>仕様: {@code docs/spec/11-snbt.md} 5.1章
 */
final class CanonicalDecimal {

    /** 固定小数点表記を使う10進指数の下限。 */
    private static final int MIN_FIXED_EXPONENT = -4;

    /** 固定小数点表記を使う10進指数の上限。 */
    private static final int MAX_FIXED_EXPONENT = 16;

    private CanonicalDecimal() {
        // ユーティリティクラス
    }

    /** binary32 を正準10進表記へ変換する。 */
    static String fromFloat(float value) {
        if (Float.isNaN(value)) {
            return "NaN";
        }

        if (value == Float.POSITIVE_INFINITY) {
            return "Infinity";
        }

        if (value == Float.NEGATIVE_INFINITY) {
            return "-Infinity";
        }

        int target = Float.floatToRawIntBits(value);

        // 有効数字を 1 桁ずつ増やし、読み戻してビット一致する最短の表記を探す
        for (int precision = 1; precision <= 9; precision++) {
            String candidate = String.format(Locale.ROOT, "%." + (precision - 1) + "e", value);

            if (Float.floatToRawIntBits(Float.parseFloat(candidate)) == target) {
                return format(candidate);
            }
        }

        // 9 桁あれば binary32 は必ず往復するので、ここへは来ない
        return format(String.format(Locale.ROOT, "%.8e", value));
    }

    /** binary64 を正準10進表記へ変換する。 */
    static String fromDouble(double value) {
        if (Double.isNaN(value)) {
            return "NaN";
        }

        if (value == Double.POSITIVE_INFINITY) {
            return "Infinity";
        }

        if (value == Double.NEGATIVE_INFINITY) {
            return "-Infinity";
        }

        long target = Double.doubleToRawLongBits(value);

        // 有効数字を 1 桁ずつ増やし、読み戻してビット一致する最短の表記を探す
        for (int precision = 1; precision <= 17; precision++) {
            String candidate = String.format(Locale.ROOT, "%." + (precision - 1) + "e", value);

            if (Double.doubleToRawLongBits(Double.parseDouble(candidate)) == target) {
                return format(candidate);
            }
        }

        // 17 桁あれば binary64 は必ず往復するので、ここへは来ない
        return format(String.format(Locale.ROOT, "%.16e", value));
    }

    /** 指数表記の文字列（例 {@code "7.5e-01"}）から、仕様が定める正準表記を組み立てる。 */
    private static String format(String exponential) {
        boolean negative = false;
        int index = 0;

        if (exponential.charAt(0) == '-' || exponential.charAt(0) == '+') {
            negative = exponential.charAt(0) == '-';
            index = 1;
        }

        StringBuilder digitsBuilder = new StringBuilder();

        // 仮数部の数字だけを集める
        while (index < exponential.length()
                && exponential.charAt(index) != 'e' && exponential.charAt(index) != 'E') {
            char c = exponential.charAt(index);

            if (c >= '0' && c <= '9') {
                digitsBuilder.append(c);
            }

            index += 1;
        }

        int exponent = Integer.parseInt(stripPlus(exponential.substring(index + 1)));
        String digits = trimTrailingZeros(digitsBuilder.toString());

        return compose(negative, digits, exponent);
    }

    /** {@code Integer.parseInt} は先頭の "+" を受け付けるが、環境差を避けるため明示的に外す。 */
    private static String stripPlus(String text) {
        if (text.startsWith("+")) {
            return text.substring(1);
        }

        return text;
    }

    /** 末尾のゼロを取り除く。すべてゼロなら "0" を残す。 */
    private static String trimTrailingZeros(String digits) {
        int end = digits.length();

        // 末尾から連続するゼロを削る
        while (end > 1 && digits.charAt(end - 1) == '0') {
            end -= 1;
        }

        return digits.substring(0, end);
    }

    /** 数字列と10進指数から最終的な文字列を組み立てる。 */
    private static String compose(boolean negative, String digits, int exponent) {
        StringBuilder builder = new StringBuilder();

        if (negative) {
            builder.append('-');
        }

        // 値が 0 のときは指数に関わらず 0.0 と書く
        if (digits.equals("0")) {
            builder.append("0.0");
            return builder.toString();
        }

        if (exponent < MIN_FIXED_EXPONENT || exponent > MAX_FIXED_EXPONENT) {
            // 指数表記
            builder.append(digits.charAt(0));
            builder.append('.');

            if (digits.length() > 1) {
                builder.append(digits, 1, digits.length());
            } else {
                builder.append('0');
            }

            builder.append('E');
            builder.append(exponent);
            return builder.toString();
        }

        if (exponent >= 0) {
            // 整数部は先頭 (exponent + 1) 桁。足りなければゼロで右詰めする
            int integerDigits = exponent + 1;

            if (digits.length() >= integerDigits) {
                builder.append(digits, 0, integerDigits);
            } else {
                builder.append(digits);

                for (int i = digits.length(); i < integerDigits; i++) {
                    builder.append('0');
                }
            }

            builder.append('.');

            if (digits.length() > integerDigits) {
                builder.append(digits, integerDigits, digits.length());
            } else {
                builder.append('0');
            }

            return builder.toString();
        }

        // 指数が負なら "0." に続けてゼロを詰めてから数字を置く
        builder.append("0.");

        for (int i = 0; i < (-exponent) - 1; i++) {
            builder.append('0');
        }

        builder.append(digits);
        return builder.toString();
    }
}

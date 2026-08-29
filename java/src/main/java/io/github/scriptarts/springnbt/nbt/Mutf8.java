package io.github.scriptarts.springnbt.nbt;

import io.github.scriptarts.springnbt.SpringNbtException;

/**
 * Modified UTF-8 (MUTF-8) の符号化・復号
 *
 * <p>標準 UTF-8 との違いは 2 点だけ
 * <ul>
 *   <li>{@code U+0000} を {@code C0 80} の 2 バイトで表す</li>
 *   <li>{@code U+10000} 以上をサロゲートペアへ分解し、3 バイト × 2 で表す (CESU-8)</li>
 * </ul>
 *
 * <p>Java の {@link String} は UTF-16 コード単位の列なので、
 * サロゲートペアも孤立サロゲートもそのまま保持できる
 *
 * <p>{@code DataInput.readUTF} と同じ符号化だが、
 * 65535 バイト超の扱いなど細部を仕様どおりに固定したいため自前で実装している
 *
 * <p>仕様: {@code docs/spec/10-nbt-binary.md} 2章
 */
public final class Mutf8 {

    /** MUTF-8 の文字列が取りうる最大バイト長（長さフィールドが u16 のため）
    /** */
    public static final int MAX_BYTE_LENGTH = 65535;

    private Mutf8() {
        // ユーティリティクラス
    }

    /**
     * MUTF-8 バイト列を文字列へ復号する
     *
     * @param data   バイト列
     * @param offset 開始位置
     * @param length 長さ
     * @return 復号した文字列
     * @throws SpringNbtException バイト列が MUTF-8 として不正な場合
     */
    public static String decode(byte[] data, int offset, int length) {
        StringBuilder builder = new StringBuilder(length);
        int index = offset;
        int end = offset + length;

        // 先頭から 1 文字ずつ取り出す
        while (index < end) {
            int b0 = data[index] & 0xFF;

            if ((b0 & 0x80) == 0x00) {
                // 1 バイト形式: 0xxxxxxx (U+0001..U+007F)
                if (b0 == 0x00) {
                    // 素の 0x00 は MUTF-8 では現れてはならない (C0 80 を使う)
                    throw SpringNbtException.malformed("MUTF-8: 素の 0x00 が現れた (U+0000 は C0 80 で表す)");
                }

                builder.append((char) b0);
                index += 1;
            } else if ((b0 & 0xE0) == 0xC0) {
                // 2 バイト形式: 110xxxxx 10xxxxxx
                if (index + 1 >= end) {
                    throw SpringNbtException.malformed("MUTF-8: 2バイト形式が途中で切れた");
                }

                int b1 = data[index + 1] & 0xFF;

                if ((b1 & 0xC0) != 0x80) {
                    throw SpringNbtException.malformed("MUTF-8: 2バイト形式の継続バイトが不正");
                }

                int value = ((b0 & 0x1F) << 6) | (b1 & 0x3F);

                // C0 80 (U+0000) だけは正当
                // それ以外の 0x80 未満は冗長符号化
                if (value < 0x80 && !(b0 == 0xC0 && b1 == 0x80)) {
                    throw SpringNbtException.malformed("MUTF-8: 冗長な2バイト符号化");
                }

                builder.append((char) value);
                index += 2;
            } else if ((b0 & 0xF0) == 0xE0) {
                // 3 バイト形式: 1110xxxx 10xxxxxx 10xxxxxx
                if (index + 2 >= end) {
                    throw SpringNbtException.malformed("MUTF-8: 3バイト形式が途中で切れた");
                }

                int b1 = data[index + 1] & 0xFF;
                int b2 = data[index + 2] & 0xFF;

                if ((b1 & 0xC0) != 0x80 || (b2 & 0xC0) != 0x80) {
                    throw SpringNbtException.malformed("MUTF-8: 3バイト形式の継続バイトが不正");
                }

                int value = ((b0 & 0x0F) << 12) | ((b1 & 0x3F) << 6) | (b2 & 0x3F);

                // 3 バイトで表すべき範囲は U+0800 以上
                if (value < 0x800) {
                    throw SpringNbtException.malformed("MUTF-8: 冗長な3バイト符号化");
                }

                builder.append((char) value);
                index += 3;
            } else {
                // 4 バイト形式 (標準 UTF-8) や継続バイト単独は MUTF-8 では不正
                throw SpringNbtException.malformed(
                        String.format("MUTF-8: 不正な先頭バイト 0x%02X", b0));
            }
        }

        return builder.toString();
    }

    /**
     * MUTF-8 バイト列を文字列へ復号する
     *
     * @param data バイト列
     * @return 復号した文字列
     * @throws SpringNbtException バイト列が MUTF-8 として不正な場合
     */
    public static String decode(byte[] data) {
        return decode(data, 0, data.length);
    }

    /**
     * 文字列を MUTF-8 バイト列へ符号化する
     *
     * <p>サロゲートは対になっているかどうかに関わらず 1 つずつ 3 バイトで符号化されるため、
     * 孤立サロゲートもそのまま往復できる
     *
     * @param text 文字列
     * @return MUTF-8 バイト列
     */
    public static byte[] encode(String text) {
        byte[] buffer = new byte[byteLength(text)];
        int position = 0;

        // コード単位ごとに 1〜3 バイトへ展開する
        for (int index = 0; index < text.length(); index++) {
            char unit = text.charAt(index);

            if (unit >= 0x0001 && unit <= 0x007F) {
                buffer[position] = (byte) unit;
                position += 1;
            } else if (unit == 0x0000 || unit <= 0x07FF) {
                // U+0000 もこの経路で C0 80 になる
                buffer[position] = (byte) (0xC0 | ((unit >> 6) & 0x1F));
                buffer[position + 1] = (byte) (0x80 | (unit & 0x3F));
                position += 2;
            } else {
                buffer[position] = (byte) (0xE0 | ((unit >> 12) & 0x0F));
                buffer[position + 1] = (byte) (0x80 | ((unit >> 6) & 0x3F));
                buffer[position + 2] = (byte) (0x80 | (unit & 0x3F));
                position += 3;
            }
        }

        return buffer;
    }

    /**
     * 文字列を MUTF-8 で符号化したときのバイト長を求める
     * 実際に符号化はしない
     *
     * @param text 文字列
     * @return バイト長
     */
    public static int byteLength(String text) {
        int length = 0;

        // 各コード単位が何バイトになるかを数える
        for (int index = 0; index < text.length(); index++) {
            char unit = text.charAt(index);

            if (unit >= 0x0001 && unit <= 0x007F) {
                length += 1;
            } else if (unit == 0x0000 || unit <= 0x07FF) {
                length += 2;
            } else {
                length += 3;
            }
        }

        return length;
    }
}

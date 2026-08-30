package io.github.scriptarts.springnbt.anvil;

import io.github.scriptarts.springnbt.SpringNbtException;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

/**
 * 圧縮方式ID 4 (LZ4) のチャンクを展開する
 *
 * <p>素の LZ4 ブロックでも LZ4 フレーム形式でもなく、
 * 独自ヘッダを持つブロックの連結である
 *
 * <p>書き込みには対応しない
 * 書き戻すときは Zlib になる
 *
 * <p>仕様: {@code docs/spec/20-anvil-region.md} 3.1.1 / 3.1.2
 */
final class Lz4 {

    /** ブロックの先頭に必ず置かれる 8 バイト */
    private static final byte[] MAGIC = "LZ4Block".getBytes(StandardCharsets.US_ASCII);

    /** ブロックヘッダの長さ */
    private static final int HEADER_LENGTH = 21;

    /** トークン上位 4 ビット: 本体が無圧縮 */
    private static final int METHOD_STORED = 0x10;

    /** トークン上位 4 ビット: 本体が LZ4 圧縮 */
    private static final int METHOD_COMPRESSED = 0x20;

    /** マッチの最小長 */
    private static final int MIN_MATCH = 4;

    private Lz4() {
        // ユーティリティクラス
    }

    /**
     * LZ4Block の連結を展開する
     *
     * @param payload 圧縮済みペイロード
     * @return 展開後のバイト列
     */
    static byte[] decompress(byte[] payload) {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        int position = 0;

        // 入力を使い切るまでブロックを読み続ける
        while (position < payload.length) {
            position = decompressBlock(payload, position, output);
        }

        return output.toByteArray();
    }

    /** ブロックを 1 つ展開し、次のブロックの開始位置を返す */
    private static int decompressBlock(byte[] payload, int position, ByteArrayOutputStream output) {
        if (position + HEADER_LENGTH > payload.length) {
            throw SpringNbtException.malformed(
                    "LZ4: ブロックヘッダが足りない（" + (payload.length - position) + " バイト）");
        }

        // マジックが違えばそもそも LZ4Block ではない
        for (int index = 0; index < MAGIC.length; index++) {
            if (payload[position + index] != MAGIC[index]) {
                throw SpringNbtException.malformed("LZ4: ブロックが LZ4Block で始まっていない");
            }
        }

        int method = payload[position + 8] & 0xF0;
        int compressedLength = readInt32LittleEndian(payload, position + 9);
        int originalLength = readInt32LittleEndian(payload, position + 13);
        int body = position + HEADER_LENGTH;

        validateLengths(compressedLength, originalLength);

        if (body + compressedLength > payload.length) {
            throw SpringNbtException.malformed("LZ4: ブロック本体が入力からはみ出している");
        }

        if (method == METHOD_STORED) {
            // 無圧縮なら 2 つの長さは一致していなければならない
            if (compressedLength != originalLength) {
                throw SpringNbtException.malformed(
                        "LZ4: 無圧縮ブロックの長さが食い違う（"
                                + compressedLength + " と " + originalLength + "）");
            }

            output.write(payload, body, compressedLength);
        } else if (method == METHOD_COMPRESSED) {
            byte[] block = decompressRawBlock(payload, body, compressedLength, originalLength);
            output.write(block, 0, block.length);
        } else {
            throw SpringNbtException.malformed(
                    "LZ4: 未知の圧縮方式 0x" + Integer.toHexString(method).toUpperCase());
        }

        return body + compressedLength;
    }

    /** ヘッダに書かれた 2 つの長さが妥当か調べる */
    private static void validateLengths(int compressedLength, int originalLength) {
        if (compressedLength < 0 || originalLength < 0) {
            throw SpringNbtException.malformed("LZ4: ブロックの長さが負値");
        }

        // 片方だけが 0 になることはない
        if ((compressedLength == 0) != (originalLength == 0)) {
            throw SpringNbtException.malformed("LZ4: ブロックの長さが片方だけ 0");
        }
    }

    /** 素の LZ4 ブロックを展開する */
    private static byte[] decompressRawBlock(byte[] source, int start, int length,
                                             int originalLength) {
        byte[] output = new byte[originalLength];
        int end = start + length;
        int[] input = {start};
        int written = 0;

        // シーケンスを順に読む
        while (input[0] < end) {
            int token = source[input[0]] & 0xFF;
            input[0]++;

            int literalLength = token >> 4;

            // 15 なら追加バイトで長さが続く
            if (literalLength == 15) {
                literalLength += readLength(source, input, end);
            }

            written = copyLiterals(source, input, end, output, written, literalLength);

            // リテラルを出し切って入力が尽きたら、そこで終わり
            if (input[0] >= end) {
                break;
            }

            if (input[0] + 2 > end) {
                throw SpringNbtException.malformed("LZ4: オフセットが入力からはみ出している");
            }

            int offset = (source[input[0]] & 0xFF) | ((source[input[0] + 1] & 0xFF) << 8);
            input[0] += 2;

            if (offset == 0 || offset > written) {
                throw SpringNbtException.malformed("LZ4: マッチのオフセットが不正: " + offset);
            }

            int matchLength = (token & 0x0F) + MIN_MATCH;

            // 下位 4 ビットが 15 なら追加バイトで長さが続く
            if ((token & 0x0F) == 15) {
                matchLength += readLength(source, input, end);
            }

            written = copyMatch(output, written, offset, matchLength);
        }

        if (written != originalLength) {
            throw SpringNbtException.malformed(
                    "LZ4: 展開後の長さが合わない（" + written + " と " + originalLength + "）");
        }

        return output;
    }

    /** 255 が続く形式の追加長さを読む */
    private static int readLength(byte[] source, int[] input, int end) {
        int total = 0;

        // 255 未満のバイトが出るまで足し続ける
        while (true) {
            if (input[0] >= end) {
                throw SpringNbtException.malformed("LZ4: 長さの追加バイトが途中で切れた");
            }

            int value = source[input[0]] & 0xFF;
            input[0]++;
            total += value;

            if (value != 255) {
                return total;
            }
        }
    }

    /** リテラルをそのまま出力へ写し、書き込み済みの長さを返す */
    private static int copyLiterals(byte[] source, int[] input, int end,
                                    byte[] output, int written, int length) {
        if (input[0] + length > end) {
            throw SpringNbtException.malformed("LZ4: リテラルが入力からはみ出している");
        }

        if (written + length > output.length) {
            throw SpringNbtException.malformed("LZ4: 展開後の長さを超えた");
        }

        System.arraycopy(source, input[0], output, written, length);
        input[0] += length;
        return written + length;
    }

    /** 出力済みのバイト列からマッチを写し、書き込み済みの長さを返す */
    private static int copyMatch(byte[] output, int written, int offset, int length) {
        if (written + length > output.length) {
            throw SpringNbtException.malformed("LZ4: 展開後の長さを超えた");
        }

        int from = written - offset;

        // コピー元と先は重なりうるので 1 バイトずつ写す
        for (int index = 0; index < length; index++) {
            output[written + index] = output[from + index];
        }

        return written + length;
    }

    /** リトルエンディアンの i32 を読む。この形式だけ他と逆になる */
    private static int readInt32LittleEndian(byte[] source, int position) {
        return (source[position] & 0xFF)
                | ((source[position + 1] & 0xFF) << 8)
                | ((source[position + 2] & 0xFF) << 16)
                | ((source[position + 3] & 0xFF) << 24);
    }
}

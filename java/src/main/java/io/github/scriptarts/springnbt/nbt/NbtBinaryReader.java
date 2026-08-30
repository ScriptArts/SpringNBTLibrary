package io.github.scriptarts.springnbt.nbt;

import io.github.scriptarts.springnbt.SpringNbtException;

/**
 * 展開済みのバイト列から NBT を読み出す
 *
 * <p>入力全体をあらかじめメモリに持つ設計にしている
 * 「宣言された長さが残り入力長を超えていないか」を確保前に検査できるようにするため
 * これがないと、長さ 0x7FFFFFFF を宣言しただけの数バイトの入力でメモリを枯渇させられる
 *
 * <p>仕様: {@code docs/spec/10-nbt-binary.md}
 */
final class NbtBinaryReader {

    private final byte[] data;
    private final int maxDepth;
    private int position;

    NbtBinaryReader(byte[] data, int maxDepth) {
        this(data, maxDepth, 0);
    }

    NbtBinaryReader(byte[] data, int maxDepth, int start) {
        this.data = data;
        this.maxDepth = maxDepth;
        this.position = start;
    }

    /** 残っている入力バイト数 */
    private int remaining() {
        return data.length - position;
    }

    /** 次に読む位置 */
    int position() {
        return position;
    }

    /** まだ読んでいないバイトが残っているか */
    boolean hasMore() {
        return remaining() > 0;
    }

    /** ルートタグを読み、末尾に余りが無いことを確かめる */
    NamedTag readRoot(NbtFormat format) {
        NamedTag tag = readRootTag(format);

        // 末尾に余分なバイトが残っていたら、読み違えている可能性が高い
        if (remaining() != 0) {
            throw SpringNbtException.malformed(
                    "ルートタグの後に " + remaining() + " バイトの余分な入力がある");
        }

        return tag;
    }

    /**
     * ルートタグを 1 つ読む
     * 末尾の余りは見ない
     */
    NamedTag readRootTag(NbtFormat format) {
        TagType type = TagType.fromId(readByteRaw() & 0xFF);

        // Java版のファイル形式でもネットワーク形式でも、ルートは必ず TAG_Compound
        if (type != TagType.COMPOUND) {
            throw SpringNbtException.malformed(
                    "ルートタグは compound でなければならないが " + type.asString() + " だった");
        }

        String name;
        if (format == NbtFormat.JAVA) {
            // ファイル形式のルートには名前が付く（通常は空文字列）
            name = requireUtf8Representable(readString(), "ルート名");
        } else {
            // ネットワーク形式 (1.20.2+) のルートに名前は無い
            name = "";
        }

        NbtCompound root = readCompoundPayload(1);
        return new NamedTag(name, root);
    }

    /** 指定した型のペイロードを読む */
    private NbtTag readPayload(TagType type, int depth) {
        // 深さ上限は再帰する型に入る手前で検査する
        if (depth > maxDepth) {
            throw SpringNbtException.limitExceeded("ネストが深すぎる (上限 " + maxDepth + ")");
        }

        return switch (type) {
            case BYTE -> new NbtByte(readByteRaw());
            case SHORT -> new NbtShort((short) readUnsigned(2));
            case INT -> new NbtInt((int) readUnsigned(4));
            case LONG -> new NbtLong(readUnsigned(8));
            case FLOAT -> new NbtFloat(Float.intBitsToFloat((int) readUnsigned(4)));
            case DOUBLE -> new NbtDouble(Double.longBitsToDouble(readUnsigned(8)));
            case BYTE_ARRAY -> new NbtByteArray(readByteArrayPayload());
            case STRING -> new NbtString(readString());
            case LIST -> readListPayload(depth);
            case COMPOUND -> readCompoundPayload(depth);
            case INT_ARRAY -> new NbtIntArray(readIntArrayPayload());
            case LONG_ARRAY -> new NbtLongArray(readLongArrayPayload());
            case END -> throw SpringNbtException.malformed("TAG_End のペイロードを読もうとした");
        };
    }

    /** TAG_Compound のペイロード（名前付きタグの並び + TAG_End）を読む */
    private NbtCompound readCompoundPayload(int depth) {
        NbtCompound compound = new NbtCompound();

        // TAG_End が現れるまで名前付きタグを読み続ける
        while (true) {
            TagType type = TagType.fromId(readByteRaw() & 0xFF);

            if (type == TagType.END) {
                return compound;
            }

            String name = requireUtf8Representable(readString(), "Compound のキー");
            compound.set(name, readPayload(type, depth + 1));
        }
    }

    /** TAG_List のペイロードを読む */
    private NbtList readListPayload(int depth) {
        TagType elementType = TagType.fromId(readByteRaw() & 0xFF);
        int count = readLength();

        if (elementType == TagType.END) {
            // 要素型 End のリストは空でなければならない
            if (count != 0) {
                throw SpringNbtException.malformed(
                        "要素型 End のリストに " + count + " 個の要素が宣言されている");
            }

            return new NbtList(TagType.END);
        }

        // 1 要素の最小バイト数から、宣言された個数が入力に収まるかを先に検査する
        ensureAvailable((long) count * minimumPayloadSize(elementType));

        NbtList list = new NbtList(elementType);

        // 宣言された個数だけペイロードを読む
        for (int index = 0; index < count; index++) {
            list.add(readPayload(elementType, depth + 1));
        }

        return list;
    }

    private byte[] readByteArrayPayload() {
        int count = readLength();
        ensureAvailable(count);

        byte[] result = new byte[count];
        System.arraycopy(data, position, result, 0, count);
        position += count;
        return result;
    }

    private int[] readIntArrayPayload() {
        int count = readLength();
        ensureAvailable((long) count * 4);

        int[] result = new int[count];

        // 4 バイトずつビッグエンディアンで読む
        for (int index = 0; index < count; index++) {
            result[index] = (int) readUnsigned(4);
        }

        return result;
    }

    private long[] readLongArrayPayload() {
        int count = readLength();
        ensureAvailable((long) count * 8);

        long[] result = new long[count];

        // 8 バイトずつビッグエンディアンで読む
        for (int index = 0; index < count; index++) {
            result[index] = readUnsigned(8);
        }

        return result;
    }

    /** MUTF-8 の文字列（u16 の長さ + 本体）を読む */
    private String readString() {
        int length = (int) readUnsigned(2);
        ensureAvailable(length);

        String text = Mutf8.decode(data, position, length);
        position += length;
        return text;
    }

    /**
     * 配列・リストの長さフィールドを読む
     * 負値は不正
     */
    private int readLength() {
        int length = (int) readUnsigned(4);

        // 長さは i32 だが、負値は仕様上ありえない
        if (length < 0) {
            throw SpringNbtException.malformed("長さが負値: " + length);
        }

        return length;
    }

    private byte readByteRaw() {
        ensureAvailable(1);
        byte value = data[position];
        position += 1;
        return value;
    }

    /** 指定バイト数をビッグエンディアンで読み進める */
    private long readUnsigned(int count) {
        ensureAvailable(count);
        long value = 0;

        // 上位バイトから順に積み上げる
        for (int index = 0; index < count; index++) {
            value = (value << 8) | (data[position + index] & 0xFFL);
        }

        position += count;
        return value;
    }

    /**
     * 残り入力が必要バイト数を満たすか検査する
     * メモリを確保する前に呼ぶ
     */
    private void ensureAvailable(long required) {
        if (required > remaining()) {
            throw SpringNbtException.malformed(
                    "入力が足りない: " + required + " バイト必要だが残り " + remaining() + " バイト");
        }
    }

    /**
     * キーやルート名として使える文字列か検査する
     *
     * <p>値と違い、キーには孤立サロゲートを許さない（仕様 10 の 2.2章）
     * Minecraft が書き出すキーは ASCII の識別子のみで、
     * 孤立サロゲートが現れるのはデータ破損を意味する
     */
    private static String requireUtf8Representable(String text, String role) {
        // 対にならないサロゲートが含まれていないか調べる
        for (int index = 0; index < text.length(); index++) {
            char c = text.charAt(index);

            // 上位サロゲートは、対になる下位サロゲートとまとめて 1 文字を成す
            if (Character.isHighSurrogate(c)) {
                // 対が揃っていれば 2 コード単位を消費する
                // 揃わなければ孤立サロゲート
                if (index + 1 < text.length() && Character.isLowSurrogate(text.charAt(index + 1))) {
                    index += 1;
                } else {
                    throw SpringNbtException.malformed(role + "が UTF-8 に写せない（孤立サロゲートを含む）");
                }
            } else if (Character.isLowSurrogate(c)) {
                throw SpringNbtException.malformed(role + "が UTF-8 に写せない（孤立サロゲートを含む）");
            }
        }

        return text;
    }

    /**
     * その型のペイロードが最低何バイトになるかを返す
     * 長さの先行検証に使う
     */
    private static int minimumPayloadSize(TagType type) {
        return switch (type) {
            case BYTE -> 1;
            case SHORT -> 2;
            case INT, FLOAT -> 4;
            case LONG, DOUBLE -> 8;
            // 長さフィールドの 4 バイトは必ずある
            case BYTE_ARRAY, INT_ARRAY, LONG_ARRAY -> 4;
            // 長さフィールドの 2 バイトは必ずある
            case STRING -> 2;
            // 要素型 1 バイト + 個数 4 バイト
            case LIST -> 5;
            // 終端の TAG_End 1 バイトは必ずある
            case COMPOUND, END -> 1;
        };
    }
}

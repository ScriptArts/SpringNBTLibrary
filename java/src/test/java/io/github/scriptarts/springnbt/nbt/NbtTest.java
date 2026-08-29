package io.github.scriptarts.springnbt.nbt;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import io.github.scriptarts.springnbt.ErrorCode;
import io.github.scriptarts.springnbt.SpringNbtException;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.EnumSource;

/**
 * NBT レイヤの単体テスト。
 *
 * <p>他言語版と同じ検証項目を持つ。
 * 共通テストベクタによる言語間比較は {@code spec/run-conformance.sh} が担当し、
 * ここでは API の振る舞いを直接確かめる。
 */
class NbtTest {

    private static NbtReadOptions uncompressedRead() {
        return NbtReadOptions.defaults().setCompression(Compression.NONE);
    }

    private static NbtWriteOptions uncompressedWrite() {
        return NbtWriteOptions.uncompressed();
    }

    /** 仕様書どおりに組んだ最小の NBT。 */
    private static byte[] helloWorldBytes() {
        ByteArrayOutputStream out = new ByteArrayOutputStream();

        // ルート: TAG_Compound、名前 "hello world"
        out.write(0x0A);
        out.write(0x00);
        out.write(0x0B);
        out.writeBytes("hello world".getBytes(StandardCharsets.US_ASCII));

        // 子: TAG_String、名前 "name"、値 "Bananrama"
        out.write(0x08);
        out.write(0x00);
        out.write(0x04);
        out.writeBytes("name".getBytes(StandardCharsets.US_ASCII));
        out.write(0x00);
        out.write(0x09);
        out.writeBytes("Bananrama".getBytes(StandardCharsets.US_ASCII));

        // ルートの終端
        out.write(0x00);

        return out.toByteArray();
    }

    private static ErrorCode codeOf(Runnable action) {
        SpringNbtException error = assertThrows(SpringNbtException.class, action::run);
        return error.code();
    }

    @Nested
    @DisplayName("MUTF-8")
    class Mutf8Test {

        @Test
        void asciiRoundtrip() {
            assertArrayEquals("Bananrama".getBytes(StandardCharsets.US_ASCII),
                    Mutf8.encode("Bananrama"));
            assertEquals("Bananrama",
                    Mutf8.decode("Bananrama".getBytes(StandardCharsets.US_ASCII)));
        }

        @Test
        void nulIsTwoBytes() {
            String sample = "a\u0000b";
            byte[] expected = { 0x61, (byte) 0xC0, (byte) 0x80, 0x62 };
            assertArrayEquals(expected, Mutf8.encode(sample));
            assertEquals(sample, Mutf8.decode(expected));
        }

        @Test
        void supplementaryCharIsCesu8() {
            // U+1F600 は UTF-16 で D83D DE00。MUTF-8 では 3 バイト × 2 になる
            String sample = "\uD83D\uDE00";
            byte[] expected = {
                (byte) 0xED, (byte) 0xA0, (byte) 0xBD,
                (byte) 0xED, (byte) 0xB8, (byte) 0x80,
            };
            assertArrayEquals(expected, Mutf8.encode(sample));
            assertEquals(sample, Mutf8.decode(expected));
        }

        @Test
        void loneSurrogateSurvivesRoundtrip() {
            // 対にならない上位サロゲート。UTF-8 には写せないが MUTF-8 では往復できる
            String lone = "\uD83D";
            byte[] expected = { (byte) 0xED, (byte) 0xA0, (byte) 0xBD };
            assertArrayEquals(expected, Mutf8.encode(lone));
            assertEquals(lone, Mutf8.decode(expected));
        }

        @Test
        void invalidInputIsRejected() {
            List<byte[]> cases = List.of(
                    new byte[] { 0x00 },
                    new byte[] { (byte) 0xC1, (byte) 0x81 },
                    new byte[] { (byte) 0xF0, (byte) 0x9F, (byte) 0x98, (byte) 0x80 },
                    new byte[] { (byte) 0xE3, (byte) 0x81 });

            // 素の 0x00 / 冗長符号化 / 4バイト形式 / 途中で切れた入力 のすべてを拒否する
            for (byte[] data : cases) {
                assertEquals(ErrorCode.MALFORMED_DATA, codeOf(() -> Mutf8.decode(data)),
                        Arrays.toString(data));
            }
        }

        @Test
        void byteLengthMatchesEncodedLength() {
            String sample = "abc\u3042\uD83D\uDE00";
            assertEquals(Mutf8.encode(sample).length, Mutf8.byteLength(sample));
        }
    }

    @Nested
    @DisplayName("バイナリ読み書き")
    class BinaryTest {

        @Test
        void readsHandBuiltHelloWorld() {
            NamedTag named = NbtIo.readBytes(helloWorldBytes(), uncompressedRead());

            assertEquals("hello world", named.name());
            assertEquals(1, named.tag().size());
            assertEquals("Bananrama", named.tag().getString("name"));
        }

        @Test
        void writesBackTheSameBytes() {
            byte[] original = helloWorldBytes();
            NamedTag named = NbtIo.readBytes(original, uncompressedRead());

            assertArrayEquals(original, NbtIo.writeBytes(named, uncompressedWrite()));
        }

        @Test
        void allTagTypesRoundtrip() {
            NbtCompound root = buildAllTags();
            byte[] encoded = NbtIo.writeBytes(new NamedTag("", root), uncompressedWrite());
            NamedTag decoded = NbtIo.readBytes(encoded, uncompressedRead());

            assertEquals(root, decoded.tag());
            assertArrayEquals(encoded, NbtIo.writeBytes(decoded, uncompressedWrite()));
        }

        @Test
        void floatSpecialsKeepTheirBitPattern() {
            NbtCompound root = new NbtCompound();
            root.set("negative_zero", new NbtDouble(-0.0));
            root.set("nan", new NbtFloat(Float.NaN));
            root.set("infinity", new NbtDouble(Double.POSITIVE_INFINITY));

            byte[] encoded = NbtIo.writeBytes(new NamedTag("", root), uncompressedWrite());
            NbtCompound decoded = NbtIo.readBytes(encoded, uncompressedRead()).tag();

            // -0.0 と +0.0 は == では区別できないので、ビットパターンで比較する
            assertEquals(Double.doubleToRawLongBits(-0.0),
                    Double.doubleToRawLongBits(decoded.getDouble("negative_zero")));
            assertTrue(Float.isNaN(decoded.getFloat("nan")));
            assertEquals(Double.POSITIVE_INFINITY, decoded.getDouble("infinity"));
        }

        @Test
        void compoundKeepsInsertionOrder() {
            NbtCompound root = new NbtCompound();
            root.set("zebra", new NbtInt(1));
            root.set("apple", new NbtInt(2));
            root.set("mango", new NbtInt(3));

            // 既存キーへの再設定は位置を変えない
            root.set("zebra", new NbtInt(9));

            assertEquals(List.of("zebra", "apple", "mango"), List.copyOf(root.keys()));

            byte[] encoded = NbtIo.writeBytes(new NamedTag("", root), uncompressedWrite());
            NbtCompound decoded = NbtIo.readBytes(encoded, uncompressedRead()).tag();

            assertEquals(List.of("zebra", "apple", "mango"), List.copyOf(decoded.keys()));
        }

        @Test
        void emptyListKeepsElementTypeEnd() {
            NbtCompound root = new NbtCompound();
            root.set("empty", new NbtList());

            byte[] encoded = NbtIo.writeBytes(new NamedTag("", root), uncompressedWrite());
            NbtCompound decoded = NbtIo.readBytes(encoded, uncompressedRead()).tag();

            assertEquals(TagType.END, decoded.getList("empty").elementType());
        }

        @Test
        void listRejectsMixedTypes() {
            NbtList list = new NbtList();
            list.add(new NbtInt(1));

            assertEquals(ErrorCode.UNEXPECTED_TAG_TYPE,
                    codeOf(() -> list.add(new NbtString("x"))));
        }

        @Test
        void typedGetterDistinguishesMissingKeyFromWrongType() {
            NbtCompound root = new NbtCompound();
            root.set("value", new NbtString("text"));

            // キーが無い場合は null
            assertNull(root.optInt("missing"));

            // 型が違う場合はキーの有無に関わらず例外
            assertEquals(ErrorCode.UNEXPECTED_TAG_TYPE, codeOf(() -> root.optInt("value")));
            assertEquals(ErrorCode.INVALID_ARGUMENT, codeOf(() -> root.getInt("missing")));
        }

        @ParameterizedTest
        @EnumSource(value = Compression.class, names = { "GZIP", "ZLIB", "NONE" })
        void compressionIsDetectedAutomatically(Compression method) {
            NamedTag named = NbtIo.readBytes(helloWorldBytes(), uncompressedRead());
            byte[] encoded = NbtIo.writeBytes(named,
                    NbtWriteOptions.defaults().setCompression(method));

            assertEquals(method, NbtIo.detectCompression(encoded));

            // 既定の ReadOptions は AUTO なので、方式を指定しなくても読める
            assertEquals("Bananrama", NbtIo.readBytes(encoded, null).tag().getString("name"));
        }

        @Test
        void networkFormatHasNoRootName() {
            NbtCompound root = new NbtCompound();
            root.set("x", new NbtInt(1));

            byte[] encoded = NbtIo.writeBytes(new NamedTag("ignored", root),
                    NbtWriteOptions.defaults()
                            .setFormat(NbtFormat.NETWORK)
                            .setCompression(Compression.NONE));

            // タグID + ペイロード のみで、名前長の 2 バイトが無い
            assertEquals(0x0A, encoded[0]);
            assertEquals(0x03, encoded[1]);

            NamedTag decoded = NbtIo.readBytes(encoded,
                    NbtReadOptions.defaults()
                            .setFormat(NbtFormat.NETWORK)
                            .setCompression(Compression.NONE));

            assertEquals("", decoded.name());
            assertEquals(1, decoded.tag().getInt("x"));
        }

        @Test
        void truncatedInputIsRejected() {
            byte[] full = helloWorldBytes();
            byte[] truncated = Arrays.copyOf(full, full.length - 3);

            assertEquals(ErrorCode.MALFORMED_DATA,
                    codeOf(() -> NbtIo.readBytes(truncated, uncompressedRead())));
        }

        @Test
        void hugeDeclaredLengthIsRejectedBeforeAllocating() {
            // ルート直下に「長さ 0x7FFFFFFF の ByteArray」を宣言するだけの入力
            byte[] data = {
                0x0A, 0x00, 0x00,
                0x07, 0x00, 0x01, 0x61,
                0x7F, (byte) 0xFF, (byte) 0xFF, (byte) 0xFF,
            };

            assertEquals(ErrorCode.MALFORMED_DATA,
                    codeOf(() -> NbtIo.readBytes(data, uncompressedRead())));
        }

        @Test
        void unknownTagIdIsRejected() {
            byte[] data = { 0x0A, 0x00, 0x00, 0x0D };

            assertEquals(ErrorCode.MALFORMED_DATA,
                    codeOf(() -> NbtIo.readBytes(data, uncompressedRead())));
        }

        @Test
        void excessiveNestingIsRejected() {
            byte[] encoded = buildNestedCompound(600);

            assertEquals(ErrorCode.LIMIT_EXCEEDED,
                    codeOf(() -> NbtIo.readBytes(encoded, uncompressedRead())));

            // 上限を上げれば読める
            NbtIo.readBytes(encoded, uncompressedRead().setMaxDepth(1000));
        }

        @Test
        void trailingBytesAfterRootAreRejected() {
            byte[] full = helloWorldBytes();
            byte[] extended = Arrays.copyOf(full, full.length + 1);
            extended[full.length] = (byte) 0xFF;

            assertEquals(ErrorCode.MALFORMED_DATA,
                    codeOf(() -> NbtIo.readBytes(extended, uncompressedRead())));
        }

        @Test
        void writeRejectsAutoCompression() {
            NamedTag named = new NamedTag("", new NbtCompound());
            NbtWriteOptions options = NbtWriteOptions.defaults().setCompression(Compression.AUTO);

            assertEquals(ErrorCode.INVALID_ARGUMENT,
                    codeOf(() -> NbtIo.writeBytes(named, options)));
        }

        @Test
        void listKeepsElementTypeAfterClear() {
            NbtList list = new NbtList();
            list.add(new NbtInt(1));
            list.clear();

            // 全要素を削除しても確定済みの要素型は維持する
            assertEquals(TagType.INT, list.elementType());
            assertFalse(list.iterator().hasNext());
        }

        @Test
        void loneSurrogateKeyIsRejected() {
            // 値と違い、キーには孤立サロゲートを許さない（仕様 10 の 2.2章）
            byte[] data = {
                0x0A, 0x00, 0x00,
                0x03, 0x00, 0x03, (byte) 0xED, (byte) 0xA0, (byte) 0xBD,
                0x00, 0x00, 0x00, 0x01,
                0x00,
            };

            assertEquals(ErrorCode.MALFORMED_DATA,
                    codeOf(() -> NbtIo.readBytes(data, uncompressedRead())));
        }
    }

    @Nested
    @DisplayName("SNBT")
    class SnbtTest {

        @ParameterizedTest
        @CsvSource({
            "1b, BYTE",
            "1s, SHORT",
            "1, INT",
            "1L, LONG",
            "1.0f, FLOAT",
            "1.0, DOUBLE",
            "1.0d, DOUBLE",
            "true, BYTE",
            "false, BYTE",
            "hello, STRING",
        })
        void suffixDecidesType(String source, TagType expected) {
            assertEquals(expected, Snbt.parse(source).type());
        }

        @Test
        void hexSuffixRuleIsFixed() {
            // 仕様 11 の 2.1: 16進では b/d/f を数字として読む。幅接尾辞は s/l のみ
            assertEquals(new NbtInt(255), Snbt.parse("0xFF"));
            assertEquals(new NbtInt(4091), Snbt.parse("0xFFb"));
            assertEquals(new NbtLong(255), Snbt.parse("0xFFl"));
            assertEquals(new NbtShort((short) 255), Snbt.parse("0xFFs"));
        }

        @Test
        void zeroByteLiteralIsNotBinary() {
            // 0b は「10進の 0 に Byte 接尾辞」。真偽値の false として広く使われる形
            assertEquals(new NbtByte((byte) 0), Snbt.parse("0b"));
            assertEquals(new NbtInt(1), Snbt.parse("0b1"));
            assertEquals(new NbtByte((byte) 9), Snbt.parse("0b1001b"));
        }

        @Test
        void extendedIntegerLiterals() {
            assertEquals(new NbtInt(16), Snbt.parse("0x10"));
            assertEquals(new NbtInt(9), Snbt.parse("0b1001"));
            assertEquals(new NbtInt(123456), Snbt.parse("123_456"));
            assertEquals(new NbtInt(7), Snbt.parse("+7"));
            assertEquals(new NbtInt(-7), Snbt.parse("-7"));
        }

        @Test
        void unsignedSuffixWrapsToSigned() {
            assertEquals(new NbtByte((byte) -1), Snbt.parse("255ub"));
            assertEquals(new NbtShort((short) -1), Snbt.parse("65535us"));
            assertEquals(ErrorCode.MALFORMED_DATA, codeOf(() -> Snbt.parse("256ub")));
        }

        @Test
        void suffixlessIntegerIsNotPromotedToLong() {
            assertEquals(ErrorCode.MALFORMED_DATA, codeOf(() -> Snbt.parse("2147483648")));
            assertEquals(new NbtLong(2147483648L), Snbt.parse("2147483648L"));
        }

        @Test
        void typedArrays() {
            assertEquals(new NbtByteArray(new byte[] { 1, 2 }), Snbt.parse("[B; 1b, 2b]"));
            assertEquals(new NbtIntArray(new int[] { 1, 2 }), Snbt.parse("[I; 1, 2]"));
            assertEquals(new NbtLongArray(new long[] { 1, 2 }), Snbt.parse("[L; 1L, 2L]"));

            // 接尾辞なしでも範囲内なら受理する（Minecraft 自身がそう書き出すため）
            assertEquals(new NbtByteArray(new byte[] { 1, 2 }), Snbt.parse("[B; 1, 2]"));
            assertEquals(ErrorCode.MALFORMED_DATA, codeOf(() -> Snbt.parse("[B; 200]")));
        }

        @Test
        void trailingCommasAreAllowed() {
            assertEquals(2, Snbt.parseCompound("{a:1,b:2,}").size());
            assertEquals(2, ((NbtList) Snbt.parse("[1,2,]")).size());
        }

        @Test
        void heterogeneousListIsRejected() {
            // 異種リストはバイナリ NBT へ写せないため受理しない (adr/0006)
            assertEquals(ErrorCode.MALFORMED_DATA, codeOf(() -> Snbt.parse("[1, \"a\"]")));
        }

        @Test
        void escapeSequences() {
            assertEquals(new NbtString("\n"), Snbt.parse("\"\\n\""));
            assertEquals(new NbtString("B"), Snbt.parse("\"\\x42\""));
            assertEquals(new NbtString("H"), Snbt.parse("\"\\u0048\""));
            assertEquals(new NbtString(" "), Snbt.parse("\"\\s\""));
            assertEquals(new NbtString("\uD83D\uDE00"), Snbt.parse("\"\\U0001F600\""));
            assertEquals(ErrorCode.UNSUPPORTED_FEATURE,
                    codeOf(() -> Snbt.parse("\"\\N{SNOWMAN}\"")));
        }

        @Test
        void singleQuotedStringsWork() {
            assertEquals(new NbtString("say \"hi\""), Snbt.parse("'say \"hi\"'"));
        }

        @Test
        void functions() {
            assertEquals(new NbtByte((byte) 1), Snbt.parse("bool(5)"));
            assertEquals(new NbtByte((byte) 0), Snbt.parse("bool(0)"));
            assertEquals(
                    new NbtIntArray(new int[] { 0x00112233, 0x44556677, 0x8899AABB, 0xCCDDEEFF }),
                    Snbt.parse("uuid(\"00112233-4455-6677-8899-aabbccddeeff\")"));
        }

        @Test
        void snbtToNbtToSnbtToNbtIsStable() {
            // 仕様 11 の 5章: 保証するのは「SNBT -> NBT -> SNBT -> NBT」で NBT が一致すること
            String source = "{ name : 'Bananrama' , list : [ 1L , 2L ] , nested : { flag : true } , "
                    + "bytes : [B; 1b, -2b] , ratio : 0.5f }";

            NbtTag first = Snbt.parse(source);
            assertEquals(first, Snbt.parse(Snbt.write(first)));
            assertEquals(first, Snbt.parse(Snbt.writePretty(first)));
        }

        @Test
        void writeUsesBareKeysWhenPossible() {
            NbtCompound compound = new NbtCompound();
            compound.set("plain", new NbtInt(1));
            compound.set("needs quote", new NbtInt(2));

            assertEquals("{plain:1,\"needs quote\":2}", Snbt.write(compound));
        }

        @Test
        void writePrettyIndentsWithFourSpaces() {
            NbtCompound nested = new NbtCompound();
            nested.set("x", new NbtInt(1));
            NbtCompound compound = new NbtCompound();
            compound.set("inner", nested);

            assertEquals("{\n    inner: {\n        x: 1\n    }\n}", Snbt.writePretty(compound));
        }

        @Test
        void trailingGarbageIsRejected() {
            assertEquals(ErrorCode.MALFORMED_DATA, codeOf(() -> Snbt.parse("{a:1} junk")));
            assertEquals(ErrorCode.UNEXPECTED_TAG_TYPE, codeOf(() -> Snbt.parseCompound("42")));
        }
    }

    @Nested
    @DisplayName("浮動小数点の正準10進表記")
    class CanonicalDecimalTest {

        @ParameterizedTest
        @CsvSource({
            "1.0, 1.0f",
            "-1.0, -1.0f",
            "0.0, 0.0f",
            "0.75, 0.75f",
            "0.49823147, 0.49823147f",
            "2000.0, 2000.0f",
            "1e20, 1.0E20f",
            "1e-30, 1.0E-30f",
            "0.5, 0.5f",
            "123.456, 123.456f",
        })
        void floatFormatting(float value, String expected) {
            assertEquals(expected, Snbt.write(new NbtFloat(value)));
        }

        @ParameterizedTest
        @CsvSource({
            "1.0, 1.0d",
            "0.015, 0.015d",
            "2000.0, 2000.0d",
            "0.4931287132182315, 0.4931287132182315d",
            "3.141592653589793, 3.141592653589793d",
            "1e20, 1.0E20d",
            "1e17, 1.0E17d",
            "1e16, 10000000000000000.0d",
            "1e-4, 0.0001d",
            "1e-5, 1.0E-5d",
        })
        void doubleFormatting(double value, String expected) {
            assertEquals(expected, Snbt.write(new NbtDouble(value)));
        }

        @Test
        void negativeZeroKeepsItsSign() {
            assertEquals("-0.0d", Snbt.write(new NbtDouble(-0.0)));
            assertEquals("-0.0f", Snbt.write(new NbtFloat(-0.0f)));
        }

        @Test
        void specialValues() {
            assertEquals("NaNd", Snbt.write(new NbtDouble(Double.NaN)));
            assertEquals("Infinityd", Snbt.write(new NbtDouble(Double.POSITIVE_INFINITY)));
            assertEquals("-Infinityd", Snbt.write(new NbtDouble(Double.NEGATIVE_INFINITY)));
            assertEquals("NaNf", Snbt.write(new NbtFloat(Float.NaN)));
        }

        @Test
        void everyFormattedValueParsesBackToTheSameBits() {
            double[] doubles = {
                0.0, -0.0, 1.0, -1.0, 0.1, 1.0 / 3.0, 1e300, 1e-300,
                Double.MIN_VALUE, Double.MAX_VALUE, 4903.0,
            };

            // 出力した文字列を読み戻して、ビットパターンが変わらないことを確かめる
            for (double value : doubles) {
                NbtDouble parsed = (NbtDouble) Snbt.parse(Snbt.write(new NbtDouble(value)));
                assertEquals(Double.doubleToRawLongBits(value),
                        Double.doubleToRawLongBits(parsed.value()), Double.toString(value));
            }

            float[] floats = {
                0.0f, -0.0f, 1.0f, -1.0f, 0.1f, 1.0f / 3.0f, 1e30f, 1e-30f,
                Float.MIN_VALUE, Float.MAX_VALUE, 4903.0f,
            };

            for (float value : floats) {
                NbtFloat parsed = (NbtFloat) Snbt.parse(Snbt.write(new NbtFloat(value)));
                assertEquals(Float.floatToRawIntBits(value),
                        Float.floatToRawIntBits(parsed.value()), Float.toString(value));
            }
        }
    }

    /** 全13タグ型を含む Compound を作る。 */
    private static NbtCompound buildAllTags() {
        NbtCompound root = new NbtCompound();
        root.set("byte", new NbtByte((byte) -128));
        root.set("short", new NbtShort((short) 32767));
        root.set("int", new NbtInt(-2147483648));
        root.set("long", new NbtLong(9223372036854775807L));
        root.set("float", new NbtFloat(0.49823147f));
        root.set("double", new NbtDouble(0.4931287132182315));
        root.set("byte_array", new NbtByteArray(new byte[] { -128, 0, 127 }));
        root.set("string", new NbtString("\u3042\u3044\u3046"));
        root.set("int_array", new NbtIntArray(new int[] { -2147483648, 0, 2147483647 }));
        root.set("long_array", new NbtLongArray(
                new long[] { Long.MIN_VALUE, 0L, Long.MAX_VALUE }));

        NbtList list = new NbtList(TagType.LONG);
        list.add(new NbtLong(11));
        list.add(new NbtLong(12));
        root.set("list", list);

        NbtCompound nested = new NbtCompound();
        nested.set("name", new NbtString("Hampus"));
        nested.set("value", new NbtFloat(0.75f));
        root.set("compound", nested);

        return root;
    }

    /** 指定した深さまで Compound を入れ子にしたバイト列を作る。 */
    private static byte[] buildNestedCompound(int depth) {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        out.write(0x0A);
        out.write(0x00);
        out.write(0x00);

        // ルート + (depth - 1) 段の入れ子
        for (int index = 0; index < depth - 1; index++) {
            out.write(0x0A);
            out.write(0x00);
            out.write(0x01);
            out.write('c');
        }

        // 内側から順に終端する
        for (int index = 0; index < depth; index++) {
            out.write(0x00);
        }

        return out.toByteArray();
    }
}

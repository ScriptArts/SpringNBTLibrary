using SpringNBTLibrary.Nbt;

namespace SpringNBTLibrary.Tests;

/// <summary>SNBT のパースと出力。仕様: docs/spec/11-snbt.md</summary>
public class SnbtTests
{
    [Theory]
    [InlineData("1b", TagType.Byte)]
    [InlineData("1s", TagType.Short)]
    [InlineData("1", TagType.Int)]
    [InlineData("1L", TagType.Long)]
    [InlineData("1.0f", TagType.Float)]
    [InlineData("1.0", TagType.Double)]
    [InlineData("1.0d", TagType.Double)]
    [InlineData("true", TagType.Byte)]
    [InlineData("false", TagType.Byte)]
    [InlineData("hello", TagType.String)]
    [InlineData("\"hello\"", TagType.String)]
    public void SuffixDecidesType(string source, TagType expected)
    {
        Assert.Equal(expected, Snbt.Parse(source).Type);
    }

    [Fact]
    public void BooleanLiteralsBecomeBytes()
    {
        Assert.Equal(new NbtByte(1), Snbt.Parse("true"));
        Assert.Equal(new NbtByte(0), Snbt.Parse("false"));
    }

    [Theory]
    [InlineData("0x10", 16)]
    [InlineData("0b1001", 9)]
    [InlineData("123_456", 123456)]
    [InlineData("+7", 7)]
    [InlineData("-7", -7)]
    public void ExtendedIntegerLiterals(string source, int expected)
    {
        Assert.Equal(new NbtInt(expected), Snbt.Parse(source));
    }

    [Fact]
    public void HexSuffixRuleIsFixed()
    {
        // 仕様 11 の 2.1: 16進では b/d/f を数字として読む。幅接尾辞は s/l のみ
        Assert.Equal(new NbtInt(255), Snbt.Parse("0xFF"));
        Assert.Equal(new NbtInt(4091), Snbt.Parse("0xFFb"));
        Assert.Equal(new NbtLong(255), Snbt.Parse("0xFFl"));
        Assert.Equal(new NbtShort(255), Snbt.Parse("0xFFs"));
    }

    [Fact]
    public void ZeroByteLiteralIsNotBinary()
    {
        // 0b は「10進の 0 に Byte 接尾辞」。真偽値の false として広く使われる形
        Assert.Equal(new NbtByte(0), Snbt.Parse("0b"));
        Assert.Equal(new NbtByte(1), Snbt.Parse("1b"));

        // 2進数字が続く場合だけ 2 進リテラルになる
        Assert.Equal(new NbtInt(1), Snbt.Parse("0b1"));
        Assert.Equal(new NbtByte(9), Snbt.Parse("0b1001b"));
    }

    [Fact]
    public void UnsignedSuffixWrapsToSigned()
    {
        // 255ub は符号なし 255 として読み、Byte へは -1 として格納される
        Assert.Equal(new NbtByte(-1), Snbt.Parse("255ub"));
        Assert.Equal(new NbtShort(-1), Snbt.Parse("65535us"));
    }

    [Fact]
    public void UnsignedOverflowIsRejected()
    {
        SpringNbtException error = Assert.Throws<SpringNbtException>(() => Snbt.Parse("256ub"));
        Assert.Equal(ErrorCode.MalformedData, error.Code);
    }

    [Fact]
    public void SuffixlessIntegerIsNotPromotedToLong()
    {
        // Int の範囲を超える接尾辞なし整数は、暗黙に Long へ格上げせずエラーにする
        SpringNbtException error = Assert.Throws<SpringNbtException>(() => Snbt.Parse("2147483648"));
        Assert.Equal(ErrorCode.MalformedData, error.Code);

        Assert.Equal(new NbtLong(2147483648L), Snbt.Parse("2147483648L"));
    }

    [Theory]
    [InlineData(".5", 0.5)]
    [InlineData("2e3", 2000.0)]
    [InlineData("1.5e-2", 0.015)]
    public void FreeformFloatLiterals(string source, double expected)
    {
        NbtDouble parsed = Assert.IsType<NbtDouble>(Snbt.Parse(source));
        Assert.Equal(expected, parsed.Value, 12);
    }

    [Fact]
    public void SpecialFloatingValues()
    {
        Assert.True(double.IsPositiveInfinity(Assert.IsType<NbtDouble>(Snbt.Parse("Infinity")).Value));
        Assert.True(double.IsNegativeInfinity(Assert.IsType<NbtDouble>(Snbt.Parse("-Infinity")).Value));
        Assert.True(double.IsNaN(Assert.IsType<NbtDouble>(Snbt.Parse("NaN")).Value));
        Assert.True(float.IsPositiveInfinity(Assert.IsType<NbtFloat>(Snbt.Parse("Infinityf")).Value));
    }

    [Fact]
    public void TypedArrays()
    {
        Assert.Equal(new NbtByteArray(new sbyte[] { 1, 2 }), Snbt.Parse("[B; 1b, 2b]"));
        Assert.Equal(new NbtIntArray(new[] { 1, 2 }), Snbt.Parse("[I; 1, 2]"));
        Assert.Equal(new NbtLongArray(new[] { 1L, 2L }), Snbt.Parse("[L; 1L, 2L]"));

        // 接尾辞なしでも範囲内なら受理する（Minecraft 自身がそう書き出すため）
        Assert.Equal(new NbtByteArray(new sbyte[] { 1, 2 }), Snbt.Parse("[B; 1, 2]"));
    }

    [Fact]
    public void TypedArrayRangeIsChecked()
    {
        SpringNbtException error = Assert.Throws<SpringNbtException>(() => Snbt.Parse("[B; 200]"));
        Assert.Equal(ErrorCode.MalformedData, error.Code);
    }

    [Fact]
    public void TrailingCommasAreAllowed()
    {
        NbtCompound compound = Snbt.ParseCompound("{a:1,b:2,}");
        Assert.Equal(2, compound.Count);

        NbtList list = Assert.IsType<NbtList>(Snbt.Parse("[1,2,]"));
        Assert.Equal(2, list.Count);
    }

    [Fact]
    public void HeterogeneousListIsRejected()
    {
        // 異種リストはバイナリ NBT へ写せないため受理しない (adr/0006)
        SpringNbtException error = Assert.Throws<SpringNbtException>(() => Snbt.Parse("[1, \"a\"]"));
        Assert.Equal(ErrorCode.MalformedData, error.Code);
    }

    [Fact]
    public void EscapeSequences()
    {
        Assert.Equal("\n", Assert.IsType<NbtString>(Snbt.Parse("\"\\n\"")).Value);
        Assert.Equal("B", Assert.IsType<NbtString>(Snbt.Parse("\"\\x42\"")).Value);
        Assert.Equal("H", Assert.IsType<NbtString>(Snbt.Parse("\"\\u0048\"")).Value);
        Assert.Equal(" ", Assert.IsType<NbtString>(Snbt.Parse("\"\\s\"")).Value);
        Assert.Equal("\U0001F600", Assert.IsType<NbtString>(Snbt.Parse("\"\\U0001F600\"")).Value);
    }

    [Fact]
    public void NamedCharacterEscapeIsUnsupported()
    {
        SpringNbtException error = Assert.Throws<SpringNbtException>(
            () => Snbt.Parse("\"\\N{SNOWMAN}\""));
        Assert.Equal(ErrorCode.UnsupportedFeature, error.Code);
    }

    [Fact]
    public void SingleQuotedStringsWork()
    {
        Assert.Equal("say \"hi\"", Assert.IsType<NbtString>(Snbt.Parse("'say \"hi\"'")).Value);
    }

    [Fact]
    public void BoolFunction()
    {
        Assert.Equal(new NbtByte(1), Snbt.Parse("bool(5)"));
        Assert.Equal(new NbtByte(0), Snbt.Parse("bool(0)"));
    }

    [Fact]
    public void UuidFunction()
    {
        NbtIntArray parsed = Assert.IsType<NbtIntArray>(
            Snbt.Parse("uuid(\"00112233-4455-6677-8899-aabbccddeeff\")"));

        Assert.Equal(
            new[] { 0x00112233, 0x44556677, unchecked((int)0x8899AABB), unchecked((int)0xCCDDEEFF) },
            parsed.Value);
    }

    [Fact]
    public void SnbtToNbtToSnbtToNbtIsStable()
    {
        // 仕様 11 の 5章: 保証するのは「SNBT -> NBT -> SNBT -> NBT」で NBT が一致すること
        string source = "{ name : 'Bananrama' , list : [ 1L , 2L ] , nested : { flag : true } , "
            + "bytes : [B; 1b, -2b] , ratio : 0.5f }";

        NbtTag first = Snbt.Parse(source);
        NbtTag second = Snbt.Parse(Snbt.Write(first));

        Assert.Equal(first, second);

        // 整形出力からも同じ NBT が得られること
        NbtTag third = Snbt.Parse(Snbt.WritePretty(first));
        Assert.Equal(first, third);
    }

    [Fact]
    public void WriteUsesBareKeysWhenPossible()
    {
        NbtCompound compound = new NbtCompound();
        compound.Set("plain", new NbtInt(1));
        compound.Set("needs quote", new NbtInt(2));

        Assert.Equal("{plain:1,\"needs quote\":2}", Snbt.Write(compound));
    }

    [Fact]
    public void WritePrettyIndentsWithFourSpaces()
    {
        NbtCompound compound = new NbtCompound();
        NbtCompound nested = new NbtCompound();
        nested.Set("x", new NbtInt(1));
        compound.Set("inner", nested);

        string expected = "{\n    inner: {\n        x: 1\n    }\n}";
        Assert.Equal(expected, Snbt.WritePretty(compound));
    }

    [Fact]
    public void TrailingGarbageIsRejected()
    {
        SpringNbtException error = Assert.Throws<SpringNbtException>(() => Snbt.Parse("{a:1} junk"));
        Assert.Equal(ErrorCode.MalformedData, error.Code);
    }

    [Fact]
    public void ParseCompoundRejectsNonCompoundRoot()
    {
        SpringNbtException error = Assert.Throws<SpringNbtException>(() => Snbt.ParseCompound("42"));
        Assert.Equal(ErrorCode.UnexpectedTagType, error.Code);
    }

    [Fact]
    public void RoundtripThroughBinaryAndSnbtAgree()
    {
        NbtCompound root = new NbtCompound();
        root.Set("byte", new NbtByte(-128));
        root.Set("short", new NbtShort(32767));
        root.Set("int", new NbtInt(-2147483648));
        root.Set("long", new NbtLong(9223372036854775807L));
        root.Set("float", new NbtFloat(0.49823147f));
        root.Set("double", new NbtDouble(0.4931287132182315));
        root.Set("string", new NbtString("あいう"));
        root.Set("byte_array", new NbtByteArray(new sbyte[] { -128, 0, 127 }));
        root.Set("int_array", new NbtIntArray(new[] { -1, 0, 1 }));
        root.Set("long_array", new NbtLongArray(new[] { -1L, 0L, 1L }));

        NbtTag reparsed = Snbt.Parse(Snbt.Write(root));
        Assert.Equal(root, reparsed);
    }
}

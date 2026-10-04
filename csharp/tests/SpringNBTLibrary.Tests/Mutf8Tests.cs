using SpringNBTLibrary.Nbt;

namespace SpringNBTLibrary.Tests;

/// <summary>
/// MUTF-8の符号化・復号
/// </summary>
public class Mutf8Tests
{
    [Fact]
    public void AsciiRoundtrip()
    {
        byte[] bytes = Mutf8.Encode("Bananrama");
        Assert.Equal("Bananrama"u8.ToArray(), bytes);
        Assert.Equal("Bananrama", Mutf8.Decode(bytes));
    }

    [Fact]
    public void NulIsTwoBytes()
    {
        // U+0000は1バイトの0x00ではなく、C0 80で表す
        string sample = "a\u0000b";
        byte[] bytes = Mutf8.Encode(sample);
        Assert.Equal(new byte[] { 0x61, 0xC0, 0x80, 0x62 }, bytes);
        Assert.Equal(sample, Mutf8.Decode(bytes));
    }

    [Fact]
    public void SupplementaryCharIsCesu8()
    {
        // U+1F600はUTF-16でD83D DE00、MUTF-8では3バイト × 2になる
        string sample = "\U0001F600";
        byte[] bytes = Mutf8.Encode(sample);
        Assert.Equal(new byte[] { 0xED, 0xA0, 0xBD, 0xED, 0xB8, 0x80 }, bytes);
        Assert.Equal(sample, Mutf8.Decode(bytes));
    }

    [Fact]
    public void LoneSurrogateSurvivesRoundtrip()
    {
        // 対にならない上位サロゲートはUTF-8には写せないが、MUTF-8では往復できる
        string lone = "\ud83d";
        byte[] bytes = Mutf8.Encode(lone);
        Assert.Equal(new byte[] { 0xED, 0xA0, 0xBD }, bytes);
        Assert.Equal(lone, Mutf8.Decode(bytes));
    }

    [Fact]
    public void RawNulIsRejected()
    {
        SpringNbtException error = Assert.Throws<SpringNbtException>(
            () => Mutf8.Decode(new byte[] { 0x00 }));
        Assert.Equal(ErrorCode.MalformedData, error.Code);
    }

    [Fact]
    public void OverlongTwoByteIsRejected()
    {
        // U+0041を2バイトで表した冗長符号化
        SpringNbtException error = Assert.Throws<SpringNbtException>(
            () => Mutf8.Decode(new byte[] { 0xC1, 0x81 }));
        Assert.Equal(ErrorCode.MalformedData, error.Code);
    }

    [Fact]
    public void FourByteUtf8IsRejected()
    {
        // 標準UTF-8の4バイト形式はMUTF-8では不正
        SpringNbtException error = Assert.Throws<SpringNbtException>(
            () => Mutf8.Decode(new byte[] { 0xF0, 0x9F, 0x98, 0x80 }));
        Assert.Equal(ErrorCode.MalformedData, error.Code);
    }

    [Fact]
    public void TruncatedInputIsRejected()
    {
        SpringNbtException error = Assert.Throws<SpringNbtException>(
            () => Mutf8.Decode(new byte[] { 0xE3, 0x81 }));
        Assert.Equal(ErrorCode.MalformedData, error.Code);
    }

    [Fact]
    public void ByteLengthMatchesEncodedLength()
    {
        string sample = "abcあ\U0001F600";
        Assert.Equal(Mutf8.Encode(sample).Length, Mutf8.ByteLength(sample));
    }
}

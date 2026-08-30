using SpringNBTLibrary.Nbt;

namespace SpringNBTLibrary.Tests;

/// <summary>
/// NBT のバイナリ読み書き。仕様: docs/spec/10-nbt-binary.md
/// </summary>
/// <remarks>
/// ここで使うバイト列は仕様書の記述だけを根拠に手で組み立てている。
/// 実装が生成した値を期待値にすると、実装のバグをそのまま正としてしまうため。
/// </remarks>
public class NbtIoTests
{
    [Fact]
    public void ReadsConcatenatedNbtOneByOne()
    {
        byte[] joined = Concat(HelloWorldBytes(), HelloWorldBytes(), HelloWorldBytes());

        int offset = 0;
        int count = 0;

        // 直前の終了位置を次の開始位置にして読み進める
        while (offset < joined.Length)
        {
            NbtReadResult result = NbtIo.ReadBytesAt(joined, offset, UncompressedRead());
            Assert.Equal("hello world", result.Tag.Name);
            Assert.Equal("Bananrama", ((NbtCompound)result.Tag.Tag).GetString("name"));
            offset = result.End;
            count++;
        }

        Assert.Equal(3, count);
        Assert.Equal(joined.Length, offset);
    }

    [Fact]
    public void ReadsEveryConcatenatedNbtAtOnce()
    {
        byte[] joined = Concat(HelloWorldBytes(), HelloWorldBytes());
        IReadOnlyList<NamedTag> tags = NbtIo.ReadBytesAll(joined, UncompressedRead());

        Assert.Equal(2, tags.Count);
        Assert.Equal("hello world", tags[0].Name);
        Assert.Equal("hello world", tags[1].Name);
    }

    [Fact]
    public void ReadsNothingFromEmptyInput()
    {
        Assert.Empty(NbtIo.ReadBytesAll(Array.Empty<byte>(), UncompressedRead()));
    }

    [Fact]
    public void RejectsOffsetOutOfRange()
    {
        byte[] bytes = HelloWorldBytes();

        SpringNbtException error = Assert.Throws<SpringNbtException>(
            () => NbtIo.ReadBytesAt(bytes, bytes.Length + 1, UncompressedRead()));
        Assert.Equal(ErrorCode.InvalidArgument, error.Code);
    }

    [Fact]
    public void RejectsCompressionWhenReadingAtOffset()
    {
        byte[] bytes = HelloWorldBytes();
        NbtReadOptions options = new NbtReadOptions { Compression = Compression.Gzip };

        SpringNbtException error = Assert.Throws<SpringNbtException>(
            () => NbtIo.ReadBytesAt(bytes, 0, options));
        Assert.Equal(ErrorCode.InvalidArgument, error.Code);
    }

    [Fact]
    public void TypedSettersMirrorTheGetters()
    {
        NbtCompound root = new NbtCompound();
        root.SetByte("b", -128);
        root.SetShort("s", 32767);
        root.SetInt("i", -2147483648);
        root.SetLong("l", 9223372036854775807L);
        root.SetFloat("f", 1.5f);
        root.SetDouble("d", -2.25);
        root.SetBool("t", true);
        root.SetBool("n", false);
        root.SetString("str", "Bananrama");
        root.SetByteArray("ba", new sbyte[] { 1, -1 });
        root.SetIntArray("ia", new int[] { 1, -1 });
        root.SetLongArray("la", new long[] { 1L, -1L });

        Assert.Equal(-128, root.GetByte("b"));
        Assert.Equal(32767, root.GetShort("s"));
        Assert.Equal(-2147483648, root.GetInt("i"));
        Assert.Equal(9223372036854775807L, root.GetLong("l"));
        Assert.Equal(1.5f, root.GetFloat("f"));
        Assert.Equal(-2.25, root.GetDouble("d"));
        Assert.True(root.GetBool("t"));
        Assert.False(root.GetBool("n"));
        Assert.Equal("Bananrama", root.GetString("str"));
        Assert.Equal(new sbyte[] { 1, -1 }, root.GetByteArray("ba"));
        Assert.Equal(new int[] { 1, -1 }, root.GetIntArray("ia"));
        Assert.Equal(new long[] { 1L, -1L }, root.GetLongArray("la"));

        // 真偽値は TAG_Byte の 0 / 1 として入る
        Assert.Equal(TagType.Byte, root.Get("t").Type);
    }

    [Fact]
    public void TypedSettersKeepTheInsertionOrder()
    {
        NbtCompound root = new NbtCompound();
        root.SetInt("a", 1);
        root.SetInt("b", 2);

        // 既存キーへの再設定は位置を変えない
        root.SetInt("a", 3);

        Assert.Equal(new[] { "a", "b" }, root.Select(entry => entry.Key).ToArray());
        Assert.Equal(3, root.GetInt("a"));
    }

    /// <summary>複数のバイト列をつなぐ。</summary>
    private static byte[] Concat(params byte[][] parts)
    {
        List<byte> joined = new List<byte>();

        // 与えられた順にそのままつなぐ
        foreach (byte[] part in parts)
        {
            joined.AddRange(part);
        }

        return joined.ToArray();
    }

    /// <summary>
    /// 仕様書どおりに組んだ最小の NBT。
    /// ルート名 "hello world" の Compound に、文字列 "Bananrama" が入っている。
    /// </summary>
    private static byte[] HelloWorldBytes()
    {
        List<byte> bytes = new List<byte>();

        // ルート: TAG_Compound、名前 "hello world"
        bytes.Add(0x0A);
        bytes.AddRange(new byte[] { 0x00, 0x0B });
        bytes.AddRange("hello world"u8.ToArray());

        // 子: TAG_String、名前 "name"、値 "Bananrama"
        bytes.Add(0x08);
        bytes.AddRange(new byte[] { 0x00, 0x04 });
        bytes.AddRange("name"u8.ToArray());
        bytes.AddRange(new byte[] { 0x00, 0x09 });
        bytes.AddRange("Bananrama"u8.ToArray());

        // ルートの終端
        bytes.Add(0x00);

        return bytes.ToArray();
    }

    [Fact]
    public void ReadsHandBuiltHelloWorld()
    {
        NamedTag named = NbtIo.ReadBytes(HelloWorldBytes(), UncompressedRead());

        Assert.Equal("hello world", named.Name);
        Assert.Equal(1, named.Tag.Count);
        Assert.Equal("Bananrama", named.Tag.GetString("name"));
    }

    [Fact]
    public void WritesBackTheSameBytes()
    {
        byte[] original = HelloWorldBytes();
        NamedTag named = NbtIo.ReadBytes(original, UncompressedRead());
        byte[] rewritten = NbtIo.WriteBytes(named, NbtWriteOptions.Uncompressed);

        Assert.Equal(original, rewritten);
    }

    [Fact]
    public void AllThirteenTagTypesRoundtrip()
    {
        NbtCompound root = BuildAllTagsCompound();
        NamedTag named = new NamedTag(string.Empty, root);

        byte[] encoded = NbtIo.WriteBytes(named, NbtWriteOptions.Uncompressed);
        NamedTag decoded = NbtIo.ReadBytes(encoded, UncompressedRead());

        Assert.Equal(root, decoded.Tag);

        // 一度往復させた結果をもう一度書いてもバイトが変わらないこと
        byte[] again = NbtIo.WriteBytes(decoded, NbtWriteOptions.Uncompressed);
        Assert.Equal(encoded, again);
    }

    [Fact]
    public void FloatSpecialsKeepTheirBitPattern()
    {
        NbtCompound root = new NbtCompound();
        root.Set("negative_zero", new NbtDouble(-0.0));
        root.Set("nan", new NbtFloat(float.NaN));
        root.Set("infinity", new NbtDouble(double.PositiveInfinity));
        root.Set("negative_infinity", new NbtFloat(float.NegativeInfinity));

        byte[] encoded = NbtIo.WriteBytes(new NamedTag(string.Empty, root), NbtWriteOptions.Uncompressed);
        NbtCompound decoded = NbtIo.ReadBytes(encoded, UncompressedRead()).Tag;

        // -0.0 と +0.0 は == では区別できないので、ビットパターンで比較する
        Assert.Equal(
            BitConverter.DoubleToInt64Bits(-0.0),
            BitConverter.DoubleToInt64Bits(decoded.GetDouble("negative_zero")));
        Assert.True(float.IsNaN(decoded.GetFloat("nan")));
        Assert.True(double.IsPositiveInfinity(decoded.GetDouble("infinity")));
        Assert.True(float.IsNegativeInfinity(decoded.GetFloat("negative_infinity")));
    }

    [Fact]
    public void CompoundKeepsInsertionOrder()
    {
        NbtCompound root = new NbtCompound();
        root.Set("zebra", new NbtInt(1));
        root.Set("apple", new NbtInt(2));
        root.Set("mango", new NbtInt(3));

        // 既存キーへの再設定は位置を変えない
        root.Set("zebra", new NbtInt(9));

        Assert.Equal(new[] { "zebra", "apple", "mango" }, root.Keys.ToArray());

        byte[] encoded = NbtIo.WriteBytes(new NamedTag(string.Empty, root), NbtWriteOptions.Uncompressed);
        NbtCompound decoded = NbtIo.ReadBytes(encoded, UncompressedRead()).Tag;

        Assert.Equal(new[] { "zebra", "apple", "mango" }, decoded.Keys.ToArray());
    }

    [Fact]
    public void EmptyListKeepsElementTypeEnd()
    {
        NbtCompound root = new NbtCompound();
        root.Set("empty", new NbtList());

        byte[] encoded = NbtIo.WriteBytes(new NamedTag(string.Empty, root), NbtWriteOptions.Uncompressed);
        NbtCompound decoded = NbtIo.ReadBytes(encoded, UncompressedRead()).Tag;

        Assert.Equal(TagType.End, decoded.GetList("empty").ElementType);
    }

    [Fact]
    public void ListRejectsMixedTypes()
    {
        NbtList list = new NbtList();
        list.Add(new NbtInt(1));

        SpringNbtException error = Assert.Throws<SpringNbtException>(() => list.Add(new NbtString("x")));
        Assert.Equal(ErrorCode.UnexpectedTagType, error.Code);
    }

    [Fact]
    public void TypedGetterDistinguishesMissingKeyFromWrongType()
    {
        NbtCompound root = new NbtCompound();
        root.Set("value", new NbtString("text"));

        // キーが無い場合は null
        Assert.Null(root.OptInt("missing"));

        // 型が違う場合はキーの有無に関わらず例外
        SpringNbtException error = Assert.Throws<SpringNbtException>(() => root.OptInt("value"));
        Assert.Equal(ErrorCode.UnexpectedTagType, error.Code);

        SpringNbtException missing = Assert.Throws<SpringNbtException>(() => root.GetInt("missing"));
        Assert.Equal(ErrorCode.InvalidArgument, missing.Code);
    }

    [Theory]
    [InlineData(Compression.Gzip)]
    [InlineData(Compression.Zlib)]
    [InlineData(Compression.None)]
    public void CompressionIsDetectedAutomatically(Compression method)
    {
        NamedTag named = NbtIo.ReadBytes(HelloWorldBytes(), UncompressedRead());
        byte[] encoded = NbtIo.WriteBytes(named, new NbtWriteOptions { Compression = method });

        Assert.Equal(method, NbtIo.DetectCompression(encoded));

        // 既定の ReadOptions は Auto なので、方式を指定しなくても読める
        NamedTag decoded = NbtIo.ReadBytes(encoded);
        Assert.Equal("Bananrama", decoded.Tag.GetString("name"));
    }

    [Fact]
    public void NetworkFormatHasNoRootName()
    {
        NbtCompound root = new NbtCompound();
        root.Set("x", new NbtInt(1));

        NbtWriteOptions write = new NbtWriteOptions
        {
            Format = NbtFormat.Network,
            Compression = Compression.None,
        };
        byte[] encoded = NbtIo.WriteBytes(new NamedTag("ignored", root), write);

        // タグID + ペイロード のみで、名前長の 2 バイトが無い
        Assert.Equal(0x0A, encoded[0]);
        Assert.Equal(0x03, encoded[1]);

        NbtReadOptions read = new NbtReadOptions
        {
            Format = NbtFormat.Network,
            Compression = Compression.None,
        };
        NamedTag decoded = NbtIo.ReadBytes(encoded, read);

        Assert.Equal(string.Empty, decoded.Name);
        Assert.Equal(1, decoded.Tag.GetInt("x"));
    }

    [Fact]
    public void TruncatedInputIsRejected()
    {
        byte[] full = HelloWorldBytes();
        byte[] truncated = full.AsSpan(0, full.Length - 3).ToArray();

        SpringNbtException error = Assert.Throws<SpringNbtException>(
            () => NbtIo.ReadBytes(truncated, UncompressedRead()));
        Assert.Equal(ErrorCode.MalformedData, error.Code);
    }

    [Fact]
    public void HugeDeclaredLengthIsRejectedBeforeAllocating()
    {
        // ルート直下に「長さ 0x7FFFFFFF の ByteArray」を宣言するだけの入力
        List<byte> bytes = new List<byte>();
        bytes.Add(0x0A);
        bytes.AddRange(new byte[] { 0x00, 0x00 });
        bytes.Add(0x07);
        bytes.AddRange(new byte[] { 0x00, 0x01 });
        bytes.AddRange("a"u8.ToArray());
        bytes.AddRange(new byte[] { 0x7F, 0xFF, 0xFF, 0xFF });

        SpringNbtException error = Assert.Throws<SpringNbtException>(
            () => NbtIo.ReadBytes(bytes.ToArray(), UncompressedRead()));
        Assert.Equal(ErrorCode.MalformedData, error.Code);
    }

    [Fact]
    public void UnknownTagIdIsRejected()
    {
        List<byte> bytes = new List<byte>();
        bytes.Add(0x0A);
        bytes.AddRange(new byte[] { 0x00, 0x00 });
        bytes.Add(0x0D);

        SpringNbtException error = Assert.Throws<SpringNbtException>(
            () => NbtIo.ReadBytes(bytes.ToArray(), UncompressedRead()));
        Assert.Equal(ErrorCode.MalformedData, error.Code);
    }

    [Fact]
    public void ExcessiveNestingIsRejected()
    {
        // 上限を超える深さの Compound を組み立てる
        byte[] encoded = BuildNestedCompound(600);

        NbtReadOptions options = UncompressedRead();
        SpringNbtException error = Assert.Throws<SpringNbtException>(
            () => NbtIo.ReadBytes(encoded, options));
        Assert.Equal(ErrorCode.LimitExceeded, error.Code);

        // 上限を上げれば読める
        NbtReadOptions relaxed = UncompressedRead();
        relaxed.MaxDepth = 1000;
        NbtIo.ReadBytes(encoded, relaxed);
    }

    [Fact]
    public void TrailingBytesAfterRootAreRejected()
    {
        List<byte> bytes = new List<byte>(HelloWorldBytes());
        bytes.Add(0xFF);

        SpringNbtException error = Assert.Throws<SpringNbtException>(
            () => NbtIo.ReadBytes(bytes.ToArray(), UncompressedRead()));
        Assert.Equal(ErrorCode.MalformedData, error.Code);
    }

    [Fact]
    public void WriteRejectsAutoCompression()
    {
        NamedTag named = new NamedTag(string.Empty, new NbtCompound());
        NbtWriteOptions options = new NbtWriteOptions { Compression = Compression.Auto };

        SpringNbtException error = Assert.Throws<SpringNbtException>(
            () => NbtIo.WriteBytes(named, options));
        Assert.Equal(ErrorCode.InvalidArgument, error.Code);
    }

    /// <summary>圧縮なしで読むための ReadOptions を作る。</summary>
    private static NbtReadOptions UncompressedRead()
    {
        return new NbtReadOptions { Compression = Compression.None };
    }

    /// <summary>全13タグ型（TAG_End を除く12種 + 入れ子の Compound）を含む Compound を作る。</summary>
    private static NbtCompound BuildAllTagsCompound()
    {
        NbtCompound root = new NbtCompound();
        root.Set("byte", new NbtByte(sbyte.MinValue));
        root.Set("short", new NbtShort(short.MaxValue));
        root.Set("int", new NbtInt(int.MinValue));
        root.Set("long", new NbtLong(long.MaxValue));
        root.Set("float", new NbtFloat(0.49823147f));
        root.Set("double", new NbtDouble(0.4931287132182315));
        root.Set("byte_array", new NbtByteArray(new sbyte[] { -128, 0, 127 }));
        root.Set("string", new NbtString("あいう"));
        root.Set("int_array", new NbtIntArray(new[] { int.MinValue, 0, int.MaxValue }));
        root.Set("long_array", new NbtLongArray(new[] { long.MinValue, 0L, long.MaxValue }));

        NbtList list = new NbtList(TagType.Long);
        list.Add(new NbtLong(11));
        list.Add(new NbtLong(12));
        root.Set("list", list);

        NbtCompound nested = new NbtCompound();
        nested.Set("name", new NbtString("Hampus"));
        nested.Set("value", new NbtFloat(0.75f));
        root.Set("compound", nested);

        return root;
    }

    /// <summary>指定した深さまで Compound を入れ子にしたバイト列を作る。</summary>
    private static byte[] BuildNestedCompound(int depth)
    {
        List<byte> bytes = new List<byte>();

        // ルート + (depth - 1) 段の入れ子
        bytes.Add(0x0A);
        bytes.AddRange(new byte[] { 0x00, 0x00 });

        for (int i = 0; i < depth - 1; i++)
        {
            bytes.Add(0x0A);
            bytes.AddRange(new byte[] { 0x00, 0x01 });
            bytes.AddRange("c"u8.ToArray());
        }

        // 内側から順に終端する
        for (int i = 0; i < depth; i++)
        {
            bytes.Add(0x00);
        }

        return bytes.ToArray();
    }
}

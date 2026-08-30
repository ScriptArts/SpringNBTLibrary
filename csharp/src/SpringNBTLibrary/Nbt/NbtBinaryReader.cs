using System.Buffers.Binary;

namespace SpringNBTLibrary.Nbt;

/// <summary>
/// 展開済みのバイト列から NBT を読み出す
/// </summary>
/// <remarks>
/// <para>
/// 入力全体をあらかじめメモリに持つ設計にしている
/// 「宣言された長さが残り入力長を超えていないか」を確保前に検査できるようにするため
/// これがないと、長さ 0x7FFFFFFF を宣言しただけの数バイトの入力でメモリを枯渇させられる
/// </para>
/// <para>仕様: <c>docs/spec/10-nbt-binary.md</c></para>
/// </remarks>
internal sealed class NbtBinaryReader
{
    private readonly byte[] data;
    private readonly int maxDepth;
    private int position;

    internal NbtBinaryReader(byte[] data, int maxDepth)
        : this(data, maxDepth, 0)
    {
    }

    internal NbtBinaryReader(byte[] data, int maxDepth, int start)
    {
        this.data = data;
        this.maxDepth = maxDepth;
        this.position = start;
    }

    /// <summary>残っている入力バイト数</summary>
    private int Remaining => data.Length - position;

    /// <summary>次に読む位置</summary>
    internal int Position => position;

    /// <summary>まだ読んでいないバイトが残っているか</summary>
    internal bool HasMore => Remaining > 0;

    /// <summary>ルートタグを読み、末尾に余りが無いことを確かめる</summary>
    internal NamedTag ReadRoot(NbtFormat format)
    {
        NamedTag tag = ReadRootTag(format);

        // 末尾に余分なバイトが残っていたら、読み違えている可能性が高い
        if (Remaining != 0)
        {
            throw SpringNbtException.Malformed($"ルートタグの後に {Remaining} バイトの余分な入力がある");
        }

        return tag;
    }

    /// <summary>ルートタグを 1 つ読む
    /// 末尾の余りは見ない</summary>
    internal NamedTag ReadRootTag(NbtFormat format)
    {
        byte id = ReadByteRaw();
        TagType type = TagTypeExtensions.FromId(id);

        // Java版のファイル形式でもネットワーク形式でも、ルートは必ず TAG_Compound
        if (type != TagType.Compound)
        {
            throw SpringNbtException.Malformed(
                $"ルートタグは compound でなければならないが {type.AsString()} だった");
        }

        string name;
        if (format == NbtFormat.Java)
        {
            // ファイル形式のルートには名前が付く（通常は空文字列）
            name = RequireUtf8Representable(ReadString(), "ルート名");
        }
        else
        {
            // ネットワーク形式 (1.20.2+) のルートに名前は無い
            name = string.Empty;
        }

        NbtCompound root = ReadCompoundPayload(1);
        return new NamedTag(name, root);
    }

    /// <summary>指定した型のペイロードを読む</summary>
    private NbtTag ReadPayload(TagType type, int depth)
    {
        // 深さ上限は再帰する型に入る手前で検査する
        if (depth > maxDepth)
        {
            throw SpringNbtException.LimitExceeded($"ネストが深すぎる (上限 {maxDepth})");
        }

        switch (type)
        {
            case TagType.Byte:
                return new NbtByte((sbyte)ReadByteRaw());
            case TagType.Short:
                return new NbtShort(BinaryPrimitives.ReadInt16BigEndian(Take(2)));
            case TagType.Int:
                return new NbtInt(BinaryPrimitives.ReadInt32BigEndian(Take(4)));
            case TagType.Long:
                return new NbtLong(BinaryPrimitives.ReadInt64BigEndian(Take(8)));
            case TagType.Float:
                return new NbtFloat(BinaryPrimitives.ReadSingleBigEndian(Take(4)));
            case TagType.Double:
                return new NbtDouble(BinaryPrimitives.ReadDoubleBigEndian(Take(8)));
            case TagType.ByteArray:
                return new NbtByteArray(ReadByteArrayPayload());
            case TagType.String:
                return new NbtString(ReadString());
            case TagType.List:
                return ReadListPayload(depth);
            case TagType.Compound:
                return ReadCompoundPayload(depth);
            case TagType.IntArray:
                return new NbtIntArray(ReadIntArrayPayload());
            case TagType.LongArray:
                return new NbtLongArray(ReadLongArrayPayload());
            case TagType.End:
                throw SpringNbtException.Malformed("TAG_End のペイロードを読もうとした");
            default:
                throw SpringNbtException.Malformed($"未知のタグ型: {type}");
        }
    }

    /// <summary>TAG_Compound のペイロード（名前付きタグの並び + TAG_End）を読む</summary>
    private NbtCompound ReadCompoundPayload(int depth)
    {
        NbtCompound compound = new NbtCompound();

        // TAG_End が現れるまで名前付きタグを読み続ける
        while (true)
        {
            byte id = ReadByteRaw();
            TagType type = TagTypeExtensions.FromId(id);

            if (type == TagType.End)
            {
                return compound;
            }

            string name = RequireUtf8Representable(ReadString(), "Compound のキー");
            NbtTag value = ReadPayload(type, depth + 1);
            compound.Set(name, value);
        }
    }

    /// <summary>TAG_List のペイロードを読む</summary>
    private NbtList ReadListPayload(int depth)
    {
        byte elementId = ReadByteRaw();
        TagType elementType = TagTypeExtensions.FromId(elementId);
        int count = ReadLength();

        if (elementType == TagType.End)
        {
            // 要素型 End のリストは空でなければならない
            if (count != 0)
            {
                throw SpringNbtException.Malformed($"要素型 End のリストに {count} 個の要素が宣言されている");
            }

            return new NbtList(TagType.End);
        }

        // 1 要素の最小バイト数から、宣言された個数が入力に収まるかを先に検査する
        EnsureAvailable((long)count * MinimumPayloadSize(elementType));

        NbtList list = new NbtList(elementType);

        // 宣言された個数だけペイロードを読む
        for (int i = 0; i < count; i++)
        {
            list.Add(ReadPayload(elementType, depth + 1));
        }

        return list;
    }

    private sbyte[] ReadByteArrayPayload()
    {
        int count = ReadLength();
        EnsureAvailable(count);

        sbyte[] result = new sbyte[count];

        // バイト単位でそのまま写す
        for (int i = 0; i < count; i++)
        {
            result[i] = (sbyte)data[position + i];
        }

        position += count;
        return result;
    }

    private int[] ReadIntArrayPayload()
    {
        int count = ReadLength();
        EnsureAvailable((long)count * 4);

        int[] result = new int[count];

        // 4 バイトずつビッグエンディアンで読む
        for (int i = 0; i < count; i++)
        {
            result[i] = BinaryPrimitives.ReadInt32BigEndian(data.AsSpan(position + (i * 4), 4));
        }

        position += count * 4;
        return result;
    }

    private long[] ReadLongArrayPayload()
    {
        int count = ReadLength();
        EnsureAvailable((long)count * 8);

        long[] result = new long[count];

        // 8 バイトずつビッグエンディアンで読む
        for (int i = 0; i < count; i++)
        {
            result[i] = BinaryPrimitives.ReadInt64BigEndian(data.AsSpan(position + (i * 8), 8));
        }

        position += count * 8;
        return result;
    }

    /// <summary>MUTF-8 の文字列（u16 の長さ + 本体）を読む</summary>
    private string ReadString()
    {
        int length = BinaryPrimitives.ReadUInt16BigEndian(Take(2));
        EnsureAvailable(length);

        string text = Mutf8.Decode(data.AsSpan(position, length));
        position += length;
        return text;
    }

    /// <summary>配列・リストの長さフィールドを読む
    /// 負値は不正</summary>
    private int ReadLength()
    {
        int length = BinaryPrimitives.ReadInt32BigEndian(Take(4));

        // 長さは i32 だが、負値は仕様上ありえない
        if (length < 0)
        {
            throw SpringNbtException.Malformed($"長さが負値: {length}");
        }

        return length;
    }

    private byte ReadByteRaw()
    {
        EnsureAvailable(1);
        byte value = data[position];
        position += 1;
        return value;
    }

    /// <summary>指定バイト数を切り出して読み進める</summary>
    private ReadOnlySpan<byte> Take(int count)
    {
        EnsureAvailable(count);
        ReadOnlySpan<byte> span = data.AsSpan(position, count);
        position += count;
        return span;
    }

    /// <summary>残り入力が必要バイト数を満たすか検査する
    /// メモリを確保する前に呼ぶ</summary>
    private void EnsureAvailable(long required)
    {
        if (required > Remaining)
        {
            throw SpringNbtException.Malformed(
                $"入力が足りない: {required} バイト必要だが残り {Remaining} バイト");
        }
    }

    /// <summary>
    /// キーやルート名として使える文字列か検査する
    /// </summary>
    /// <remarks>
    /// 値と違い、キーには孤立サロゲートを許さない（仕様 10 の 2.2章）
    /// Minecraft が書き出すキーは ASCII の識別子のみで、
    /// 孤立サロゲートが現れるのはデータ破損を意味する
    /// またキーを「ただの文字列」として扱えることが、
    /// 4言語すべてでマップ型をそのまま使えるという実装上の利点につながる
    /// </remarks>
    private static string RequireUtf8Representable(string text, string role)
    {
        // 対にならないサロゲートが含まれていないか調べる
        for (int index = 0; index < text.Length; index++)
        {
            char c = text[index];

            // 上位サロゲートは、対になる下位サロゲートとまとめて 1 文字を成す
            if (char.IsHighSurrogate(c))
            {
                // 対が揃っていれば 2 コード単位を消費する
                // 揃わなければ孤立サロゲート
                if (index + 1 < text.Length && char.IsLowSurrogate(text[index + 1]))
                {
                    index += 1;
                }
                else
                {
                    throw SpringNbtException.Malformed(
                        $"{role}が UTF-8 に写せない（孤立サロゲートを含む）");
                }
            }
            else if (char.IsLowSurrogate(c))
            {
                throw SpringNbtException.Malformed(
                    $"{role}が UTF-8 に写せない（孤立サロゲートを含む）");
            }
        }

        return text;
    }

    /// <summary>その型のペイロードが最低何バイトになるかを返す
    /// 長さの先行検証に使う</summary>
    private static int MinimumPayloadSize(TagType type)
    {
        switch (type)
        {
            case TagType.Byte:
                return 1;
            case TagType.Short:
                return 2;
            case TagType.Int:
            case TagType.Float:
                return 4;
            case TagType.Long:
            case TagType.Double:
                return 8;
            case TagType.ByteArray:
            case TagType.IntArray:
            case TagType.LongArray:
                // 長さフィールドの 4 バイトは必ずある
                return 4;
            case TagType.String:
                // 長さフィールドの 2 バイトは必ずある
                return 2;
            case TagType.List:
                // 要素型 1 バイト + 個数 4 バイト
                return 5;
            case TagType.Compound:
                // 終端の TAG_End 1 バイトは必ずある
                return 1;
            default:
                return 1;
        }
    }
}

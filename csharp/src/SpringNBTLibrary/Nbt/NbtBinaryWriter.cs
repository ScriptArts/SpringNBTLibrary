using System.Buffers.Binary;

namespace SpringNBTLibrary.Nbt;

/// <summary>
/// NBT を展開済みのバイト列へ書き出す
/// </summary>
/// <remarks>
/// <para>
/// 出力は一意でなければならない（ラウンドトリップ検証が成立するため）
/// Compound は挿入順のまま、浮動小数点はビットパターンのまま書き出す
/// </para>
/// <para>仕様: <c>docs/spec/10-nbt-binary.md</c> 5章</para>
/// </remarks>
internal sealed class NbtBinaryWriter
{
    private readonly List<byte> buffer = new List<byte>();

    /// <summary>ルートタグを書き出し、結果のバイト列を返す</summary>
    internal byte[] WriteRoot(NamedTag named, NbtFormat format)
    {
        buffer.Add((byte)TagType.Compound);

        if (format == NbtFormat.Java)
        {
            // ファイル形式のルートには名前が付く
            WriteString(named.Name);
        }

        WriteCompoundPayload(named.Tag);
        return buffer.ToArray();
    }

    private void WritePayload(NbtTag tag)
    {
        switch (tag)
        {
            case NbtByte value:
                buffer.Add((byte)value.Value);
                break;
            case NbtShort value:
                WriteInt16(value.Value);
                break;
            case NbtInt value:
                WriteInt32(value.Value);
                break;
            case NbtLong value:
                WriteInt64(value.Value);
                break;
            case NbtFloat value:
                // NaN や -0.0 を保つため、ビットパターンをそのまま書く
                WriteInt32(BitConverter.SingleToInt32Bits(value.Value));
                break;
            case NbtDouble value:
                WriteInt64(BitConverter.DoubleToInt64Bits(value.Value));
                break;
            case NbtByteArray value:
                WriteByteArrayPayload(value.Value);
                break;
            case NbtString value:
                WriteString(value.Value);
                break;
            case NbtList value:
                WriteListPayload(value);
                break;
            case NbtCompound value:
                WriteCompoundPayload(value);
                break;
            case NbtIntArray value:
                WriteIntArrayPayload(value.Value);
                break;
            case NbtLongArray value:
                WriteLongArrayPayload(value.Value);
                break;
            default:
                throw SpringNbtException.Malformed($"書き出せないタグ: {tag.Type.AsString()}");
        }
    }

    private void WriteCompoundPayload(NbtCompound compound)
    {
        // 挿入順のまま「タグID + 名前 + ペイロード」を並べる
        foreach (KeyValuePair<string, NbtTag> entry in compound)
        {
            buffer.Add((byte)entry.Value.Type);
            WriteString(entry.Key);
            WritePayload(entry.Value);
        }

        buffer.Add((byte)TagType.End);
    }

    private void WriteListPayload(NbtList list)
    {
        buffer.Add((byte)list.ElementType);
        WriteInt32(list.Count);

        // 要素型は共通なので、ペイロードだけを並べる
        foreach (NbtTag item in list)
        {
            WritePayload(item);
        }
    }

    private void WriteByteArrayPayload(sbyte[] values)
    {
        WriteInt32(values.Length);

        // 1 バイトずつそのまま書く
        foreach (sbyte value in values)
        {
            buffer.Add((byte)value);
        }
    }

    private void WriteIntArrayPayload(int[] values)
    {
        WriteInt32(values.Length);

        // 4 バイトずつビッグエンディアンで書く
        foreach (int value in values)
        {
            WriteInt32(value);
        }
    }

    private void WriteLongArrayPayload(long[] values)
    {
        WriteInt32(values.Length);

        // 8 バイトずつビッグエンディアンで書く
        foreach (long value in values)
        {
            WriteInt64(value);
        }
    }

    private void WriteString(string text)
    {
        byte[] encoded = Mutf8.Encode(text);

        // 長さフィールドは u16
        // NbtString 側でも検査しているが、キー名は素の string なのでここでも見る
        if (encoded.Length > Mutf8.MaxByteLength)
        {
            throw SpringNbtException.InvalidArgument(
                $"文字列が長すぎる: MUTF-8 で {encoded.Length} バイト (上限 {Mutf8.MaxByteLength})");
        }

        Span<byte> lengthBytes = stackalloc byte[2];
        BinaryPrimitives.WriteUInt16BigEndian(lengthBytes, (ushort)encoded.Length);
        buffer.Add(lengthBytes[0]);
        buffer.Add(lengthBytes[1]);
        buffer.AddRange(encoded);
    }

    private void WriteInt16(short value)
    {
        Span<byte> bytes = stackalloc byte[2];
        BinaryPrimitives.WriteInt16BigEndian(bytes, value);
        buffer.Add(bytes[0]);
        buffer.Add(bytes[1]);
    }

    private void WriteInt32(int value)
    {
        Span<byte> bytes = stackalloc byte[4];
        BinaryPrimitives.WriteInt32BigEndian(bytes, value);

        // Span は AddRange に渡せないので 1 バイトずつ積む
        for (int i = 0; i < bytes.Length; i++)
        {
            buffer.Add(bytes[i]);
        }
    }

    private void WriteInt64(long value)
    {
        Span<byte> bytes = stackalloc byte[8];
        BinaryPrimitives.WriteInt64BigEndian(bytes, value);

        // Span は AddRange に渡せないので 1 バイトずつ積む
        for (int i = 0; i < bytes.Length; i++)
        {
            buffer.Add(bytes[i]);
        }
    }
}

using System.Buffers.Binary;

namespace SpringNBTLibrary.Anvil;

/// <summary>
/// 圧縮方式ID 4 (LZ4) のチャンクを展開する
/// </summary>
/// <remarks>
/// <para>
/// 素の LZ4 ブロックでも LZ4 フレーム形式でもなく、
/// 独自ヘッダを持つブロックの連結である
/// </para>
/// <para>書き込みには対応しない</para>
/// <para>書き戻すときは Zlib になる</para>
/// <para>仕様: <c>docs/spec/20-anvil-region.md</c> 3.1.1 / 3.1.2</para>
/// </remarks>
internal static class Lz4
{
    /// <summary>ブロックの先頭に必ず置かれる 8 バイト</summary>
    private static readonly byte[] Magic = "LZ4Block"u8.ToArray();

    /// <summary>ブロックヘッダの長さ</summary>
    private const int HeaderLength = 21;

    /// <summary>トークン上位 4 ビット: 本体が無圧縮</summary>
    private const int MethodStored = 0x10;

    /// <summary>トークン上位 4 ビット: 本体が LZ4 圧縮</summary>
    private const int MethodCompressed = 0x20;

    /// <summary>マッチの最小長</summary>
    private const int MinMatch = 4;

    /// <summary>LZ4Block の連結を展開する</summary>
    /// <exception cref="SpringNbtException">
    /// 形式に反する入力（<see cref="ErrorCode.MalformedData"/>）
    /// </exception>
    internal static byte[] Decompress(byte[] payload)
    {
        using MemoryStream output = new MemoryStream();
        int position = 0;

        // 入力を使い切るまでブロックを読み続ける
        while (position < payload.Length)
        {
            position = DecompressBlock(payload, position, output);
        }

        return output.ToArray();
    }

    /// <summary>ブロックを 1 つ展開し、次のブロックの開始位置を返す</summary>
    private static int DecompressBlock(byte[] payload, int position, MemoryStream output)
    {
        if (position + HeaderLength > payload.Length)
        {
            throw SpringNbtException.Malformed(
                $"LZ4: ブロックヘッダが足りない（{payload.Length - position} バイト）");
        }

        // マジックが違えばそもそも LZ4Block ではない
        for (int index = 0; index < Magic.Length; index++)
        {
            if (payload[position + index] != Magic[index])
            {
                throw SpringNbtException.Malformed("LZ4: ブロックが LZ4Block で始まっていない");
            }
        }

        int method = payload[position + 8] & 0xF0;
        int compressedLength = BinaryPrimitives.ReadInt32LittleEndian(
            payload.AsSpan(position + 9, 4));
        int originalLength = BinaryPrimitives.ReadInt32LittleEndian(
            payload.AsSpan(position + 13, 4));
        int body = position + HeaderLength;

        ValidateLengths(compressedLength, originalLength);

        if (body + compressedLength > payload.Length)
        {
            throw SpringNbtException.Malformed("LZ4: ブロック本体が入力からはみ出している");
        }

        if (method == MethodStored)
        {
            // 無圧縮なら 2 つの長さは一致していなければならない
            if (compressedLength != originalLength)
            {
                throw SpringNbtException.Malformed(
                    $"LZ4: 無圧縮ブロックの長さが食い違う（{compressedLength} と {originalLength}）");
            }

            output.Write(payload, body, compressedLength);
        }
        else if (method == MethodCompressed)
        {
            byte[] block = DecompressRawBlock(
                payload.AsSpan(body, compressedLength), originalLength);
            output.Write(block, 0, block.Length);
        }
        else
        {
            throw SpringNbtException.Malformed(
                $"LZ4: 未知の圧縮方式 0x{method:X2}");
        }

        return body + compressedLength;
    }

    /// <summary>ヘッダに書かれた 2 つの長さが妥当か調べる</summary>
    private static void ValidateLengths(int compressedLength, int originalLength)
    {
        if (compressedLength < 0 || originalLength < 0)
        {
            throw SpringNbtException.Malformed("LZ4: ブロックの長さが負値");
        }

        // 片方だけが 0 になることはない
        if ((compressedLength == 0) != (originalLength == 0))
        {
            throw SpringNbtException.Malformed("LZ4: ブロックの長さが片方だけ 0");
        }
    }

    /// <summary>素の LZ4 ブロックを展開する</summary>
    private static byte[] DecompressRawBlock(ReadOnlySpan<byte> source, int originalLength)
    {
        byte[] output = new byte[originalLength];
        int input = 0;
        int written = 0;

        // シーケンスを順に読む
        while (input < source.Length)
        {
            int token = source[input];
            input++;

            int literalLength = token >> 4;

            // 15 なら追加バイトで長さが続く
            if (literalLength == 15)
            {
                literalLength += ReadLength(source, ref input);
            }

            CopyLiterals(source, ref input, output, ref written, literalLength);

            // リテラルを出し切って入力が尽きたら、そこで終わり
            if (input >= source.Length)
            {
                break;
            }

            if (input + 2 > source.Length)
            {
                throw SpringNbtException.Malformed("LZ4: オフセットが入力からはみ出している");
            }

            int offset = source[input] | (source[input + 1] << 8);
            input += 2;

            if (offset == 0 || offset > written)
            {
                throw SpringNbtException.Malformed($"LZ4: マッチのオフセットが不正: {offset}");
            }

            int matchLength = (token & 0x0F) + MinMatch;

            // 下位 4 ビットが 15 なら追加バイトで長さが続く
            if ((token & 0x0F) == 15)
            {
                matchLength += ReadLength(source, ref input);
            }

            CopyMatch(output, ref written, offset, matchLength);
        }

        if (written != originalLength)
        {
            throw SpringNbtException.Malformed(
                $"LZ4: 展開後の長さが合わない（{written} と {originalLength}）");
        }

        return output;
    }

    /// <summary>255 が続く形式の追加長さを読む</summary>
    private static int ReadLength(ReadOnlySpan<byte> source, ref int input)
    {
        int total = 0;

        // 255 未満のバイトが出るまで足し続ける
        while (true)
        {
            if (input >= source.Length)
            {
                throw SpringNbtException.Malformed("LZ4: 長さの追加バイトが途中で切れた");
            }

            int value = source[input];
            input++;
            total += value;

            if (value != 255)
            {
                return total;
            }
        }
    }

    /// <summary>リテラルをそのまま出力へ写す</summary>
    private static void CopyLiterals(ReadOnlySpan<byte> source, ref int input,
                                     byte[] output, ref int written, int length)
    {
        if (input + length > source.Length)
        {
            throw SpringNbtException.Malformed("LZ4: リテラルが入力からはみ出している");
        }

        if (written + length > output.Length)
        {
            throw SpringNbtException.Malformed("LZ4: 展開後の長さを超えた");
        }

        source.Slice(input, length).CopyTo(output.AsSpan(written, length));
        input += length;
        written += length;
    }

    /// <summary>出力済みのバイト列からマッチを写す</summary>
    private static void CopyMatch(byte[] output, ref int written, int offset, int length)
    {
        if (written + length > output.Length)
        {
            throw SpringNbtException.Malformed("LZ4: 展開後の長さを超えた");
        }

        int from = written - offset;

        // コピー元と先は重なりうるので 1 バイトずつ写す
        for (int index = 0; index < length; index++)
        {
            output[written + index] = output[from + index];
        }

        written += length;
    }
}

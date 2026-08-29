using System.Text;

namespace SpringNBTLibrary.Nbt;

/// <summary>
/// Modified UTF-8 (MUTF-8) の符号化・復号
/// </summary>
/// <remarks>
/// <para>標準 UTF-8 との違いは 2 点だけ</para>
/// <list type="bullet">
///   <item><description><c>U+0000</c> を <c>C0 80</c> の 2 バイトで表す</description></item>
///   <item><description><c>U+10000</c> 以上をサロゲートペアへ分解し、3 バイト × 2 で表す (CESU-8)</description></item>
/// </list>
/// <para>
/// C# の <see cref="string"/> は UTF-16 コード単位の列なので、
/// サロゲートペアも孤立サロゲートもそのまま保持できる
/// </para>
/// <para>仕様: <c>docs/spec/10-nbt-binary.md</c> 2章</para>
/// </remarks>
public static class Mutf8
{
    /// <summary>MUTF-8 の文字列が取りうる最大バイト長（長さフィールドが <c>u16</c> のため）</summary>
    public const int MaxByteLength = 65535;

    /// <summary>
    /// MUTF-8 バイト列を文字列へ復号する
    /// </summary>
    /// <exception cref="SpringNbtException">
    /// バイト列が MUTF-8 として不正な場合（<see cref="ErrorCode.MalformedData"/>）
    /// </exception>
    public static string Decode(ReadOnlySpan<byte> bytes)
    {
        StringBuilder builder = new StringBuilder(bytes.Length);
        int i = 0;

        // 先頭から 1 文字ずつ取り出す
        while (i < bytes.Length)
        {
            byte b0 = bytes[i];

            if ((b0 & 0x80) == 0x00)
            {
                // 1 バイト形式: 0xxxxxxx (U+0001..U+007F)
                if (b0 == 0x00)
                {
                    // 素の 0x00 は MUTF-8 では現れてはならない (C0 80 を使う)
                    throw SpringNbtException.Malformed("MUTF-8: 素の 0x00 が現れた (U+0000 は C0 80 で表す)");
                }

                builder.Append((char)b0);
                i += 1;
            }
            else if ((b0 & 0xE0) == 0xC0)
            {
                // 2 バイト形式: 110xxxxx 10xxxxxx
                if (i + 1 >= bytes.Length)
                {
                    throw SpringNbtException.Malformed("MUTF-8: 2バイト形式が途中で切れた");
                }

                byte b1 = bytes[i + 1];
                if ((b1 & 0xC0) != 0x80)
                {
                    throw SpringNbtException.Malformed("MUTF-8: 2バイト形式の継続バイトが不正");
                }

                int value = ((b0 & 0x1F) << 6) | (b1 & 0x3F);

                // C0 80 (U+0000) だけは正当
                // それ以外の 0x80 未満は冗長符号化
                if (value < 0x80 && !(b0 == 0xC0 && b1 == 0x80))
                {
                    throw SpringNbtException.Malformed("MUTF-8: 冗長な2バイト符号化");
                }

                builder.Append((char)value);
                i += 2;
            }
            else if ((b0 & 0xF0) == 0xE0)
            {
                // 3 バイト形式: 1110xxxx 10xxxxxx 10xxxxxx
                if (i + 2 >= bytes.Length)
                {
                    throw SpringNbtException.Malformed("MUTF-8: 3バイト形式が途中で切れた");
                }

                byte b1 = bytes[i + 1];
                byte b2 = bytes[i + 2];
                if ((b1 & 0xC0) != 0x80 || (b2 & 0xC0) != 0x80)
                {
                    throw SpringNbtException.Malformed("MUTF-8: 3バイト形式の継続バイトが不正");
                }

                int value = ((b0 & 0x0F) << 12) | ((b1 & 0x3F) << 6) | (b2 & 0x3F);

                // 3 バイトで表すべき範囲は U+0800 以上
                if (value < 0x800)
                {
                    throw SpringNbtException.Malformed("MUTF-8: 冗長な3バイト符号化");
                }

                builder.Append((char)value);
                i += 3;
            }
            else
            {
                // 4 バイト形式 (標準 UTF-8) や継続バイト単独は MUTF-8 では不正
                throw SpringNbtException.Malformed($"MUTF-8: 不正な先頭バイト 0x{b0:X2}");
            }
        }

        return builder.ToString();
    }

    /// <summary>
    /// 文字列を MUTF-8 バイト列へ符号化する
    /// </summary>
    /// <remarks>
    /// サロゲートは対になっているかどうかに関わらず 1 つずつ 3 バイトで符号化されるため、
    /// 孤立サロゲートもそのまま往復できる
    /// </remarks>
    public static byte[] Encode(string text)
    {
        byte[] buffer = new byte[ByteLength(text)];
        int position = 0;

        // コード単位ごとに 1〜3 バイトへ展開する
        foreach (char unit in text)
        {
            // U+0001..U+007F だけが 1 バイト
            // U+0000 は 2 バイトになる
            if (unit >= 0x0001 && unit <= 0x007F)
            {
                buffer[position] = (byte)unit;
                position += 1;
            }
            else if (unit == 0x0000 || unit <= 0x07FF)
            {
                // U+0000 もこの経路で C0 80 になる
                buffer[position] = (byte)(0xC0 | ((unit >> 6) & 0x1F));
                buffer[position + 1] = (byte)(0x80 | (unit & 0x3F));
                position += 2;
            }
            else
            {
                buffer[position] = (byte)(0xE0 | ((unit >> 12) & 0x0F));
                buffer[position + 1] = (byte)(0x80 | ((unit >> 6) & 0x3F));
                buffer[position + 2] = (byte)(0x80 | (unit & 0x3F));
                position += 3;
            }
        }

        return buffer;
    }

    /// <summary>
    /// 文字列を MUTF-8 で符号化したときのバイト長を求める
    /// 実際に符号化はしない
    /// </summary>
    public static int ByteLength(string text)
    {
        int length = 0;

        // 各コード単位が何バイトになるかを数える
        foreach (char unit in text)
        {
            // U+0001..U+007F だけが 1 バイト
            // U+0000 は 2 バイトになる
            if (unit >= 0x0001 && unit <= 0x007F)
            {
                length += 1;
            }
            else if (unit == 0x0000 || unit <= 0x07FF)
            {
                length += 2;
            }
            else
            {
                length += 3;
            }
        }

        return length;
    }
}

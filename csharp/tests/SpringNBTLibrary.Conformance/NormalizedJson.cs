using System.Globalization;
using System.Text;
using SpringNBTLibrary.Nbt;

namespace SpringNBTLibrary.Conformance;

/// <summary>
/// NBT を、言語をまたいで文字列として完全一致する JSON へ写す。
/// </summary>
/// <remarks>
/// <para>
/// 浮動小数点をビットパターンで、64bit 整数を10進文字列で表すのが要。
/// 10進表記の丸めや JSON 数値の精度は処理系ごとに差が出るため、
/// そのまま出すと4言語の出力が一致しない。
/// </para>
/// <para>仕様: <c>docs/spec/00-conventions.md</c> 6章 / <c>docs/spec/90-conformance.md</c></para>
/// </remarks>
internal static class NormalizedJson
{
    /// <summary>ルートを含む全体を JSON 文字列へ変換する。末尾に改行を1つ付ける。</summary>
    internal static string Write(NamedTag named, NbtFormat format)
    {
        StringBuilder builder = new StringBuilder();
        builder.Append("{\"format\":");
        AppendString(builder, FormatName(format));
        builder.Append(",\"root_name\":");
        AppendString(builder, named.Name);
        builder.Append(",\"root\":");
        AppendTag(builder, named.Tag);
        builder.Append("}\n");
        return builder.ToString();
    }

    private static string FormatName(NbtFormat format)
    {
        if (format == NbtFormat.Network)
        {
            return "network";
        }

        return "java";
    }

    private static void AppendTag(StringBuilder builder, NbtTag tag)
    {
        builder.Append("{\"type\":");
        AppendString(builder, tag.Type.AsString());

        // list だけは value の前に element_type が入る（仕様が定めるキー順）
        if (tag is NbtList listTag)
        {
            builder.Append(",\"element_type\":");
            AppendString(builder, listTag.ElementType.AsString());
        }

        builder.Append(",\"value\":");

        switch (tag)
        {
            case NbtByte value:
                builder.Append(value.Value.ToString(CultureInfo.InvariantCulture));
                break;
            case NbtShort value:
                builder.Append(value.Value.ToString(CultureInfo.InvariantCulture));
                break;
            case NbtInt value:
                builder.Append(value.Value.ToString(CultureInfo.InvariantCulture));
                break;
            case NbtLong value:
                // 64bit 整数は JSON 数値だと処理系によって精度が落ちるため10進文字列で表す
                AppendString(builder, value.Value.ToString(CultureInfo.InvariantCulture));
                break;
            case NbtFloat value:
                AppendString(builder, HexBits(BitConverter.SingleToUInt32Bits(value.Value), 8));
                break;
            case NbtDouble value:
                AppendString(builder, HexBits(BitConverter.DoubleToUInt64Bits(value.Value), 16));
                break;
            case NbtString value:
                AppendString(builder, value.Value);

                // MUTF-8 のバイト列も併記する。孤立サロゲートなど UTF-8 に写せない値を厳密に比較するため
                builder.Append(",\"mutf8\":");
                AppendString(builder, ToHex(Mutf8.Encode(value.Value)));
                break;
            case NbtByteArray value:
                AppendByteArray(builder, value.Value);
                break;
            case NbtIntArray value:
                AppendIntArray(builder, value.Value);
                break;
            case NbtLongArray value:
                AppendLongArray(builder, value.Value);
                break;
            case NbtList value:
                AppendList(builder, value);
                break;
            case NbtCompound value:
                AppendCompound(builder, value);
                break;
            default:
                throw new InvalidOperationException($"JSON へ写せないタグ: {tag.Type.AsString()}");
        }

        builder.Append('}');
    }

    private static void AppendList(StringBuilder builder, NbtList list)
    {
        builder.Append('[');
        bool first = true;

        // 要素を順に書き出す
        foreach (NbtTag item in list)
        {
            if (!first)
            {
                builder.Append(',');
            }

            first = false;
            AppendTag(builder, item);
        }

        builder.Append(']');
    }

    private static void AppendCompound(StringBuilder builder, NbtCompound compound)
    {
        // JSON オブジェクトだと挿入順の保持が処理系依存になるため、組の配列で表す
        builder.Append('[');
        bool first = true;

        foreach (KeyValuePair<string, NbtTag> entry in compound)
        {
            if (!first)
            {
                builder.Append(',');
            }

            first = false;
            builder.Append('[');
            AppendString(builder, entry.Key);
            builder.Append(',');
            AppendTag(builder, entry.Value);
            builder.Append(']');
        }

        builder.Append(']');
    }

    private static void AppendByteArray(StringBuilder builder, sbyte[] values)
    {
        builder.Append('[');

        for (int i = 0; i < values.Length; i++)
        {
            if (i > 0)
            {
                builder.Append(',');
            }

            builder.Append(values[i].ToString(CultureInfo.InvariantCulture));
        }

        builder.Append(']');
    }

    private static void AppendIntArray(StringBuilder builder, int[] values)
    {
        builder.Append('[');

        for (int i = 0; i < values.Length; i++)
        {
            if (i > 0)
            {
                builder.Append(',');
            }

            builder.Append(values[i].ToString(CultureInfo.InvariantCulture));
        }

        builder.Append(']');
    }

    private static void AppendLongArray(StringBuilder builder, long[] values)
    {
        builder.Append('[');

        // 64bit 整数は10進文字列の配列で表す
        for (int i = 0; i < values.Length; i++)
        {
            if (i > 0)
            {
                builder.Append(',');
            }

            AppendString(builder, values[i].ToString(CultureInfo.InvariantCulture));
        }

        builder.Append(']');
    }

    /// <summary>浮動小数点のビットパターンを "0x..." 形式で表す。</summary>
    private static string HexBits(ulong bits, int digits)
    {
        return "0x" + bits.ToString("x" + digits.ToString(CultureInfo.InvariantCulture), CultureInfo.InvariantCulture);
    }

    private static string ToHex(byte[] bytes)
    {
        StringBuilder builder = new StringBuilder(bytes.Length * 2);

        foreach (byte value in bytes)
        {
            builder.Append(value.ToString("x2", CultureInfo.InvariantCulture));
        }

        return builder.ToString();
    }

    /// <summary>
    /// JSON 文字列を書き出す。非 ASCII は必ず <c>\uXXXX</c> へ逃がす。
    /// </summary>
    /// <remarks>
    /// 言語ごとに既定のエスケープ方針が違うため、ここで一律に固定しないと出力が一致しない。
    /// </remarks>
    private static void AppendString(StringBuilder builder, string text)
    {
        builder.Append('"');

        foreach (char c in text)
        {
            switch (c)
            {
                case '"':
                    builder.Append("\\\"");
                    break;
                case '\\':
                    builder.Append("\\\\");
                    break;
                case '\b':
                    builder.Append("\\b");
                    break;
                case '\f':
                    builder.Append("\\f");
                    break;
                case '\n':
                    builder.Append("\\n");
                    break;
                case '\r':
                    builder.Append("\\r");
                    break;
                case '\t':
                    builder.Append("\\t");
                    break;
                default:
                    // ASCII の印字可能文字だけ生で出し、それ以外は \\uXXXX にする
                    if (c >= 0x20 && c <= 0x7E)
                    {
                        builder.Append(c);
                    }
                    else
                    {
                        builder.Append("\\u")
                            .Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                    }

                    break;
            }
        }

        builder.Append('"');
    }
}

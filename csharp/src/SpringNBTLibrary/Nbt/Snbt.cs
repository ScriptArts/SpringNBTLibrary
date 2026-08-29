using System.Globalization;
using System.Text;

namespace SpringNBTLibrary.Nbt;

/// <summary>
/// SNBT (Stringified NBT) のパースと出力
/// </summary>
/// <remarks>
/// <para>
/// 対応範囲は「バイナリ NBT へ損失なく写せる部分集合」
/// 1.21.5 以降の異種リスト（<c>[1, "a"]</c>）は受理しない
/// </para>
/// <para>仕様: <c>docs/spec/11-snbt.md</c> / <c>docs/adr/0006-snbt-scope.md</c></para>
/// </remarks>
public static class Snbt
{
    private const string IndentUnit = "    ";

    /// <summary>SNBT 文字列をタグへ変換する</summary>
    /// <exception cref="SpringNbtException">構文が不正な場合</exception>
    public static NbtTag Parse(string text)
    {
        ArgumentNullException.ThrowIfNull(text);
        SnbtParser parser = new SnbtParser(text);
        return parser.ParseWhole();
    }

    /// <summary>SNBT 文字列を Compound へ変換する</summary>
    /// <exception cref="SpringNbtException">
    /// 構文が不正、またはルートが Compound でない場合
    /// </exception>
    public static NbtCompound ParseCompound(string text)
    {
        NbtTag tag = Parse(text);

        if (tag is NbtCompound compound)
        {
            return compound;
        }

        throw SpringNbtException.UnexpectedTagType(
            $"ルートが compound でない: {tag.Type.AsString()}");
    }

    /// <summary>タグを 1 行の SNBT へ変換する</summary>
    public static string Write(NbtTag tag)
    {
        ArgumentNullException.ThrowIfNull(tag);
        StringBuilder builder = new StringBuilder();
        WriteTag(builder, tag, -1);
        return builder.ToString();
    }

    /// <summary>タグを整形した SNBT へ変換する
    /// インデントは空白 4 個</summary>
    public static string WritePretty(NbtTag tag)
    {
        ArgumentNullException.ThrowIfNull(tag);
        StringBuilder builder = new StringBuilder();
        WriteTag(builder, tag, 0);
        return builder.ToString();
    }

    /// <summary>
    /// タグを書き出す
    /// <paramref name="depth"/> が負なら 1 行、0 以上なら整形して出力する
    /// </summary>
    private static void WriteTag(StringBuilder builder, NbtTag tag, int depth)
    {
        switch (tag)
        {
            case NbtByte value:
                builder.Append(value.Value.ToString(CultureInfo.InvariantCulture)).Append('b');
                break;
            case NbtShort value:
                builder.Append(value.Value.ToString(CultureInfo.InvariantCulture)).Append('s');
                break;
            case NbtInt value:
                builder.Append(value.Value.ToString(CultureInfo.InvariantCulture));
                break;
            case NbtLong value:
                builder.Append(value.Value.ToString(CultureInfo.InvariantCulture)).Append('L');
                break;
            case NbtFloat value:
                builder.Append(FormatFloat(value.Value)).Append('f');
                break;
            case NbtDouble value:
                builder.Append(FormatDouble(value.Value)).Append('d');
                break;
            case NbtString value:
                builder.Append(QuoteString(value.Value));
                break;
            case NbtByteArray value:
                WriteByteArray(builder, value);
                break;
            case NbtIntArray value:
                WriteIntArray(builder, value);
                break;
            case NbtLongArray value:
                WriteLongArray(builder, value);
                break;
            case NbtList value:
                WriteList(builder, value, depth);
                break;
            case NbtCompound value:
                WriteCompound(builder, value, depth);
                break;
            default:
                throw SpringNbtException.UnexpectedTagType($"SNBT へ書けないタグ: {tag.Type.AsString()}");
        }
    }

    private static void WriteCompound(StringBuilder builder, NbtCompound compound, int depth)
    {
        // 空の compound は改行もインデントも入れず {} と書く
        if (compound.Count == 0)
        {
            builder.Append("{}");
            return;
        }

        builder.Append('{');
        bool first = true;

        // 挿入順のまま「キー: 値」を並べる
        foreach (KeyValuePair<string, NbtTag> entry in compound)
        {
            // 2 つ目以降の前に区切りのカンマを置く
            if (!first)
            {
                builder.Append(',');
            }

            first = false;
            AppendSeparator(builder, NextDepth(depth));
            builder.Append(QuoteKey(entry.Key));
            builder.Append(':');

            // 整形時はコロンの後に空白を入れて読みやすくする
            if (depth >= 0)
            {
                builder.Append(' ');
            }

            WriteTag(builder, entry.Value, NextDepth(depth));
        }

        AppendSeparator(builder, depth);
        builder.Append('}');
    }

    private static void WriteList(StringBuilder builder, NbtList list, int depth)
    {
        // 空のリストは改行もインデントも入れず [] と書く
        if (list.Count == 0)
        {
            builder.Append("[]");
            return;
        }

        builder.Append('[');
        bool first = true;

        // 要素型は共通なので値だけを並べる
        foreach (NbtTag item in list)
        {
            // 2 つ目以降の前に区切りのカンマを置く
            if (!first)
            {
                builder.Append(',');
            }

            first = false;
            AppendSeparator(builder, NextDepth(depth));
            WriteTag(builder, item, NextDepth(depth));
        }

        AppendSeparator(builder, depth);
        builder.Append(']');
    }

    private static void WriteByteArray(StringBuilder builder, NbtByteArray array)
    {
        builder.Append("[B;");

        // 型付き配列は 1 行に収める
        // 要素には接尾辞を付ける
        for (int i = 0; i < array.Value.Length; i++)
        {
            // 2 つ目以降の前に区切りのカンマを置く
            if (i > 0)
            {
                builder.Append(',');
            }

            builder.Append(array.Value[i].ToString(CultureInfo.InvariantCulture)).Append('B');
        }

        builder.Append(']');
    }

    private static void WriteIntArray(StringBuilder builder, NbtIntArray array)
    {
        builder.Append("[I;");

        // IntArray の要素は接尾辞なし
        for (int i = 0; i < array.Value.Length; i++)
        {
            // 2 つ目以降の前に区切りのカンマを置く
            if (i > 0)
            {
                builder.Append(',');
            }

            builder.Append(array.Value[i].ToString(CultureInfo.InvariantCulture));
        }

        builder.Append(']');
    }

    private static void WriteLongArray(StringBuilder builder, NbtLongArray array)
    {
        builder.Append("[L;");

        // LongArray の要素には L 接尾辞を付ける
        for (int i = 0; i < array.Value.Length; i++)
        {
            // 2 つ目以降の前に区切りのカンマを置く
            if (i > 0)
            {
                builder.Append(',');
            }

            builder.Append(array.Value[i].ToString(CultureInfo.InvariantCulture)).Append('L');
        }

        builder.Append(']');
    }

    /// <summary>整形出力なら改行とインデントを、1 行出力なら何も入れない</summary>
    private static void AppendSeparator(StringBuilder builder, int depth)
    {
        if (depth < 0)
        {
            return;
        }

        builder.Append('\n');

        // 深さぶんインデントを積む
        for (int i = 0; i < depth; i++)
        {
            builder.Append(IndentUnit);
        }
    }

    /// <summary>整形出力のときだけ深さを 1 段進める</summary>
    private static int NextDepth(int depth)
    {
        if (depth < 0)
        {
            return -1;
        }

        return depth + 1;
    }

    /// <summary>キーを出力する
    /// 引用符なしで書ける場合はそのまま出す</summary>
    private static string QuoteKey(string key)
    {
        if (IsBareWritable(key))
        {
            return key;
        }

        return QuoteString(key);
    }

    private static bool IsBareWritable(string text)
    {
        if (text.Length == 0)
        {
            return false;
        }

        // 引用符なしで書ける文字だけで構成されているか調べる
        foreach (char c in text)
        {
            if (!SnbtParser.IsBareChar(c))
            {
                return false;
            }
        }

        return true;
    }

    /// <summary>文字列を二重引用符で囲み、必要な文字だけエスケープする</summary>
    private static string QuoteString(string text)
    {
        StringBuilder builder = new StringBuilder(text.Length + 2);
        builder.Append('"');

        // 1 文字ずつ見てエスケープが要るものだけ置き換える
        for (int index = 0; index < text.Length; index++)
        {
            char c = text[index];
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
                case '\t':
                    builder.Append("\\t");
                    break;
                case '\n':
                    builder.Append("\\n");
                    break;
                case '\f':
                    builder.Append("\\f");
                    break;
                case '\r':
                    builder.Append("\\r");
                    break;
                default:
                    // 正しいサロゲートペアはそのまま出す
                    // ここでエスケープすると、コードポイント単位の言語（Python / Rust）と出力が食い違う
                    if (char.IsHighSurrogate(c)
                        && index + 1 < text.Length
                        && char.IsLowSurrogate(text[index + 1]))
                    {
                        builder.Append(c);
                        builder.Append(text[index + 1]);
                        index += 1;
                    }
                    else if (c < 0x20 || c == 0x7F || char.IsSurrogate(c))
                    {
                        // 制御文字と孤立サロゲートは \uXXXX で表す
                        builder.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                    }
                    else
                    {
                        builder.Append(c);
                    }

                    break;
            }
        }

        builder.Append('"');
        return builder.ToString();
    }

    private static string FormatFloat(float value)
    {
        return CanonicalDecimal.FromFloat(value);
    }

    private static string FormatDouble(double value)
    {
        return CanonicalDecimal.FromDouble(value);
    }
}

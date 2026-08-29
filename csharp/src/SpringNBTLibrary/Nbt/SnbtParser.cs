using System.Globalization;
using System.Text;

namespace SpringNBTLibrary.Nbt;

/// <summary>
/// SNBT (Stringified NBT) のパーサ。
/// </summary>
/// <remarks>仕様: <c>docs/spec/11-snbt.md</c></remarks>
internal sealed class SnbtParser
{
    private readonly string text;
    private int position;

    internal SnbtParser(string text)
    {
        this.text = text;
        this.position = 0;
    }

    /// <summary>入力全体を 1 つの値として読む。末尾に余りがあれば例外。</summary>
    internal NbtTag ParseWhole()
    {
        NbtTag value = ParseValue();
        SkipWhitespace();

        // 値の後に余分な文字が残っていたら、書き手の意図と違う解釈をしている
        if (position < text.Length)
        {
            throw Malformed($"値の後に余分な文字がある: '{text[position]}'");
        }

        return value;
    }

    private NbtTag ParseValue()
    {
        SkipWhitespace();

        if (position >= text.Length)
        {
            throw Malformed("値が来るべき位置で入力が尽きた");
        }

        char c = text[position];

        if (c == '{')
        {
            return ParseCompound();
        }

        if (c == '[')
        {
            return ParseListOrArray();
        }

        if (c == '"' || c == '\'')
        {
            return new NbtString(ParseQuotedString());
        }

        return ParseUnquoted();
    }

    private NbtCompound ParseCompound()
    {
        Expect('{');
        NbtCompound compound = new NbtCompound();
        SkipWhitespace();

        // 空の Compound
        if (Peek() == '}')
        {
            position += 1;
            return compound;
        }

        // 要素を 1 つずつ読む
        while (true)
        {
            SkipWhitespace();

            // 末尾カンマの直後に閉じ括弧が来る形を許す
            if (Peek() == '}')
            {
                position += 1;
                return compound;
            }

            string key = ParseKey();
            SkipWhitespace();
            Expect(':');
            NbtTag value = ParseValue();
            compound.Set(key, value);

            SkipWhitespace();
            char next = Peek();

            if (next == ',')
            {
                position += 1;
            }
            else if (next == '}')
            {
                position += 1;
                return compound;
            }
            else
            {
                throw Malformed($"Compound の区切りが不正: '{next}'");
            }
        }
    }

    private NbtTag ParseListOrArray()
    {
        Expect('[');

        // "[B;" のような型付き配列かどうかを先に判定する
        if (position + 1 < text.Length && text[position + 1] == ';')
        {
            char marker = text[position];

            if (marker == 'B' || marker == 'I' || marker == 'L')
            {
                position += 2;
                return ParseTypedArray(marker);
            }
        }

        return ParseList();
    }

    private NbtList ParseList()
    {
        NbtList list = new NbtList();
        SkipWhitespace();

        // 空のリスト
        if (Peek() == ']')
        {
            position += 1;
            return list;
        }

        // 要素を 1 つずつ読む
        while (true)
        {
            SkipWhitespace();

            // 末尾カンマの直後に閉じ括弧が来る形を許す
            if (Peek() == ']')
            {
                position += 1;
                return list;
            }

            NbtTag value = ParseValue();

            // 異種リストはバイナリ NBT へ写せないため受理しない (adr/0006)
            if (list.ElementType != TagType.End && list.ElementType != value.Type)
            {
                throw Malformed(
                    $"リストに異なる型が混在している: {list.ElementType.AsString()} と {value.Type.AsString()}");
            }

            list.Add(value);

            SkipWhitespace();
            char next = Peek();

            if (next == ',')
            {
                position += 1;
            }
            else if (next == ']')
            {
                position += 1;
                return list;
            }
            else
            {
                throw Malformed($"リストの区切りが不正: '{next}'");
            }
        }
    }

    private NbtTag ParseTypedArray(char marker)
    {
        List<long> values = new List<long>();
        SkipWhitespace();

        // 空でなければ要素を読む
        if (Peek() == ']')
        {
            position += 1;
        }
        else
        {
            while (true)
            {
                SkipWhitespace();

                // 末尾カンマの直後に閉じ括弧が来る形を許す
                if (Peek() == ']')
                {
                    position += 1;
                    break;
                }

                NbtTag element = ParseValue();
                values.Add(ToIntegral(element));

                SkipWhitespace();
                char next = Peek();

                if (next == ',')
                {
                    position += 1;
                }
                else if (next == ']')
                {
                    position += 1;
                    break;
                }
                else
                {
                    throw Malformed($"配列の区切りが不正: '{next}'");
                }
            }
        }

        if (marker == 'B')
        {
            sbyte[] result = new sbyte[values.Count];

            // 各要素が Byte の範囲に収まるか確認しながら詰める
            for (int i = 0; i < values.Count; i++)
            {
                if (values[i] < sbyte.MinValue || values[i] > sbyte.MaxValue)
                {
                    throw Malformed($"ByteArray の要素が範囲外: {values[i]}");
                }

                result[i] = (sbyte)values[i];
            }

            return new NbtByteArray(result);
        }

        if (marker == 'I')
        {
            int[] result = new int[values.Count];

            // 各要素が Int の範囲に収まるか確認しながら詰める
            for (int i = 0; i < values.Count; i++)
            {
                if (values[i] < int.MinValue || values[i] > int.MaxValue)
                {
                    throw Malformed($"IntArray の要素が範囲外: {values[i]}");
                }

                result[i] = (int)values[i];
            }

            return new NbtIntArray(result);
        }

        return new NbtLongArray(values.ToArray());
    }

    /// <summary>整数タグから値を取り出す。整数以外なら例外。</summary>
    private long ToIntegral(NbtTag tag)
    {
        switch (tag)
        {
            case NbtByte value:
                return value.Value;
            case NbtShort value:
                return value.Value;
            case NbtInt value:
                return value.Value;
            case NbtLong value:
                return value.Value;
            default:
                throw Malformed($"型付き配列の要素が整数でない: {tag.Type.AsString()}");
        }
    }

    private string ParseKey()
    {
        char c = Peek();

        if (c == '"' || c == '\'')
        {
            return ParseQuotedString();
        }

        string bare = ReadBareToken();

        if (bare.Length == 0)
        {
            throw Malformed("Compound のキーが空");
        }

        return bare;
    }

    private string ParseQuotedString()
    {
        char quote = text[position];
        position += 1;
        StringBuilder builder = new StringBuilder();

        // 閉じ引用符が来るまで読む
        while (true)
        {
            if (position >= text.Length)
            {
                throw Malformed("文字列が閉じられていない");
            }

            char c = text[position];

            if (c == quote)
            {
                position += 1;
                return builder.ToString();
            }

            if (c == '\\')
            {
                position += 1;
                AppendEscape(builder);
            }
            else
            {
                builder.Append(c);
                position += 1;
            }
        }
    }

    private void AppendEscape(StringBuilder builder)
    {
        if (position >= text.Length)
        {
            throw Malformed("エスケープが途中で切れている");
        }

        char c = text[position];
        position += 1;

        switch (c)
        {
            case '\\':
                builder.Append('\\');
                return;
            case '"':
                builder.Append('"');
                return;
            case '\'':
                builder.Append('\'');
                return;
            case 'b':
                builder.Append('\b');
                return;
            case 's':
                builder.Append(' ');
                return;
            case 't':
                builder.Append('\t');
                return;
            case 'n':
                builder.Append('\n');
                return;
            case 'f':
                builder.Append('\f');
                return;
            case 'r':
                builder.Append('\r');
                return;
            case 'x':
                builder.Append((char)ReadHexDigits(2));
                return;
            case 'u':
                builder.Append((char)ReadHexDigits(4));
                return;
            case 'U':
                AppendCodePoint(builder, ReadHexDigits(8));
                return;
            case 'N':
                AppendNamedCharacter(builder);
                return;
            default:
                throw Malformed($"未知のエスケープ: '\\{c}'");
        }
    }

    private long ReadHexDigits(int count)
    {
        if (position + count > text.Length)
        {
            throw Malformed("エスケープの16進数字が足りない");
        }

        long value = 0;

        // 指定桁数ぶん 16進数字を読む
        for (int i = 0; i < count; i++)
        {
            char c = text[position + i];
            int digit = HexDigitValue(c);

            if (digit < 0)
            {
                throw Malformed($"エスケープに16進数字でない文字がある: '{c}'");
            }

            value = (value * 16) + digit;
        }

        position += count;
        return value;
    }

    private void AppendCodePoint(StringBuilder builder, long codePoint)
    {
        // Unicode のコードポイント範囲を外れていないか確認する
        if (codePoint < 0 || codePoint > 0x10FFFF)
        {
            throw Malformed($"コードポイントが範囲外: U+{codePoint:X}");
        }

        builder.Append(char.ConvertFromUtf32((int)codePoint));
    }

    /// <summary>Unicode 文字名によるエスケープ <c>\N{...}</c> を読む。</summary>
    private void AppendNamedCharacter(StringBuilder builder)
    {
        Expect('{');
        int start = position;

        // 閉じ波括弧まで名前を読む
        while (position < text.Length && text[position] != '}')
        {
            position += 1;
        }

        if (position >= text.Length)
        {
            throw Malformed("文字名エスケープが閉じられていない");
        }

        string name = text.Substring(start, position - start);
        position += 1;

        // .NET には Unicode 文字名の表が無い。実装間で表が揃わないため対応しない
        throw new SpringNbtException(
            ErrorCode.UnsupportedFeature,
            $"文字名によるエスケープには対応していない: \\N{{{name}}}");
    }

    private NbtTag ParseUnquoted()
    {
        string token = ReadBareToken();

        if (token.Length == 0)
        {
            throw Malformed($"値が来るべき位置に解釈できない文字がある: '{PeekOrNul()}'");
        }

        // bool(...) / uuid(...) の関数呼び出し
        SkipWhitespace();
        if (PeekOrNul() == '(' && (token == "bool" || token == "uuid"))
        {
            return ParseFunction(token);
        }

        if (token == "true")
        {
            return new NbtByte(1);
        }

        if (token == "false")
        {
            return new NbtByte(0);
        }

        NbtTag? number = TryParseNumber(token);

        if (number is not null)
        {
            return number;
        }

        return new NbtString(token);
    }

    private NbtTag ParseFunction(string name)
    {
        Expect('(');
        NbtTag argument = ParseValue();
        SkipWhitespace();
        Expect(')');

        if (name == "bool")
        {
            // 0 以外を真とする
            if (ToIntegral(argument) != 0)
            {
                return new NbtByte(1);
            }

            return new NbtByte(0);
        }

        return UuidToIntArray(argument);
    }

    private NbtIntArray UuidToIntArray(NbtTag argument)
    {
        if (argument is not NbtString stringTag)
        {
            throw Malformed("uuid() の引数は文字列でなければならない");
        }

        if (!Guid.TryParse(stringTag.Value, out Guid guid))
        {
            throw Malformed($"UUID として解釈できない: {stringTag.Value}");
        }

        // UUID を上位から 32bit ずつ 4 要素の IntArray へ写す
        byte[] bytes = guid.ToByteArray(bigEndian: true);
        int[] result = new int[4];

        for (int i = 0; i < 4; i++)
        {
            result[i] = (bytes[i * 4] << 24)
                | (bytes[(i * 4) + 1] << 16)
                | (bytes[(i * 4) + 2] << 8)
                | bytes[(i * 4) + 3];
        }

        return new NbtIntArray(result);
    }

    /// <summary>
    /// 数値トークンを解釈する。数値として読めなければ null を返す（文字列として扱われる）。
    /// </summary>
    private NbtTag? TryParseNumber(string token)
    {
        bool negative = false;
        int start = 0;

        if (token[0] == '+' || token[0] == '-')
        {
            negative = token[0] == '-';
            start = 1;
        }

        string body = token.Substring(start);

        if (body.Length == 0)
        {
            return null;
        }

        bool isHex = body.Length > 2 && body[0] == '0' && (body[1] == 'x' || body[1] == 'X');
        bool isBinary = body.Length > 2 && body[0] == '0' && (body[1] == 'b' || body[1] == 'B')
            && IsBinaryBody(body.Substring(2));

        char widthSuffix = '\0';
        bool unsignedSuffix = false;

        // 幅接尾辞を末尾から剥がす。16進では b/d/f が数字と紛れるため s/l だけを認める
        char last = body[body.Length - 1];
        bool suffixAllowed;

        if (isHex)
        {
            suffixAllowed = last == 's' || last == 'S' || last == 'l' || last == 'L';
        }
        else
        {
            suffixAllowed = "bBsSlLfFdD".IndexOf(last) >= 0;
        }

        if (suffixAllowed && body.Length >= 2)
        {
            widthSuffix = char.ToLowerInvariant(last);
            body = body.Substring(0, body.Length - 1);

            // 符号接尾辞 u / s は幅接尾辞の手前に置かれる
            if (body.Length >= 2)
            {
                char signChar = body[body.Length - 1];

                if (signChar == 'u' || signChar == 'U')
                {
                    unsignedSuffix = true;
                    body = body.Substring(0, body.Length - 1);
                }
                else if (signChar == 's' || signChar == 'S')
                {
                    body = body.Substring(0, body.Length - 1);
                }
            }

            // 接尾辞を剥がした結果で基数を判定し直す
            isHex = body.Length > 2 && body[0] == '0' && (body[1] == 'x' || body[1] == 'X');
            isBinary = body.Length > 2 && body[0] == '0' && (body[1] == 'b' || body[1] == 'B')
                && IsBinaryBody(body.Substring(2));
        }

        body = body.Replace("_", string.Empty);

        if (body.Length == 0)
        {
            return null;
        }

        // 特殊な浮動小数点値
        if (body == "Infinity")
        {
            return MakeFloating(double.PositiveInfinity, negative, widthSuffix);
        }

        if (body == "NaN")
        {
            return MakeFloating(double.NaN, negative, widthSuffix);
        }

        if (isHex)
        {
            return ParseRadix(body.Substring(2), 16, negative, widthSuffix, unsignedSuffix);
        }

        if (isBinary)
        {
            return ParseRadix(body.Substring(2), 2, negative, widthSuffix, unsignedSuffix);
        }

        bool looksFloating = body.IndexOf('.') >= 0 || body.IndexOf('e') >= 0 || body.IndexOf('E') >= 0;

        if (looksFloating || widthSuffix == 'f' || widthSuffix == 'd')
        {
            if (!double.TryParse(body, NumberStyles.Float, CultureInfo.InvariantCulture, out double parsed))
            {
                return null;
            }

            return MakeFloating(parsed, negative, widthSuffix);
        }

        return ParseRadix(body, 10, negative, widthSuffix, unsignedSuffix);
    }

    private static bool IsBinaryBody(string body)
    {
        if (body.Length == 0)
        {
            return false;
        }

        // 2進リテラルの本体は 0 と 1 と桁区切りだけ
        foreach (char c in body)
        {
            if (c != '0' && c != '1' && c != '_')
            {
                return false;
            }
        }

        return true;
    }

    private NbtTag MakeFloating(double value, bool negative, char widthSuffix)
    {
        double signed;

        if (negative)
        {
            signed = -value;
        }
        else
        {
            signed = value;
        }

        if (widthSuffix == 'f')
        {
            return new NbtFloat((float)signed);
        }

        // 接尾辞なしの小数は Double
        if (widthSuffix == '\0' || widthSuffix == 'd')
        {
            return new NbtDouble(signed);
        }

        throw Malformed($"小数に整数の接尾辞 '{widthSuffix}' は付けられない");
    }

    private NbtTag? ParseRadix(string digits, int radix, bool negative, char widthSuffix, bool unsignedSuffix)
    {
        if (digits.Length == 0)
        {
            return null;
        }

        ulong magnitude = 0;

        // 桁を1つずつ積み上げる。桁あふれはその場で検出する
        foreach (char c in digits)
        {
            int digit = DigitValue(c, radix);

            if (digit < 0)
            {
                return null;
            }

            ulong next = (magnitude * (ulong)radix) + (ulong)digit;

            if (next < magnitude)
            {
                throw Malformed($"整数が大きすぎる: {digits}");
            }

            magnitude = next;
        }

        return MakeIntegral(magnitude, negative, widthSuffix, unsignedSuffix);
    }

    private NbtTag MakeIntegral(ulong magnitude, bool negative, char widthSuffix, bool unsignedSuffix)
    {
        if (unsignedSuffix)
        {
            // 符号なし指定は、その幅の符号なし最大値までを受け付けて符号付きへ読み替える
            switch (widthSuffix)
            {
                case 'b':
                    return new NbtByte(unchecked((sbyte)CheckUnsigned(magnitude, byte.MaxValue)));
                case 's':
                    return new NbtShort(unchecked((short)CheckUnsigned(magnitude, ushort.MaxValue)));
                case 'l':
                    return new NbtLong(unchecked((long)CheckUnsigned(magnitude, ulong.MaxValue)));
                default:
                    return new NbtInt(unchecked((int)CheckUnsigned(magnitude, uint.MaxValue)));
            }
        }

        long value = ToSigned(magnitude, negative);

        switch (widthSuffix)
        {
            case 'b':
                return new NbtByte((sbyte)CheckRange(value, sbyte.MinValue, sbyte.MaxValue, "byte"));
            case 's':
                return new NbtShort((short)CheckRange(value, short.MinValue, short.MaxValue, "short"));
            case 'l':
                return new NbtLong(value);
            case 'f':
                return new NbtFloat((float)value);
            case 'd':
                return new NbtDouble(value);
            default:
                // 接尾辞なしの整数は Int。暗黙に Long へ格上げしない
                return new NbtInt((int)CheckRange(value, int.MinValue, int.MaxValue, "int"));
        }
    }

    private ulong CheckUnsigned(ulong magnitude, ulong max)
    {
        if (magnitude > max)
        {
            throw Malformed($"符号なし整数が範囲外: {magnitude} (上限 {max})");
        }

        return magnitude;
    }

    private long ToSigned(ulong magnitude, bool negative)
    {
        if (negative)
        {
            // long.MinValue の絶対値は long に収まらないため個別に扱う
            if (magnitude == 9223372036854775808UL)
            {
                return long.MinValue;
            }

            if (magnitude > long.MaxValue)
            {
                throw Malformed($"整数が小さすぎる: -{magnitude}");
            }

            return -(long)magnitude;
        }

        if (magnitude > long.MaxValue)
        {
            throw Malformed($"整数が大きすぎる: {magnitude}");
        }

        return (long)magnitude;
    }

    private long CheckRange(long value, long min, long max, string typeName)
    {
        if (value < min || value > max)
        {
            throw Malformed($"{typeName} の範囲外: {value}");
        }

        return value;
    }

    private static int DigitValue(char c, int radix)
    {
        int value = HexDigitValue(c);

        if (value < 0 || value >= radix)
        {
            return -1;
        }

        return value;
    }

    private static int HexDigitValue(char c)
    {
        if (c >= '0' && c <= '9')
        {
            return c - '0';
        }

        if (c >= 'a' && c <= 'f')
        {
            return (c - 'a') + 10;
        }

        if (c >= 'A' && c <= 'F')
        {
            return (c - 'A') + 10;
        }

        return -1;
    }

    private string ReadBareToken()
    {
        int start = position;

        // 引用符なしトークンに使える文字を読み進める
        while (position < text.Length && IsBareChar(text[position]))
        {
            position += 1;
        }

        return text.Substring(start, position - start);
    }

    /// <summary>引用符なしで書ける文字か。</summary>
    internal static bool IsBareChar(char c)
    {
        if (c >= 'a' && c <= 'z')
        {
            return true;
        }

        if (c >= 'A' && c <= 'Z')
        {
            return true;
        }

        if (c >= '0' && c <= '9')
        {
            return true;
        }

        return c == '_' || c == '-' || c == '.' || c == '+';
    }

    private void SkipWhitespace()
    {
        // 空白・改行・タブを読み飛ばす
        while (position < text.Length && char.IsWhiteSpace(text[position]))
        {
            position += 1;
        }
    }

    private char Peek()
    {
        if (position >= text.Length)
        {
            throw Malformed("入力が途中で尽きた");
        }

        return text[position];
    }

    /// <summary>末尾でも例外にしない先読み。入力が尽きていれば NUL を返す。</summary>
    private char PeekOrNul()
    {
        if (position >= text.Length)
        {
            return '\0';
        }

        return text[position];
    }

    private void Expect(char expected)
    {
        SkipWhitespace();

        if (position >= text.Length)
        {
            throw Malformed($"'{expected}' が来るべき位置で入力が尽きた");
        }

        if (text[position] != expected)
        {
            throw Malformed($"'{expected}' を期待したが '{text[position]}' だった");
        }

        position += 1;
    }

    private SpringNbtException Malformed(string message)
    {
        return SpringNbtException.Malformed($"SNBT ({position} 文字目): {message}");
    }
}

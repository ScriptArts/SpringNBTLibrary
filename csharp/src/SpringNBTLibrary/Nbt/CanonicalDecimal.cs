using System.Globalization;
using System.Text;

namespace SpringNBTLibrary.Nbt;

/// <summary>
/// 浮動小数点の正準10進表記。
/// </summary>
/// <remarks>
/// <para>
/// 各言語の標準の数値書式は互いに一致しない。指数表記へ切り替わる閾値も、
/// 指数部の桁数も、E の大文字小文字も処理系ごとに違う。
/// そのままでは SNBT 出力の言語間一致が成立しないため、書式をここで固定する。
/// </para>
/// <para>仕様: <c>docs/spec/11-snbt.md</c> 5.1章</para>
/// </remarks>
internal static class CanonicalDecimal
{
    /// <summary>固定小数点表記を使う10進指数の下限。</summary>
    private const int MinFixedExponent = -4;

    /// <summary>固定小数点表記を使う10進指数の上限。</summary>
    private const int MaxFixedExponent = 16;

    /// <summary>binary32 を正準10進表記へ変換する。</summary>
    internal static string FromFloat(float value)
    {
        if (float.IsNaN(value))
        {
            return "NaN";
        }

        if (float.IsPositiveInfinity(value))
        {
            return "Infinity";
        }

        if (float.IsNegativeInfinity(value))
        {
            return "-Infinity";
        }

        // 有効数字を 1 桁ずつ増やし、読み戻してビット一致する最短の表記を探す
        for (int precision = 1; precision <= 9; precision++)
        {
            string candidate = value.ToString(
                "E" + (precision - 1).ToString(CultureInfo.InvariantCulture),
                CultureInfo.InvariantCulture);

            float parsed = float.Parse(candidate, NumberStyles.Float, CultureInfo.InvariantCulture);

            if (BitConverter.SingleToInt32Bits(parsed) == BitConverter.SingleToInt32Bits(value))
            {
                return Format(candidate);
            }
        }

        // 9 桁あれば binary32 は必ず往復するので、ここへは来ない
        return Format(value.ToString("E8", CultureInfo.InvariantCulture));
    }

    /// <summary>binary64 を正準10進表記へ変換する。</summary>
    internal static string FromDouble(double value)
    {
        if (double.IsNaN(value))
        {
            return "NaN";
        }

        if (double.IsPositiveInfinity(value))
        {
            return "Infinity";
        }

        if (double.IsNegativeInfinity(value))
        {
            return "-Infinity";
        }

        // 有効数字を 1 桁ずつ増やし、読み戻してビット一致する最短の表記を探す
        for (int precision = 1; precision <= 17; precision++)
        {
            string candidate = value.ToString(
                "E" + (precision - 1).ToString(CultureInfo.InvariantCulture),
                CultureInfo.InvariantCulture);

            double parsed = double.Parse(candidate, NumberStyles.Float, CultureInfo.InvariantCulture);

            if (BitConverter.DoubleToInt64Bits(parsed) == BitConverter.DoubleToInt64Bits(value))
            {
                return Format(candidate);
            }
        }

        // 17 桁あれば binary64 は必ず往復するので、ここへは来ない
        return Format(value.ToString("E16", CultureInfo.InvariantCulture));
    }

    /// <summary>
    /// 指数表記の文字列（例 <c>"7.5E-001"</c>）から、仕様が定める正準表記を組み立てる。
    /// </summary>
    private static string Format(string exponential)
    {
        bool negative = false;
        int index = 0;

        if (exponential[0] == '-' || exponential[0] == '+')
        {
            negative = exponential[0] == '-';
            index = 1;
        }

        // 仮数部の数字だけを集める
        StringBuilder digitsBuilder = new StringBuilder();

        while (index < exponential.Length
            && exponential[index] != 'E' && exponential[index] != 'e')
        {
            char c = exponential[index];

            if (c >= '0' && c <= '9')
            {
                digitsBuilder.Append(c);
            }

            index += 1;
        }

        int exponent = int.Parse(
            exponential.Substring(index + 1), NumberStyles.Integer, CultureInfo.InvariantCulture);

        string digits = TrimTrailingZeros(digitsBuilder.ToString());

        return Compose(negative, digits, exponent);
    }

    /// <summary>末尾のゼロを取り除く。すべてゼロなら "0" を残す。</summary>
    private static string TrimTrailingZeros(string digits)
    {
        int end = digits.Length;

        // 末尾から連続するゼロを削る
        while (end > 1 && digits[end - 1] == '0')
        {
            end -= 1;
        }

        return digits.Substring(0, end);
    }

    /// <summary>数字列と10進指数から最終的な文字列を組み立てる。</summary>
    private static string Compose(bool negative, string digits, int exponent)
    {
        StringBuilder builder = new StringBuilder();

        if (negative)
        {
            builder.Append('-');
        }

        // 値が 0 のときは指数に関わらず 0.0 と書く
        if (digits == "0")
        {
            builder.Append("0.0");
            return builder.ToString();
        }

        if (exponent < MinFixedExponent || exponent > MaxFixedExponent)
        {
            // 指数表記
            builder.Append(digits[0]);
            builder.Append('.');

            if (digits.Length > 1)
            {
                builder.Append(digits, 1, digits.Length - 1);
            }
            else
            {
                builder.Append('0');
            }

            builder.Append('E');
            builder.Append(exponent.ToString(CultureInfo.InvariantCulture));
            return builder.ToString();
        }

        if (exponent >= 0)
        {
            // 整数部は先頭 (exponent + 1) 桁。足りなければゼロで右詰めする
            int integerDigits = exponent + 1;

            if (digits.Length >= integerDigits)
            {
                builder.Append(digits, 0, integerDigits);
            }
            else
            {
                builder.Append(digits);

                for (int i = digits.Length; i < integerDigits; i++)
                {
                    builder.Append('0');
                }
            }

            builder.Append('.');

            if (digits.Length > integerDigits)
            {
                builder.Append(digits, integerDigits, digits.Length - integerDigits);
            }
            else
            {
                builder.Append('0');
            }

            return builder.ToString();
        }

        // 指数が負なら "0." に続けてゼロを詰めてから数字を置く
        builder.Append("0.");

        for (int i = 0; i < (-exponent) - 1; i++)
        {
            builder.Append('0');
        }

        builder.Append(digits);
        return builder.ToString();
    }
}

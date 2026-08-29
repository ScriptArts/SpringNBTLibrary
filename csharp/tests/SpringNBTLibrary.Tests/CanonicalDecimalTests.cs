using SpringNBTLibrary.Nbt;

namespace SpringNBTLibrary.Tests;

/// <summary>
/// 浮動小数点の正準10進表記。仕様: docs/spec/11-snbt.md 5.1章
/// </summary>
/// <remarks>
/// ここが言語ごとにずれると SNBT 出力の言語間一致が崩れるため、
/// 期待値は仕様の記述から手で書き下している。
/// </remarks>
public class CanonicalDecimalTests
{
    [Theory]
    [InlineData(1.0f, "1.0f")]
    [InlineData(-1.0f, "-1.0f")]
    [InlineData(0.0f, "0.0f")]
    [InlineData(0.75f, "0.75f")]
    [InlineData(0.49823147f, "0.49823147f")]
    [InlineData(2000.0f, "2000.0f")]
    [InlineData(1e20f, "1.0E20f")]
    [InlineData(1e-30f, "1.0E-30f")]
    [InlineData(0.5f, "0.5f")]
    [InlineData(123.456f, "123.456f")]
    public void FloatFormatting(float value, string expected)
    {
        Assert.Equal(expected, Snbt.Write(new NbtFloat(value)));
    }

    [Theory]
    [InlineData(1.0, "1.0d")]
    [InlineData(0.015, "0.015d")]
    [InlineData(2000.0, "2000.0d")]
    [InlineData(0.4931287132182315, "0.4931287132182315d")]
    [InlineData(3.141592653589793, "3.141592653589793d")]
    [InlineData(1e20, "1.0E20d")]
    [InlineData(1e17, "1.0E17d")]
    [InlineData(1e16, "10000000000000000.0d")]
    [InlineData(1e-4, "0.0001d")]
    [InlineData(1e-5, "1.0E-5d")]
    public void DoubleFormatting(double value, string expected)
    {
        Assert.Equal(expected, Snbt.Write(new NbtDouble(value)));
    }

    [Fact]
    public void NegativeZeroKeepsItsSign()
    {
        Assert.Equal("-0.0d", Snbt.Write(new NbtDouble(-0.0)));
        Assert.Equal("-0.0f", Snbt.Write(new NbtFloat(-0.0f)));
    }

    [Fact]
    public void SpecialValues()
    {
        Assert.Equal("NaNd", Snbt.Write(new NbtDouble(double.NaN)));
        Assert.Equal("Infinityd", Snbt.Write(new NbtDouble(double.PositiveInfinity)));
        Assert.Equal("-Infinityd", Snbt.Write(new NbtDouble(double.NegativeInfinity)));
        Assert.Equal("NaNf", Snbt.Write(new NbtFloat(float.NaN)));
        Assert.Equal("Infinityf", Snbt.Write(new NbtFloat(float.PositiveInfinity)));
    }

    [Fact]
    public void EveryFormattedValueParsesBackToTheSameBits()
    {
        double[] doubles =
        {
            0.0, -0.0, 1.0, -1.0, 0.1, 1.0 / 3.0, 1e300, 1e-300,
            double.Epsilon, double.MaxValue, double.MinValue, 4903.0,
        };

        // 出力した文字列を読み戻して、ビットパターンが変わらないことを確かめる
        foreach (double value in doubles)
        {
            string text = Snbt.Write(new NbtDouble(value));
            NbtDouble parsed = Assert.IsType<NbtDouble>(Snbt.Parse(text));
            Assert.Equal(BitConverter.DoubleToInt64Bits(value), BitConverter.DoubleToInt64Bits(parsed.Value));
        }

        float[] floats =
        {
            0.0f, -0.0f, 1.0f, -1.0f, 0.1f, 1.0f / 3.0f, 1e30f, 1e-30f,
            float.Epsilon, float.MaxValue, float.MinValue, 4903.0f,
        };

        foreach (float value in floats)
        {
            string text = Snbt.Write(new NbtFloat(value));
            NbtFloat parsed = Assert.IsType<NbtFloat>(Snbt.Parse(text));
            Assert.Equal(BitConverter.SingleToInt32Bits(value), BitConverter.SingleToInt32Bits(parsed.Value));
        }
    }
}

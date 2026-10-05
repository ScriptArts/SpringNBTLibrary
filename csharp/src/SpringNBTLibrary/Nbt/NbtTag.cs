namespace SpringNBTLibrary.Nbt;

/// <summary>
/// NBTのタグ
/// 具象型は<see cref="NbtByte"/>などの派生クラス
/// </summary>
/// <remarks>
/// <para>
/// パターンマッチで分岐することを想定している
/// <c>if (tag is NbtInt intTag) { ... }</c>のように使う
/// </para>
/// </remarks>
public abstract class NbtTag
{
    /// <summary>ライブラリ外での派生を防ぐため、コンストラクタは内部限定にする</summary>
    internal NbtTag()
    {
    }

    /// <summary>このタグの型</summary>
    public abstract TagType Type { get; }

    /// <summary>このタグの深いコピーを作る</summary>
    public abstract NbtTag Copy();
}

/// <summary>TAG_Byte
/// 8bit符号付き整数</summary>
public sealed class NbtByte : NbtTag
{
    /// <summary>値を指定して作る</summary>
    public NbtByte(sbyte value)
    {
        Value = value;
    }

    /// <summary>保持している値</summary>
    public sbyte Value { get; set; }

    /// <inheritdoc/>
    public override TagType Type => TagType.Byte;

    /// <inheritdoc/>
    public override NbtTag Copy() => new NbtByte(Value);

    /// <inheritdoc/>
    public override bool Equals(object? obj) => obj is NbtByte other && other.Value == Value;

    /// <inheritdoc/>
    public override int GetHashCode() => HashCode.Combine(Type, Value);

    /// <inheritdoc/>
    public override string ToString() => $"{Value}b";
}

/// <summary>TAG_Short
/// 16bit符号付き整数</summary>
public sealed class NbtShort : NbtTag
{
    /// <summary>値を指定して作る</summary>
    public NbtShort(short value)
    {
        Value = value;
    }

    /// <summary>保持している値</summary>
    public short Value { get; set; }

    /// <inheritdoc/>
    public override TagType Type => TagType.Short;

    /// <inheritdoc/>
    public override NbtTag Copy() => new NbtShort(Value);

    /// <inheritdoc/>
    public override bool Equals(object? obj) => obj is NbtShort other && other.Value == Value;

    /// <inheritdoc/>
    public override int GetHashCode() => HashCode.Combine(Type, Value);

    /// <inheritdoc/>
    public override string ToString() => $"{Value}s";
}

/// <summary>TAG_Int
/// 32bit符号付き整数</summary>
public sealed class NbtInt : NbtTag
{
    /// <summary>値を指定して作る</summary>
    public NbtInt(int value)
    {
        Value = value;
    }

    /// <summary>保持している値</summary>
    public int Value { get; set; }

    /// <inheritdoc/>
    public override TagType Type => TagType.Int;

    /// <inheritdoc/>
    public override NbtTag Copy() => new NbtInt(Value);

    /// <inheritdoc/>
    public override bool Equals(object? obj) => obj is NbtInt other && other.Value == Value;

    /// <inheritdoc/>
    public override int GetHashCode() => HashCode.Combine(Type, Value);

    /// <inheritdoc/>
    public override string ToString() => Value.ToString();
}

/// <summary>TAG_Long
/// 64bit符号付き整数</summary>
public sealed class NbtLong : NbtTag
{
    /// <summary>値を指定して作る</summary>
    public NbtLong(long value)
    {
        Value = value;
    }

    /// <summary>保持している値</summary>
    public long Value { get; set; }

    /// <inheritdoc/>
    public override TagType Type => TagType.Long;

    /// <inheritdoc/>
    public override NbtTag Copy() => new NbtLong(Value);

    /// <inheritdoc/>
    public override bool Equals(object? obj) => obj is NbtLong other && other.Value == Value;

    /// <inheritdoc/>
    public override int GetHashCode() => HashCode.Combine(Type, Value);

    /// <inheritdoc/>
    public override string ToString() => $"{Value}L";
}

/// <summary>TAG_Float
/// IEEE 754 binary32</summary>
public sealed class NbtFloat : NbtTag
{
    /// <summary>値を指定して作る</summary>
    public NbtFloat(float value)
    {
        Value = value;
    }

    /// <summary>保持している値</summary>
    public float Value { get; set; }

    /// <inheritdoc/>
    public override TagType Type => TagType.Float;

    /// <inheritdoc/>
    public override NbtTag Copy() => new NbtFloat(Value);

    /// <inheritdoc/>
    /// <remarks>NaNや-0.0を区別するため、値ではなくビットパターンで比較する</remarks>
    public override bool Equals(object? obj)
    {
        return obj is NbtFloat other
            && BitConverter.SingleToInt32Bits(other.Value) == BitConverter.SingleToInt32Bits(Value);
    }

    /// <inheritdoc/>
    public override int GetHashCode() => HashCode.Combine(Type, BitConverter.SingleToInt32Bits(Value));

    /// <inheritdoc/>
    public override string ToString() => $"{Value}f";
}

/// <summary>TAG_Double
/// IEEE 754 binary64</summary>
public sealed class NbtDouble : NbtTag
{
    /// <summary>値を指定して作る</summary>
    public NbtDouble(double value)
    {
        Value = value;
    }

    /// <summary>保持している値</summary>
    public double Value { get; set; }

    /// <inheritdoc/>
    public override TagType Type => TagType.Double;

    /// <inheritdoc/>
    public override NbtTag Copy() => new NbtDouble(Value);

    /// <inheritdoc/>
    /// <remarks>NaNや-0.0を区別するため、値ではなくビットパターンで比較する</remarks>
    public override bool Equals(object? obj)
    {
        return obj is NbtDouble other
            && BitConverter.DoubleToInt64Bits(other.Value) == BitConverter.DoubleToInt64Bits(Value);
    }

    /// <inheritdoc/>
    public override int GetHashCode() => HashCode.Combine(Type, BitConverter.DoubleToInt64Bits(Value));

    /// <inheritdoc/>
    public override string ToString() => $"{Value}d";
}

/// <summary>TAG_String
/// MUTF-8で符号化される文字列</summary>
public sealed class NbtString : NbtTag
{
    private string value;

    /// <summary>値を指定して作る</summary>
    /// <exception cref="SpringNbtException">
    /// MUTF-8に符号化すると65535バイトを超える場合（<see cref="ErrorCode.InvalidArgument"/>）
    /// </exception>
    public NbtString(string value)
    {
        ArgumentNullException.ThrowIfNull(value);
        Validate(value);
        this.value = value;
    }

    /// <summary>保持している値</summary>
    /// <exception cref="SpringNbtException">
    /// MUTF-8に符号化すると65535バイトを超える場合（<see cref="ErrorCode.InvalidArgument"/>）
    /// </exception>
    public string Value
    {
        get => value;
        set
        {
            ArgumentNullException.ThrowIfNull(value);
            Validate(value);
            this.value = value;
        }
    }

    /// <inheritdoc/>
    public override TagType Type => TagType.String;

    /// <inheritdoc/>
    public override NbtTag Copy() => new NbtString(value);

    /// <inheritdoc/>
    public override bool Equals(object? obj)
    {
        return obj is NbtString other && string.Equals(other.value, value, StringComparison.Ordinal);
    }

    /// <inheritdoc/>
    public override int GetHashCode() => HashCode.Combine(Type, value);

    /// <inheritdoc/>
    public override string ToString() => value;

    /// <summary>長さフィールドがu16のため、符号化後65535バイトを超える文字列は保持できない</summary>
    private static void Validate(string candidate)
    {
        int byteLength = Mutf8.ByteLength(candidate);

        // 長さフィールドはu16
        // 65535を超えると書き出せない
        if (byteLength > Mutf8.MaxByteLength)
        {
            throw SpringNbtException.InvalidArgument(
                $"文字列が長すぎる: MUTF-8 で {byteLength} バイト (上限 {Mutf8.MaxByteLength})");
        }
    }
}

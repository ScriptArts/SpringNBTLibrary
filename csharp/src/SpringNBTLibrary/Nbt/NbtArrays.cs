namespace SpringNBTLibrary.Nbt;

/// <summary>TAG_Byte_Array
/// 8bit 符号付き整数の配列</summary>
public sealed class NbtByteArray : NbtTag
{
    /// <summary>配列を指定して作る
    /// 渡した配列をそのまま保持する（コピーしない）</summary>
    public NbtByteArray(sbyte[] value)
    {
        ArgumentNullException.ThrowIfNull(value);
        Value = value;
    }

    /// <summary>保持している配列</summary>
    public sbyte[] Value { get; set; }

    /// <inheritdoc/>
    public override TagType Type => TagType.ByteArray;

    /// <inheritdoc/>
    public override NbtTag Copy() => new NbtByteArray((sbyte[])Value.Clone());

    /// <inheritdoc/>
    public override bool Equals(object? obj)
    {
        return obj is NbtByteArray other && other.Value.AsSpan().SequenceEqual(Value);
    }

    /// <inheritdoc/>
    public override int GetHashCode() => HashCode.Combine(Type, Value.Length);

    /// <inheritdoc/>
    public override string ToString() => $"[B; {Value.Length} 要素]";
}

/// <summary>TAG_Int_Array
/// 32bit 符号付き整数の配列</summary>
public sealed class NbtIntArray : NbtTag
{
    /// <summary>配列を指定して作る
    /// 渡した配列をそのまま保持する（コピーしない）</summary>
    public NbtIntArray(int[] value)
    {
        ArgumentNullException.ThrowIfNull(value);
        Value = value;
    }

    /// <summary>保持している配列</summary>
    public int[] Value { get; set; }

    /// <inheritdoc/>
    public override TagType Type => TagType.IntArray;

    /// <inheritdoc/>
    public override NbtTag Copy() => new NbtIntArray((int[])Value.Clone());

    /// <inheritdoc/>
    public override bool Equals(object? obj)
    {
        return obj is NbtIntArray other && other.Value.AsSpan().SequenceEqual(Value);
    }

    /// <inheritdoc/>
    public override int GetHashCode() => HashCode.Combine(Type, Value.Length);

    /// <inheritdoc/>
    public override string ToString() => $"[I; {Value.Length} 要素]";
}

/// <summary>TAG_Long_Array
/// 64bit 符号付き整数の配列</summary>
public sealed class NbtLongArray : NbtTag
{
    /// <summary>配列を指定して作る
    /// 渡した配列をそのまま保持する（コピーしない）</summary>
    public NbtLongArray(long[] value)
    {
        ArgumentNullException.ThrowIfNull(value);
        Value = value;
    }

    /// <summary>保持している配列</summary>
    public long[] Value { get; set; }

    /// <inheritdoc/>
    public override TagType Type => TagType.LongArray;

    /// <inheritdoc/>
    public override NbtTag Copy() => new NbtLongArray((long[])Value.Clone());

    /// <inheritdoc/>
    public override bool Equals(object? obj)
    {
        return obj is NbtLongArray other && other.Value.AsSpan().SequenceEqual(Value);
    }

    /// <inheritdoc/>
    public override int GetHashCode() => HashCode.Combine(Type, Value.Length);

    /// <inheritdoc/>
    public override string ToString() => $"[L; {Value.Length} 要素]";
}

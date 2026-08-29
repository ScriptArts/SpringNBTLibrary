namespace SpringNBTLibrary.Nbt;

/// <summary>
/// <see cref="NbtCompound"/> の型付き取得子。
/// </summary>
/// <remarks>
/// <para>
/// 「キーが無い」と「型が違う」は区別する。
/// <c>Opt*</c> はキーが無ければ null を返し、<c>Get*</c> は例外を送出する。
/// どちらも型が違えば必ず <see cref="ErrorCode.UnexpectedTagType"/> の例外になる。
/// </para>
/// <para>仕様: <c>docs/spec/10-nbt-binary.md</c> 7.1章</para>
/// </remarks>
public sealed partial class NbtCompound
{
    /// <summary>TAG_Byte を取得する。キーが無ければ null。</summary>
    public sbyte? OptByte(string key)
    {
        NbtByte? tag = Cast<NbtByte>(key);

        if (tag is null)
        {
            return null;
        }

        return tag.Value;
    }

    /// <summary>TAG_Byte を取得する。キーが無ければ例外。</summary>
    public sbyte GetByte(string key) => Require<NbtByte>(key).Value;

    /// <summary>TAG_Short を取得する。キーが無ければ null。</summary>
    public short? OptShort(string key)
    {
        NbtShort? tag = Cast<NbtShort>(key);

        if (tag is null)
        {
            return null;
        }

        return tag.Value;
    }

    /// <summary>TAG_Short を取得する。キーが無ければ例外。</summary>
    public short GetShort(string key) => Require<NbtShort>(key).Value;

    /// <summary>TAG_Int を取得する。キーが無ければ null。</summary>
    public int? OptInt(string key)
    {
        NbtInt? tag = Cast<NbtInt>(key);

        if (tag is null)
        {
            return null;
        }

        return tag.Value;
    }

    /// <summary>TAG_Int を取得する。キーが無ければ例外。</summary>
    public int GetInt(string key) => Require<NbtInt>(key).Value;

    /// <summary>TAG_Long を取得する。キーが無ければ null。</summary>
    public long? OptLong(string key)
    {
        NbtLong? tag = Cast<NbtLong>(key);

        if (tag is null)
        {
            return null;
        }

        return tag.Value;
    }

    /// <summary>TAG_Long を取得する。キーが無ければ例外。</summary>
    public long GetLong(string key) => Require<NbtLong>(key).Value;

    /// <summary>TAG_Float を取得する。キーが無ければ null。</summary>
    public float? OptFloat(string key)
    {
        NbtFloat? tag = Cast<NbtFloat>(key);

        if (tag is null)
        {
            return null;
        }

        return tag.Value;
    }

    /// <summary>TAG_Float を取得する。キーが無ければ例外。</summary>
    public float GetFloat(string key) => Require<NbtFloat>(key).Value;

    /// <summary>TAG_Double を取得する。キーが無ければ null。</summary>
    public double? OptDouble(string key)
    {
        NbtDouble? tag = Cast<NbtDouble>(key);

        if (tag is null)
        {
            return null;
        }

        return tag.Value;
    }

    /// <summary>TAG_Double を取得する。キーが無ければ例外。</summary>
    public double GetDouble(string key) => Require<NbtDouble>(key).Value;

    /// <summary>TAG_Byte を真偽値として取得する。0 以外が true。キーが無ければ null。</summary>
    public bool? OptBool(string key)
    {
        sbyte? raw = OptByte(key);

        if (raw is null)
        {
            return null;
        }

        return raw.Value != 0;
    }

    /// <summary>TAG_Byte を真偽値として取得する。0 以外が true。キーが無ければ例外。</summary>
    public bool GetBool(string key) => GetByte(key) != 0;

    /// <summary>TAG_String を取得する。キーが無ければ null。</summary>
    public string? OptString(string key)
    {
        NbtString? tag = Cast<NbtString>(key);

        if (tag is null)
        {
            return null;
        }

        return tag.Value;
    }

    /// <summary>TAG_String を取得する。キーが無ければ例外。</summary>
    public string GetString(string key) => Require<NbtString>(key).Value;

    /// <summary>TAG_Byte_Array を取得する。キーが無ければ null。</summary>
    public sbyte[]? OptByteArray(string key)
    {
        NbtByteArray? tag = Cast<NbtByteArray>(key);

        if (tag is null)
        {
            return null;
        }

        return tag.Value;
    }

    /// <summary>TAG_Byte_Array を取得する。キーが無ければ例外。</summary>
    public sbyte[] GetByteArray(string key) => Require<NbtByteArray>(key).Value;

    /// <summary>TAG_Int_Array を取得する。キーが無ければ null。</summary>
    public int[]? OptIntArray(string key)
    {
        NbtIntArray? tag = Cast<NbtIntArray>(key);

        if (tag is null)
        {
            return null;
        }

        return tag.Value;
    }

    /// <summary>TAG_Int_Array を取得する。キーが無ければ例外。</summary>
    public int[] GetIntArray(string key) => Require<NbtIntArray>(key).Value;

    /// <summary>TAG_Long_Array を取得する。キーが無ければ null。</summary>
    public long[]? OptLongArray(string key)
    {
        NbtLongArray? tag = Cast<NbtLongArray>(key);

        if (tag is null)
        {
            return null;
        }

        return tag.Value;
    }

    /// <summary>TAG_Long_Array を取得する。キーが無ければ例外。</summary>
    public long[] GetLongArray(string key) => Require<NbtLongArray>(key).Value;

    /// <summary>TAG_List を取得する。キーが無ければ null。</summary>
    public NbtList? OptList(string key) => Cast<NbtList>(key);

    /// <summary>TAG_List を取得する。キーが無ければ例外。</summary>
    public NbtList GetList(string key) => Require<NbtList>(key);

    /// <summary>TAG_Compound を取得する。キーが無ければ null。</summary>
    public NbtCompound? OptCompound(string key) => Cast<NbtCompound>(key);

    /// <summary>TAG_Compound を取得する。キーが無ければ例外。</summary>
    public NbtCompound GetCompound(string key) => Require<NbtCompound>(key);

    /// <summary>
    /// キーに対応するタグを目的の型として取り出す。キーが無ければ null、型が違えば例外。
    /// </summary>
    private T? Cast<T>(string key)
        where T : NbtTag
    {
        NbtTag? tag = Opt(key);

        if (tag is null)
        {
            return null;
        }

        if (tag is T typed)
        {
            return typed;
        }

        throw SpringNbtException.UnexpectedTagType(
            $"キー \"{key}\" は {tag.Type.AsString()} だが {typeof(T).Name} として取り出そうとした");
    }

    /// <summary>
    /// キーに対応するタグを目的の型として取り出す。キーが無くても型が違っても例外。
    /// </summary>
    private T Require<T>(string key)
        where T : NbtTag
    {
        T? typed = Cast<T>(key);

        if (typed is null)
        {
            throw SpringNbtException.InvalidArgument($"キーが存在しない: {key}");
        }

        return typed;
    }
}

namespace SpringNBTLibrary.Nbt;

/// <summary>
/// <see cref="NbtCompound"/>の型付き設定子
/// </summary>
/// <remarks>
/// <para>
/// <c>Set(key, new NbtInt(42))</c>と書かずに済むようにするための糖衣
/// 取得子の<c>GetInt</c>と対になる
/// </para>
/// </remarks>
public sealed partial class NbtCompound
{
    /// <summary>TAG_Byteとして設定する</summary>
    public void SetByte(string key, sbyte value) => Set(key, new NbtByte(value));

    /// <summary>TAG_Shortとして設定する</summary>
    public void SetShort(string key, short value) => Set(key, new NbtShort(value));

    /// <summary>TAG_Intとして設定する</summary>
    public void SetInt(string key, int value) => Set(key, new NbtInt(value));

    /// <summary>TAG_Longとして設定する</summary>
    public void SetLong(string key, long value) => Set(key, new NbtLong(value));

    /// <summary>TAG_Floatとして設定する</summary>
    public void SetFloat(string key, float value) => Set(key, new NbtFloat(value));

    /// <summary>TAG_Doubleとして設定する</summary>
    public void SetDouble(string key, double value) => Set(key, new NbtDouble(value));

    /// <summary>
    /// TAG_Byteとして設定する
    /// trueは1、falseは0
    /// </summary>
    public void SetBool(string key, bool value)
    {
        // NBTに真偽値の専用型は無いので、TAG_Byteの0 / 1で表す
        if (value)
        {
            SetByte(key, 1);
        }
        else
        {
            SetByte(key, 0);
        }
    }

    /// <summary>TAG_Stringとして設定する</summary>
    /// <exception cref="SpringNbtException">
    /// MUTF-8に符号化すると65535バイトを超える場合（<see cref="ErrorCode.InvalidArgument"/>）
    /// </exception>
    public void SetString(string key, string value) => Set(key, new NbtString(value));

    /// <summary>TAG_Byte_Arrayとして設定する</summary>
    public void SetByteArray(string key, sbyte[] value) => Set(key, new NbtByteArray(value));

    /// <summary>TAG_Int_Arrayとして設定する</summary>
    public void SetIntArray(string key, int[] value) => Set(key, new NbtIntArray(value));

    /// <summary>TAG_Long_Arrayとして設定する</summary>
    public void SetLongArray(string key, long[] value) => Set(key, new NbtLongArray(value));
}

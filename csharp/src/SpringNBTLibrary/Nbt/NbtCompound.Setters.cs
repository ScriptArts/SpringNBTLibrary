namespace SpringNBTLibrary.Nbt;

/// <summary>
/// <see cref="NbtCompound"/> の型付き設定子
/// </summary>
/// <remarks>
/// <para>
/// <c>Set(key, new NbtInt(42))</c> と書かずに済むようにするための糖衣
/// 取得子の <c>GetInt</c> と対になる
/// </para>
/// <para>仕様: <c>docs/spec/10-nbt-binary.md</c> 7.1章</para>
/// </remarks>
public sealed partial class NbtCompound
{
    /// <summary>TAG_Byte として設定する</summary>
    public void SetByte(string key, sbyte value) => Set(key, new NbtByte(value));

    /// <summary>TAG_Short として設定する</summary>
    public void SetShort(string key, short value) => Set(key, new NbtShort(value));

    /// <summary>TAG_Int として設定する</summary>
    public void SetInt(string key, int value) => Set(key, new NbtInt(value));

    /// <summary>TAG_Long として設定する</summary>
    public void SetLong(string key, long value) => Set(key, new NbtLong(value));

    /// <summary>TAG_Float として設定する</summary>
    public void SetFloat(string key, float value) => Set(key, new NbtFloat(value));

    /// <summary>TAG_Double として設定する</summary>
    public void SetDouble(string key, double value) => Set(key, new NbtDouble(value));

    /// <summary>
    /// TAG_Byte として設定する
    /// true は 1、false は 0
    /// </summary>
    public void SetBool(string key, bool value)
    {
        // NBT に真偽値の専用型は無いので TAG_Byte の 0 / 1 で表す
        if (value)
        {
            SetByte(key, 1);
        }
        else
        {
            SetByte(key, 0);
        }
    }

    /// <summary>TAG_String として設定する</summary>
    /// <exception cref="SpringNbtException">
    /// MUTF-8 に符号化すると 65535 バイトを超える場合（<see cref="ErrorCode.InvalidArgument"/>）
    /// </exception>
    public void SetString(string key, string value) => Set(key, new NbtString(value));

    /// <summary>TAG_Byte_Array として設定する</summary>
    public void SetByteArray(string key, sbyte[] value) => Set(key, new NbtByteArray(value));

    /// <summary>TAG_Int_Array として設定する</summary>
    public void SetIntArray(string key, int[] value) => Set(key, new NbtIntArray(value));

    /// <summary>TAG_Long_Array として設定する</summary>
    public void SetLongArray(string key, long[] value) => Set(key, new NbtLongArray(value));
}

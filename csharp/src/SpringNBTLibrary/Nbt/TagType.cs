namespace SpringNBTLibrary.Nbt;

/// <summary>
/// NBT のタグ型
/// 値は仕様が定めるタグIDと一致する
/// </summary>
/// <remarks>仕様: <c>docs/spec/10-nbt-binary.md</c> 1章</remarks>
public enum TagType : byte
{
    /// <summary>TAG_End (0)
    /// Compound の終端を表す</summary>
    End = 0,

    /// <summary>TAG_Byte (1)</summary>
    Byte = 1,

    /// <summary>TAG_Short (2)</summary>
    Short = 2,

    /// <summary>TAG_Int (3)</summary>
    Int = 3,

    /// <summary>TAG_Long (4)</summary>
    Long = 4,

    /// <summary>TAG_Float (5)</summary>
    Float = 5,

    /// <summary>TAG_Double (6)</summary>
    Double = 6,

    /// <summary>TAG_Byte_Array (7)</summary>
    ByteArray = 7,

    /// <summary>TAG_String (8)</summary>
    String = 8,

    /// <summary>TAG_List (9)</summary>
    List = 9,

    /// <summary>TAG_Compound (10)</summary>
    Compound = 10,

    /// <summary>TAG_Int_Array (11)</summary>
    IntArray = 11,

    /// <summary>TAG_Long_Array (12)</summary>
    LongArray = 12,
}

/// <summary><see cref="TagType"/> の拡張メソッド</summary>
public static class TagTypeExtensions
{
    /// <summary>
    /// 適合性テストで言語間比較に使う識別子を返す
    /// </summary>
    public static string AsString(this TagType type)
    {
        switch (type)
        {
            case TagType.End:
                return "end";
            case TagType.Byte:
                return "byte";
            case TagType.Short:
                return "short";
            case TagType.Int:
                return "int";
            case TagType.Long:
                return "long";
            case TagType.Float:
                return "float";
            case TagType.Double:
                return "double";
            case TagType.ByteArray:
                return "byte_array";
            case TagType.String:
                return "string";
            case TagType.List:
                return "list";
            case TagType.Compound:
                return "compound";
            case TagType.IntArray:
                return "int_array";
            case TagType.LongArray:
                return "long_array";
            default:
                throw new ArgumentOutOfRangeException(nameof(type), type, "未知の TagType");
        }
    }

    /// <summary>
    /// タグIDから <see cref="TagType"/> を得る
    /// 未知のIDなら例外を送出する
    /// </summary>
    /// <exception cref="SpringNbtException">未知のタグID（<see cref="ErrorCode.MalformedData"/>）</exception>
    public static TagType FromId(byte id)
    {
        // 0..12 の範囲外はすべて不正なタグID
        if (id > (byte)TagType.LongArray)
        {
            throw SpringNbtException.Malformed($"未知のタグID: {id}");
        }

        return (TagType)id;
    }
}

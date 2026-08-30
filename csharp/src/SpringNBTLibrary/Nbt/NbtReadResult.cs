namespace SpringNBTLibrary.Nbt;

/// <summary>
/// 位置を指定した読み込みの結果
/// </summary>
/// <remarks>
/// <para>読んだタグと、その直後の位置を持つ</para>
/// <para>
/// 続けて読むときは <see cref="End"/> を次の開始位置として渡す
/// </para>
/// <para>仕様: <c>docs/spec/10-nbt-binary.md</c> 3.1章</para>
/// </remarks>
public sealed class NbtReadResult
{
    /// <summary>読んだタグと、その直後の位置を指定して作る</summary>
    public NbtReadResult(NamedTag tag, int end)
    {
        Tag = tag;
        End = end;
    }

    /// <summary>読んだタグ</summary>
    public NamedTag Tag { get; }

    /// <summary>読み終わった直後の位置</summary>
    public int End { get; }
}

using System.Collections;

namespace SpringNBTLibrary.Nbt;

/// <summary>
/// TAG_List
/// 要素型が 1 つに固定されたタグの列
/// </summary>
/// <remarks>
/// <para>
/// 空リストの要素型は <see cref="TagType.End"/>
/// 最初の要素を追加した時点で型が確定する
/// 全要素を削除しても確定済みの要素型は維持される（読み書きの往復で型が消えないようにするため）
/// </para>
/// <para>仕様: <c>docs/spec/10-nbt-binary.md</c> 7.2章</para>
/// </remarks>
public sealed class NbtList : NbtTag, IList<NbtTag>
{
    private readonly List<NbtTag> items = new List<NbtTag>();

    /// <summary>空のリストを作る
    /// 要素型は未確定</summary>
    public NbtList()
    {
        ElementType = TagType.End;
    }

    /// <summary>要素型を明示して空のリストを作る</summary>
    public NbtList(TagType elementType)
    {
        ElementType = elementType;
    }

    /// <summary>要素型を明示し、要素を与えてリストを作る</summary>
    /// <exception cref="SpringNbtException">
    /// 要素型と一致しない要素が含まれる場合（<see cref="ErrorCode.UnexpectedTagType"/>）
    /// </exception>
    public NbtList(TagType elementType, IEnumerable<NbtTag> elements)
        : this(elementType)
    {
        ArgumentNullException.ThrowIfNull(elements);

        // 1 要素ずつ型検査しながら追加する
        foreach (NbtTag element in elements)
        {
            Add(element);
        }
    }

    /// <summary>要素の型
    /// 空で未確定なら <see cref="TagType.End"/></summary>
    public TagType ElementType { get; private set; }

    /// <inheritdoc/>
    public override TagType Type => TagType.List;

    /// <inheritdoc/>
    public int Count => items.Count;

    /// <inheritdoc/>
    public bool IsReadOnly => false;

    /// <inheritdoc/>
    /// <exception cref="SpringNbtException">
    /// 要素型と一致しないタグを設定した場合（<see cref="ErrorCode.UnexpectedTagType"/>）
    /// </exception>
    public NbtTag this[int index]
    {
        get => items[index];
        set
        {
            ArgumentNullException.ThrowIfNull(value);
            EnsureElementType(value);
            items[index] = value;
        }
    }

    /// <inheritdoc/>
    /// <exception cref="SpringNbtException">
    /// 要素型と一致しないタグを追加した場合（<see cref="ErrorCode.UnexpectedTagType"/>）
    /// </exception>
    public void Add(NbtTag item)
    {
        ArgumentNullException.ThrowIfNull(item);
        EnsureElementType(item);
        items.Add(item);
    }

    /// <inheritdoc/>
    /// <exception cref="SpringNbtException">
    /// 要素型と一致しないタグを挿入した場合（<see cref="ErrorCode.UnexpectedTagType"/>）
    /// </exception>
    public void Insert(int index, NbtTag item)
    {
        ArgumentNullException.ThrowIfNull(item);
        EnsureElementType(item);
        items.Insert(index, item);
    }

    /// <summary>全要素を削除する
    /// 確定済みの要素型は維持する</summary>
    public void Clear() => items.Clear();

    /// <inheritdoc/>
    public bool Contains(NbtTag item) => items.Contains(item);

    /// <inheritdoc/>
    public void CopyTo(NbtTag[] array, int arrayIndex) => items.CopyTo(array, arrayIndex);

    /// <inheritdoc/>
    public int IndexOf(NbtTag item) => items.IndexOf(item);

    /// <inheritdoc/>
    public bool Remove(NbtTag item) => items.Remove(item);

    /// <inheritdoc/>
    public void RemoveAt(int index) => items.RemoveAt(index);

    /// <inheritdoc/>
    public IEnumerator<NbtTag> GetEnumerator() => items.GetEnumerator();

    IEnumerator IEnumerable.GetEnumerator() => GetEnumerator();

    /// <inheritdoc/>
    public override NbtTag Clone()
    {
        NbtList copy = new NbtList(ElementType);

        // 要素も深くコピーする
        foreach (NbtTag item in items)
        {
            copy.items.Add(item.Clone());
        }

        return copy;
    }

    /// <inheritdoc/>
    public override bool Equals(object? obj)
    {
        if (obj is not NbtList other)
        {
            return false;
        }

        if (other.ElementType != ElementType || other.items.Count != items.Count)
        {
            return false;
        }

        // 同じ位置の要素同士を比較する
        for (int i = 0; i < items.Count; i++)
        {
            if (!items[i].Equals(other.items[i]))
            {
                return false;
            }
        }

        return true;
    }

    /// <inheritdoc/>
    public override int GetHashCode() => HashCode.Combine(Type, ElementType, items.Count);

    /// <inheritdoc/>
    public override string ToString() => $"[{ElementType.AsString()}; {items.Count} 要素]";

    /// <summary>
    /// 追加しようとしているタグが要素型と一致するか調べる
    /// リストが未確定なら、そのタグの型で確定させる
    /// </summary>
    private void EnsureElementType(NbtTag item)
    {
        // TAG_End はリストの要素になれない
        if (item.Type == TagType.End)
        {
            throw SpringNbtException.UnexpectedTagType("TAG_End はリストの要素にできない");
        }

        if (ElementType == TagType.End)
        {
            // 未確定のリストは最初の要素で型が決まる
            ElementType = item.Type;
        }
        else if (ElementType != item.Type)
        {
            throw SpringNbtException.UnexpectedTagType(
                $"リストの要素型は {ElementType.AsString()} だが {item.Type.AsString()} を追加しようとした");
        }
    }
}

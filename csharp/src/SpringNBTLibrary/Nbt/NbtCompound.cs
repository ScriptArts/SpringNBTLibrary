using System.Collections;

namespace SpringNBTLibrary.Nbt;

/// <summary>
/// TAG_Compound。挿入順を保持する、名前付きタグのマップ。
/// </summary>
/// <remarks>
/// <para>
/// 既存キーへの再設定は位置を維持したまま値だけを置き換える。
/// これにより読み込んだ順序が書き出しでも保たれ、ラウンドトリップが成立する。
/// </para>
/// <para>仕様: <c>docs/spec/10-nbt-binary.md</c> 7.1章</para>
/// </remarks>
public sealed partial class NbtCompound : NbtTag, IEnumerable<KeyValuePair<string, NbtTag>>
{
    private readonly List<KeyValuePair<string, NbtTag>> entries = new List<KeyValuePair<string, NbtTag>>();
    private readonly Dictionary<string, int> index = new Dictionary<string, int>(StringComparer.Ordinal);

    /// <summary>空の Compound を作る。</summary>
    public NbtCompound()
    {
    }

    /// <inheritdoc/>
    public override TagType Type => TagType.Compound;

    /// <summary>要素数。</summary>
    public int Count => entries.Count;

    /// <summary>挿入順のキー一覧。</summary>
    public IEnumerable<string> Keys
    {
        get
        {
            // 挿入順を保つため entries 側から取り出す
            foreach (KeyValuePair<string, NbtTag> entry in entries)
            {
                yield return entry.Key;
            }
        }
    }

    /// <summary>キーで値を取得・設定する。</summary>
    /// <exception cref="SpringNbtException">
    /// 取得時にキーが存在しない場合（<see cref="ErrorCode.InvalidArgument"/>）。
    /// </exception>
    public NbtTag this[string key]
    {
        get
        {
            NbtTag? found = Opt(key);

            if (found is null)
            {
                throw SpringNbtException.InvalidArgument($"キーが存在しない: {key}");
            }

            return found;
        }
        set => Set(key, value);
    }

    /// <summary>キーが存在するか。</summary>
    public bool ContainsKey(string key)
    {
        ArgumentNullException.ThrowIfNull(key);
        return index.ContainsKey(key);
    }

    /// <summary>
    /// 値を設定する。既存キーなら位置を維持して値だけ置き換える。
    /// </summary>
    public void Set(string key, NbtTag value)
    {
        ArgumentNullException.ThrowIfNull(key);
        ArgumentNullException.ThrowIfNull(value);

        // TAG_End は Compound の終端マーカーなので値として持てない
        if (value.Type == TagType.End)
        {
            throw SpringNbtException.UnexpectedTagType("TAG_End は Compound の値にできない");
        }

        if (index.TryGetValue(key, out int position))
        {
            // 既存キーは順序を変えずに値だけ差し替える
            entries[position] = new KeyValuePair<string, NbtTag>(key, value);
        }
        else
        {
            index[key] = entries.Count;
            entries.Add(new KeyValuePair<string, NbtTag>(key, value));
        }
    }

    /// <summary>キーを削除する。削除できたら true。</summary>
    public bool Remove(string key)
    {
        ArgumentNullException.ThrowIfNull(key);

        if (!index.TryGetValue(key, out int position))
        {
            return false;
        }

        entries.RemoveAt(position);
        index.Remove(key);

        // 削除位置より後ろのキーは添字がひとつ前へずれる
        for (int i = position; i < entries.Count; i++)
        {
            index[entries[i].Key] = i;
        }

        return true;
    }

    /// <summary>全要素を削除する。</summary>
    public void Clear()
    {
        entries.Clear();
        index.Clear();
    }

    /// <summary>キーに対応するタグを返す。存在しなければ null。</summary>
    public NbtTag? Opt(string key)
    {
        ArgumentNullException.ThrowIfNull(key);

        if (index.TryGetValue(key, out int position))
        {
            return entries[position].Value;
        }

        return null;
    }

    /// <summary>キーに対応するタグを返す。存在しなければ例外。</summary>
    /// <exception cref="SpringNbtException">
    /// キーが存在しない場合（<see cref="ErrorCode.InvalidArgument"/>）。
    /// </exception>
    public NbtTag Get(string key) => this[key];

    /// <inheritdoc/>
    public IEnumerator<KeyValuePair<string, NbtTag>> GetEnumerator() => entries.GetEnumerator();

    IEnumerator IEnumerable.GetEnumerator() => GetEnumerator();

    /// <inheritdoc/>
    public override NbtTag Clone()
    {
        NbtCompound copy = new NbtCompound();

        // 挿入順のまま深くコピーする
        foreach (KeyValuePair<string, NbtTag> entry in entries)
        {
            copy.Set(entry.Key, entry.Value.Clone());
        }

        return copy;
    }

    /// <inheritdoc/>
    public override bool Equals(object? obj)
    {
        if (obj is not NbtCompound other || other.entries.Count != entries.Count)
        {
            return false;
        }

        // 順序も含めて一致することを確認する
        for (int i = 0; i < entries.Count; i++)
        {
            if (!string.Equals(entries[i].Key, other.entries[i].Key, StringComparison.Ordinal))
            {
                return false;
            }

            if (!entries[i].Value.Equals(other.entries[i].Value))
            {
                return false;
            }
        }

        return true;
    }

    /// <inheritdoc/>
    public override int GetHashCode() => HashCode.Combine(Type, entries.Count);

    /// <inheritdoc/>
    public override string ToString() => $"{{{entries.Count} 要素}}";
}

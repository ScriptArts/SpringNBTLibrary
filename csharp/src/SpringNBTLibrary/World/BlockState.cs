using System.Text;
using SpringNBTLibrary.Nbt;

namespace SpringNBTLibrary.World;

/// <summary>
/// ブロックの状態
/// 名前と、任意のプロパティの組
/// </summary>
/// <remarks>
/// <para>
/// プロパティは**常に名前の昇順で保持する**
/// こうしておくと文字列表現が一意になり、
/// 全言語で同じ出力になる
/// Minecraft が書き出した並び順は
/// <see cref="PalettedContainer"/> がパレットを生の NBT のまま持つことで守られるので、
/// 触っていないブロックの並びが崩れることはない
/// </para>
/// <para>仕様: <c>docs/spec/30-chunk-format.md</c> 2.1章</para>
/// </remarks>
public sealed class BlockState : IEquatable<BlockState>
{
    private readonly SortedDictionary<string, string> properties;

    /// <summary>名前とプロパティを指定して作る</summary>
    /// <param name="name">
    /// ブロックID
    /// 名前空間が省略されていたら <c>minecraft:</c> を補う
    /// </param>
    /// <param name="properties">プロパティ
    /// null なら空</param>
    public BlockState(string name, IEnumerable<KeyValuePair<string, string>>? properties = null)
    {
        ArgumentNullException.ThrowIfNull(name);
        Name = Normalize(name);
        this.properties = new SortedDictionary<string, string>(StringComparer.Ordinal);

        if (properties is null)
        {
            return;
        }

        // 与えられたプロパティを取り込む
        // 並びは常に昇順になる
        foreach (KeyValuePair<string, string> entry in properties)
        {
            this.properties[entry.Key] = entry.Value;
        }
    }

    /// <summary>ブロックID（名前空間つき）</summary>
    public string Name { get; }

    /// <summary>プロパティ
    /// 名前の昇順</summary>
    public IReadOnlyDictionary<string, string> Properties => properties;

    /// <summary>プロパティを取得する
    /// 無ければ null</summary>
    public string? Property(string key)
    {
        if (properties.TryGetValue(key, out string? value))
        {
            return value;
        }

        return null;
    }

    /// <summary>プロパティを 1 つ差し替えた新しい状態を返す</summary>
    public BlockState With(string key, string value)
    {
        ArgumentNullException.ThrowIfNull(key);
        ArgumentNullException.ThrowIfNull(value);

        BlockState result = new BlockState(Name, properties);
        result.properties[key] = value;
        return result;
    }

    /// <summary>
    /// <c>minecraft:oak_stairs[facing=north,half=top]</c> 形式の文字列から作る
    /// </summary>
    /// <exception cref="SpringNbtException">
    /// 形式が不正な場合（<see cref="ErrorCode.MalformedData"/>）
    /// </exception>
    public static BlockState Parse(string text)
    {
        ArgumentNullException.ThrowIfNull(text);

        int bracket = text.IndexOf('[', StringComparison.Ordinal);

        // 角括弧が無ければプロパティ無しのブロック名
        if (bracket < 0)
        {
            if (text.Length == 0)
            {
                throw SpringNbtException.InvalidArgument("ブロック名が空");
            }

            return new BlockState(text);
        }

        if (!text.EndsWith(']'))
        {
            throw SpringNbtException.InvalidArgument($"角括弧が閉じられていない: {text}");
        }

        string name = text.Substring(0, bracket);
        string body = text.Substring(bracket + 1, text.Length - bracket - 2);
        BlockState state = new BlockState(name);

        if (body.Length == 0)
        {
            return state;
        }

        // "key=value" をカンマ区切りで読む
        foreach (string pair in body.Split(','))
        {
            int equals = pair.IndexOf('=', StringComparison.Ordinal);

            if (equals < 0)
            {
                throw SpringNbtException.InvalidArgument($"プロパティに '=' が無い: {pair}");
            }

            string key = pair.Substring(0, equals).Trim();
            string value = pair.Substring(equals + 1).Trim();

            if (key.Length == 0)
            {
                throw SpringNbtException.InvalidArgument($"プロパティ名が空: {pair}");
            }

            // どちらが採用されたか分からないまま書き込まれるのを避けるため、重複は弾く
            if (state.properties.ContainsKey(key))
            {
                throw SpringNbtException.InvalidArgument($"プロパティ名が重複している: {key}");
            }

            state.properties[key] = value;
        }

        return state;
    }

    /// <summary>パレット要素の NBT から作る</summary>
    /// <exception cref="SpringNbtException">
    /// <c>Name</c> が無い、または <c>Properties</c> の値が文字列でない場合
    /// </exception>
    public static BlockState FromNbt(NbtCompound nbt)
    {
        ArgumentNullException.ThrowIfNull(nbt);
        BlockState state = new BlockState(nbt.GetString("Name"));
        NbtCompound? propertiesTag = nbt.OptCompound("Properties");

        if (propertiesTag is null)
        {
            return state;
        }

        // Properties の値はすべて文字列（数値や真偽値も文字列で入る）
        foreach (KeyValuePair<string, NbtTag> entry in propertiesTag)
        {
            if (entry.Value is not NbtString text)
            {
                throw SpringNbtException.UnexpectedTagType(
                    $"Properties の \"{entry.Key}\" が文字列でない: {entry.Value.Type.AsString()}");
            }

            state.properties[entry.Key] = text.Value;
        }

        return state;
    }

    /// <summary>パレット要素の NBT へ変換する</summary>
    /// <remarks>
    /// プロパティが空なら <c>Properties</c> キー自体を出力しない
    /// Minecraft と同じ振る舞い
    /// </remarks>
    public NbtCompound ToNbt()
    {
        NbtCompound result = new NbtCompound();
        result.Set("Name", new NbtString(Name));

        if (properties.Count == 0)
        {
            return result;
        }

        NbtCompound propertiesTag = new NbtCompound();

        // 名前の昇順で並ぶ
        foreach (KeyValuePair<string, string> entry in properties)
        {
            propertiesTag.Set(entry.Key, new NbtString(entry.Value));
        }

        result.Set("Properties", propertiesTag);
        return result;
    }

    /// <summary>名前空間が省略されていたら <c>minecraft:</c> を補う</summary>
    private static string Normalize(string name)
    {
        if (name.Contains(':', StringComparison.Ordinal))
        {
            return name;
        }

        return "minecraft:" + name;
    }

    /// <inheritdoc/>
    public bool Equals(BlockState? other)
    {
        if (other is null || !string.Equals(other.Name, Name, StringComparison.Ordinal))
        {
            return false;
        }

        if (other.properties.Count != properties.Count)
        {
            return false;
        }

        // 昇順で持っているので、順に突き合わせれば足りる
        using IEnumerator<KeyValuePair<string, string>> left = properties.GetEnumerator();
        using IEnumerator<KeyValuePair<string, string>> right = other.properties.GetEnumerator();

        // 名前と値を先頭から突き合わせる
        // 並びは昇順に揃っている
        while (left.MoveNext() && right.MoveNext())
        {
            if (!string.Equals(left.Current.Key, right.Current.Key, StringComparison.Ordinal))
            {
                return false;
            }

            if (!string.Equals(left.Current.Value, right.Current.Value, StringComparison.Ordinal))
            {
                return false;
            }
        }

        return true;
    }

    /// <inheritdoc/>
    public override bool Equals(object? obj) => Equals(obj as BlockState);

    /// <inheritdoc/>
    public override int GetHashCode() => HashCode.Combine(Name, properties.Count);

    /// <summary>
    /// <c>minecraft:oak_stairs[facing=north,half=top]</c> 形式の文字列を返す
    /// </summary>
    public override string ToString()
    {
        if (properties.Count == 0)
        {
            return Name;
        }

        StringBuilder builder = new StringBuilder(Name);
        builder.Append('[');
        bool first = true;

        // 名前の昇順で並べるので、同じ状態なら必ず同じ文字列になる
        foreach (KeyValuePair<string, string> entry in properties)
        {
            // 2 つ目以降の前に区切りのカンマを置く
            if (!first)
            {
                builder.Append(',');
            }

            first = false;
            builder.Append(entry.Key).Append('=').Append(entry.Value);
        }

        builder.Append(']');
        return builder.ToString();
    }
}

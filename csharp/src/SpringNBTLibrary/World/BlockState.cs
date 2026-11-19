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
/// こうしておくと文字列表現が一意になり、全言語で同じ出力になる
/// Minecraftが書き出した並び順は、<see cref="PalettedContainer"/>がパレットを生のNBTのまま持つことで守られる
/// そのため、触っていないブロックの並びが崩れることはない
/// </para>
/// </remarks>
public sealed class BlockState : IEquatable<BlockState>
{
    private readonly SortedDictionary<string, string> properties;

    /// <summary>名前とプロパティを指定して作る</summary>
    /// <param name="name">
    /// ブロックID
    /// 名前空間が省略されていたら<c>minecraft:</c>を補う
    /// </param>
    /// <param name="properties">プロパティ
    /// nullなら空</param>
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
    /// 無ければnull</summary>
    public string? Property(string key)
    {
        if (properties.TryGetValue(key, out string? value))
        {
            return value;
        }

        return null;
    }

    /// <summary>プロパティを1つ差し替えた新しい状態を返す</summary>
    public BlockState With(string key, string value)
    {
        ArgumentNullException.ThrowIfNull(key);
        ArgumentNullException.ThrowIfNull(value);

        BlockState result = new BlockState(Name, properties);
        result.properties[key] = value;
        return result;
    }

    /// <summary>
    /// <c>minecraft:oak_stairs[facing=north,half=top]</c>形式の文字列から作る
    /// </summary>
    /// <exception cref="SpringNbtException">
    /// 形式が不正な場合（<see cref="ErrorCode.InvalidArgument"/>）
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

        // "key=value"をカンマ区切りで読む
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

    /// <summary>パレット要素のNBTから作る</summary>
    /// <remarks>
    /// 26.3で入った形式を読む
    /// 既定の状態はブロックIDだけの文字列で、それ以外は<c>id</c>と<c>properties</c>を持つCompoundで入っている
    /// 異種リストの要素を包む<c>{"": &lt;値&gt;}</c>は外してから読む
    /// </remarks>
    /// <exception cref="SpringNbtException">
    /// 文字列でもCompoundでもない、<c>id</c>が無い、または<c>properties</c>の値が文字列でない場合
    /// </exception>
    public static BlockState FromNbt(NbtTag nbt)
    {
        ArgumentNullException.ThrowIfNull(nbt);
        NbtTag entry = PalettedContainer.UnwrapListElement(nbt);

        // 既定の状態は、ブロックIDだけの文字列で入っている
        if (entry is NbtString plain)
        {
            return new BlockState(plain.Value);
        }

        if (entry is not NbtCompound compound)
        {
            throw SpringNbtException.UnexpectedTagType(
                $"ブロックのパレット要素が string でも compound でもない: {entry.Type.AsString()}");
        }

        string? name = compound.OptString("id");

        if (name is null)
        {
            // Name / Propertiesは26.2までの形式で、読み替えると誤った状態を返しかねない
            if (compound.ContainsKey("Name"))
            {
                throw SpringNbtException.Malformed(
                    "ブロックのパレット要素に id が無い。Name は26.2までの形式で、本ライブラリでは扱わない");
            }

            throw SpringNbtException.Malformed("ブロックのパレット要素に id が無い");
        }

        BlockState state = new BlockState(name);
        NbtCompound? propertiesTag = compound.OptCompound("properties");

        if (propertiesTag is null)
        {
            return state;
        }

        // propertiesの値はすべて文字列（数値や真偽値も文字列で入る）
        foreach (KeyValuePair<string, NbtTag> property in propertiesTag)
        {
            if (property.Value is not NbtString text)
            {
                throw SpringNbtException.UnexpectedTagType(
                    $"properties の \"{property.Key}\" が文字列でない: {property.Value.Type.AsString()}");
            }

            state.properties[property.Key] = text.Value;
        }

        return state;
    }

    /// <summary>パレット要素のNBTへ変換する</summary>
    /// <remarks>
    /// プロパティが空ならブロックIDだけの文字列にし、それ以外は<c>id</c>と<c>properties</c>を持つCompoundにする
    /// Minecraftと同じ振る舞い
    /// </remarks>
    public NbtTag ToNbt()
    {
        // プロパティが無ければ、Minecraftが既定の状態を書くときと同じく文字列にする
        if (properties.Count == 0)
        {
            return new NbtString(Name);
        }

        NbtCompound result = new NbtCompound();
        result.Set("id", new NbtString(Name));
        NbtCompound propertiesTag = new NbtCompound();

        // 名前の昇順で並ぶ
        foreach (KeyValuePair<string, string> entry in properties)
        {
            propertiesTag.Set(entry.Key, new NbtString(entry.Value));
        }

        result.Set("properties", propertiesTag);
        return result;
    }

    /// <summary>名前空間が省略されていたら<c>minecraft:</c>を補う</summary>
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

        // 昇順で持っているので、順に比べれば足りる
        using IEnumerator<KeyValuePair<string, string>> left = properties.GetEnumerator();
        using IEnumerator<KeyValuePair<string, string>> right = other.properties.GetEnumerator();

        // 名前と値を先頭から比べる
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
    /// <c>minecraft:oak_stairs[facing=north,half=top]</c>形式の文字列を返す
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
            // 2つ目以降の前に区切りのカンマを置く
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

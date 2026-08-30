using SpringNBTLibrary.Nbt;

namespace SpringNBTLibrary.Tests;

/// <summary>
/// タグの等値比較と深い複製。仕様: docs/spec/10-nbt-binary.md 7.3
/// </summary>
/// <remarks>
/// 規則は全言語で同じでなければならない。
/// 各言語の同名テストと突き合わせて読むこと。
/// </remarks>
public class TagEqualityTests
{
    // NbtList / NbtCompound は IEnumerable なので、Assert.Equal を使うと
    // xUnit がコレクション比較に切り替えてしまう
    // 等値の規則そのものを見たいので、Equals を直接呼ぶ

    [Fact]
    public void SameTypeSameValueIsEqual()
    {
        Assert.True(new NbtInt(42).Equals(new NbtInt(42)));
        Assert.True(new NbtString("あ").Equals(new NbtString("あ")));
        Assert.True(new NbtByteArray(new sbyte[] { 1, 2 })
            .Equals(new NbtByteArray(new sbyte[] { 1, 2 })));

        Assert.False(new NbtInt(42).Equals(new NbtInt(43)));
        Assert.False(new NbtByteArray(new sbyte[] { 1 })
            .Equals(new NbtByteArray(new sbyte[] { 1, 2 })));
    }

    [Fact]
    public void DifferentTagTypeIsNotEqual()
    {
        // 値が同じでもタグの型が違えば別物
        Assert.False(new NbtInt(1).Equals(new NbtShort(1)));
        Assert.False(new NbtInt(1).Equals(null));
    }

    [Fact]
    public void FloatsCompareByBitPattern()
    {
        // NaN 同士は等しく、+0.0 と -0.0 は等しくない
        Assert.True(new NbtFloat(float.NaN).Equals(new NbtFloat(float.NaN)));
        Assert.True(new NbtDouble(double.NaN).Equals(new NbtDouble(double.NaN)));
        Assert.False(new NbtFloat(0.0f).Equals(new NbtFloat(-0.0f)));
        Assert.False(new NbtDouble(0.0).Equals(new NbtDouble(-0.0)));
    }

    [Fact]
    public void ListComparesElementTypeAndOrder()
    {
        NbtList left = new NbtList();
        left.Add(new NbtInt(1));
        left.Add(new NbtInt(2));

        NbtList same = new NbtList();
        same.Add(new NbtInt(1));
        same.Add(new NbtInt(2));
        Assert.True(left.Equals(same));

        NbtList reversed = new NbtList();
        reversed.Add(new NbtInt(2));
        reversed.Add(new NbtInt(1));
        Assert.False(left.Equals(reversed));

        // 空でも要素型が違えば別物
        Assert.False(new NbtList(TagType.Int).Equals(new NbtList(TagType.Byte)));
    }

    [Fact]
    public void CompoundComparesInsertionOrder()
    {
        NbtCompound left = new NbtCompound();
        left.Set("a", new NbtInt(1));
        left.Set("b", new NbtInt(2));

        NbtCompound same = new NbtCompound();
        same.Set("a", new NbtInt(1));
        same.Set("b", new NbtInt(2));
        Assert.True(left.Equals(same));

        // 中身は同じでも挿入順が違えば別物
        NbtCompound reordered = new NbtCompound();
        reordered.Set("b", new NbtInt(2));
        reordered.Set("a", new NbtInt(1));
        Assert.False(left.Equals(reordered));
    }

    [Fact]
    public void CopyIsDeep()
    {
        NbtCompound original = new NbtCompound();
        NbtList inner = new NbtList();
        inner.Add(new NbtInt(1));
        original.Set("l", inner);

        NbtCompound copied = (NbtCompound)original.Copy();
        copied.GetList("l").Add(new NbtInt(2));

        Assert.Single(original.GetList("l"));
        Assert.Equal(2, copied.GetList("l").Count);
        Assert.False(original.Equals(copied));
    }
}

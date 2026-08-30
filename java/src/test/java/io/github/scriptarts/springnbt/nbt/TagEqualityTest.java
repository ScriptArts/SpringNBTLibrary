package io.github.scriptarts.springnbt.nbt;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * タグの等値比較と深い複製
 *
 * <p>仕様: {@code docs/spec/10-nbt-binary.md} 7.3
 *
 * <p>規則は全言語で同じでなければならない
 * 各言語の同名テストと突き合わせて読むこと
 */
class TagEqualityTest {

    @Test
    @DisplayName("同じ型で同じ値なら等しい")
    void sameTypeSameValueIsEqual() {
        assertTrue(new NbtInt(42).equals(new NbtInt(42)));
        assertTrue(new NbtString("あ").equals(new NbtString("あ")));
        assertTrue(new NbtByteArray(new byte[] {1, 2}).equals(new NbtByteArray(new byte[] {1, 2})));

        assertFalse(new NbtInt(42).equals(new NbtInt(43)));
        assertFalse(new NbtByteArray(new byte[] {1}).equals(new NbtByteArray(new byte[] {1, 2})));
    }

    @Test
    @DisplayName("型が違えば等しくない")
    void differentTagTypeIsNotEqual() {
        // 値が同じでもタグの型が違えば別物
        assertFalse(new NbtInt(1).equals(new NbtShort((short) 1)));
        assertFalse(new NbtInt(1).equals(null));
    }

    @Test
    @DisplayName("浮動小数点はビットパターンで比べる")
    void floatsCompareByBitPattern() {
        // NaN 同士は等しく、+0.0 と -0.0 は等しくない
        assertTrue(new NbtFloat(Float.NaN).equals(new NbtFloat(Float.NaN)));
        assertTrue(new NbtDouble(Double.NaN).equals(new NbtDouble(Double.NaN)));
        assertFalse(new NbtFloat(0.0f).equals(new NbtFloat(-0.0f)));
        assertFalse(new NbtDouble(0.0).equals(new NbtDouble(-0.0)));
    }

    @Test
    @DisplayName("リストは要素型と並びを見る")
    void listComparesElementTypeAndOrder() {
        NbtList left = new NbtList();
        left.add(new NbtInt(1));
        left.add(new NbtInt(2));

        NbtList same = new NbtList();
        same.add(new NbtInt(1));
        same.add(new NbtInt(2));
        assertTrue(left.equals(same));

        NbtList reversed = new NbtList();
        reversed.add(new NbtInt(2));
        reversed.add(new NbtInt(1));
        assertFalse(left.equals(reversed));

        // 空でも要素型が違えば別物
        assertFalse(new NbtList(TagType.INT).equals(new NbtList(TagType.BYTE)));
    }

    @Test
    @DisplayName("Compound はキーの並び順も見る")
    void compoundComparesInsertionOrder() {
        NbtCompound left = new NbtCompound();
        left.set("a", new NbtInt(1));
        left.set("b", new NbtInt(2));

        NbtCompound same = new NbtCompound();
        same.set("a", new NbtInt(1));
        same.set("b", new NbtInt(2));
        assertTrue(left.equals(same));

        // 中身は同じでも挿入順が違えば別物
        NbtCompound reordered = new NbtCompound();
        reordered.set("b", new NbtInt(2));
        reordered.set("a", new NbtInt(1));
        assertFalse(left.equals(reordered));
    }

    @Test
    @DisplayName("copy は深いコピーになっている")
    void copyIsDeep() {
        NbtCompound original = new NbtCompound();
        NbtList inner = new NbtList();
        inner.add(new NbtInt(1));
        original.set("l", inner);

        NbtCompound copied = (NbtCompound) original.copy();
        copied.getList("l").add(new NbtInt(2));

        assertEquals(1, original.getList("l").size());
        assertEquals(2, copied.getList("l").size());
        assertFalse(original.equals(copied));
    }
}

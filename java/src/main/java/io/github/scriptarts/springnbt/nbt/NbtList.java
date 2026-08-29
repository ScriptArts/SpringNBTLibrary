package io.github.scriptarts.springnbt.nbt;

import io.github.scriptarts.springnbt.SpringNbtException;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Objects;

/**
 * TAG_List
 * 要素型が 1 つに固定されたタグの列
 *
 * <p>空リストの要素型は {@link TagType#END}
 * 最初の要素を追加した時点で型が確定する
 * 全要素を削除しても確定済みの要素型は維持される
 * （読み書きの往復で型が消えないようにするため）
 *
 * <p>仕様: {@code docs/spec/10-nbt-binary.md} 7.2章
 */
public final class NbtList implements NbtTag, Iterable<NbtTag> {

    private final List<NbtTag> items = new ArrayList<>();
    private TagType elementType;

    /** 空のリストを作る
    /** 要素型は未確定
    /** */
    public NbtList() {
        this.elementType = TagType.END;
    }

    /**
     * 要素型を明示して空のリストを作る
     *
     * @param elementType 要素型
     */
    public NbtList(TagType elementType) {
        this.elementType = Objects.requireNonNull(elementType, "elementType");
    }

    /**
     * 要素の型
     * 空で未確定なら {@link TagType#END}
     *
     * @return 要素型
     */
    public TagType elementType() {
        return elementType;
    }

    /**
     * 要素数
     *
     * @return 要素数
     */
    public int size() {
        return items.size();
    }

    /**
     * 位置を指定して取り出す
     *
     * @param index 位置
     * @return 要素
     */
    public NbtTag get(int index) {
        return items.get(index);
    }

    /**
     * 位置を指定して置き換える
     *
     * @param index 位置
     * @param item  新しい要素
     * @throws SpringNbtException 要素型と一致しない場合
     */
    public void set(int index, NbtTag item) {
        ensureElementType(item);
        items.set(index, item);
    }

    /**
     * 末尾に追加する
     *
     * @param item 要素
     * @throws SpringNbtException 要素型と一致しない場合
     */
    public void add(NbtTag item) {
        ensureElementType(item);
        items.add(item);
    }

    /**
     * 位置を指定して挿入する
     *
     * @param index 位置
     * @param item  要素
     * @throws SpringNbtException 要素型と一致しない場合
     */
    public void insert(int index, NbtTag item) {
        ensureElementType(item);
        items.add(index, item);
    }

    /**
     * 位置を指定して削除する
     *
     * @param index 位置
     */
    public void removeAt(int index) {
        items.remove(index);
    }

    /** 全要素を削除する
    /** 確定済みの要素型は維持する
    /** */
    public void clear() {
        items.clear();
    }

    @Override
    public Iterator<NbtTag> iterator() {
        return items.iterator();
    }

    @Override
    public TagType type() {
        return TagType.LIST;
    }

    @Override
    public NbtTag copy() {
        NbtList result = new NbtList(elementType);

        // 要素も深くコピーする
        for (NbtTag item : items) {
            result.items.add(item.copy());
        }

        return result;
    }

    @Override
    public boolean equals(Object other) {
        if (!(other instanceof NbtList tag)) {
            return false;
        }

        return tag.elementType == elementType && tag.items.equals(items);
    }

    @Override
    public int hashCode() {
        return Objects.hash(elementType, items);
    }

    @Override
    public String toString() {
        return "[" + elementType.asString() + "; " + items.size() + " 要素]";
    }

    /**
     * 追加しようとしているタグが要素型と一致するか調べる
     * リストが未確定なら、そのタグの型で確定させる
     */
    private void ensureElementType(NbtTag item) {
        Objects.requireNonNull(item, "item");

        if (elementType == TagType.END) {
            // 未確定のリストは最初の要素で型が決まる
            elementType = item.type();
        } else if (elementType != item.type()) {
            throw SpringNbtException.unexpectedTagType(
                    "リストの要素型は " + elementType.asString() + " だが "
                            + item.type().asString() + " を追加しようとした");
        }
    }
}

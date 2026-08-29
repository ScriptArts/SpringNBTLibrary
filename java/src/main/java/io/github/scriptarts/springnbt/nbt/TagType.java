package io.github.scriptarts.springnbt.nbt;

import io.github.scriptarts.springnbt.SpringNbtException;

/**
 * NBT のタグ型
 * {@link #id()} は仕様が定めるタグIDと一致する
 *
 * <p>仕様: {@code docs/spec/10-nbt-binary.md} 1章
 */
public enum TagType {

    /** TAG_End (0)
    /** Compound の終端を表す
    /** */
    END(0, "end"),

    /** TAG_Byte (1)
    /** */
    BYTE(1, "byte"),

    /** TAG_Short (2)
    /** */
    SHORT(2, "short"),

    /** TAG_Int (3)
    /** */
    INT(3, "int"),

    /** TAG_Long (4)
    /** */
    LONG(4, "long"),

    /** TAG_Float (5)
    /** */
    FLOAT(5, "float"),

    /** TAG_Double (6)
    /** */
    DOUBLE(6, "double"),

    /** TAG_Byte_Array (7)
    /** */
    BYTE_ARRAY(7, "byte_array"),

    /** TAG_String (8)
    /** */
    STRING(8, "string"),

    /** TAG_List (9)
    /** */
    LIST(9, "list"),

    /** TAG_Compound (10)
    /** */
    COMPOUND(10, "compound"),

    /** TAG_Int_Array (11)
    /** */
    INT_ARRAY(11, "int_array"),

    /** TAG_Long_Array (12)
    /** */
    LONG_ARRAY(12, "long_array");

    private static final TagType[] BY_ID = values();

    private final int id;
    private final String label;

    TagType(int id, String label) {
        this.id = id;
        this.label = label;
    }

    /**
     * 仕様が定めるタグID
     *
     * @return タグID
     */
    public int id() {
        return id;
    }

    /**
     * 適合性テストで言語間比較に使う識別子を返す
     *
     * @return 識別子
     */
    public String asString() {
        return label;
    }

    /**
     * タグIDから {@link TagType} を得る
     *
     * @param id タグID
     * @return タグ型
     * @throws SpringNbtException 未知のタグIDの場合
     */
    public static TagType fromId(int id) {
        // 0..12 の範囲外はすべて不正なタグID
        if (id < 0 || id >= BY_ID.length) {
            throw SpringNbtException.malformed("未知のタグID: " + id);
        }

        return BY_ID[id];
    }
}

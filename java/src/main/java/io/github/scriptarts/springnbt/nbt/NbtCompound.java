package io.github.scriptarts.springnbt.nbt;

import io.github.scriptarts.springnbt.SpringNbtException;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * TAG_Compound。挿入順を保持する、名前付きタグのマップ。
 *
 * <p>既存キーへの再設定は位置を維持したまま値だけを置き換える
 * （{@link LinkedHashMap} の既定の振る舞い）。
 * これにより読み込んだ順序が書き出しでも保たれ、ラウンドトリップが成立する。
 *
 * <p>「キーが無い」と「型が違う」は区別する。
 * {@code opt*} はキーが無ければ {@code null} を返し、{@code get*} は例外を送出する。
 * どちらも型が違えば必ず {@link io.github.scriptarts.springnbt.ErrorCode#UNEXPECTED_TAG_TYPE}
 * の例外になる。
 *
 * <p>仕様: {@code docs/spec/10-nbt-binary.md} 7.1章
 */
public final class NbtCompound implements NbtTag, Iterable<Map.Entry<String, NbtTag>> {

    private final Map<String, NbtTag> entries = new LinkedHashMap<>();

    /** 空の Compound を作る。 */
    public NbtCompound() {
        // 既定の状態で空
    }

    @Override
    public TagType type() {
        return TagType.COMPOUND;
    }

    /**
     * 要素数。
     *
     * @return 要素数
     */
    public int size() {
        return entries.size();
    }

    /**
     * 挿入順のキー一覧。
     *
     * @return キー一覧
     */
    public Set<String> keys() {
        return entries.keySet();
    }

    /**
     * キーが存在するか。
     *
     * @param key キー
     * @return 存在すれば true
     */
    public boolean containsKey(String key) {
        return entries.containsKey(key);
    }

    /**
     * 値を設定する。既存キーなら位置を維持して値だけ置き換える。
     *
     * @param key   キー
     * @param value 値
     */
    public void set(String key, NbtTag value) {
        Objects.requireNonNull(key, "key");
        Objects.requireNonNull(value, "value");
        entries.put(key, value);
    }

    /**
     * キーに対応するタグを返す。存在しなければ null。
     *
     * @param key キー
     * @return タグ、または null
     */
    public NbtTag opt(String key) {
        return entries.get(key);
    }

    /**
     * キーに対応するタグを返す。存在しなければ例外。
     *
     * @param key キー
     * @return タグ
     * @throws SpringNbtException キーが存在しない場合
     */
    public NbtTag get(String key) {
        NbtTag found = entries.get(key);

        if (found == null) {
            throw SpringNbtException.invalidArgument("キーが存在しない: " + key);
        }

        return found;
    }

    /**
     * キーを削除する。
     *
     * @param key キー
     * @return 削除できたら true
     */
    public boolean remove(String key) {
        return entries.remove(key) != null;
    }

    /** 全要素を削除する。 */
    public void clear() {
        entries.clear();
    }

    @Override
    public java.util.Iterator<Map.Entry<String, NbtTag>> iterator() {
        return entries.entrySet().iterator();
    }

    @Override
    public NbtTag copy() {
        NbtCompound result = new NbtCompound();

        // 挿入順のまま深くコピーする
        for (Map.Entry<String, NbtTag> entry : entries.entrySet()) {
            result.set(entry.getKey(), entry.getValue().copy());
        }

        return result;
    }

    @Override
    public boolean equals(Object other) {
        if (!(other instanceof NbtCompound tag)) {
            return false;
        }

        if (tag.entries.size() != entries.size()) {
            return false;
        }

        // 順序も含めて一致することを確認する
        var left = entries.entrySet().iterator();
        var right = tag.entries.entrySet().iterator();

        while (left.hasNext()) {
            Map.Entry<String, NbtTag> a = left.next();
            Map.Entry<String, NbtTag> b = right.next();

            if (!a.getKey().equals(b.getKey()) || !a.getValue().equals(b.getValue())) {
                return false;
            }
        }

        return true;
    }

    @Override
    public int hashCode() {
        return entries.hashCode();
    }

    @Override
    public String toString() {
        return "{" + entries.size() + " 要素}";
    }

    // -- 型付き取得子 -------------------------------------------------------

    /**
     * TAG_Byte を取得する。キーが無ければ null。
     *
     * @param key キー
     * @return 値、または null
     */
    public Byte optByte(String key) {
        NbtByte tag = cast(key, NbtByte.class);

        if (tag == null) {
            return null;
        }

        return tag.value();
    }

    /**
     * TAG_Byte を取得する。キーが無ければ例外。
     *
     * @param key キー
     * @return 値
     */
    public byte getByte(String key) {
        return require(key, NbtByte.class).value();
    }

    /**
     * TAG_Short を取得する。キーが無ければ null。
     *
     * @param key キー
     * @return 値、または null
     */
    public Short optShort(String key) {
        NbtShort tag = cast(key, NbtShort.class);

        if (tag == null) {
            return null;
        }

        return tag.value();
    }

    /**
     * TAG_Short を取得する。キーが無ければ例外。
     *
     * @param key キー
     * @return 値
     */
    public short getShort(String key) {
        return require(key, NbtShort.class).value();
    }

    /**
     * TAG_Int を取得する。キーが無ければ null。
     *
     * @param key キー
     * @return 値、または null
     */
    public Integer optInt(String key) {
        NbtInt tag = cast(key, NbtInt.class);

        if (tag == null) {
            return null;
        }

        return tag.value();
    }

    /**
     * TAG_Int を取得する。キーが無ければ例外。
     *
     * @param key キー
     * @return 値
     */
    public int getInt(String key) {
        return require(key, NbtInt.class).value();
    }

    /**
     * TAG_Long を取得する。キーが無ければ null。
     *
     * @param key キー
     * @return 値、または null
     */
    public Long optLong(String key) {
        NbtLong tag = cast(key, NbtLong.class);

        if (tag == null) {
            return null;
        }

        return tag.value();
    }

    /**
     * TAG_Long を取得する。キーが無ければ例外。
     *
     * @param key キー
     * @return 値
     */
    public long getLong(String key) {
        return require(key, NbtLong.class).value();
    }

    /**
     * TAG_Float を取得する。キーが無ければ null。
     *
     * @param key キー
     * @return 値、または null
     */
    public Float optFloat(String key) {
        NbtFloat tag = cast(key, NbtFloat.class);

        if (tag == null) {
            return null;
        }

        return tag.value();
    }

    /**
     * TAG_Float を取得する。キーが無ければ例外。
     *
     * @param key キー
     * @return 値
     */
    public float getFloat(String key) {
        return require(key, NbtFloat.class).value();
    }

    /**
     * TAG_Double を取得する。キーが無ければ null。
     *
     * @param key キー
     * @return 値、または null
     */
    public Double optDouble(String key) {
        NbtDouble tag = cast(key, NbtDouble.class);

        if (tag == null) {
            return null;
        }

        return tag.value();
    }

    /**
     * TAG_Double を取得する。キーが無ければ例外。
     *
     * @param key キー
     * @return 値
     */
    public double getDouble(String key) {
        return require(key, NbtDouble.class).value();
    }

    /**
     * TAG_Byte を真偽値として取得する。0 以外が true。キーが無ければ null。
     *
     * @param key キー
     * @return 値、または null
     */
    public Boolean optBool(String key) {
        Byte raw = optByte(key);

        if (raw == null) {
            return null;
        }

        return raw != 0;
    }

    /**
     * TAG_Byte を真偽値として取得する。0 以外が true。キーが無ければ例外。
     *
     * @param key キー
     * @return 値
     */
    public boolean getBool(String key) {
        return getByte(key) != 0;
    }

    /**
     * TAG_String を取得する。キーが無ければ null。
     *
     * @param key キー
     * @return 値、または null
     */
    public String optString(String key) {
        NbtString tag = cast(key, NbtString.class);

        if (tag == null) {
            return null;
        }

        return tag.value();
    }

    /**
     * TAG_String を取得する。キーが無ければ例外。
     *
     * @param key キー
     * @return 値
     */
    public String getString(String key) {
        return require(key, NbtString.class).value();
    }

    /**
     * TAG_Byte_Array を取得する。キーが無ければ null。
     *
     * @param key キー
     * @return 値、または null
     */
    public byte[] optByteArray(String key) {
        NbtByteArray tag = cast(key, NbtByteArray.class);

        if (tag == null) {
            return null;
        }

        return tag.value();
    }

    /**
     * TAG_Byte_Array を取得する。キーが無ければ例外。
     *
     * @param key キー
     * @return 値
     */
    public byte[] getByteArray(String key) {
        return require(key, NbtByteArray.class).value();
    }

    /**
     * TAG_Int_Array を取得する。キーが無ければ null。
     *
     * @param key キー
     * @return 値、または null
     */
    public int[] optIntArray(String key) {
        NbtIntArray tag = cast(key, NbtIntArray.class);

        if (tag == null) {
            return null;
        }

        return tag.value();
    }

    /**
     * TAG_Int_Array を取得する。キーが無ければ例外。
     *
     * @param key キー
     * @return 値
     */
    public int[] getIntArray(String key) {
        return require(key, NbtIntArray.class).value();
    }

    /**
     * TAG_Long_Array を取得する。キーが無ければ null。
     *
     * @param key キー
     * @return 値、または null
     */
    public long[] optLongArray(String key) {
        NbtLongArray tag = cast(key, NbtLongArray.class);

        if (tag == null) {
            return null;
        }

        return tag.value();
    }

    /**
     * TAG_Long_Array を取得する。キーが無ければ例外。
     *
     * @param key キー
     * @return 値
     */
    public long[] getLongArray(String key) {
        return require(key, NbtLongArray.class).value();
    }

    /**
     * TAG_List を取得する。キーが無ければ null。
     *
     * @param key キー
     * @return 値、または null
     */
    public NbtList optList(String key) {
        return cast(key, NbtList.class);
    }

    /**
     * TAG_List を取得する。キーが無ければ例外。
     *
     * @param key キー
     * @return 値
     */
    public NbtList getList(String key) {
        return require(key, NbtList.class);
    }

    /**
     * TAG_Compound を取得する。キーが無ければ null。
     *
     * @param key キー
     * @return 値、または null
     */
    public NbtCompound optCompound(String key) {
        return cast(key, NbtCompound.class);
    }

    /**
     * TAG_Compound を取得する。キーが無ければ例外。
     *
     * @param key キー
     * @return 値
     */
    public NbtCompound getCompound(String key) {
        return require(key, NbtCompound.class);
    }

    /** キーに対応するタグを目的の型として取り出す。キーが無ければ null、型が違えば例外。 */
    private <T extends NbtTag> T cast(String key, Class<T> expected) {
        NbtTag tag = entries.get(key);

        if (tag == null) {
            return null;
        }

        if (expected.isInstance(tag)) {
            return expected.cast(tag);
        }

        throw SpringNbtException.unexpectedTagType(
                "キー \"" + key + "\" は " + tag.type().asString() + " だが "
                        + expected.getSimpleName() + " として取り出そうとした");
    }

    /** キーに対応するタグを目的の型として取り出す。キーが無くても型が違っても例外。 */
    private <T extends NbtTag> T require(String key, Class<T> expected) {
        T tag = cast(key, expected);

        if (tag == null) {
            throw SpringNbtException.invalidArgument("キーが存在しない: " + key);
        }

        return tag;
    }
}

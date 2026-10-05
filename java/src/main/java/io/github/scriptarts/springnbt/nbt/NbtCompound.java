package io.github.scriptarts.springnbt.nbt;

import io.github.scriptarts.springnbt.SpringNbtException;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * TAG_Compound
 * 挿入順を保持する、名前付きタグのマップ
 *
 * <p>既存キーへの再設定は位置を維持したまま値だけを置き換える
 * （{@link LinkedHashMap}の既定の振る舞い）
 * これにより読み込んだ順序が書き出しでも保たれ、ラウンドトリップが成立する
 *
 * <p>「キーが無い」と「型が違う」は区別する
 * {@code opt*}はキーが無ければ{@code null}を返し、{@code get*}は例外を送出する
 * どちらも型が違えば必ず{@link io.github.scriptarts.springnbt.ErrorCode#UNEXPECTED_TAG_TYPE}の例外になる
 */
public final class NbtCompound implements NbtTag, Iterable<Map.Entry<String, NbtTag>> {

    private final Map<String, NbtTag> entries = new LinkedHashMap<>();

    /** 空のCompoundを作る */
    public NbtCompound() {
        // 既定の状態で空
    }

    @Override
    public TagType type() {
        return TagType.COMPOUND;
    }

    /**
     * 要素数
     *
     * @return 要素数
     */
    public int size() {
        return entries.size();
    }

    /**
     * 挿入順のキー一覧
     *
     * @return キー一覧
     */
    public Set<String> keys() {
        return entries.keySet();
    }

    /**
     * キーが存在するか
     *
     * @param key キー
     * @return 存在すればtrue
     */
    public boolean containsKey(String key) {
        return entries.containsKey(key);
    }

    /**
     * 値を設定する
     * 既存キーなら位置を維持して値だけ置き換える
     *
     * @param key   キー
     * @param value 値
     */
    public void set(String key, NbtTag value) {
        Objects.requireNonNull(key, "key");
        Objects.requireNonNull(value, "value");

        // 孤立サロゲートを含むキーは書き出すと読み戻せないので、ここで止める
        if (Mutf8.hasLoneSurrogate(key)) {
            throw SpringNbtException.invalidArgument("キーに孤立サロゲートは使えない");
        }

        entries.put(key, value);
    }

    /**
     * キーに対応するタグを返す
     * 存在しなければnull
     *
     * @param key キー
     * @return タグ、またはnull
     */
    public NbtTag opt(String key) {
        return entries.get(key);
    }

    /**
     * キーに対応するタグを返す
     * 存在しなければ例外
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
     * キーを削除する
     *
     * @param key キー
     * @return 削除できたらtrue
     */
    public boolean remove(String key) {
        return entries.remove(key) != null;
    }

    /** 全要素を削除する */
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

        // キーと値を挿入順に比較する
        // 順序も等価性の一部
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
     * TAG_Byteを取得する
     * キーが無ければnull
     *
     * @param key キー
     * @return 値、またはnull
     */
    public Byte optByte(String key) {
        NbtByte tag = cast(key, NbtByte.class);

        if (tag == null) {
            return null;
        }

        return tag.value();
    }

    /**
     * TAG_Byteを取得する
     * キーが無ければ例外
     *
     * @param key キー
     * @return 値
     */
    public byte getByte(String key) {
        return require(key, NbtByte.class).value();
    }

    /**
     * TAG_Shortを取得する
     * キーが無ければnull
     *
     * @param key キー
     * @return 値、またはnull
     */
    public Short optShort(String key) {
        NbtShort tag = cast(key, NbtShort.class);

        if (tag == null) {
            return null;
        }

        return tag.value();
    }

    /**
     * TAG_Shortを取得する
     * キーが無ければ例外
     *
     * @param key キー
     * @return 値
     */
    public short getShort(String key) {
        return require(key, NbtShort.class).value();
    }

    /**
     * TAG_Intを取得する
     * キーが無ければnull
     *
     * @param key キー
     * @return 値、またはnull
     */
    public Integer optInt(String key) {
        NbtInt tag = cast(key, NbtInt.class);

        if (tag == null) {
            return null;
        }

        return tag.value();
    }

    /**
     * TAG_Intを取得する
     * キーが無ければ例外
     *
     * @param key キー
     * @return 値
     */
    public int getInt(String key) {
        return require(key, NbtInt.class).value();
    }

    /**
     * TAG_Longを取得する
     * キーが無ければnull
     *
     * @param key キー
     * @return 値、またはnull
     */
    public Long optLong(String key) {
        NbtLong tag = cast(key, NbtLong.class);

        if (tag == null) {
            return null;
        }

        return tag.value();
    }

    /**
     * TAG_Longを取得する
     * キーが無ければ例外
     *
     * @param key キー
     * @return 値
     */
    public long getLong(String key) {
        return require(key, NbtLong.class).value();
    }

    /**
     * TAG_Floatを取得する
     * キーが無ければnull
     *
     * @param key キー
     * @return 値、またはnull
     */
    public Float optFloat(String key) {
        NbtFloat tag = cast(key, NbtFloat.class);

        if (tag == null) {
            return null;
        }

        return tag.value();
    }

    /**
     * TAG_Floatを取得する
     * キーが無ければ例外
     *
     * @param key キー
     * @return 値
     */
    public float getFloat(String key) {
        return require(key, NbtFloat.class).value();
    }

    /**
     * TAG_Doubleを取得する
     * キーが無ければnull
     *
     * @param key キー
     * @return 値、またはnull
     */
    public Double optDouble(String key) {
        NbtDouble tag = cast(key, NbtDouble.class);

        if (tag == null) {
            return null;
        }

        return tag.value();
    }

    /**
     * TAG_Doubleを取得する
     * キーが無ければ例外
     *
     * @param key キー
     * @return 値
     */
    public double getDouble(String key) {
        return require(key, NbtDouble.class).value();
    }

    /**
     * TAG_Byteを真偽値として取得する
     * 0以外がtrue
     * キーが無ければnull
     *
     * @param key キー
     * @return 値、またはnull
     */
    public Boolean optBool(String key) {
        Byte raw = optByte(key);

        if (raw == null) {
            return null;
        }

        return raw != 0;
    }

    /**
     * TAG_Byteを真偽値として取得する
     * 0以外がtrue
     * キーが無ければ例外
     *
     * @param key キー
     * @return 値
     */
    public boolean getBool(String key) {
        return getByte(key) != 0;
    }

    /**
     * TAG_Stringを取得する
     * キーが無ければnull
     *
     * @param key キー
     * @return 値、またはnull
     */
    public String optString(String key) {
        NbtString tag = cast(key, NbtString.class);

        if (tag == null) {
            return null;
        }

        return tag.value();
    }

    /**
     * TAG_Stringを取得する
     * キーが無ければ例外
     *
     * @param key キー
     * @return 値
     */
    public String getString(String key) {
        return require(key, NbtString.class).value();
    }

    /**
     * TAG_Byte_Arrayを取得する
     * キーが無ければnull
     *
     * @param key キー
     * @return 値、またはnull
     */
    public byte[] optByteArray(String key) {
        NbtByteArray tag = cast(key, NbtByteArray.class);

        if (tag == null) {
            return null;
        }

        return tag.value();
    }

    /**
     * TAG_Byte_Arrayを取得する
     * キーが無ければ例外
     *
     * @param key キー
     * @return 値
     */
    public byte[] getByteArray(String key) {
        return require(key, NbtByteArray.class).value();
    }

    /**
     * TAG_Int_Arrayを取得する
     * キーが無ければnull
     *
     * @param key キー
     * @return 値、またはnull
     */
    public int[] optIntArray(String key) {
        NbtIntArray tag = cast(key, NbtIntArray.class);

        if (tag == null) {
            return null;
        }

        return tag.value();
    }

    /**
     * TAG_Int_Arrayを取得する
     * キーが無ければ例外
     *
     * @param key キー
     * @return 値
     */
    public int[] getIntArray(String key) {
        return require(key, NbtIntArray.class).value();
    }

    /**
     * TAG_Long_Arrayを取得する
     * キーが無ければnull
     *
     * @param key キー
     * @return 値、またはnull
     */
    public long[] optLongArray(String key) {
        NbtLongArray tag = cast(key, NbtLongArray.class);

        if (tag == null) {
            return null;
        }

        return tag.value();
    }

    /**
     * TAG_Long_Arrayを取得する
     * キーが無ければ例外
     *
     * @param key キー
     * @return 値
     */
    public long[] getLongArray(String key) {
        return require(key, NbtLongArray.class).value();
    }

    /**
     * TAG_Listを取得する
     * キーが無ければnull
     *
     * @param key キー
     * @return 値、またはnull
     */
    public NbtList optList(String key) {
        return cast(key, NbtList.class);
    }

    /**
     * TAG_Listを取得する
     * キーが無ければ例外
     *
     * @param key キー
     * @return 値
     */
    public NbtList getList(String key) {
        return require(key, NbtList.class);
    }

    /**
     * TAG_Compoundを取得する
     * キーが無ければnull
     *
     * @param key キー
     * @return 値、またはnull
     */
    public NbtCompound optCompound(String key) {
        return cast(key, NbtCompound.class);
    }

    /**
     * TAG_Compoundを取得する
     * キーが無ければ例外
     *
     * @param key キー
     * @return 値
     */
    public NbtCompound getCompound(String key) {
        return require(key, NbtCompound.class);
    }

    /**
     * キーに対応するタグを目的の型として取り出す
     * キーが無ければnull、型が違えば例外
     */
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

    /**
     * キーに対応するタグを目的の型として取り出す
     * キーが無くても型が違っても例外
     */
    private <T extends NbtTag> T require(String key, Class<T> expected) {
        T tag = cast(key, expected);

        if (tag == null) {
            throw SpringNbtException.invalidArgument("キーが存在しない: " + key);
        }

        return tag;
    }
    // -- 型付き設定子 -------------------------------------------------------
    //
    // set(key, new NbtInt(42))と書かずに済むようにするための糖衣
    // 取得子のgetIntと対になる

    /**
     * TAG_Byteとして設定する
     *
     * @param key キー
     * @param value 値
     */
    public void setByte(String key, byte value) {
        set(key, new NbtByte(value));
    }

    /**
     * TAG_Shortとして設定する
     *
     * @param key キー
     * @param value 値
     */
    public void setShort(String key, short value) {
        set(key, new NbtShort(value));
    }

    /**
     * TAG_Intとして設定する
     *
     * @param key キー
     * @param value 値
     */
    public void setInt(String key, int value) {
        set(key, new NbtInt(value));
    }

    /**
     * TAG_Longとして設定する
     *
     * @param key キー
     * @param value 値
     */
    public void setLong(String key, long value) {
        set(key, new NbtLong(value));
    }

    /**
     * TAG_Floatとして設定する
     *
     * @param key キー
     * @param value 値
     */
    public void setFloat(String key, float value) {
        set(key, new NbtFloat(value));
    }

    /**
     * TAG_Doubleとして設定する
     *
     * @param key キー
     * @param value 値
     */
    public void setDouble(String key, double value) {
        set(key, new NbtDouble(value));
    }

    /**
     * TAG_Byteとして設定する
     * trueは1、falseは0
     *
     * @param key キー
     * @param value 値
     */
    public void setBool(String key, boolean value) {
        // NBTに真偽値の専用型は無いので、TAG_Byteの0 / 1で表す
        if (value) {
            setByte(key, (byte) 1);
        } else {
            setByte(key, (byte) 0);
        }
    }

    /**
     * TAG_Stringとして設定する
     *
     * @param key キー
     * @param value 値
     * @throws SpringNbtException MUTF-8に符号化すると65535バイトを超える場合
     */
    public void setString(String key, String value) {
        set(key, new NbtString(value));
    }

    /**
     * TAG_Byte_Arrayとして設定する
     *
     * @param key キー
     * @param value 値
     */
    public void setByteArray(String key, byte[] value) {
        set(key, new NbtByteArray(value));
    }

    /**
     * TAG_Int_Arrayとして設定する
     *
     * @param key キー
     * @param value 値
     */
    public void setIntArray(String key, int[] value) {
        set(key, new NbtIntArray(value));
    }

    /**
     * TAG_Long_Arrayとして設定する
     *
     * @param key キー
     * @param value 値
     */
    public void setLongArray(String key, long[] value) {
        set(key, new NbtLongArray(value));
    }

}

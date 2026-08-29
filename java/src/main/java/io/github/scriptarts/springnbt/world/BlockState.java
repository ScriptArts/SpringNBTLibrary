package io.github.scriptarts.springnbt.world;

import io.github.scriptarts.springnbt.SpringNbtException;
import io.github.scriptarts.springnbt.nbt.NbtCompound;
import io.github.scriptarts.springnbt.nbt.NbtString;
import io.github.scriptarts.springnbt.nbt.NbtTag;
import java.util.Collections;
import java.util.Map;
import java.util.Objects;
import java.util.SortedMap;
import java.util.TreeMap;

/**
 * ブロックの状態。名前と、任意のプロパティの組。
 *
 * <p>プロパティは<strong>常に名前の昇順で保持する</strong>。こうしておくと文字列表現が一意になり、
 * 全言語で同じ出力になる。Minecraft が書き出した並び順は
 * {@link PalettedContainer} がパレットを生の NBT のまま持つことで守られるので、
 * 触っていないブロックの並びが崩れることはない。
 *
 * <p>仕様: {@code docs/spec/30-chunk-format.md} 2.1章
 */
public final class BlockState {

    private final String name;
    private final SortedMap<String, String> properties;

    /**
     * 名前とプロパティを指定して作る。
     *
     * @param name       ブロックID。名前空間が省略されていたら {@code minecraft:} を補う
     * @param properties プロパティ。null なら空
     */
    public BlockState(String name, Map<String, String> properties) {
        Objects.requireNonNull(name, "name");
        this.name = normalize(name);
        this.properties = new TreeMap<>();

        if (properties != null) {
            this.properties.putAll(properties);
        }
    }

    /**
     * プロパティを持たない状態を作る。
     *
     * @param name ブロックID
     */
    public BlockState(String name) {
        this(name, null);
    }

    /**
     * ブロックID（名前空間つき）。
     *
     * @return ブロックID
     */
    public String name() {
        return name;
    }

    /**
     * プロパティ。名前の昇順。
     *
     * @return プロパティ
     */
    public Map<String, String> properties() {
        return Collections.unmodifiableSortedMap(properties);
    }

    /**
     * プロパティを取得する。
     *
     * @param key プロパティ名
     * @return 値。無ければ null
     */
    public String property(String key) {
        return properties.get(key);
    }

    /**
     * プロパティを 1 つ差し替えた新しい状態を返す。
     *
     * @param key   プロパティ名
     * @param value 値
     * @return 新しい状態
     */
    public BlockState with(String key, String value) {
        Objects.requireNonNull(key, "key");
        Objects.requireNonNull(value, "value");

        BlockState result = new BlockState(name, properties);
        result.properties.put(key, value);
        return result;
    }

    /**
     * {@code minecraft:oak_stairs[facing=north,half=top]} 形式の文字列から作る。
     *
     * @param text 文字列
     * @return ブロック状態
     * @throws SpringNbtException 形式が不正な場合
     */
    public static BlockState parse(String text) {
        Objects.requireNonNull(text, "text");
        int bracket = text.indexOf('[');

        if (bracket < 0) {
            if (text.isEmpty()) {
                throw SpringNbtException.invalidArgument("ブロック名が空");
            }

            return new BlockState(text);
        }

        if (!text.endsWith("]")) {
            throw SpringNbtException.invalidArgument("角括弧が閉じられていない: " + text);
        }

        BlockState state = new BlockState(text.substring(0, bracket));
        String body = text.substring(bracket + 1, text.length() - 1);

        if (body.isEmpty()) {
            return state;
        }

        // "key=value" をカンマ区切りで読む
        for (String pair : body.split(",")) {
            int equals = pair.indexOf('=');

            if (equals < 0) {
                throw SpringNbtException.invalidArgument("プロパティに '=' が無い: " + pair);
            }

            String key = pair.substring(0, equals).trim();

            if (key.isEmpty()) {
                throw SpringNbtException.invalidArgument("プロパティ名が空: " + pair);
            }

            // どちらが採用されたか分からないまま書き込まれるのを避けるため、重複は弾く
            if (state.properties.containsKey(key)) {
                throw SpringNbtException.invalidArgument("プロパティ名が重複している: " + key);
            }

            state.properties.put(key, pair.substring(equals + 1).trim());
        }

        return state;
    }

    /**
     * パレット要素の NBT から作る。
     *
     * @param nbt パレット要素
     * @return ブロック状態
     * @throws SpringNbtException {@code Name} が無い、または {@code Properties} の値が文字列でない場合
     */
    public static BlockState fromNbt(NbtCompound nbt) {
        Objects.requireNonNull(nbt, "nbt");
        BlockState state = new BlockState(nbt.getString("Name"));
        NbtCompound propertiesTag = nbt.optCompound("Properties");

        if (propertiesTag == null) {
            return state;
        }

        // Properties の値はすべて文字列（数値や真偽値も文字列で入る）
        for (Map.Entry<String, NbtTag> entry : propertiesTag) {
            if (!(entry.getValue() instanceof NbtString text)) {
                throw SpringNbtException.unexpectedTagType("Properties の \"" + entry.getKey()
                        + "\" が文字列でない: " + entry.getValue().type().asString());
            }

            state.properties.put(entry.getKey(), text.value());
        }

        return state;
    }

    /**
     * パレット要素の NBT へ変換する。
     *
     * <p>プロパティが空なら {@code Properties} キー自体を出力しない。Minecraft と同じ振る舞い。
     *
     * @return NBT
     */
    public NbtCompound toNbt() {
        NbtCompound result = new NbtCompound();
        result.set("Name", new NbtString(name));

        if (properties.isEmpty()) {
            return result;
        }

        NbtCompound propertiesTag = new NbtCompound();

        // 名前の昇順で並ぶ
        for (Map.Entry<String, String> entry : properties.entrySet()) {
            propertiesTag.set(entry.getKey(), new NbtString(entry.getValue()));
        }

        result.set("Properties", propertiesTag);
        return result;
    }

    /** 名前空間が省略されていたら {@code minecraft:} を補う。 */
    private static String normalize(String name) {
        if (name.indexOf(':') >= 0) {
            return name;
        }

        return "minecraft:" + name;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof BlockState state
                && state.name.equals(name)
                && state.properties.equals(properties);
    }

    @Override
    public int hashCode() {
        return Objects.hash(name, properties);
    }

    /**
     * {@code minecraft:oak_stairs[facing=north,half=top]} 形式の文字列を返す。
     */
    @Override
    public String toString() {
        if (properties.isEmpty()) {
            return name;
        }

        StringBuilder builder = new StringBuilder(name);
        builder.append('[');
        boolean first = true;

        // 名前の昇順で並べるので、同じ状態なら必ず同じ文字列になる
        for (Map.Entry<String, String> entry : properties.entrySet()) {
            if (!first) {
                builder.append(',');
            }

            first = false;
            builder.append(entry.getKey()).append('=').append(entry.getValue());
        }

        builder.append(']');
        return builder.toString();
    }
}

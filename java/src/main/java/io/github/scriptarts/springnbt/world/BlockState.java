package io.github.scriptarts.springnbt.world;

import io.github.scriptarts.springnbt.SpringNbt;
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
 * ブロックの状態
 * 名前と、任意のプロパティの組
 *
 * <p>プロパティは<strong>常に名前の昇順で保持する</strong>
 * こうしておくと文字列表現が一意になり、全言語で同じ出力になる
 * Minecraftが書き出した並び順は、{@link PalettedContainer}がパレットを生のNBTのまま持つことで守られる
 * そのため、触っていないブロックの並びが崩れることはない
 */
public final class BlockState {

    private final String name;
    private final SortedMap<String, String> properties;

    /**
     * 名前とプロパティを指定して作る
     *
     * @param name       ブロックID
     * 名前空間が省略されていたら{@code minecraft:}を補う
     * @param properties プロパティ
     * nullなら空
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
     * プロパティを持たない状態を作る
     *
     * @param name ブロックID
     */
    public BlockState(String name) {
        this(name, null);
    }

    /**
     * ブロックID（名前空間つき）
     *
     * @return ブロックID
     */
    public String name() {
        return name;
    }

    /**
     * プロパティ
     * 名前の昇順
     *
     * @return プロパティ
     */
    public Map<String, String> properties() {
        return Collections.unmodifiableSortedMap(properties);
    }

    /**
     * プロパティを取得する
     *
     * @param key プロパティ名
     * @return 値
     * 無ければnull
     */
    public String property(String key) {
        return properties.get(key);
    }

    /**
     * プロパティを1つ差し替えた新しい状態を返す
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
     * {@code minecraft:oak_stairs[facing=north,half=top]}形式の文字列から作る
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

        // "key=value"をカンマ区切りで読む
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
     * パレット要素のNBTから作る
     *
     * <p>{@link SpringNbt#TARGET_DATA_VERSION}の形式で読む
     * DataVersionを指定するときは{@link #fromNbtForDataVersion}を使う
     *
     * @param nbt パレット要素
     * @return ブロック状態
     * @throws SpringNbtException 文字列でもCompoundでもない、{@code id}が無い、または{@code properties}の値が文字列でない場合
     */
    public static BlockState fromNbt(NbtTag nbt) {
        return fromNbtForDataVersion(nbt, SpringNbt.TARGET_DATA_VERSION);
    }

    /**
     * DataVersionを指定して、パレット要素のNBTから作る
     *
     * <p>26.3（DataVersion 5006）以降は、既定の状態がブロックIDだけの文字列で、それ以外は{@code id}と{@code properties}を持つCompoundで入っている
     * 異種リストの要素を包む{@code {"": <値>}}は外してから読む
     * 1519以上5006未満は、{@code Name}と{@code Properties}を持つCompoundを読む
     * 文字列は受け付けない
     *
     * @param nbt         パレット要素
     * @param dataVersion パレット要素を含むチャンクのDataVersion（1519以上）
     * @return ブロック状態
     * @throws SpringNbtException {@code dataVersion}が1519未満の場合（INVALID_ARGUMENT）、
     * 要素が形式に合うタグでない場合、{@code id} / {@code Name}が無い場合、またはプロパティの値が文字列でない場合
     */
    public static BlockState fromNbtForDataVersion(NbtTag nbt, int dataVersion) {
        Objects.requireNonNull(nbt, "nbt");
        checkDataVersion(dataVersion);

        // 26.3より前は、Name / Propertiesの形式で入っている
        if (dataVersion < ChunkFormat.PALETTE_ID_FORMAT_DATA_VERSION) {
            return fromNameProperties(nbt);
        }

        return fromPaletteId(nbt);
    }

    /** 26.3以降の{@code id} / {@code properties}の形式から読む */
    private static BlockState fromPaletteId(NbtTag nbt) {
        NbtTag entry = PalettedContainer.unwrapListElement(nbt);

        // 既定の状態は、ブロックIDだけの文字列で入っている
        if (entry instanceof NbtString plain) {
            return new BlockState(plain.value());
        }

        if (!(entry instanceof NbtCompound compound)) {
            throw SpringNbtException.unexpectedTagType(
                    "ブロックのパレット要素が string でも compound でもない: " + entry.type().asString());
        }

        String name = compound.optString("id");

        if (name == null) {
            // Name / Propertiesは26.2までの形式で、読み替えると誤った状態を返しかねない
            if (compound.containsKey("Name")) {
                throw SpringNbtException.malformed(
                        "ブロックのパレット要素にidが無い。NameはDataVersion 5006より前の形式なので、5006未満のDataVersionで読むこと");
            }

            throw SpringNbtException.malformed("ブロックのパレット要素に id が無い");
        }

        BlockState state = new BlockState(name);
        NbtCompound propertiesTag = compound.optCompound("properties");

        if (propertiesTag == null) {
            return state;
        }

        // propertiesの値はすべて文字列（数値や真偽値も文字列で入る）
        for (Map.Entry<String, NbtTag> property : propertiesTag) {
            if (!(property.getValue() instanceof NbtString text)) {
                throw SpringNbtException.unexpectedTagType("properties の \"" + property.getKey()
                        + "\" が文字列でない: " + property.getValue().type().asString());
            }

            state.properties.put(property.getKey(), text.value());
        }

        return state;
    }

    /** 26.2までの{@code Name} / {@code Properties}の形式から読む */
    private static BlockState fromNameProperties(NbtTag nbt) {
        // 26.2までは文字列のパレット要素も、異種リストの包みも無い
        if (!(nbt instanceof NbtCompound compound)) {
            throw SpringNbtException.unexpectedTagType(
                    "ブロックのパレット要素が compound でない: " + nbt.type().asString());
        }

        String name = compound.optString("Name");

        if (name == null) {
            throw SpringNbtException.malformed("ブロックのパレット要素に Name が無い");
        }

        BlockState state = new BlockState(name);
        NbtCompound propertiesTag = compound.optCompound("Properties");

        if (propertiesTag == null) {
            return state;
        }

        // Propertiesの値はすべて文字列（数値や真偽値も文字列で入る）
        for (Map.Entry<String, NbtTag> property : propertiesTag) {
            if (!(property.getValue() instanceof NbtString text)) {
                throw SpringNbtException.unexpectedTagType("Properties の \"" + property.getKey()
                        + "\" が文字列でない: " + property.getValue().type().asString());
            }

            state.properties.put(property.getKey(), text.value());
        }

        return state;
    }

    /** 指定されたDataVersionが、読み書きできる下限以上であることを確かめる */
    private static void checkDataVersion(int dataVersion) {
        if (dataVersion < ChunkFormat.OLDEST_FORMAT_DATA_VERSION) {
            throw SpringNbtException.invalidArgument(
                    "DataVersionは" + ChunkFormat.OLDEST_FORMAT_DATA_VERSION + "以上でなければならない: " + dataVersion);
        }
    }

    /**
     * パレット要素のNBTへ変換する
     *
     * <p>{@link SpringNbt#TARGET_DATA_VERSION}の形式で書く
     * DataVersionを指定するときは{@link #toNbtForDataVersion}を使う
     *
     * @return NBT
     */
    public NbtTag toNbt() {
        return toNbtForDataVersion(SpringNbt.TARGET_DATA_VERSION);
    }

    /**
     * DataVersionを指定して、パレット要素のNBTへ変換する
     *
     * <p>26.3（DataVersion 5006）以降は、プロパティが空ならブロックIDだけの文字列にし、それ以外は{@code id}と{@code properties}を持つCompoundにする
     * 1519以上5006未満は、{@code Name}を持つCompoundにし、プロパティが空なら{@code Properties}キー自体を出力しない
     * いずれもMinecraftと同じ振る舞い
     *
     * @param dataVersion 書き込み先のチャンクのDataVersion（1519以上）
     * @return NBT
     * @throws SpringNbtException {@code dataVersion}が1519未満の場合（INVALID_ARGUMENT）
     */
    public NbtTag toNbtForDataVersion(int dataVersion) {
        checkDataVersion(dataVersion);

        // 26.3より前は、Name / Propertiesの形式で書く
        if (dataVersion < ChunkFormat.PALETTE_ID_FORMAT_DATA_VERSION) {
            return toNameProperties();
        }

        return toPaletteId();
    }

    /** 26.3以降の{@code id} / {@code properties}の形式へ変換する */
    private NbtTag toPaletteId() {
        // プロパティが無ければ、Minecraftが既定の状態を書くときと同じく文字列にする
        if (properties.isEmpty()) {
            return new NbtString(name);
        }

        NbtCompound result = new NbtCompound();
        result.set("id", new NbtString(name));
        NbtCompound propertiesTag = new NbtCompound();

        // 名前の昇順で並ぶ
        for (Map.Entry<String, String> entry : properties.entrySet()) {
            propertiesTag.set(entry.getKey(), new NbtString(entry.getValue()));
        }

        result.set("properties", propertiesTag);
        return result;
    }

    /** 26.2までの{@code Name} / {@code Properties}の形式へ変換する */
    private NbtCompound toNameProperties() {
        NbtCompound result = new NbtCompound();
        result.set("Name", new NbtString(name));

        // プロパティが無ければ、Propertiesキー自体を出力しない
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

    /** 名前空間が省略されていたら{@code minecraft:}を補う */
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
     * {@code minecraft:oak_stairs[facing=north,half=top]}形式の文字列を返す
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

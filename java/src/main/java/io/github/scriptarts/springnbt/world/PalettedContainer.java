package io.github.scriptarts.springnbt.world;

import io.github.scriptarts.springnbt.SpringNbtException;
import io.github.scriptarts.springnbt.nbt.NbtCompound;
import io.github.scriptarts.springnbt.nbt.NbtList;
import io.github.scriptarts.springnbt.nbt.NbtLongArray;
import io.github.scriptarts.springnbt.nbt.NbtTag;
import io.github.scriptarts.springnbt.nbt.TagType;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * パレットとビットストレージの組
 * セクション内のブロック状態やバイオームを格納する
 *
 * <p>パレットの要素は<strong>生の{@link NbtTag}のまま</strong>持つ
 * こうすると、触っていないブロックについてはMinecraftが書き出したときの
 * プロパティの並び順まで含めてそのまま書き戻せる
 *
 * <p>26.3からは、ブロックのパレットに文字列とCompoundが混ざる
 * Minecraftはこうした異種リストをCompoundのリストとして保存し、Compoundでない要素を{@code {"": <値>}}で包む
 * 読むときにこの包みを外して持ち、書くときに要素の型を見て包み直す
 */
public final class PalettedContainer {

    private final List<NbtTag> palette = new ArrayList<>();
    private final int entryCount;
    private final int minBits;
    private final boolean spanning;
    private final boolean alwaysHasData;

    private BitStorage storage;

    private PalettedContainer(int entryCount, int minBits, boolean spanning, boolean alwaysHasData) {
        this.entryCount = entryCount;
        this.minBits = minBits;
        this.spanning = spanning;
        this.alwaysHasData = alwaysHasData;
    }

    /**
     * パレットとdataに分けた結果
     *
     * @param palette パレットの要素
     * @param data    packedな配列（無ければnull）
     */
    record Parts(List<NbtTag> palette, long[] data) {
    }

    /**
     * エントリ数
     * ブロックなら4096、バイオームなら64
     *
     * @return エントリ数
     */
    public int entryCount() {
        return entryCount;
    }

    /**
     * ビット幅の下限
     * ブロックなら4、バイオームなら1
     *
     * @return 下限
     */
    public int minBits() {
        return minBits;
    }

    /**
     * パレット
     * 読み取り専用
     *
     * @return パレット
     */
    public List<NbtTag> palette() {
        return Collections.unmodifiableList(palette);
    }

    /**
     * 現在のビット幅
     * パレットが1要素なら0（記憶域を持たない）
     *
     * @return ビット幅
     */
    public int bitsPerEntry() {
        if (storage == null) {
            return 0;
        }

        return storage.bitsPerEntry();
    }

    /**
     * 単一の値で埋めたコンテナを作る
     *
     * @param value      値
     * @param entryCount エントリ数
     * @param minBits    ビット幅の下限
     * @return コンテナ
     */
    public static PalettedContainer filled(NbtTag value, int entryCount, int minBits) {
        Objects.requireNonNull(value, "value");
        PalettedContainer result = new PalettedContainer(entryCount, minBits, false, false);
        result.palette.add(value);
        return result;
    }

    /**
     * NBTから読み込む
     *
     * @param nbt                 コンテナのNBT
     * @param entryCount          エントリ数
     * @param minBits             ビット幅の下限
     * @param lenientBitStorage   dataの長さが合わないとき、長さから逆算するか
     * @return コンテナ
     * @throws SpringNbtException パレットが空、dataの長さが合わない、添字がパレット範囲外のいずれか
     */
    public static PalettedContainer fromNbt(
            NbtCompound nbt, int entryCount, int minBits, boolean lenientBitStorage) {
        Objects.requireNonNull(nbt, "nbt");
        NbtList paletteTag = nbt.optList("palette");

        if (paletteTag == null || paletteTag.size() == 0) {
            throw SpringNbtException.malformed("palette が無いか空");
        }

        // パレットの要素は生のNbtTagのまま持つ
        // 並び順まで元どおりに書き戻すため
        // 異種リストの包みだけは外しておき、書くときに包み直す
        List<NbtTag> entries = new ArrayList<>();

        // 包みを外しながら、パレットの要素を順に集める
        for (NbtTag entry : paletteTag) {
            entries.add(unwrapListElement(entry));
        }

        return fromParts(entries, nbt.optLongArray("data"), entryCount, minBits, false, false,
                lenientBitStorage);
    }

    /**
     * パレットとdataから作る
     * 1.13から1.15までの詰め方や、dataが必ず書かれる形式を読むための入口
     *
     * @param palette           パレットの要素（異種リストの包みは外してあること）
     * @param data              packedな配列（無ければnull）
     * @param entryCount        エントリ数
     * @param minBits           ビット幅の下限
     * @param spanning          64bitの境目をまたいで詰めるか
     * @param alwaysHasData     パレットが1要素でもdataを書く形式か
     * @param lenientBitStorage dataの長さが合わないとき、長さから逆算するか
     * @return コンテナ
     * @throws SpringNbtException パレットが空、dataの長さが合わない、添字がパレット範囲外、
     *                            dataが必ず書かれる形式なのにdataが無い、のいずれか
     */
    static PalettedContainer fromParts(List<NbtTag> palette, long[] data, int entryCount, int minBits,
            boolean spanning, boolean alwaysHasData, boolean lenientBitStorage) {
        Objects.requireNonNull(palette, "palette");

        if (palette.isEmpty()) {
            throw SpringNbtException.malformed("palette が無いか空");
        }

        PalettedContainer result = new PalettedContainer(entryCount, minBits, spanning, alwaysHasData);
        result.palette.addAll(palette);

        if (data == null) {
            // dataが必ず書かれる形式で無いなら、壊れたデータとして扱う
            // 書き戻しで元に無いdataを作ってしまわないため
            if (alwaysHasData) {
                throw SpringNbtException.malformed("data が必ず書かれる形式なのに data が無い");
            }

            // パレットが1要素ならdataは無くてよい
            if (result.palette.size() != 1) {
                throw SpringNbtException.malformed(
                        "palette が " + result.palette.size() + " 要素なのに data が無い");
            }

            return result;
        }

        int bits = Math.max(minBits, ceilLog2(result.palette.size()));
        result.storage = BitStorage.fromLongs(data, bits, entryCount, lenientBitStorage, spanning);

        // 取り出した添字がパレットの範囲に収まっているか確かめる
        // エラーを出さずに0番目で代替すると、おかしくなったデータをそうと分からない形で書き戻してしまう
        for (int index = 0; index < entryCount; index++) {
            int value = result.storage.get(index);

            if (value >= result.palette.size()) {
                throw SpringNbtException.malformed("添字 " + index + " の値 " + value
                        + " がパレット（" + result.palette.size() + " 要素）の範囲外");
            }
        }

        return result;
    }

    /**
     * パレットとdataに分けて返す
     * パレットの要素は異種リストの包みを掛けないまま返す
     * dataは、パレットが1要素なら（{@code alwaysHasData}でない限り）null
     *
     * @return パレットとdata
     */
    Parts toParts() {
        List<NbtTag> entries = new ArrayList<>(palette);

        // パレットが2要素以上なら、記憶域をそのまま返す
        if (storage != null && palette.size() > 1) {
            return new Parts(entries, storage.toLongs());
        }

        // 1要素でもdataを書く形式なら、記憶域が無くてもゼロで埋めた配列を作る
        if (alwaysHasData) {
            int bits = Math.max(minBits, ceilLog2(palette.size()));
            return new Parts(entries, BitStorage.create(bits, entryCount, spanning).toLongs());
        }

        return new Parts(entries, null);
    }

    /**
     * NBTへ変換する
     *
     * @return NBT
     */
    public NbtCompound toNbt() {
        NbtCompound result = new NbtCompound();

        // パレットの要素は読んだときのまま書き出す
        // 型が混ざっていれば、Minecraftと同じく包んでCompoundのリストにする
        NbtList paletteTag = paletteToList(palette);

        // パレットが1要素ならdataは書かない
        // Minecraftと同じ振る舞い
        if (storage != null && palette.size() > 1) {
            result.set("data", new NbtLongArray(storage.toLongs()));
        }

        result.set("palette", paletteTag);
        return result;
    }

    /**
     * 異種リストの包みを外す
     * 包みでなければそのまま返す
     */
    static NbtTag unwrapListElement(NbtTag tag) {
        if (isListWrapper(tag)) {
            return ((NbtCompound) tag).get("");
        }

        return tag;
    }

    /**
     * 異種リストの要素を包むCompoundか
     * 空のキー1つだけを持つものがそれに当たる（MinecraftのListTagと同じ判定）
     */
    private static boolean isListWrapper(NbtTag tag) {
        if (!(tag instanceof NbtCompound compound)) {
            return false;
        }

        return compound.size() == 1 && compound.containsKey("");
    }

    /**
     * パレットの要素をリストへ詰める
     *
     * <p>要素の型がすべて同じならその型のリストにする
     * 1つでも違えば、Minecraftと同じくCompoundのリストにして、Compoundでない要素と包みに見える要素を包む
     */
    private static NbtList paletteToList(List<NbtTag> entries) {
        TagType elementType = entries.get(0).type();

        // 先頭と型の違う要素があるか調べる
        for (NbtTag entry : entries) {
            // 1つでも違えば、異種リストとしてCompoundのリストにする
            if (entry.type() != elementType) {
                elementType = TagType.COMPOUND;
                break;
            }
        }

        NbtList result = new NbtList(elementType);

        // 要素を順にリストへ入れる
        for (NbtTag entry : entries) {
            // Compoundのリストでは、Compoundでない要素と包みに見える要素を包む
            if (elementType == TagType.COMPOUND && (!(entry instanceof NbtCompound) || isListWrapper(entry))) {
                NbtCompound wrapper = new NbtCompound();
                wrapper.set("", entry);
                result.add(wrapper);
            } else {
                result.add(entry);
            }
        }

        return result;
    }

    /**
     * 添字の値を取り出す
     *
     * @param index 添字
     * @return 値
     */
    public NbtTag get(int index) {
        checkIndex(index);

        // 記憶域が無いということは、全エントリがパレットの0番目
        if (storage == null) {
            return palette.get(0);
        }

        return palette.get(storage.get(index));
    }

    /**
     * 添字の値を書き換える
     * パレットに無ければ追加する
     *
     * @param index 添字
     * @param value 値
     */
    public void set(int index, NbtTag value) {
        Objects.requireNonNull(value, "value");
        checkIndex(index);

        int paletteIndex = indexOfOrAdd(value);

        // 記憶域が無く、書き込む値も0番目なら何もしなくてよい
        if (storage == null && paletteIndex == 0) {
            return;
        }

        ensureStorage();
        storage.set(index, paletteIndex);
    }

    /**
     * 全エントリを1つの値で埋める
     * パレットもその1要素だけにする
     *
     * @param value 値
     */
    public void fill(NbtTag value) {
        Objects.requireNonNull(value, "value");
        palette.clear();
        palette.add(value);
        storage = null;
    }

    /**
     * どのエントリからも参照されていないパレット要素を取り除き、添字を振り直す
     *
     * <p>大量の{@code set}を行う用途で遅くならないよう、明示的に呼んだときだけ実行する
     */
    public void compact() {
        if (storage == null) {
            return;
        }

        boolean[] usedEntries = new boolean[palette.size()];

        // どのパレット要素が実際に使われているかを数える
        for (int index = 0; index < entryCount; index++) {
            usedEntries[storage.get(index)] = true;
        }

        List<NbtTag> compacted = new ArrayList<>();
        int[] remap = new int[palette.size()];

        // 使われている要素だけを詰め直し、新しい添字を割り当てる
        for (int old = 0; old < palette.size(); old++) {
            if (!usedEntries[old]) {
                remap[old] = -1;
                continue;
            }

            remap[old] = compacted.size();
            compacted.add(palette.get(old));
        }

        if (compacted.size() == palette.size()) {
            return;
        }

        int newBits = Math.max(minBits, ceilLog2(compacted.size()));
        BitStorage rebuilt = BitStorage.create(newBits, entryCount, spanning);

        // 新しい添字へ置き換えながら詰め直す
        for (int index = 0; index < entryCount; index++) {
            rebuilt.set(index, remap[storage.get(index)]);
        }

        palette.clear();
        palette.addAll(compacted);

        if (compacted.size() == 1) {
            // 1要素になったら記憶域を捨てる
            storage = null;
        } else {
            storage = rebuilt;
        }
    }

    /**
     * パレット内の位置を返す
     * 無ければ末尾へ追加する
     */
    private int indexOfOrAdd(NbtTag value) {
        // パレットは高々4096要素なので線形探索で足りる
        for (int index = 0; index < palette.size(); index++) {
            if (palette.get(index).equals(value)) {
                return index;
            }
        }

        palette.add(value);
        return palette.size() - 1;
    }

    /** 現在のパレット長に合うビット幅の記憶域を用意する */
    private void ensureStorage() {
        int required = Math.max(minBits, ceilLog2(palette.size()));

        if (storage == null) {
            // これまで単一値だったので、全エントリが0番目のまま始まる
            storage = BitStorage.create(required, entryCount, spanning);
            return;
        }

        if (storage.bitsPerEntry() >= required) {
            return;
        }

        // パレットが増えてビット幅が足りなくなったら、全体を詰め直す
        storage = storage.resize(required);
    }

    private void checkIndex(int index) {
        if (index < 0 || index >= entryCount) {
            throw SpringNbtException.invalidArgument(
                    "添字が範囲外: " + index + " (0.." + (entryCount - 1) + ")");
        }
    }

    /**
     * {@code count}個の値を表すのに必要な最小ビット数
     * 1なら0
     *
     * @param count 値の個数
     * @return ビット数
     */
    public static int ceilLog2(int count) {
        int bits = 0;

        // 1を超える分だけシフトして数える
        while ((1 << bits) < count) {
            bits += 1;
        }

        return bits;
    }
}

package io.github.scriptarts.springnbt.world;

import io.github.scriptarts.springnbt.SpringNbtException;
import io.github.scriptarts.springnbt.nbt.NbtCompound;
import io.github.scriptarts.springnbt.nbt.NbtList;
import io.github.scriptarts.springnbt.nbt.NbtLongArray;
import io.github.scriptarts.springnbt.nbt.NbtTag;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * パレットとビットストレージの組。セクション内のブロック状態やバイオームを格納する。
 *
 * <p>パレットの要素は<strong>生の {@link NbtTag} のまま</strong>持つ。
 * こうすると、触っていないブロックについては Minecraft が書き出したときの
 * プロパティの並び順まで含めてそのまま書き戻せる。
 *
 * <p>仕様: {@code docs/spec/31-paletted-container.md}
 */
public final class PalettedContainer {

    private final List<NbtTag> palette = new ArrayList<>();
    private final int entryCount;
    private final int minBits;

    private BitStorage storage;

    private PalettedContainer(int entryCount, int minBits) {
        this.entryCount = entryCount;
        this.minBits = minBits;
    }

    /**
     * エントリ数。ブロックなら 4096、バイオームなら 64。
     *
     * @return エントリ数
     */
    public int entryCount() {
        return entryCount;
    }

    /**
     * ビット幅の下限。ブロックなら 4、バイオームなら 1。
     *
     * @return 下限
     */
    public int minBits() {
        return minBits;
    }

    /**
     * パレット。読み取り専用。
     *
     * @return パレット
     */
    public List<NbtTag> palette() {
        return Collections.unmodifiableList(palette);
    }

    /**
     * 現在のビット幅。パレットが 1 要素なら 0（記憶域を持たない）。
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
     * 単一の値で埋めたコンテナを作る。
     *
     * @param value      値
     * @param entryCount エントリ数
     * @param minBits    ビット幅の下限
     * @return コンテナ
     */
    public static PalettedContainer filled(NbtTag value, int entryCount, int minBits) {
        Objects.requireNonNull(value, "value");
        PalettedContainer result = new PalettedContainer(entryCount, minBits);
        result.palette.add(value);
        return result;
    }

    /**
     * NBT から読み込む。
     *
     * @param nbt                 コンテナの NBT
     * @param entryCount          エントリ数
     * @param minBits             ビット幅の下限
     * @param lenientBitStorage   data の長さが合わないとき、長さから逆算するか
     * @return コンテナ
     * @throws SpringNbtException パレットが空、data の長さが合わない、添字が範囲外のいずれか
     */
    public static PalettedContainer fromNbt(
            NbtCompound nbt, int entryCount, int minBits, boolean lenientBitStorage) {
        Objects.requireNonNull(nbt, "nbt");
        PalettedContainer result = new PalettedContainer(entryCount, minBits);
        NbtList paletteTag = nbt.optList("palette");

        if (paletteTag == null || paletteTag.size() == 0) {
            throw SpringNbtException.malformed("palette が無いか空");
        }

        // パレットの要素は生の NbtTag のまま持つ。並び順まで元どおりに書き戻すため
        for (NbtTag entry : paletteTag) {
            result.palette.add(entry);
        }

        long[] data = nbt.optLongArray("data");

        if (data == null) {
            // パレットが 1 要素なら data は無くてよい
            if (result.palette.size() != 1) {
                throw SpringNbtException.malformed(
                        "palette が " + result.palette.size() + " 要素なのに data が無い");
            }

            return result;
        }

        int bits = Math.max(minBits, ceilLog2(result.palette.size()));
        result.storage = BitStorage.fromLongs(data, bits, entryCount, lenientBitStorage);

        // 取り出した添字がパレットの範囲に収まっているか確かめる。
        // 黙って 0 番目で代替すると、壊れたデータをそうと分からない形で書き戻してしまう
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
     * NBT へ変換する。
     *
     * @return NBT
     */
    public NbtCompound toNbt() {
        NbtCompound result = new NbtCompound();
        NbtList paletteTag = new NbtList();

        // パレットの要素は読んだときのまま書き出す
        for (NbtTag entry : palette) {
            paletteTag.add(entry);
        }

        // パレットが 1 要素なら data は書かない。Minecraft と同じ振る舞い
        if (storage != null && palette.size() > 1) {
            result.set("data", new NbtLongArray(storage.toLongs()));
        }

        result.set("palette", paletteTag);
        return result;
    }

    /**
     * 添字の値を取り出す。
     *
     * @param index 添字
     * @return 値
     */
    public NbtTag get(int index) {
        checkIndex(index);

        // 記憶域が無いということは、全エントリがパレットの 0 番目
        if (storage == null) {
            return palette.get(0);
        }

        return palette.get(storage.get(index));
    }

    /**
     * 添字の値を書き換える。パレットに無ければ追加する。
     *
     * @param index 添字
     * @param value 値
     */
    public void set(int index, NbtTag value) {
        Objects.requireNonNull(value, "value");
        checkIndex(index);

        int paletteIndex = indexOfOrAdd(value);

        // 記憶域が無く、書き込む値も 0 番目なら何もしなくてよい
        if (storage == null && paletteIndex == 0) {
            return;
        }

        ensureStorage();
        storage.set(index, paletteIndex);
    }

    /**
     * 全エントリを 1 つの値で埋める。パレットもその 1 要素だけにする。
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
     * どのエントリからも参照されていないパレット要素を取り除き、添字を振り直す。
     *
     * <p>大量の {@code set} を行う用途で遅くならないよう、明示的に呼んだときだけ実行する。
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
        BitStorage rebuilt = BitStorage.create(newBits, entryCount);

        // 新しい添字へ置き換えながら詰め直す
        for (int index = 0; index < entryCount; index++) {
            rebuilt.set(index, remap[storage.get(index)]);
        }

        palette.clear();
        palette.addAll(compacted);

        if (compacted.size() == 1) {
            // 1 要素になったら記憶域を捨てる
            storage = null;
        } else {
            storage = rebuilt;
        }
    }

    /** パレット内の位置を返す。無ければ末尾へ追加する。 */
    private int indexOfOrAdd(NbtTag value) {
        // パレットは高々 4096 要素なので線形探索で足りる
        for (int index = 0; index < palette.size(); index++) {
            if (palette.get(index).equals(value)) {
                return index;
            }
        }

        palette.add(value);
        return palette.size() - 1;
    }

    /** 現在のパレット長に合うビット幅の記憶域を用意する。 */
    private void ensureStorage() {
        int required = Math.max(minBits, ceilLog2(palette.size()));

        if (storage == null) {
            // これまで単一値だったので、全エントリが 0 番目のまま始まる
            storage = BitStorage.create(required, entryCount);
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
     * {@code count} 個の値を表すのに必要な最小ビット数。1 なら 0。
     *
     * @param count 値の個数
     * @return ビット数
     */
    public static int ceilLog2(int count) {
        int bits = 0;

        // 1 を超える分だけシフトして数える
        while ((1 << bits) < count) {
            bits += 1;
        }

        return bits;
    }
}

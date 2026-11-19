package io.github.scriptarts.springnbt.world;

import io.github.scriptarts.springnbt.nbt.NamedTag;
import io.github.scriptarts.springnbt.nbt.NbtCompound;

/**
 * {@code level.dat}の内容
 *
 * <p>26.1以降は大幅に軽量化されており、ゲームルールやワールド生成設定は{@code data/minecraft/}配下の個別ファイルへ分離されている
 * それより前は、{@code level.dat}の中に入っている
 *
 * <p>スポーン地点・難易度・ハードコアの取得子は、構成の世代ごとのキーを読む
 */
public final class LevelData {

    private final String rootName;
    private final NbtCompound raw;
    private final NbtCompound data;
    private final WorldLayout layout;

    LevelData(NamedTag named, Integer formatDataVersion) {
        this.rootName = named.name();
        this.raw = named.tag();
        this.data = named.tag().getCompound("Data");
        this.layout = WorldLayout.detect(this.data, formatDataVersion);
    }

    /**
     * ワールドの構成の世代
     *
     * @return 世代
     */
    WorldLayout layout() {
        return layout;
    }

    /**
     * ルートのNBT
     * {@code Data}を含む
     *
     * @return NBT
     */
    public NbtCompound raw() {
        return raw;
    }

    /**
     * {@code Data}の中身
     * 実際の設定はここに入っている
     *
     * @return NBT
     */
    public NbtCompound data() {
        return data;
    }

    /**
     * チャンク構造のバージョン
     *
     * @return バージョン
     */
    public int dataVersion() {
        return data.getInt("DataVersion");
    }

    /**
     * ワールド名
     *
     * @return 名前
     */
    public String levelName() {
        return data.getString("LevelName");
    }

    /**
     * ワールドの経過時間（tick）
     *
     * @return 時間
     */
    public long time() {
        return data.getLong("Time");
    }

    /**
     * ゲームモード
     * 0=サバイバル 1=クリエイティブ 2=アドベンチャー 3=スペクテイター
     *
     * @return ゲームモード
     */
    public int gameType() {
        return data.getInt("GameType");
    }

    /**
     * スポーン地点の{@code [x, y, z]}
     *
     * @return 座標
     */
    public int[] spawnPos() {
        return layout.spawnPos(data);
    }

    /**
     * スポーン地点の次元ID
     *
     * <p>26.1より前の{@code level.dat}には無いので、{@code UNSUPPORTED_FEATURE}になる
     *
     * @return 次元ID
     */
    public String spawnDimension() {
        return layout.spawnDimension(data);
    }

    /**
     * 難易度（{@code normal}など）
     *
     * <p>26.1より前の数値は、0 {@code peaceful} 1 {@code easy} 2 {@code normal} 3 {@code hard}に直す
     *
     * @return 難易度
     */
    public String difficulty() {
        return layout.difficulty(data);
    }

    /**
     * ハードコアか
     *
     * @return ハードコアならtrue
     */
    public boolean isHardcore() {
        return layout.isHardcore(data);
    }

    /**
     * バージョン名（{@code 26.3}など）
     *
     * @return バージョン名
     */
    public String versionName() {
        return data.getCompound("Version").getString("Name");
    }

    /**
     * 書き出し用の{@link NamedTag}を作る
     *
     * @return NamedTag
     */
    public NamedTag toNamedTag() {
        return new NamedTag(rootName, raw);
    }
}

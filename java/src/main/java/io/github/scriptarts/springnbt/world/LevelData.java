package io.github.scriptarts.springnbt.world;

import io.github.scriptarts.springnbt.nbt.NamedTag;
import io.github.scriptarts.springnbt.nbt.NbtCompound;

/**
 * {@code level.dat} の内容
 *
 * <p>26.x では大幅に軽量化されており、ゲームルールやワールド生成設定は
 * {@code data/minecraft/} 配下の個別ファイルへ分離されている
 *
 * <p>仕様: {@code docs/spec/40-world-layout.md} 2章
 */
public final class LevelData {

    private final String rootName;
    private final NbtCompound raw;
    private final NbtCompound data;

    LevelData(NamedTag named) {
        this.rootName = named.name();
        this.raw = named.tag();
        this.data = named.tag().getCompound("Data");
    }

    /**
     * ルートの NBT
     * {@code Data} を含む
     *
     * @return NBT
     */
    public NbtCompound raw() {
        return raw;
    }

    /**
     * {@code Data} の中身
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
     * スポーン地点の {@code [x, y, z]}
     *
     * @return 座標
     */
    public int[] spawnPos() {
        return data.getCompound("spawn").getIntArray("pos");
    }

    /**
     * スポーン地点の次元ID
     *
     * @return 次元ID
     */
    public String spawnDimension() {
        return data.getCompound("spawn").getString("dimension");
    }

    /**
     * 難易度（{@code normal} など）
     *
     * @return 難易度
     */
    public String difficulty() {
        return data.getCompound("difficulty_settings").getString("difficulty");
    }

    /**
     * ハードコアか
     *
     * @return ハードコアなら true
     */
    public boolean isHardcore() {
        return data.getCompound("difficulty_settings").getBool("hardcore");
    }

    /**
     * バージョン名（{@code 26.2} など）
     *
     * @return バージョン名
     */
    public String versionName() {
        return data.getCompound("Version").getString("Name");
    }

    /**
     * 書き出し用の {@link NamedTag} を作る
     *
     * @return NamedTag
     */
    public NamedTag toNamedTag() {
        return new NamedTag(rootName, raw);
    }
}

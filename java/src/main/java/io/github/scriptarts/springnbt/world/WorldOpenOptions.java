package io.github.scriptarts.springnbt.world;

/** ワールドを開くときの動作 */
public final class WorldOpenOptions {

    private boolean writable;
    private boolean ignoreSessionLock;
    private ChunkReadOptions chunkRead = ChunkReadOptions.defaults();
    private ChunkWriteOptions chunkWrite = ChunkWriteOptions.defaults();

    /**
     * 既定のオプションを作る
     *
     * @return オプション
     */
    public static WorldOpenOptions defaults() {
        return new WorldOpenOptions();
    }

    /**
     * 読み書きで開くか
     * 既定は読み取り専用
     *
     * @return 読み書きなら true
     */
    public boolean writable() {
        return writable;
    }

    /**
     * 読み書きで開くかを設定する
     *
     * @param value 読み書きなら true
     * @return このオブジェクト
     */
    public WorldOpenOptions setWritable(boolean value) {
        this.writable = value;
        return this;
    }

    /**
     * {@code session.lock} の確認を飛ばすか
     *
     * <p>Minecraft が起動中のワールドへ書き込むとデータが壊れる
     * 既定では書き込みモードで開くときに必ず確認する
     * これを立てるのは自己責任
     *
     * @return 飛ばすなら true
     */
    public boolean ignoreSessionLock() {
        return ignoreSessionLock;
    }

    /**
     * {@code session.lock} の確認を飛ばすかを設定する
     *
     * @param value 飛ばすなら true
     * @return このオブジェクト
     */
    public WorldOpenOptions setIgnoreSessionLock(boolean value) {
        this.ignoreSessionLock = value;
        return this;
    }

    /**
     * チャンク読み込みのオプション
     *
     * @return オプション
     */
    public ChunkReadOptions chunkRead() {
        return chunkRead;
    }

    /**
     * チャンク読み込みのオプションを設定する
     *
     * @param value オプション
     * @return このオブジェクト
     */
    public WorldOpenOptions setChunkRead(ChunkReadOptions value) {
        this.chunkRead = value;
        return this;
    }

    /**
     * チャンク書き込みのオプション
     *
     * @return オプション
     */
    public ChunkWriteOptions chunkWrite() {
        return chunkWrite;
    }

    /**
     * チャンク書き込みのオプションを設定する
     *
     * @param value オプション
     * @return このオブジェクト
     */
    public WorldOpenOptions setChunkWrite(ChunkWriteOptions value) {
        this.chunkWrite = value;
        return this;
    }
}

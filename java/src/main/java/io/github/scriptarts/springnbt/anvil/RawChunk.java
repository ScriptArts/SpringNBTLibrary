package io.github.scriptarts.springnbt.anvil;

import java.util.Objects;

/**
 * リージョンファイルに格納されたままの、圧縮済みチャンクデータ
 *
 * <p>本ライブラリが解釈できない圧縮方式（LZ4 未導入、カスタム方式）でも
 * これなら取り出せる
 * バックアップや別ツールへの受け渡しに使う
 *
 * <p>仕様: {@code docs/spec/20-anvil-region.md} 5章
 *
 * @param compression この本体に使われている圧縮方式
 * @param data        圧縮されたままの本体
 * @param external    外部ファイル {@code c.X.Z.mcc} に格納されていたか
 */
public record RawChunk(ChunkCompression compression, byte[] data, boolean external) {

    /** 引数を検証する */
    public RawChunk {
        Objects.requireNonNull(compression, "compression");
        Objects.requireNonNull(data, "data");
    }

    /**
     * 内部格納のチャンクとして作る
     *
     * @param compression 圧縮方式
     * @param data        本体
     */
    public RawChunk(ChunkCompression compression, byte[] data) {
        this(compression, data, false);
    }
}

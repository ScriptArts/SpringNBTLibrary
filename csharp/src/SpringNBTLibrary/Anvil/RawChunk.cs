namespace SpringNBTLibrary.Anvil;

/// <summary>
/// リージョンファイルに格納されたままの、圧縮済みチャンクデータ
/// </summary>
/// <remarks>
/// <para>
/// 本ライブラリが解釈できない圧縮方式（LZ4 未導入、カスタム方式）でも
/// これなら取り出せる
/// バックアップや別ツールへの受け渡しに使う
/// </para>
/// <para>仕様: <c>docs/spec/20-anvil-region.md</c> 5章</para>
/// </remarks>
public sealed class RawChunk
{
    /// <summary>圧縮方式と本体を指定して作る</summary>
    public RawChunk(ChunkCompression compression, byte[] data, bool external = false)
    {
        ArgumentNullException.ThrowIfNull(data);
        Compression = compression;
        Data = data;
        External = external;
    }

    /// <summary>この本体に使われている圧縮方式</summary>
    public ChunkCompression Compression { get; }

    /// <summary>圧縮されたままの本体</summary>
    public byte[] Data { get; }

    /// <summary>
    /// 外部ファイル <c>c.X.Z.mcc</c> に格納されていたか
    /// </summary>
    /// <remarks>
    /// 書き込み時にこの値を指定する必要はない
    /// サイズに応じて <see cref="RegionFile"/> が自動的に判断する
    /// </remarks>
    public bool External { get; }

    /// <inheritdoc/>
    public override string ToString() =>
        $"RawChunk({Compression.AsString()}, {Data.Length} バイト, external={External})";
}

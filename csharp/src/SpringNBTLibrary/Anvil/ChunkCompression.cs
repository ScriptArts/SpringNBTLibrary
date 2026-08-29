namespace SpringNBTLibrary.Anvil;

/// <summary>
/// リージョンファイル内でチャンクに使われる圧縮方式。値は仕様が定める圧縮方式IDと一致する。
/// </summary>
/// <remarks>
/// <para>
/// NBT 層の <see cref="Nbt.Compression"/> とは別物であることに注意。
/// あちらはファイル全体の圧縮を表し、こちらはリージョン内の 1 チャンクに付く 1 バイトのIDを表す。
/// </para>
/// <para>仕様: <c>docs/spec/20-anvil-region.md</c> 3.1章</para>
/// </remarks>
public enum ChunkCompression
{
    /// <summary>GZip (RFC 1952)。ID=1。実データではほぼ使われない。</summary>
    Gzip = 1,

    /// <summary>Zlib (RFC 1950)。ID=2。Minecraft が実際に書き出す方式。</summary>
    Zlib = 2,

    /// <summary>無圧縮。ID=3。</summary>
    None = 3,

    /// <summary>LZ4（ブロック形式）。ID=4。任意依存。</summary>
    Lz4 = 4,

    /// <summary>サードパーティ製サーバのカスタム方式。ID=127。中身は解釈できない。</summary>
    Custom = 127,
}

/// <summary><see cref="ChunkCompression"/> の拡張メソッド。</summary>
public static class ChunkCompressionExtensions
{
    /// <summary>適合性テストで言語間比較に使う識別子を返す。</summary>
    public static string AsString(this ChunkCompression compression)
    {
        switch (compression)
        {
            case ChunkCompression.Gzip:
                return "gzip";
            case ChunkCompression.Zlib:
                return "zlib";
            case ChunkCompression.None:
                return "none";
            case ChunkCompression.Lz4:
                return "lz4";
            case ChunkCompression.Custom:
                return "custom";
            default:
                throw new ArgumentOutOfRangeException(
                    nameof(compression), compression, "未知の ChunkCompression");
        }
    }

    /// <summary>
    /// 圧縮方式IDから <see cref="ChunkCompression"/> を得る。
    /// </summary>
    /// <exception cref="SpringNbtException">未知のIDの場合（<see cref="ErrorCode.MalformedData"/>）。</exception>
    public static ChunkCompression FromId(int id)
    {
        // 仕様が定めるのは 1・2・3・4・127 の 5 種類だけ
        if (id == 1 || id == 2 || id == 3 || id == 4 || id == 127)
        {
            return (ChunkCompression)id;
        }

        throw SpringNbtException.Malformed($"未知の圧縮方式ID: {id}");
    }
}

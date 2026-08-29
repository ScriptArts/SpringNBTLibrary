using System.Globalization;
using System.Text;
using SpringNBTLibrary.Anvil;
using SpringNBTLibrary.Nbt;

namespace SpringNBTLibrary.Conformance;

/// <summary>
/// リージョンファイルの中身を、言語をまたいで文字列として完全一致する形へ写す。
/// </summary>
/// <remarks>仕様: <c>docs/spec/90-conformance.md</c> 2.3章</remarks>
internal static class RegionReport
{
    /// <summary>
    /// 存在するチャンクを 1 行 1 チャンクで書き出す。並びはロケーションテーブルの添字順。
    /// </summary>
    /// <remarks>
    /// 各行は「絶対X 絶対Z セクタ数 タイムスタンプ 圧縮方式 展開後バイト数 ルート直下キー数」。
    /// 展開後バイト数を含めるのは、ヘッダ解析だけでなく展開と NBT 解釈まで通ったことを確かめるため。
    /// </remarks>
    internal static string List(RegionFile region)
    {
        StringBuilder builder = new StringBuilder();
        builder.Append(string.Create(
            CultureInfo.InvariantCulture, $"region {region.RegionX} {region.RegionZ}\n"));

        int total = 0;

        foreach (ChunkPos position in region.ChunkPositions())
        {
            RawChunk? raw = region.ReadChunkRaw(position.X, position.Z);

            if (raw is null)
            {
                continue;
            }

            NbtCompound? chunk = region.ReadChunk(position.X, position.Z);
            int keyCount = 0;

            if (chunk is not null)
            {
                keyCount = chunk.Count;
            }

            NbtWriteOptions options = new NbtWriteOptions { Compression = Nbt.Compression.None };
            int plainLength = 0;

            if (chunk is not null)
            {
                plainLength = NbtIo.WriteBytes(new NamedTag(string.Empty, chunk), options).Length;
            }

            builder.Append(string.Create(
                CultureInfo.InvariantCulture,
                $"{position.X} {position.Z} {region.Timestamp(position.X, position.Z)} "
                    + $"{raw.Compression.AsString()} {raw.Data.Length} {plainLength} {keyCount}\n"));
            total += 1;
        }

        builder.Append(string.Create(CultureInfo.InvariantCulture, $"total {total}\n"));
        return builder.ToString();
    }

    /// <summary>
    /// 全チャンクを読み直し、無圧縮で新しいリージョンへ詰め直して書き出す。
    /// </summary>
    /// <remarks>
    /// 無圧縮にするのは、zlib の出力が処理系ごとに違い、
    /// 圧縮したままでは言語間でバイトが一致しないため。
    /// これによりセクタ確保とヘッダ生成のロジックを直接比較できる。
    /// </remarks>
    internal static void Rewrite(RegionFile source, string outputPath)
    {
        // 途中結果が残らないよう、書き出し先は必ず作り直す
        if (File.Exists(outputPath))
        {
            File.Delete(outputPath);
        }

        using RegionFile destination = RegionFile.Open(outputPath, RegionFileMode.ReadWrite);

        foreach (ChunkPos position in source.ChunkPositions())
        {
            NbtCompound? chunk = source.ReadChunk(position.X, position.Z);

            if (chunk is null)
            {
                continue;
            }

            destination.WriteChunk(position.X, position.Z, chunk, ChunkCompression.None);
            destination.SetTimestamp(
                position.X, position.Z, source.Timestamp(position.X, position.Z));
        }

        destination.Flush();
    }
}

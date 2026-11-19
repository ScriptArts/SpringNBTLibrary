using System.Globalization;
using System.Text;
using SpringNBTLibrary.Nbt;
using SpringNBTLibrary.World;

namespace SpringNBTLibrary.Conformance;

/// <summary>
/// チャンクの中身を、言語をまたいで文字列として完全一致する形へ写す
/// </summary>
internal static class ChunkReport
{
    /// <summary>
    /// バイオームを数値のIDで持つチャンクか
    /// </summary>
    /// <remarks>
    /// <see cref="Chunk.GetBiome"/>が<see cref="ErrorCode.UnsupportedFeature"/>になれば、数値のIDで持つ1.17までの形式
    /// </remarks>
    internal static bool UsesBiomeIds(Chunk chunk, int y)
    {
        // UNSUPPORTED_FEATUREだけを受け止め、ほかのエラーは検証の失敗としてそのまま伝える
        try
        {
            chunk.GetBiome(0, y, 0);
        }
        catch (SpringNbtException error) when (error.Code == ErrorCode.UnsupportedFeature)
        {
            return true;
        }

        return false;
    }

    /// <summary>
    /// チャンクの全ブロック・全バイオームを走査して集計する
    /// </summary>
    /// <remarks>
    /// パレットとビットストレージを端から端まで通すので、
    /// ビット詰めの実装が1か所でもずれれば集計値が変わる
    /// </remarks>
    internal static string Describe(Chunk chunk)
    {
        StringBuilder builder = new StringBuilder();
        builder.Append(string.Create(
            CultureInfo.InvariantCulture,
            $"chunk {chunk.X} {chunk.Z} {chunk.MinSectionY} {chunk.Status}\n"));

        SortedDictionary<string, int> blocks = new SortedDictionary<string, int>(StringComparer.Ordinal);
        SortedDictionary<string, int> biomes = new SortedDictionary<string, int>(StringComparer.Ordinal);
        SortedDictionary<int, int> biomeIds = new SortedDictionary<int, int>();
        bool numericBiomes = false;
        List<int> sectionYs = chunk.SectionYs.ToList();

        // 最初に読む位置で、バイオームを名前とIDのどちらで持つかを決める
        if (sectionYs.Count > 0)
        {
            numericBiomes = UsesBiomeIds(chunk, sectionYs[0] * 16);
        }

        foreach (int sectionY in sectionYs)
        {
            ChunkSection section = chunk.Section(sectionY)!;
            int blockPalette = 0;
            int biomePalette = 0;
            int blockBits = 0;
            int biomeBits = 0;

            if (section.HasBlockStates)
            {
                blockPalette = section.BlockStates!.Palette.Count;
                blockBits = section.BlockStates.BitsPerEntry;
            }

            if (section.HasBiomes)
            {
                biomePalette = section.Biomes!.Palette.Count;
                biomeBits = section.Biomes.BitsPerEntry;
            }

            builder.Append(string.Create(
                CultureInfo.InvariantCulture,
                $"section {sectionY} {blockPalette} {blockBits} {biomePalette} {biomeBits}\n"));

            // 全ブロックを1つずつ読んで、状態の文字列表現ごとに数える
            for (int y = 0; y < 16; y++)
            {
                for (int z = 0; z < 16; z++)
                {
                    for (int x = 0; x < 16; x++)
                    {
                        BlockState? block = chunk.GetBlock(x, (sectionY * 16) + y, z);

                        // ブロックを持たないセクションの位置は数えない
                        if (block is null)
                        {
                            continue;
                        }

                        string key = block.ToString();
                        blocks.TryGetValue(key, out int count);
                        blocks[key] = count + 1;
                    }
                }
            }

            // バイオームは4×4×4単位なので、4ブロックおきに見る
            for (int y = 0; y < 16; y += 4)
            {
                for (int z = 0; z < 16; z += 4)
                {
                    for (int x = 0; x < 16; x += 4)
                    {
                        // 数値のIDで持つチャンクは、IDごとに数える
                        if (numericBiomes)
                        {
                            int? biomeId = chunk.GetBiomeId(x, (sectionY * 16) + y, z);

                            // Biomesを読めない位置は数えない
                            if (biomeId is null)
                            {
                                continue;
                            }

                            biomeIds.TryGetValue(biomeId.Value, out int idCount);
                            biomeIds[biomeId.Value] = idCount + 1;
                            continue;
                        }

                        string? biome = chunk.GetBiome(x, (sectionY * 16) + y, z);

                        // バイオームを持たないセクションの位置は数えない
                        if (biome is null)
                        {
                            continue;
                        }

                        biomes.TryGetValue(biome, out int count);
                        biomes[biome] = count + 1;
                    }
                }
            }
        }

        // 名前の昇順で出すので、内部の並びに関係なく同じ出力になる
        foreach (KeyValuePair<string, int> entry in blocks)
        {
            builder.Append(string.Create(CultureInfo.InvariantCulture, $"block {entry.Key} {entry.Value}\n"));
        }

        foreach (KeyValuePair<string, int> entry in biomes)
        {
            builder.Append(string.Create(CultureInfo.InvariantCulture, $"biome {entry.Key} {entry.Value}\n"));
        }

        // IDの数値の昇順で出す
        foreach (KeyValuePair<int, int> entry in biomeIds)
        {
            builder.Append(string.Create(CultureInfo.InvariantCulture, $"biome-id {entry.Key} {entry.Value}\n"));
        }

        return builder.ToString();
    }

    /// <summary>
    /// 決まった手順でチャンクを編集する
    /// 全言語で同じ結果になるはず
    /// </summary>
    /// <remarks>
    /// パレット拡張・ビット幅の再計算・未使用要素の掃除を一通り通す
    /// 出力バイト列を比較すれば、これらの実装が一致していることを確かめられる
    /// </remarks>
    internal static void Edit(Chunk chunk)
    {
        int baseY = chunk.MinSectionY * 16;

        // パレットに無いブロックを次々に置き、ビット幅の拡張を起こす
        for (int index = 0; index < 20; index++)
        {
            BlockState state = BlockState.Parse(
                string.Create(CultureInfo.InvariantCulture, $"minecraft:edited_{index}[step={index}]"));
            chunk.SetBlock(index % 16, baseY + (index / 16), index % 16, state);
        }

        // プロパティ付きのブロックを置く
        // 1つ目と2つ目はプロパティの並び順だけが違う同じ状態、3つ目は名前空間を省いて書いた別の状態
        chunk.SetBlock(1, baseY + 2, 1, BlockState.Parse("minecraft:oak_stairs[facing=north,half=top]"));
        chunk.SetBlock(2, baseY + 2, 2, BlockState.Parse("minecraft:oak_stairs[half=top,facing=north]"));
        chunk.SetBlock(3, baseY + 2, 3, BlockState.Parse("oak_stairs[facing=south]"));

        // プロパティの無いブロックを置く
        // パレットには文字列で入るので、Compoundの要素と混ざったリストの書き出しを通る
        chunk.SetBlock(4, baseY + 2, 4, BlockState.Parse("minecraft:edited_plain"));

        // バイオームも書き換える
        // 数値のIDで持つチャンクは、名前の代わりにID（2は砂漠、21はジャングル）で書く
        if (UsesBiomeIds(chunk, baseY))
        {
            chunk.SetBiomeId(0, baseY, 0, 2);
            chunk.SetBiomeId(8, baseY + 8, 8, 21);
        }
        else
        {
            chunk.SetBiome(0, baseY, 0, "minecraft:desert");
            chunk.SetBiome(8, baseY + 8, 8, "minecraft:jungle");
        }

        // 使われなくなったパレット要素を掃除する
        chunk.Compact();

        // 高さマップと光源は再計算しないので、無効化してMinecraftに任せる
        chunk.ClearHeightmaps();
        chunk.InvalidateLighting();
    }
}

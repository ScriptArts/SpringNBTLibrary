package io.github.scriptarts.springnbt.conformance;

import io.github.scriptarts.springnbt.world.BlockState;
import io.github.scriptarts.springnbt.world.Chunk;
import io.github.scriptarts.springnbt.world.ChunkSection;
import java.util.Map;
import java.util.SortedMap;
import java.util.TreeMap;

/**
 * チャンクの中身を、言語をまたいで文字列として完全一致する形へ写す。
 *
 * <p>仕様: {@code docs/spec/90-conformance.md} 2.3章
 */
final class ChunkReport {

    private ChunkReport() {
        // ユーティリティクラス
    }

    /**
     * チャンクの全ブロック・全バイオームを走査して集計する。
     *
     * <p>パレットとビットストレージを端から端まで通すので、
     * ビット詰めの実装が 1 か所でもずれれば集計値が変わる。
     */
    static String describe(Chunk chunk) {
        StringBuilder builder = new StringBuilder();
        builder.append("chunk ").append(chunk.x()).append(' ').append(chunk.z()).append(' ')
                .append(chunk.minSectionY()).append(' ').append(chunk.status()).append('\n');

        SortedMap<String, Integer> blocks = new TreeMap<>();
        SortedMap<String, Integer> biomes = new TreeMap<>();

        for (int sectionY : chunk.sectionYs()) {
            ChunkSection section = chunk.section(sectionY);
            int blockPalette = 0;
            int biomePalette = 0;
            int blockBits = 0;
            int biomeBits = 0;

            if (section.hasBlockStates()) {
                blockPalette = section.blockStates().palette().size();
                blockBits = section.blockStates().bitsPerEntry();
            }

            if (section.hasBiomes()) {
                biomePalette = section.biomes().palette().size();
                biomeBits = section.biomes().bitsPerEntry();
            }

            builder.append("section ").append(sectionY).append(' ')
                    .append(blockPalette).append(' ').append(blockBits).append(' ')
                    .append(biomePalette).append(' ').append(biomeBits).append('\n');

            // 全ブロックを 1 つずつ読んで、状態の文字列表現ごとに数える
            for (int y = 0; y < 16; y++) {
                for (int z = 0; z < 16; z++) {
                    for (int x = 0; x < 16; x++) {
                        BlockState block = chunk.getBlock(x, (sectionY * 16) + y, z);

                        if (block == null) {
                            continue;
                        }

                        blocks.merge(block.toString(), 1, Integer::sum);
                    }
                }
            }

            // バイオームは 4×4×4 単位なので、4 ブロックおきに見る
            for (int y = 0; y < 16; y += 4) {
                for (int z = 0; z < 16; z += 4) {
                    for (int x = 0; x < 16; x += 4) {
                        String biome = chunk.getBiome(x, (sectionY * 16) + y, z);

                        if (biome == null) {
                            continue;
                        }

                        biomes.merge(biome, 1, Integer::sum);
                    }
                }
            }
        }

        // 名前の昇順で出すので、内部の並びに関係なく同じ出力になる
        for (Map.Entry<String, Integer> entry : blocks.entrySet()) {
            builder.append("block ").append(entry.getKey()).append(' ')
                    .append(entry.getValue()).append('\n');
        }

        for (Map.Entry<String, Integer> entry : biomes.entrySet()) {
            builder.append("biome ").append(entry.getKey()).append(' ')
                    .append(entry.getValue()).append('\n');
        }

        return builder.toString();
    }

    /**
     * 決まった手順でチャンクを編集する。全言語で同じ結果になるはず。
     *
     * <p>パレット拡張・ビット幅の再計算・未使用要素の掃除を一通り通す。
     */
    static void edit(Chunk chunk) {
        int baseY = chunk.minSectionY() * 16;

        // パレットに無いブロックを次々に置き、ビット幅の拡張を起こす
        for (int index = 0; index < 20; index++) {
            BlockState state = BlockState.parse(
                    "minecraft:edited_" + index + "[step=" + index + "]");
            chunk.setBlock(index % 16, baseY + (index / 16), index % 16, state);
        }

        // プロパティ付きのブロックを、名前は同じで状態違いで置く
        chunk.setBlock(1, baseY + 2, 1, BlockState.parse("minecraft:oak_stairs[facing=north,half=top]"));
        chunk.setBlock(2, baseY + 2, 2, BlockState.parse("minecraft:oak_stairs[half=top,facing=north]"));
        chunk.setBlock(3, baseY + 2, 3, BlockState.parse("oak_stairs[facing=south]"));

        // バイオームも書き換える
        chunk.setBiome(0, baseY, 0, "minecraft:desert");
        chunk.setBiome(8, baseY + 8, 8, "minecraft:jungle");

        // 使われなくなったパレット要素を掃除する
        chunk.compact();

        // 高さマップと光源は再計算しないので、無効化して Minecraft に任せる
        chunk.clearHeightmaps();
        chunk.invalidateLighting();
    }
}

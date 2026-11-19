package io.github.scriptarts.springnbt.conformance;

import io.github.scriptarts.springnbt.ErrorCode;
import io.github.scriptarts.springnbt.SpringNbtException;
import io.github.scriptarts.springnbt.world.BlockState;
import io.github.scriptarts.springnbt.world.Chunk;
import io.github.scriptarts.springnbt.world.ChunkSection;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.SortedMap;
import java.util.TreeMap;

/**
 * チャンクの中身を、言語をまたいで文字列として完全一致する形へ写す
 */
final class ChunkReport {

    private ChunkReport() {
        // ユーティリティクラス
    }

    /**
     * バイオームを数値のIDで持つチャンクか
     *
     * <p>{@link Chunk#getBiome}が{@code UNSUPPORTED_FEATURE}になれば、数値のIDで持つ1.17までの形式
     */
    static boolean usesBiomeIds(Chunk chunk, int y) {
        try {
            chunk.getBiome(0, y, 0);
        } catch (SpringNbtException error) {
            // ほかのエラーは検証の失敗としてそのまま伝える
            if (error.code() != ErrorCode.UNSUPPORTED_FEATURE) {
                throw error;
            }

            return true;
        }

        return false;
    }

    /**
     * チャンクの全ブロック・全バイオームを走査して集計する
     *
     * <p>パレットとビットストレージを端から端まで通すので、
     * ビット詰めの実装が1か所でもずれれば集計値が変わる
     */
    static String describe(Chunk chunk) {
        StringBuilder builder = new StringBuilder();
        builder.append("chunk ").append(chunk.x()).append(' ').append(chunk.z()).append(' ')
                .append(chunk.minSectionY()).append(' ').append(chunk.status()).append('\n');

        SortedMap<String, Integer> blocks = new TreeMap<>();
        SortedMap<String, Integer> biomes = new TreeMap<>();
        SortedMap<Integer, Integer> biomeIds = new TreeMap<>();
        boolean numericBiomes = false;
        List<Integer> sectionYs = new ArrayList<>(chunk.sectionYs());

        // 最初に読む位置で、バイオームを名前とIDのどちらで持つかを決める
        if (!sectionYs.isEmpty()) {
            numericBiomes = usesBiomeIds(chunk, sectionYs.get(0) * 16);
        }

        for (int sectionY : sectionYs) {
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

            // 全ブロックを1つずつ読んで、状態の文字列表現ごとに数える
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

            // バイオームは4×4×4単位なので、4ブロックおきに見る
            for (int y = 0; y < 16; y += 4) {
                for (int z = 0; z < 16; z += 4) {
                    for (int x = 0; x < 16; x += 4) {
                        // 数値のIDで持つチャンクは、IDごとに数える
                        if (numericBiomes) {
                            Integer biomeId = chunk.getBiomeId(x, (sectionY * 16) + y, z);

                            if (biomeId == null) {
                                continue;
                            }

                            biomeIds.merge(biomeId, 1, Integer::sum);
                            continue;
                        }

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

        // IDの数値の昇順で出す
        for (Map.Entry<Integer, Integer> entry : biomeIds.entrySet()) {
            builder.append("biome-id ").append(entry.getKey()).append(' ')
                    .append(entry.getValue()).append('\n');
        }

        return builder.toString();
    }

    /**
     * 決まった手順でチャンクを編集する
     * 全言語で同じ結果になるはず
     *
     * <p>パレット拡張・ビット幅の再計算・未使用要素の掃除を一通り通す
     */
    static void edit(Chunk chunk) {
        int baseY = chunk.minSectionY() * 16;

        // パレットに無いブロックを次々に置き、ビット幅の拡張を起こす
        for (int index = 0; index < 20; index++) {
            BlockState state = BlockState.parse(
                    "minecraft:edited_" + index + "[step=" + index + "]");
            chunk.setBlock(index % 16, baseY + (index / 16), index % 16, state);
        }

        // プロパティ付きのブロックを置く
        // 1つ目と2つ目はプロパティの並び順だけが違う同じ状態、3つ目は名前空間を省いて書いた別の状態
        chunk.setBlock(1, baseY + 2, 1, BlockState.parse("minecraft:oak_stairs[facing=north,half=top]"));
        chunk.setBlock(2, baseY + 2, 2, BlockState.parse("minecraft:oak_stairs[half=top,facing=north]"));
        chunk.setBlock(3, baseY + 2, 3, BlockState.parse("oak_stairs[facing=south]"));

        // プロパティの無いブロックを置く
        // パレットには文字列で入るので、Compoundの要素と混ざったリストの書き出しを通る
        chunk.setBlock(4, baseY + 2, 4, BlockState.parse("minecraft:edited_plain"));

        // バイオームも書き換える
        // 数値のIDで持つチャンクは、名前の代わりにID（2は砂漠、21はジャングル）で書く
        if (usesBiomeIds(chunk, baseY)) {
            chunk.setBiomeId(0, baseY, 0, 2);
            chunk.setBiomeId(8, baseY + 8, 8, 21);
        } else {
            chunk.setBiome(0, baseY, 0, "minecraft:desert");
            chunk.setBiome(8, baseY + 8, 8, "minecraft:jungle");
        }

        // 使われなくなったパレット要素を掃除する
        chunk.compact();

        // 高さマップと光源は再計算しないので、無効化してMinecraftに任せる
        chunk.clearHeightmaps();
        chunk.invalidateLighting();
    }
}

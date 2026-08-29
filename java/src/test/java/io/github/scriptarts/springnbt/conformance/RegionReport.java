package io.github.scriptarts.springnbt.conformance;

import io.github.scriptarts.springnbt.anvil.ChunkCompression;
import io.github.scriptarts.springnbt.anvil.ChunkPos;
import io.github.scriptarts.springnbt.anvil.RawChunk;
import io.github.scriptarts.springnbt.anvil.RegionFile;
import io.github.scriptarts.springnbt.anvil.RegionFileMode;
import io.github.scriptarts.springnbt.nbt.Compression;
import io.github.scriptarts.springnbt.nbt.NamedTag;
import io.github.scriptarts.springnbt.nbt.NbtCompound;
import io.github.scriptarts.springnbt.nbt.NbtIo;
import io.github.scriptarts.springnbt.nbt.NbtWriteOptions;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * リージョンファイルの中身を、言語をまたいで文字列として完全一致する形へ写す。
 *
 * <p>仕様: {@code docs/spec/90-conformance.md} 2.3章
 */
final class RegionReport {

    private RegionReport() {
        // ユーティリティクラス
    }

    /**
     * 存在するチャンクを 1 行 1 チャンクで書き出す。並びはロケーションテーブルの添字順。
     *
     * <p>各行は「絶対X 絶対Z タイムスタンプ 圧縮方式 圧縮後バイト数 展開後バイト数 キー数」。
     */
    static String list(RegionFile region) {
        StringBuilder builder = new StringBuilder();
        builder.append("region ").append(region.regionX()).append(' ')
                .append(region.regionZ()).append('\n');

        int total = 0;

        for (ChunkPos position : region.chunkPositions()) {
            RawChunk raw = region.readChunkRaw(position.x(), position.z());

            if (raw == null) {
                continue;
            }

            NbtCompound chunk = region.readChunk(position.x(), position.z());
            int keyCount = 0;
            int plainLength = 0;

            if (chunk != null) {
                keyCount = chunk.size();
                NbtWriteOptions options =
                        NbtWriteOptions.defaults().setCompression(Compression.NONE);
                plainLength = NbtIo.writeBytes(new NamedTag("", chunk), options).length;
            }

            builder.append(position.x()).append(' ')
                    .append(position.z()).append(' ')
                    .append(region.timestamp(position.x(), position.z())).append(' ')
                    .append(raw.compression().asString()).append(' ')
                    .append(raw.data().length).append(' ')
                    .append(plainLength).append(' ')
                    .append(keyCount).append('\n');
            total += 1;
        }

        builder.append("total ").append(total).append('\n');
        return builder.toString();
    }

    /**
     * 全チャンクを読み直し、無圧縮で新しいリージョンへ詰め直して書き出す。
     *
     * <p>無圧縮にするのは、zlib の出力が処理系ごとに違い、
     * 圧縮したままでは言語間でバイトが一致しないため。
     */
    static void rewrite(RegionFile source, Path outputPath) throws IOException {
        // 途中結果が残らないよう、書き出し先は必ず作り直す
        Files.deleteIfExists(outputPath);

        try (RegionFile destination = RegionFile.open(outputPath, RegionFileMode.READ_WRITE)) {
            for (ChunkPos position : source.chunkPositions()) {
                NbtCompound chunk = source.readChunk(position.x(), position.z());

                if (chunk == null) {
                    continue;
                }

                destination.writeChunk(position.x(), position.z(), chunk, ChunkCompression.NONE);
                destination.setTimestamp(position.x(), position.z(),
                        source.timestamp(position.x(), position.z()));
            }

            destination.flush();
        }
    }
}

package io.github.scriptarts.springnbt.conformance;

import io.github.scriptarts.springnbt.SpringNbt;
import io.github.scriptarts.springnbt.SpringNbtException;
import io.github.scriptarts.springnbt.anvil.RegionFile;
import io.github.scriptarts.springnbt.anvil.RegionFileMode;
import io.github.scriptarts.springnbt.nbt.Compression;
import io.github.scriptarts.springnbt.nbt.NamedTag;
import io.github.scriptarts.springnbt.nbt.NbtFormat;
import io.github.scriptarts.springnbt.nbt.NbtIo;
import io.github.scriptarts.springnbt.nbt.NbtReadOptions;
import io.github.scriptarts.springnbt.nbt.NbtReadResult;
import io.github.scriptarts.springnbt.nbt.NbtWriteOptions;
import io.github.scriptarts.springnbt.nbt.Snbt;
import io.github.scriptarts.springnbt.world.Chunk;
import io.github.scriptarts.springnbt.world.ChunkReadOptions;
import io.github.scriptarts.springnbt.world.VersionMismatchAction;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

/**
 * 適合性検証ツール。4言語すべてが同じインターフェースで同じ出力を出す。
 *
 * <p>{@code spec/run-conformance.sh} がこのツールを4言語ぶん起動し、
 * 出力を相互に diff することで「4言語が同一に振る舞う」ことを機械的に確かめる。
 *
 * <p>仕様: {@code docs/spec/90-conformance.md} 2.3章
 */
public final class Conformance {

    private Conformance() {
        // エントリポイントのみ
    }

    /**
     * エントリポイント。
     *
     * @param args コマンドライン引数
     */
    public static void main(String[] args) {
        System.exit(run(args));
    }

    private static int run(String[] args) {
        if (args.length == 0) {
            System.err.println(usage());
            return 2;
        }

        try {
            return switch (args[0]) {
                case "decode" -> runDecode(args);
                case "encode" -> runEncode(args);
                case "snbt" -> runSnbt(args);
                case "nbt-list" -> runNbtList(args);
                case "region-list" -> runRegionList(args);
                case "region-rewrite" -> runRegionRewrite(args);
                case "chunk-report" -> runChunkReport(args);
                case "chunk-edit" -> runChunkEdit(args);
                case "version" -> {
                    System.out.print(versionLine());
                    yield 0;
                }
                default -> {
                    System.err.println(usage());
                    yield 2;
                }
            };
        } catch (SpringNbtException error) {
            // 4言語で同じ ErrorCode を出すことが検証対象なので、コードを機械可読な形で出す
            System.err.print("ERROR " + error.code().asString() + " " + error.getMessage() + "\n");
            return 1;
        } catch (IOException error) {
            System.err.print("ERROR IO " + error.getMessage() + "\n");
            return 1;
        }
    }

    /** 入力を読み、正規化JSON を書き出す。 */
    private static int runDecode(String[] args) throws IOException {
        if (args.length < 3) {
            System.err.println(usage());
            return 2;
        }

        NbtFormat format = parseFormat(args);
        NamedTag named = NbtIo.readFile(Path.of(args[1]), NbtReadOptions.defaults().setFormat(format));

        writeTextFile(args[2], NormalizedJson.write(named, format));
        return 0;
    }

    /** 入力を読み、無圧縮で書き直す。ラウンドトリップ検証に使う。 */
    private static int runEncode(String[] args) throws IOException {
        if (args.length < 3) {
            System.err.println(usage());
            return 2;
        }

        NbtFormat format = parseFormat(args);
        NamedTag named = NbtIo.readFile(Path.of(args[1]), NbtReadOptions.defaults().setFormat(format));

        NbtWriteOptions write = NbtWriteOptions.defaults()
                .setFormat(format)
                .setCompression(Compression.NONE);
        Files.write(Path.of(args[2]), NbtIo.writeBytes(named, write));
        return 0;
    }

    /** 入力を読み、1行の SNBT を書き出す。 */
    private static int runSnbt(String[] args) throws IOException {
        if (args.length < 3) {
            System.err.println(usage());
            return 2;
        }

        NbtFormat format = parseFormat(args);
        NamedTag named = NbtIo.readFile(Path.of(args[1]), NbtReadOptions.defaults().setFormat(format));

        writeTextFile(args[2], Snbt.write(named.tag()) + "\n");
        return 0;
    }

    /** 連なった NBT を、位置を追いながら一覧として書き出す。 */
    private static int runNbtList(String[] args) throws IOException {
        if (args.length < 3) {
            System.err.println(usage());
            return 2;
        }

        NbtFormat format = parseFormat(args);
        NbtReadOptions options =
                NbtReadOptions.defaults().setFormat(format).setCompression(Compression.NONE);

        byte[] bytes = Files.readAllBytes(Path.of(args[1]));
        List<NamedTag> all = NbtIo.readBytesAll(bytes, options);
        StringBuilder builder = new StringBuilder();
        builder.append("count ").append(all.size()).append("\n");

        int offset = 0;
        int index = 0;

        // 位置を指定した読み込みでも同じ並びになることを確かめる
        while (offset < bytes.length) {
            NbtReadResult result = NbtIo.readBytesAt(bytes, offset, options);
            builder.append(index).append(" ").append(offset).append(" ").append(result.end())
                    .append(" ").append(result.tag().name())
                    .append(" ").append(result.tag().tag().size()).append("\n");
            offset = result.end();
            index++;
        }

        builder.append("total ").append(index).append(" ").append(offset).append("\n");
        writeTextFile(args[2], builder.toString());
        return 0;
    }

    /** リージョンの中身を一覧として書き出す。 */
    private static int runRegionList(String[] args) throws IOException {
        if (args.length < 3) {
            System.err.println(usage());
            return 2;
        }

        try (RegionFile region = RegionFile.open(Path.of(args[1]), RegionFileMode.READ_ONLY)) {
            writeTextFile(args[2], RegionReport.list(region));
        }

        return 0;
    }

    /** リージョンを読み直し、無圧縮で詰め直して書き出す。 */
    private static int runRegionRewrite(String[] args) throws IOException {
        if (args.length < 3) {
            System.err.println(usage());
            return 2;
        }

        try (RegionFile region = RegionFile.open(Path.of(args[1]), RegionFileMode.READ_ONLY)) {
            RegionReport.rewrite(region, Path.of(args[2]));
        }

        return 0;
    }

    /** チャンクの全ブロック・全バイオームを走査して集計を書き出す。 */
    private static int runChunkReport(String[] args) throws IOException {
        if (args.length < 3) {
            System.err.println(usage());
            return 2;
        }

        writeTextFile(args[2], ChunkReport.describe(readChunkFile(args[1])));
        return 0;
    }

    /** 決まった手順でチャンクを編集し、無圧縮で書き出す。 */
    private static int runChunkEdit(String[] args) throws IOException {
        if (args.length < 3) {
            System.err.println(usage());
            return 2;
        }

        Chunk chunk = readChunkFile(args[1]);
        ChunkReport.edit(chunk);

        NbtWriteOptions write = NbtWriteOptions.defaults().setCompression(Compression.NONE);
        Files.write(Path.of(args[2]),
                NbtIo.writeBytes(new NamedTag("", chunk.toNbt(null)), write));
        return 0;
    }

    /** チャンク NBT のファイルを読む。 */
    private static Chunk readChunkFile(String path) {
        NamedTag named = NbtIo.readFile(Path.of(path), null);

        // 検証では DataVersion の違いを警告にせず、そのまま読む
        ChunkReadOptions options = ChunkReadOptions.defaults()
                .setOnVersionMismatch(VersionMismatchAction.IGNORE);
        return Chunk.fromNbt(named.tag(), options);
    }

    /** {@code --format network} が指定されていればネットワーク形式として読む。 */
    private static NbtFormat parseFormat(String[] args) {
        // 3 番目以降の引数からオプションを探す
        for (int index = 3; index < args.length - 1; index++) {
            if (args[index].equals("--format") && args[index + 1].equals("network")) {
                return NbtFormat.NETWORK;
            }
        }

        return NbtFormat.JAVA;
    }

    /**
     * 改行を変換せず、BOM も付けずに UTF-8 で書く。
     *
     * <p>孤立サロゲートを含みうるが、標準の UTF-8 エンコーダは置換文字にしてしまうため、
     * 自前で符号化する。
     */
    private static void writeTextFile(String path, String content) throws IOException {
        Files.write(Path.of(path), encodeUtf8KeepingSurrogates(content));
    }

    /** 孤立サロゲートを WTF-8（3バイト形式）として保持したまま UTF-8 へ符号化する。 */
    private static byte[] encodeUtf8KeepingSurrogates(String text) {
        java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream();

        // コード単位を順に見て、正しいサロゲートペアだけ 1 文字として符号化する
        for (int index = 0; index < text.length(); index++) {
            char unit = text.charAt(index);

            if (Character.isHighSurrogate(unit)
                    && index + 1 < text.length()
                    && Character.isLowSurrogate(text.charAt(index + 1))) {
                int codePoint = Character.toCodePoint(unit, text.charAt(index + 1));
                out.writeBytes(new String(Character.toChars(codePoint))
                        .getBytes(StandardCharsets.UTF_8));
                index += 1;
            } else if (Character.isSurrogate(unit)) {
                // 孤立サロゲートは 3 バイト形式でそのまま書く
                out.write(0xE0 | ((unit >> 12) & 0x0F));
                out.write(0x80 | ((unit >> 6) & 0x3F));
                out.write(0x80 | (unit & 0x3F));
            } else {
                out.writeBytes(String.valueOf(unit).getBytes(StandardCharsets.UTF_8));
            }
        }

        return out.toByteArray();
    }

    private static String versionLine() {
        return "java spring-nbt-library 0.1.0 target_data_version="
                + SpringNbt.TARGET_DATA_VERSION + "\n";
    }

    private static String usage() {
        return """
                使い方:
                  Conformance decode  <入力パス> <出力JSONパス> [--format network]
                  Conformance encode  <入力パス> <出力バイナリパス> [--format network]
                  Conformance snbt    <入力パス> <出力SNBTパス> [--format network]
                  Conformance nbt-list <入力パス> <出力テキストパス> [--format network]
                  Conformance region-list    <入力mcaパス> <出力テキストパス>
                  Conformance region-rewrite <入力mcaパス> <出力mcaパス>
                  Conformance chunk-report   <入力チャンクnbt> <出力テキストパス>
                  Conformance chunk-edit     <入力チャンクnbt> <出力nbtパス>
                  Conformance version""";
    }
}

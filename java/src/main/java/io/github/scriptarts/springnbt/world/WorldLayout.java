package io.github.scriptarts.springnbt.world;

import io.github.scriptarts.springnbt.ErrorCode;
import io.github.scriptarts.springnbt.SpringNbtException;
import io.github.scriptarts.springnbt.nbt.NbtCompound;
import java.io.IOException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * ワールドの構成の世代1つ分
 * ライブラリの内部だけで使う
 *
 * <p>世代ごとの違いはこの表に集める
 * ワールドと{@code level.dat}の読み書きは表の値に従い、DataVersionによる分岐をほかの場所に書かない
 */
final class WorldLayout {

    /** L2（26.1以降）が始まるDataVersion */
    static final int L2_MIN_DATA_VERSION = 4786;

    /**
     * 標準の次元のIDと、L1でのワールド直下からの相対ディレクトリ
     * 並びがL1の{@code dimensionIds}の並びになる
     */
    private static final String[][] L1_STANDARD_DIMENSIONS = {
        {"minecraft:overworld", ""},
        {"minecraft:the_nether", "DIM-1"},
        {"minecraft:the_end", "DIM1"},
    };

    /** L1の{@code Difficulty}の数値に対応する名前 */
    private static final String[] L1_DIFFICULTIES = {"peaceful", "easy", "normal", "hard"};

    /** L1: 1.13〜1.21.x */
    private static final WorldLayout L1 = new WorldLayout(
            ChunkFormat.OLDEST_FORMAT_DATA_VERSION,
            true,
            new String[] {"playerdata"},
            new String[] {"data"});

    /** L2: 26.1以降 */
    private static final WorldLayout L2 = new WorldLayout(
            L2_MIN_DATA_VERSION,
            false,
            new String[] {"players", "data"},
            new String[] {"data", "minecraft"});

    private final int minDataVersion;
    private final boolean legacy;
    private final String[] playerFolder;
    private final String[] dataFolder;

    private WorldLayout(int minDataVersion, boolean legacy, String[] playerFolder, String[] dataFolder) {
        this.minDataVersion = minDataVersion;
        this.legacy = legacy;
        this.playerFolder = playerFolder;
        this.dataFolder = dataFolder;
    }

    /**
     * この世代が始まるDataVersion
     *
     * @return DataVersion
     */
    int minDataVersion() {
        return minDataVersion;
    }

    /**
     * DataVersionから世代を引く
     * L1より古い値もL1として扱う
     *
     * @param dataVersion DataVersion
     * @return 世代
     */
    static WorldLayout forDataVersion(int dataVersion) {
        // 境界以上ならL2、それ未満はL1
        if (dataVersion >= L2_MIN_DATA_VERSION) {
            return L2;
        }

        return L1;
    }

    /**
     * {@code level.dat}の{@code Data}と、利用者の指定から世代を決める
     *
     * <p>指定があればそれを使い、無ければ{@code Data.DataVersion}で決める
     * {@code DataVersion}が無い古いワールドはL1として扱う
     *
     * @param data      {@code level.dat}の{@code Data}
     * @param requested 利用者の指定
     * 無ければnull
     * @return 世代
     * @throws SpringNbtException 指定が扱える下限より小さい場合
     */
    static WorldLayout detect(NbtCompound data, Integer requested) {
        if (requested != null) {
            // 指定は下限より小さいと解釈のしようがない
            if (requested < ChunkFormat.OLDEST_FORMAT_DATA_VERSION) {
                throw SpringNbtException.invalidArgument(
                        "世代を選ぶDataVersionは" + ChunkFormat.OLDEST_FORMAT_DATA_VERSION
                                + "以上でなければならない: " + requested);
            }

            return forDataVersion(requested);
        }

        Integer found = data.optInt("DataVersion");

        // DataVersionが無いのは1.9より前のワールドなのでL1
        if (found == null) {
            return L1;
        }

        return forDataVersion(found);
    }

    /**
     * 次元のフォルダのパス
     * 次元のIDは名前空間つきで渡す
     *
     * @param worldDirectory ワールドのフォルダ
     * @param dimensionId    次元ID
     * @return パス
     */
    Path dimensionDirectory(Path worldDirectory, String dimensionId) {
        // L1の標準の次元は、ワールド直下かDIM-1/ DIM1/に置かれる
        if (legacy) {
            for (String[] standard : L1_STANDARD_DIMENSIONS) {
                // 標準の次元ならその専用の場所を返す
                if (dimensionId.equals(standard[0])) {
                    // オーバーワールドはワールドのフォルダそのもの
                    if (standard[1].isEmpty()) {
                        return worldDirectory;
                    }

                    return worldDirectory.resolve(standard[1]);
                }
            }
        }

        int colon = dimensionId.indexOf(':');
        return worldDirectory.resolve("dimensions")
                .resolve(dimensionId.substring(0, colon))
                .resolve(dimensionId.substring(colon + 1));
    }

    /**
     * 次元が存在するか
     *
     * @param worldDirectory ワールドのフォルダ
     * @param dimensionId    次元ID
     * @return 存在すればtrue
     */
    boolean hasDimension(Path worldDirectory, String dimensionId) {
        Path directory = dimensionDirectory(worldDirectory, dimensionId);

        // L1のオーバーワールドはワールド直下なので、region/の有無で判断する
        if (legacy && dimensionId.equals(L1_STANDARD_DIMENSIONS[0][0])) {
            return Files.isDirectory(directory.resolve("region"));
        }

        return Files.isDirectory(directory);
    }

    /**
     * 存在する次元のIDを返す
     * L1では標準の3つを固定の順に並べ、そのあとにデータパックの次元をIDの順に並べる
     *
     * @param worldDirectory ワールドのフォルダ
     * @return 次元IDの一覧
     */
    List<String> dimensionIds(Path worldDirectory) {
        List<String> found = new ArrayList<>();

        // L1の標準の次元は固定の順で先に並べる
        if (legacy) {
            for (String[] standard : L1_STANDARD_DIMENSIONS) {
                // 存在する標準の次元だけを数える
                if (hasDimension(worldDirectory, standard[0])) {
                    found.add(standard[0]);
                }
            }
        }

        List<String> extra = new ArrayList<>();
        Path root = worldDirectory.resolve("dimensions");

        if (Files.isDirectory(root)) {
            // dimensions/<名前空間>/<パス>/の2段を辿る
            try (DirectoryStream<Path> namespaces = Files.newDirectoryStream(root)) {
                // 1段目が名前空間
                for (Path namespaceDir : namespaces) {
                    if (!Files.isDirectory(namespaceDir)) {
                        continue;
                    }

                    try (DirectoryStream<Path> paths = Files.newDirectoryStream(namespaceDir)) {
                        // 2段目が次元のパス
                        for (Path pathDir : paths) {
                            String dimensionId = namespaceDir.getFileName() + ":" + pathDir.getFileName();

                            // ディレクトリだけを次元として数える
                            // L1では標準の次元をdimensions/の下からは探さない
                            if (Files.isDirectory(pathDir) && !(legacy && found.contains(dimensionId))) {
                                extra.add(dimensionId);
                            }
                        }
                    }
                }
            } catch (IOException error) {
                throw new SpringNbtException(
                        ErrorCode.IO, "dimensions を走査できない: " + root, error);
            }
        }

        // 走査順がファイルシステム依存にならないよう並べる
        Collections.sort(extra);
        found.addAll(extra);
        return found;
    }

    /**
     * プレイヤーデータのフォルダのパス
     *
     * @param worldDirectory ワールドのフォルダ
     * @return パス
     */
    Path playerDirectory(Path worldDirectory) {
        Path result = worldDirectory;

        // フォルダの道を1段ずつ辿る
        for (String part : playerFolder) {
            result = result.resolve(part);
        }

        return result;
    }

    /**
     * 次元のフォルダの下の付随データのファイルのパス
     *
     * @param dimensionDirectory 次元のフォルダ
     * @param name               ファイル名（拡張子なし）
     * @return パス
     */
    Path dataFilePath(Path dimensionDirectory, String name) {
        Path result = dimensionDirectory;

        // フォルダの道を1段ずつ辿る
        for (String part : dataFolder) {
            result = result.resolve(part);
        }

        return result.resolve(name + ".dat");
    }

    /**
     * スポーン地点の{@code [x, y, z]}
     *
     * @param data {@code level.dat}の{@code Data}
     * @return 座標
     */
    int[] spawnPos(NbtCompound data) {
        // L1は3つの整数に分かれて入っている
        if (legacy) {
            return new int[] {data.getInt("SpawnX"), data.getInt("SpawnY"), data.getInt("SpawnZ")};
        }

        return data.getCompound("spawn").getIntArray("pos");
    }

    /**
     * スポーン地点の次元ID
     *
     * @param data {@code level.dat}の{@code Data}
     * @return 次元ID
     * @throws SpringNbtException この世代の{@code level.dat}に無い場合（{@code UNSUPPORTED_FEATURE}）
     */
    String spawnDimension(NbtCompound data) {
        // L1にはスポーン地点の次元を持つキーが無い
        if (legacy) {
            throw SpringNbtException.unsupportedFeature("26.1より前のlevel.datにはスポーン地点の次元が無い");
        }

        return data.getCompound("spawn").getString("dimension");
    }

    /**
     * 難易度（{@code normal}など）
     *
     * @param data {@code level.dat}の{@code Data}
     * @return 難易度
     * @throws SpringNbtException 数値が0〜3の外の場合（{@code MALFORMED_DATA}）
     */
    String difficulty(NbtCompound data) {
        // L1は0〜3の数値で入っている
        if (legacy) {
            byte number = data.getByte("Difficulty");

            if (number < 0 || number >= L1_DIFFICULTIES.length) {
                throw SpringNbtException.malformed("Difficultyが0〜3の外: " + number);
            }

            return L1_DIFFICULTIES[number];
        }

        return data.getCompound("difficulty_settings").getString("difficulty");
    }

    /**
     * ハードコアか
     *
     * @param data {@code level.dat}の{@code Data}
     * @return ハードコアならtrue
     */
    boolean isHardcore(NbtCompound data) {
        // L1はDataの直下に入っている
        if (legacy) {
            return data.getBool("hardcore");
        }

        return data.getCompound("difficulty_settings").getBool("hardcore");
    }
}

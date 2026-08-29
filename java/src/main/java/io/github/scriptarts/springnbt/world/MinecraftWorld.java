package io.github.scriptarts.springnbt.world;

import io.github.scriptarts.springnbt.ErrorCode;
import io.github.scriptarts.springnbt.SpringNbtException;
import io.github.scriptarts.springnbt.nbt.NamedTag;
import io.github.scriptarts.springnbt.nbt.NbtCompound;
import io.github.scriptarts.springnbt.nbt.NbtIo;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * Minecraft Java版のセーブデータ 1 つ分。
 *
 * <p>26.x では構成が大きく変わっており、標準の3次元も
 * {@code dimensions/<名前空間>/<パス>/} の下に並ぶ。
 *
 * <p>仕様: {@code docs/spec/40-world-layout.md}
 */
public final class MinecraftWorld implements AutoCloseable {

    private final Path directory;
    private final WorldOpenOptions options;
    private final LevelData level;
    private final Map<String, Dimension> dimensions = new HashMap<>();
    private boolean closed;

    private MinecraftWorld(Path directory, WorldOpenOptions options, NamedTag level) {
        this.directory = directory;
        this.options = options;
        this.level = new LevelData(level);
    }

    /**
     * ワールドディレクトリのパス。
     *
     * @return パス
     */
    public Path directory() {
        return directory;
    }

    /**
     * {@code level.dat} の内容。
     *
     * @return level.dat
     */
    public LevelData level() {
        return level;
    }

    /**
     * ワールドを開く。
     *
     * @param directory ワールドディレクトリ
     * @param options   オプション。null なら既定値
     * @return ワールド
     * @throws SpringNbtException ディレクトリや level.dat が無い場合、
     *                            または書き込みモードで session.lock を取得できない場合
     */
    public static MinecraftWorld open(Path directory, WorldOpenOptions options) {
        Objects.requireNonNull(directory, "directory");

        WorldOpenOptions effective;
        if (options == null) {
            effective = WorldOpenOptions.defaults();
        } else {
            effective = options;
        }

        if (!Files.isDirectory(directory)) {
            throw new SpringNbtException(ErrorCode.IO, "ワールドディレクトリが無い: " + directory);
        }

        Path levelPath = directory.resolve("level.dat");

        if (!Files.exists(levelPath)) {
            throw new SpringNbtException(ErrorCode.IO, "level.dat が無い: " + levelPath);
        }

        // 書き込むなら、Minecraft が起動中でないことを先に確かめる
        if (effective.writable() && !effective.ignoreSessionLock()) {
            checkSessionLock(directory);
        }

        return new MinecraftWorld(directory, effective, NbtIo.readFile(levelPath, null));
    }

    /**
     * 読み取り専用でワールドを開く。
     *
     * @param directory ワールドディレクトリ
     * @return ワールド
     */
    public static MinecraftWorld open(Path directory) {
        return open(directory, null);
    }

    /** {@code session.lock} を排他で開けるか確かめる。 */
    private static void checkSessionLock(Path directory) {
        Path lockPath = directory.resolve("session.lock");

        if (!Files.exists(lockPath)) {
            return;
        }

        try (RandomAccessFile file = new RandomAccessFile(lockPath.toFile(), "rw");
             FileChannel channel = file.getChannel()) {
            FileLock lock = channel.tryLock();

            if (lock == null) {
                throw new SpringNbtException(ErrorCode.IO,
                        "session.lock を排他で開けない。Minecraft が起動中の可能性がある。"
                                + "無視するなら WorldOpenOptions.setIgnoreSessionLock(true)");
            }

            lock.release();
        } catch (IOException error) {
            throw new SpringNbtException(ErrorCode.IO,
                    "session.lock を確認できない: " + lockPath, error);
        }
    }

    /**
     * {@code data/minecraft/<name>.dat} を読む。
     *
     * <p>26.x では {@code game_rules} / {@code weather} / {@code world_gen_settings} などが
     * この形で {@code level.dat} から分離されている。
     *
     * @param name ファイル名（拡張子なし）
     * @return NBT。存在しなければ null
     */
    public NbtCompound dataFile(String name) {
        ensureOpen();
        Path path = directory.resolve("data").resolve("minecraft").resolve(name + ".dat");

        if (!Files.exists(path)) {
            return null;
        }

        return NbtIo.readFile(path, null).tag();
    }

    /**
     * 存在する次元のIDを返す。
     *
     * @return 次元IDの一覧
     */
    public List<String> dimensionIds() {
        ensureOpen();
        Path root = directory.resolve("dimensions");
        List<String> found = new ArrayList<>();

        if (!Files.isDirectory(root)) {
            return found;
        }

        // dimensions/<名前空間>/<パス>/ の 2 段を辿る
        try (DirectoryStream<Path> namespaces = Files.newDirectoryStream(root)) {
            // 1 段目が名前空間
            for (Path namespaceDir : namespaces) {
                if (!Files.isDirectory(namespaceDir)) {
                    continue;
                }

                try (DirectoryStream<Path> paths = Files.newDirectoryStream(namespaceDir)) {
                    // 2 段目が次元のパス
                    for (Path pathDir : paths) {
                        // ディレクトリだけを次元として数える
                        if (Files.isDirectory(pathDir)) {
                            found.add(namespaceDir.getFileName() + ":" + pathDir.getFileName());
                        }
                    }
                }
            }
        } catch (IOException error) {
            throw new SpringNbtException(ErrorCode.IO, "dimensions を走査できない: " + root, error);
        }

        // 走査順がファイルシステム依存にならないよう並べる
        Collections.sort(found);
        return found;
    }

    /**
     * 次元を得る。
     *
     * @param dimensionId {@code minecraft:overworld} のような名前空間つきのID。
     *                    名前空間が省略されていたら {@code minecraft:} を補う
     * @return 次元。ディレクトリが無ければ null
     */
    public Dimension dimension(String dimensionId) {
        ensureOpen();
        Objects.requireNonNull(dimensionId, "dimensionId");

        String normalized = normalizeDimensionId(dimensionId);
        Dimension cached = dimensions.get(normalized);

        if (cached != null) {
            return cached;
        }

        int colon = normalized.indexOf(':');
        Path path = directory.resolve("dimensions")
                .resolve(normalized.substring(0, colon))
                .resolve(normalized.substring(colon + 1));

        if (!Files.isDirectory(path)) {
            return null;
        }

        Dimension opened = new Dimension(normalized, path, options);
        dimensions.put(normalized, opened);
        return opened;
    }

    /**
     * プレイヤーのUUID一覧。
     *
     * @return UUIDの一覧
     */
    public List<String> playerIds() {
        ensureOpen();
        Path path = directory.resolve("players").resolve("data");
        List<String> found = new ArrayList<>();

        if (!Files.isDirectory(path)) {
            return found;
        }

        try (DirectoryStream<Path> files = Files.newDirectoryStream(path, "*.dat")) {
            // <uuid>.dat の名前部分が UUID にあたる
            for (Path file : files) {
                String name = file.getFileName().toString();
                found.add(name.substring(0, name.length() - 4));
            }
        } catch (IOException error) {
            throw new SpringNbtException(ErrorCode.IO, "players/data を走査できない: " + path, error);
        }

        Collections.sort(found);
        return found;
    }

    /**
     * プレイヤーデータを読む。
     *
     * @param uuid プレイヤーのUUID
     * @return NBT。存在しなければ null
     */
    public NbtCompound player(String uuid) {
        ensureOpen();
        Objects.requireNonNull(uuid, "uuid");
        Path path = directory.resolve("players").resolve("data").resolve(uuid + ".dat");

        if (!Files.exists(path)) {
            return null;
        }

        return NbtIo.readFile(path, null).tag();
    }

    /**
     * {@code level.dat} を書き戻す。
     *
     * <p>壊れるとワールド全体が開けなくなるため、
     * 一時ファイルへ書いてから {@code level.dat_old} へ退避し、最後に置き換える。
     */
    public void saveLevel() {
        ensureOpen();

        if (!options.writable()) {
            throw SpringNbtException.invalidArgument("読み取り専用で開いたワールドには書き込めない");
        }

        Path path = directory.resolve("level.dat");
        Path temporary = directory.resolve("level.dat.tmp");
        Path backup = directory.resolve("level.dat_old");

        try {
            NbtIo.writeFile(temporary, level.toNamedTag(), null);

            // 既存の level.dat は、置き換える前に level.dat_old へ退避する
            if (Files.exists(path)) {
                Files.copy(path, backup, StandardCopyOption.REPLACE_EXISTING);
            }

            Files.move(temporary, path, StandardCopyOption.REPLACE_EXISTING);
        } catch (IOException error) {
            throw new SpringNbtException(ErrorCode.IO, "level.dat を書けない: " + path, error);
        }
    }

    /** 開いている次元をすべて閉じる。 */
    @Override
    public void close() {
        if (closed) {
            return;
        }

        // 開いている次元をすべて閉じる
        for (Dimension dimension : dimensions.values()) {
            dimension.close();
        }

        dimensions.clear();
        closed = true;
    }

    private void ensureOpen() {
        if (closed) {
            throw SpringNbtException.invalidArgument("既に閉じられたワールド");
        }
    }

    /** 名前空間が省略されていたら {@code minecraft:} を補う。 */
    private static String normalizeDimensionId(String dimensionId) {
        if (dimensionId.indexOf(':') >= 0) {
            return dimensionId;
        }

        return "minecraft:" + dimensionId;
    }
}

package io.github.scriptarts.springnbt.world;

import io.github.scriptarts.springnbt.ErrorCode;
import io.github.scriptarts.springnbt.SpringNbtException;
import io.github.scriptarts.springnbt.nbt.NamedTag;
import io.github.scriptarts.springnbt.nbt.NbtCompound;
import io.github.scriptarts.springnbt.nbt.NbtIo;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * Minecraft Java版のセーブデータ1つ分
 *
 * <p>26.1以降は構成が大きく変わっており、標準の3次元も{@code dimensions/<名前空間>/<パス>/}の下に並ぶ
 * それより前の構成も、{@code level.dat}のDataVersionで見分けて読み書きできる
 */
public final class MinecraftWorld implements AutoCloseable {

    private final Path directory;
    private final WorldOpenOptions options;
    private final LevelData level;
    private final WorldLayout layout;
    private final Map<String, Dimension> dimensions = new HashMap<>();
    private boolean closed;

    private MinecraftWorld(Path directory, WorldOpenOptions options, NamedTag level) {
        this.directory = directory;
        this.level = new LevelData(level, options.formatDataVersion());
        this.layout = this.level.layout();
        this.options = withFormatDataVersion(options);
    }

    /**
     * ワールドディレクトリのパス
     *
     * @return パス
     */
    public Path directory() {
        return directory;
    }

    /**
     * {@code level.dat}の内容
     *
     * @return level.dat
     */
    public LevelData level() {
        return level;
    }

    /**
     * ワールドを開く
     *
     * @param directory ワールドディレクトリ
     * @param options   オプション
     * nullなら既定値
     * @return ワールド
     * @throws SpringNbtException ディレクトリやlevel.datが無い場合、
     *                            または書き込みモードでsession.lockを取得できない場合、
     *                            またはformatDataVersionが1519未満の場合
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

        // 書き込むなら、Minecraftが起動中でないことを先に確かめる
        if (effective.writable() && !effective.ignoreSessionLock()) {
            checkSessionLock(directory);
        }

        return new MinecraftWorld(directory, effective, NbtIo.readFile(levelPath, null));
    }

    /**
     * 読み取り専用でワールドを開く
     *
     * @param directory ワールドディレクトリ
     * @return ワールド
     */
    public static MinecraftWorld open(Path directory) {
        return open(directory, null);
    }

    /** {@code session.lock}を排他で開けるか確かめる */
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
     * {@code data/minecraft/<name>.dat}を読む
     *
     * <p>26.1以降は{@code game_rules} / {@code weather} / {@code world_gen_settings}などがこの形で{@code level.dat}から分離されている
     * 26.1より前は{@code data/<name>.dat}を読む
     *
     * @param name ファイル名（拡張子なし）
     * @return NBT
     * 存在しなければnull
     */
    public NbtCompound dataFile(String name) {
        ensureOpen();
        Path path = layout.dataFilePath(directory, name);

        if (!Files.exists(path)) {
            return null;
        }

        return NbtIo.readFile(path, null).tag();
    }

    /**
     * 存在する次元のIDを返す
     * 26.1より前は標準の3次元を固定の順で先に並べ、データパックの次元を{@code dimensions/}から探す
     *
     * @return 次元IDの一覧
     */
    public List<String> dimensionIds() {
        ensureOpen();
        return layout.dimensionIds(directory);
    }

    /**
     * 次元を得る
     *
     * @param dimensionId {@code minecraft:overworld}のような名前空間つきのID
     *                    名前空間が省略されていたら{@code minecraft:}を補う
     * @return 次元
     * ディレクトリが無ければnull
     */
    public Dimension dimension(String dimensionId) {
        ensureOpen();
        Objects.requireNonNull(dimensionId, "dimensionId");

        String normalized = normalizeDimensionId(dimensionId);
        Dimension cached = dimensions.get(normalized);

        if (cached != null) {
            return cached;
        }

        // 存在しない次元はnullのまま
        if (!layout.hasDimension(directory, normalized)) {
            return null;
        }

        Path path = layout.dimensionDirectory(directory, normalized);
        Dimension opened = new Dimension(normalized, path, options, layout);
        dimensions.put(normalized, opened);
        return opened;
    }

    /**
     * プレイヤーのUUID一覧
     *
     * @return UUIDの一覧
     */
    public List<String> playerIds() {
        ensureOpen();
        Path path = layout.playerDirectory(directory);
        List<String> found = new ArrayList<>();

        if (!Files.isDirectory(path)) {
            return found;
        }

        try (DirectoryStream<Path> files = Files.newDirectoryStream(path, "*.dat")) {
            // <uuid>.datの名前部分がUUIDにあたる
            for (Path file : files) {
                String name = file.getFileName().toString();
                found.add(name.substring(0, name.length() - 4));
            }
        } catch (IOException error) {
            throw new SpringNbtException(ErrorCode.IO, "プレイヤーのフォルダを走査できない: " + path, error);
        }

        Collections.sort(found);
        return found;
    }

    /**
     * プレイヤーデータを読む
     *
     * @param uuid プレイヤーのUUID
     * @return NBT
     * 存在しなければnull
     */
    public NbtCompound player(String uuid) {
        ensureOpen();
        Objects.requireNonNull(uuid, "uuid");
        Path path = layout.playerDirectory(directory).resolve(uuid + ".dat");

        if (!Files.exists(path)) {
            return null;
        }

        return NbtIo.readFile(path, null).tag();
    }

    /**
     * {@code level.dat}を書き戻す
     *
     * <p>{@code level.dat}がおかしくなるとワールド全体が開けなくなるため、
     * 一時ファイルへ書いて内容をディスクへ確実に書き出してから、既存の{@code level.dat}を{@code level.dat_old}へ退避し、最後に置き換える
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
            byte[] encoded = NbtIo.writeBytes(level.toNamedTag(), null);

            // 一時ファイルへ書き、置き換える前に内容をディスクへ確実に書き出す
            try (FileChannel channel = FileChannel.open(temporary,
                    StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE)) {
                ByteBuffer buffer = ByteBuffer.wrap(encoded);

                // 全バイトを書き終えるまで書き続ける
                while (buffer.hasRemaining()) {
                    channel.write(buffer);
                }

                channel.force(true);
            }

            // 既存のlevel.datは、置き換える前にlevel.dat_oldへ退避する
            if (Files.exists(path)) {
                Files.copy(path, backup, StandardCopyOption.REPLACE_EXISTING);
            }

            Files.move(temporary, path, StandardCopyOption.REPLACE_EXISTING);
        } catch (IOException error) {
            throw new SpringNbtException(ErrorCode.IO, "level.dat を書けない: " + path, error);
        }
    }

    /** 開いている次元をすべて閉じる */
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

    /**
     * ワールドで世代を指定されていれば、チャンクの読み込みにも同じ指定を入れた複製を返す
     * 渡されたオプションは書き換えない
     */
    private static WorldOpenOptions withFormatDataVersion(WorldOpenOptions source) {
        // 指定が無ければ、チャンクごとの指定やチャンク自身のDataVersionに任せる
        if (source.formatDataVersion() == null) {
            return source;
        }

        ChunkReadOptions read = source.chunkRead();

        return new WorldOpenOptions()
                .setWritable(source.writable())
                .setIgnoreSessionLock(source.ignoreSessionLock())
                .setChunkRead(new ChunkReadOptions()
                        .setOnVersionMismatch(read.onVersionMismatch())
                        .setOnWarning(read.onWarning())
                        .setLenientBitStorage(read.lenientBitStorage())
                        .setFormatDataVersion(source.formatDataVersion()))
                .setChunkWrite(source.chunkWrite())
                .setFormatDataVersion(source.formatDataVersion());
    }

    /** 名前空間が省略されていたら{@code minecraft:}を補う */
    private static String normalizeDimensionId(String dimensionId) {
        if (dimensionId.indexOf(':') >= 0) {
            return dimensionId;
        }

        return "minecraft:" + dimensionId;
    }
}

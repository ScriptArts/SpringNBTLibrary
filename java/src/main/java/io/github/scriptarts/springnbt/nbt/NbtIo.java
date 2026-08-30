package io.github.scriptarts.springnbt.nbt;

import io.github.scriptarts.springnbt.ErrorCode;
import io.github.scriptarts.springnbt.SpringNbtException;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;
import java.util.zip.Deflater;
import java.util.zip.DeflaterOutputStream;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;
import java.util.zip.InflaterInputStream;

/**
 * NBT のファイル・バイト列・ストリームからの読み書き
 *
 * <p>仕様: {@code docs/spec/10-nbt-binary.md} 3章・4章
 */
public final class NbtIo {

    private NbtIo() {
        // ユーティリティクラス
    }

    /**
     * ファイルから NBT を読む
     *
     * @param path    ファイルパス
     * @param options 読み込みオプション
     * null なら既定値
     * @return 読み込んだルート
     * @throws SpringNbtException 読み込みに失敗した場合
     */
    public static NamedTag readFile(Path path, NbtReadOptions options) {
        Objects.requireNonNull(path, "path");

        byte[] raw;
        try {
            raw = Files.readAllBytes(path);
        } catch (IOException error) {
            // 下位の入出力エラーは情報を失わないよう原因として保持する
            throw new SpringNbtException(ErrorCode.IO, "ファイルを読めない: " + path, error);
        }

        return readBytes(raw, options);
    }

    /**
     * バイト列から NBT を読む
     *
     * @param bytes   バイト列
     * @param options 読み込みオプション
     * null なら既定値
     * @return 読み込んだルート
     * @throws SpringNbtException 読み込みに失敗した場合
     */
    public static NamedTag readBytes(byte[] bytes, NbtReadOptions options) {
        Objects.requireNonNull(bytes, "bytes");

        NbtReadOptions effective;
        if (options == null) {
            effective = NbtReadOptions.defaults();
        } else {
            effective = options;
        }

        byte[] plain = decompress(bytes, effective);
        return new NbtBinaryReader(plain, effective.maxDepth()).readRoot(effective.format());
    }

    /**
     * ストリームから NBT を読む
     * ストリームは最後まで読み切る
     *
     * @param stream  入力ストリーム
     * @param options 読み込みオプション
     * null なら既定値
     * @return 読み込んだルート
     * @throws SpringNbtException 読み込みに失敗した場合
     */
    public static NamedTag readStream(InputStream stream, NbtReadOptions options) {
        Objects.requireNonNull(stream, "stream");

        try {
            return readBytes(stream.readAllBytes(), options);
        } catch (IOException error) {
            throw new SpringNbtException(ErrorCode.IO, "ストリームを読めない", error);
        }
    }

    /**
     * NBT をファイルへ書き出す
     *
     * @param path    ファイルパス
     * @param tag     書き出すルート
     * @param options 書き込みオプション
     * null なら既定値
     * @throws SpringNbtException 書き込みに失敗した場合
     */
    public static void writeFile(Path path, NamedTag tag, NbtWriteOptions options) {
        Objects.requireNonNull(path, "path");

        byte[] bytes = writeBytes(tag, options);

        try {
            Files.write(path, bytes);
        } catch (IOException error) {
            throw new SpringNbtException(ErrorCode.IO, "ファイルへ書けない: " + path, error);
        }
    }

    /**
     * NBT をバイト列へ書き出す
     *
     * @param tag     書き出すルート
     * @param options 書き込みオプション
     * null なら既定値
     * @return バイト列
     * @throws SpringNbtException 書き込みに失敗した場合
     */
    public static byte[] writeBytes(NamedTag tag, NbtWriteOptions options) {
        Objects.requireNonNull(tag, "tag");

        NbtWriteOptions effective;
        if (options == null) {
            effective = NbtWriteOptions.defaults();
        } else {
            effective = options;
        }

        // 書き込み時に AUTO は決められない
        if (effective.compression() == Compression.AUTO) {
            throw SpringNbtException.invalidArgument("書き込みで Compression.AUTO は指定できない");
        }

        byte[] plain = new NbtBinaryWriter().writeRoot(tag, effective.format());
        return compress(plain, effective.compression());
    }

    /**
     * NBT をストリームへ書き出す
     *
     * @param stream  出力ストリーム
     * @param tag     書き出すルート
     * @param options 書き込みオプション
     * null なら既定値
     * @throws SpringNbtException 書き込みに失敗した場合
     */
    public static void writeStream(OutputStream stream, NamedTag tag, NbtWriteOptions options) {
        Objects.requireNonNull(stream, "stream");

        byte[] bytes = writeBytes(tag, options);

        try {
            stream.write(bytes);
        } catch (IOException error) {
            throw new SpringNbtException(ErrorCode.IO, "ストリームへ書けない", error);
        }
    }

    /**
     * 先頭バイトから圧縮方式を判定する
     *
     * @param bytes バイト列
     * @return 圧縮方式
     * @throws SpringNbtException どの方式とも判定できない場合
     */
    public static Compression detectCompression(byte[] bytes) {
        Objects.requireNonNull(bytes, "bytes");

        if (bytes.length == 0) {
            throw SpringNbtException.malformed("入力が空で圧縮方式を判定できない");
        }

        // GZip は必ず 1F 8B で始まる
        if (bytes.length >= 2 && (bytes[0] & 0xFF) == 0x1F && (bytes[1] & 0xFF) == 0x8B) {
            return Compression.GZIP;
        }

        if (bytes.length >= 2) {
            // zlib ヘッダは「圧縮法が 8 (deflate)」かつ「先頭2バイトが 31 の倍数」
            boolean isDeflate = (bytes[0] & 0x0F) == 0x08;
            int header = ((bytes[0] & 0xFF) << 8) | (bytes[1] & 0xFF);

            if (isDeflate && header % 31 == 0) {
                return Compression.ZLIB;
            }
        }

        // 無圧縮なら先頭は TAG_Compound のタグID
        if ((bytes[0] & 0xFF) == TagType.COMPOUND.id()) {
            return Compression.NONE;
        }

        throw SpringNbtException.malformed(
                String.format("圧縮方式を判定できない (先頭バイト 0x%02X)", bytes[0] & 0xFF));
    }

    /** 指定された方式で展開する */
    private static byte[] decompress(byte[] bytes, NbtReadOptions options) {
        Compression method;
        // AUTO なら先頭バイトから圧縮方式を見分ける
        if (options.compression() == Compression.AUTO) {
            method = detectCompression(bytes);
        } else {
            method = options.compression();
        }

        if (method == Compression.NONE) {
            return bytes;
        }

        try (InputStream source = new ByteArrayInputStream(bytes);
             InputStream decoder = createDecoder(source, method);
             ByteArrayOutputStream destination = new ByteArrayOutputStream()) {
            copyWithLimit(decoder, destination, options.maxDecompressedSize());
            return destination.toByteArray();
        } catch (IOException error) {
            throw new SpringNbtException(ErrorCode.MALFORMED_DATA, "圧縮データを展開できない", error);
        }
    }

    /** 指定された方式で圧縮する */
    private static byte[] compress(byte[] plain, Compression method) {
        if (method == Compression.NONE) {
            return plain;
        }

        try (ByteArrayOutputStream destination = new ByteArrayOutputStream()) {
            // ストリームを閉じてフッタを書かせてから toByteArray する必要がある
            try (OutputStream encoder = createEncoder(destination, method)) {
                encoder.write(plain);
            }

            return destination.toByteArray();
        } catch (IOException error) {
            throw new SpringNbtException(ErrorCode.IO, "圧縮に失敗した", error);
        }
    }

    private static InputStream createDecoder(InputStream source, Compression method)
            throws IOException {
        if (method == Compression.GZIP) {
            return new GZIPInputStream(source);
        }

        if (method == Compression.ZLIB) {
            return new InflaterInputStream(source);
        }

        throw SpringNbtException.invalidArgument("展開できない圧縮方式: " + method);
    }

    private static OutputStream createEncoder(OutputStream destination, Compression method)
            throws IOException {
        if (method == Compression.GZIP) {
            return new GZIPOutputStream(destination);
        }

        if (method == Compression.ZLIB) {
            return new DeflaterOutputStream(destination, new Deflater(Deflater.BEST_COMPRESSION));
        }

        throw SpringNbtException.invalidArgument("圧縮できない方式: " + method);
    }

    /** 展開後のサイズ上限を見ながらコピーする */
    private static void copyWithLimit(InputStream source, OutputStream destination, long maxSize)
            throws IOException {
        byte[] chunk = new byte[81920];
        long total = 0;

        // 展開しながら、上限を超えた時点で打ち切る
        while (true) {
            int read = source.read(chunk, 0, chunk.length);

            if (read <= 0) {
                return;
            }

            total += read;

            if (maxSize >= 0 && total > maxSize) {
                throw SpringNbtException.limitExceeded(
                        "展開後のサイズが上限 " + maxSize + " バイトを超えた");
            }

            destination.write(chunk, 0, read);
        }
    }
}

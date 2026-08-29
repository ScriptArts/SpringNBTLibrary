using System.IO.Compression;

namespace SpringNBTLibrary.Nbt;

/// <summary>
/// NBT のファイル・バイト列・ストリームからの読み書き
/// </summary>
/// <remarks>仕様: <c>docs/spec/10-nbt-binary.md</c> 3章・4章</remarks>
public static class NbtIo
{
    /// <summary>ファイルから NBT を読む</summary>
    /// <exception cref="SpringNbtException">読み込みに失敗した場合</exception>
    public static NamedTag ReadFile(string path, NbtReadOptions? options = null)
    {
        ArgumentNullException.ThrowIfNull(path);

        byte[] raw;
        try
        {
            raw = File.ReadAllBytes(path);
        }
        catch (IOException error)
        {
            // 下位の入出力エラーは原因を保持したままラップする
            throw new SpringNbtException(ErrorCode.Io, $"ファイルを読めない: {path}", error);
        }
        catch (UnauthorizedAccessException error)
        {
            throw new SpringNbtException(ErrorCode.Io, $"ファイルを読めない: {path}", error);
        }

        return ReadBytes(raw, options);
    }

    /// <summary>バイト列から NBT を読む</summary>
    /// <exception cref="SpringNbtException">読み込みに失敗した場合</exception>
    public static NamedTag ReadBytes(byte[] bytes, NbtReadOptions? options = null)
    {
        ArgumentNullException.ThrowIfNull(bytes);

        NbtReadOptions effective;
        // 省略されたら既定のオプションで読む
        if (options is null)
        {
            effective = NbtReadOptions.Default;
        }
        else
        {
            effective = options;
        }

        byte[] plain = Decompress(bytes, effective);
        NbtBinaryReader reader = new NbtBinaryReader(plain, effective.MaxDepth);
        return reader.ReadRoot(effective.Format);
    }

    /// <summary>ストリームから NBT を読む
    /// ストリームは最後まで読み切る</summary>
    /// <exception cref="SpringNbtException">読み込みに失敗した場合</exception>
    public static NamedTag ReadStream(Stream stream, NbtReadOptions? options = null)
    {
        ArgumentNullException.ThrowIfNull(stream);

        using MemoryStream memory = new MemoryStream();
        try
        {
            stream.CopyTo(memory);
        }
        catch (IOException error)
        {
            throw new SpringNbtException(ErrorCode.Io, "ストリームを読めない", error);
        }

        return ReadBytes(memory.ToArray(), options);
    }

    /// <summary>NBT をファイルへ書き出す</summary>
    /// <exception cref="SpringNbtException">書き込みに失敗した場合</exception>
    public static void WriteFile(string path, NamedTag tag, NbtWriteOptions? options = null)
    {
        ArgumentNullException.ThrowIfNull(path);

        byte[] bytes = WriteBytes(tag, options);

        try
        {
            File.WriteAllBytes(path, bytes);
        }
        catch (IOException error)
        {
            throw new SpringNbtException(ErrorCode.Io, $"ファイルへ書けない: {path}", error);
        }
        catch (UnauthorizedAccessException error)
        {
            throw new SpringNbtException(ErrorCode.Io, $"ファイルへ書けない: {path}", error);
        }
    }

    /// <summary>NBT をバイト列へ書き出す</summary>
    /// <exception cref="SpringNbtException">書き込みに失敗した場合</exception>
    public static byte[] WriteBytes(NamedTag tag, NbtWriteOptions? options = null)
    {
        ArgumentNullException.ThrowIfNull(tag);

        NbtWriteOptions effective;
        // 省略されたら既定のオプションで書く
        if (options is null)
        {
            effective = NbtWriteOptions.Default;
        }
        else
        {
            effective = options;
        }

        // 書き込み時に Auto は決められない
        if (effective.Compression == Compression.Auto)
        {
            throw SpringNbtException.InvalidArgument("書き込みで Compression.Auto は指定できない");
        }

        NbtBinaryWriter writer = new NbtBinaryWriter();
        byte[] plain = writer.WriteRoot(tag, effective.Format);
        return Compress(plain, effective.Compression);
    }

    /// <summary>NBT をストリームへ書き出す</summary>
    /// <exception cref="SpringNbtException">書き込みに失敗した場合</exception>
    public static void WriteStream(Stream stream, NamedTag tag, NbtWriteOptions? options = null)
    {
        ArgumentNullException.ThrowIfNull(stream);

        byte[] bytes = WriteBytes(tag, options);

        try
        {
            stream.Write(bytes, 0, bytes.Length);
        }
        catch (IOException error)
        {
            throw new SpringNbtException(ErrorCode.Io, "ストリームへ書けない", error);
        }
    }

    /// <summary>
    /// 先頭バイトから圧縮方式を判定する
    /// </summary>
    /// <exception cref="SpringNbtException">
    /// どの方式とも判定できない場合（<see cref="ErrorCode.MalformedData"/>）
    /// </exception>
    public static Compression DetectCompression(byte[] bytes)
    {
        ArgumentNullException.ThrowIfNull(bytes);

        if (bytes.Length == 0)
        {
            throw SpringNbtException.Malformed("入力が空で圧縮方式を判定できない");
        }

        // GZip は必ず 1F 8B で始まる
        if (bytes.Length >= 2 && bytes[0] == 0x1F && bytes[1] == 0x8B)
        {
            return Compression.Gzip;
        }

        if (bytes.Length >= 2)
        {
            // zlib ヘッダは「圧縮法が 8 (deflate)」かつ「先頭2バイトが 31 の倍数」
            bool isDeflate = (bytes[0] & 0x0F) == 0x08;
            int header = (bytes[0] << 8) | bytes[1];
            if (isDeflate && header % 31 == 0)
            {
                return Compression.Zlib;
            }
        }

        // 無圧縮なら先頭は TAG_Compound のタグID
        if (bytes[0] == (byte)TagType.Compound)
        {
            return Compression.None;
        }

        throw SpringNbtException.Malformed($"圧縮方式を判定できない (先頭バイト 0x{bytes[0]:X2})");
    }

    /// <summary>指定された方式で展開する</summary>
    private static byte[] Decompress(byte[] bytes, NbtReadOptions options)
    {
        Compression method;
        // Auto なら先頭バイトから圧縮方式を見分ける
        if (options.Compression == Compression.Auto)
        {
            method = DetectCompression(bytes);
        }
        else
        {
            method = options.Compression;
        }

        if (method == Compression.None)
        {
            return bytes;
        }

        using MemoryStream source = new MemoryStream(bytes, writable: false);
        using Stream decoder = CreateDecoder(source, method);
        using MemoryStream destination = new MemoryStream();

        try
        {
            CopyWithLimit(decoder, destination, options.MaxDecompressedSize);
        }
        catch (InvalidDataException error)
        {
            throw new SpringNbtException(ErrorCode.MalformedData, "圧縮データを展開できない", error);
        }

        return destination.ToArray();
    }

    /// <summary>指定された方式で圧縮する</summary>
    private static byte[] Compress(byte[] plain, Compression method)
    {
        if (method == Compression.None)
        {
            return plain;
        }

        using MemoryStream destination = new MemoryStream();

        // using ブロックを閉じてフッタを書かせてから ToArray する必要がある
        using (Stream encoder = CreateEncoder(destination, method))
        {
            encoder.Write(plain, 0, plain.Length);
        }

        return destination.ToArray();
    }

    private static Stream CreateDecoder(Stream source, Compression method)
    {
        if (method == Compression.Gzip)
        {
            return new GZipStream(source, CompressionMode.Decompress, leaveOpen: true);
        }

        if (method == Compression.Zlib)
        {
            return new ZLibStream(source, CompressionMode.Decompress, leaveOpen: true);
        }

        throw SpringNbtException.InvalidArgument($"展開できない圧縮方式: {method}");
    }

    private static Stream CreateEncoder(Stream destination, Compression method)
    {
        if (method == Compression.Gzip)
        {
            return new GZipStream(destination, CompressionLevel.Optimal, leaveOpen: true);
        }

        if (method == Compression.Zlib)
        {
            return new ZLibStream(destination, CompressionLevel.Optimal, leaveOpen: true);
        }

        throw SpringNbtException.InvalidArgument($"圧縮できない方式: {method}");
    }

    /// <summary>展開後のサイズ上限を見ながらコピーする</summary>
    private static void CopyWithLimit(Stream source, Stream destination, long maxSize)
    {
        byte[] chunk = new byte[81920];
        long total = 0;

        // 展開しながら、上限を超えた時点で打ち切る
        while (true)
        {
            int read = source.Read(chunk, 0, chunk.Length);

            if (read <= 0)
            {
                return;
            }

            total += read;

            if (maxSize >= 0 && total > maxSize)
            {
                throw SpringNbtException.LimitExceeded($"展開後のサイズが上限 {maxSize} バイトを超えた");
            }

            destination.Write(chunk, 0, read);
        }
    }
}

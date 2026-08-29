using System.Buffers.Binary;
using System.Globalization;
using System.IO.Compression;
using SpringNBTLibrary.Nbt;

namespace SpringNBTLibrary.Anvil;

/// <summary>リージョンファイルを開くときの動作</summary>
public enum RegionFileMode
{
    /// <summary>読み取り専用
    /// 書き込み系の操作はエラーになる</summary>
    ReadOnly,

    /// <summary>読み書き
    /// ファイルが無ければ空のリージョンとして扱う</summary>
    ReadWrite,
}

/// <summary>
/// Anvil のリージョンファイル (<c>r.X.Z.mca</c>)
/// 32×32 チャンクを格納する
/// </summary>
/// <remarks>
/// <para>
/// ファイル全体をメモリに読み込んで扱う
/// 実データのリージョンは数 MB 程度で、
/// この方が「触っていないチャンクのバイト配置をそのまま保つ」ことを保証しやすい
/// 開いて何も変えずに <see cref="Flush"/> すると、バイト単位で元と同じファイルになる
/// </para>
/// <para>仕様: <c>docs/spec/20-anvil-region.md</c></para>
/// </remarks>
public sealed class RegionFile : IDisposable
{
    /// <summary>セクタ長</summary>
    public const int SectorSize = 4096;

    /// <summary>ロケーションテーブルとタイムスタンプテーブルが占めるセクタ数</summary>
    private const int HeaderSectors = 2;

    /// <summary>1リージョンに入るチャンク数</summary>
    private const int ChunkCount = 1024;

    /// <summary>1チャンクが確保できるセクタ数の上限（長さフィールドが u8 のため）</summary>
    private const int MaxSectors = 255;

    /// <summary>リージョン内に収められるペイロードの上限
    /// 超えると外部ファイルへ退避する</summary>
    private const int MaxInlinePayload = (MaxSectors * SectorSize) - 5;

    private readonly string path;
    private readonly string directory;
    private readonly RegionFileMode mode;
    private readonly int[] offsets = new int[ChunkCount];
    private readonly int[] sectorCounts = new int[ChunkCount];
    private readonly int[] timestamps = new int[ChunkCount];

    private byte[] data;
    private bool dirty;
    private bool closed;

    private RegionFile(string path, RegionFileMode mode, RegionPos position, byte[] data)
    {
        this.path = path;
        this.mode = mode;
        this.data = data;

        string? parent = Path.GetDirectoryName(path);
        // パスが階層を含まない場合、.mcc の置き場としてカレントディレクトリを使う
        if (string.IsNullOrEmpty(parent))
        {
            this.directory = ".";
        }
        else
        {
            this.directory = parent;
        }

        RegionX = position.X;
        RegionZ = position.Z;
        ParseHeader();
    }

    /// <summary>このリージョンのX座標</summary>
    public int RegionX { get; }

    /// <summary>このリージョンのZ座標</summary>
    public int RegionZ { get; }

    /// <summary>
    /// リージョンファイルを開く
    /// </summary>
    /// <param name="path">
    /// <c>r.X.Z.mca</c> という名前のファイル
    /// 座標はファイル名から読み取る
    /// </param>
    /// <param name="mode">読み取り専用か読み書きか</param>
    /// <exception cref="SpringNbtException">
    /// ファイル名から座標を読み取れない、または読み込みに失敗した場合
    /// </exception>
    public static RegionFile Open(string path, RegionFileMode mode = RegionFileMode.ReadOnly)
    {
        ArgumentNullException.ThrowIfNull(path);

        RegionPos? position = RegionPos.FromFileName(Path.GetFileName(path));

        if (position is null)
        {
            throw SpringNbtException.InvalidArgument(
                $"リージョンファイル名として解釈できない: {Path.GetFileName(path)}");
        }

        byte[] raw;

        // 既にあるファイルは読み込み、無ければ空のヘッダだけを組み立てる
        if (File.Exists(path))
        {
            try
            {
                raw = File.ReadAllBytes(path);
            }
            catch (IOException error)
            {
                throw new SpringNbtException(ErrorCode.Io, $"ファイルを読めない: {path}", error);
            }
            catch (UnauthorizedAccessException error)
            {
                throw new SpringNbtException(ErrorCode.Io, $"ファイルを読めない: {path}", error);
            }
        }
        else if (mode == RegionFileMode.ReadWrite)
        {
            // 読み書きモードなら、存在しないファイルは空のリージョンとして扱う
            raw = new byte[HeaderSectors * SectorSize];
        }
        else
        {
            throw new SpringNbtException(ErrorCode.Io, $"ファイルが存在しない: {path}");
        }

        return new RegionFile(path, mode, position.Value, raw);
    }

    /// <summary>ヘッダを解析し、ロケーションとタイムスタンプを取り込む</summary>
    private void ParseHeader()
    {
        // 空ファイルは「チャンクが 1 つも無いリージョン」として受け入れる
        if (data.Length == 0)
        {
            data = new byte[HeaderSectors * SectorSize];
            return;
        }

        if (data.Length < HeaderSectors * SectorSize)
        {
            throw SpringNbtException.Malformed(
                $"ヘッダが足りない: {data.Length} バイト（最低 {HeaderSectors * SectorSize} バイト必要）");
        }

        if (data.Length % SectorSize != 0)
        {
            throw SpringNbtException.Malformed(
                $"ファイル長がセクタ境界に揃っていない: {data.Length} バイト");
        }

        int totalSectors = data.Length / SectorSize;
        Dictionary<int, int> sectorOwner = new Dictionary<int, int>();

        // ロケーションテーブルの 1024 エントリを順に取り込む
        for (int index = 0; index < ChunkCount; index++)
        {
            uint entry = BinaryPrimitives.ReadUInt32BigEndian(data.AsSpan(index * 4, 4));
            int offset = (int)(entry >> 8);
            int count = (int)(entry & 0xFF);

            timestamps[index] = BinaryPrimitives.ReadInt32BigEndian(
                data.AsSpan((SectorSize + (index * 4)), 4));

            if (offset == 0 && count == 0)
            {
                continue;
            }

            if (offset < HeaderSectors)
            {
                throw SpringNbtException.Malformed(
                    $"チャンク {index} のオフセットがヘッダ領域を指している: {offset}");
            }

            if (count == 0)
            {
                throw SpringNbtException.Malformed(
                    $"チャンク {index} のセクタ数が 0 なのにオフセットが設定されている");
            }

            if (offset + count > totalSectors)
            {
                throw SpringNbtException.Malformed(
                    $"チャンク {index} の割り当てがファイル外へはみ出している");
            }

            // 同じセクタを 2 つのチャンクが指していたら、どちらかが壊れている
            for (int sector = offset; sector < offset + count; sector++)
            {
                if (sectorOwner.TryGetValue(sector, out int owner))
                {
                    throw SpringNbtException.Malformed(
                        $"セクタ {sector} がチャンク {owner} とチャンク {index} で重複している");
                }

                sectorOwner[sector] = index;
            }

            offsets[index] = offset;
            sectorCounts[index] = count;
        }
    }

    /// <summary>指定した座標がこのリージョンの担当範囲にあるか確認し、添字を返す</summary>
    private int IndexOf(int chunkX, int chunkZ)
    {
        ChunkPos position = new ChunkPos(chunkX, chunkZ);
        RegionPos region = position.Region;

        if (region.X != RegionX || region.Z != RegionZ)
        {
            throw SpringNbtException.InvalidArgument(string.Create(
                CultureInfo.InvariantCulture,
                $"チャンク ({chunkX}, {chunkZ}) はリージョン ({RegionX}, {RegionZ}) の担当外"));
        }

        return position.Index;
    }

    private void EnsureWritable()
    {
        if (mode == RegionFileMode.ReadOnly)
        {
            throw SpringNbtException.InvalidArgument("読み取り専用で開いたリージョンには書き込めない");
        }
    }

    private void EnsureOpen()
    {
        if (closed)
        {
            throw SpringNbtException.InvalidArgument("既に閉じられたリージョンファイル");
        }
    }

    /// <summary>チャンクが存在するか</summary>
    public bool HasChunk(int chunkX, int chunkZ)
    {
        EnsureOpen();
        return sectorCounts[IndexOf(chunkX, chunkZ)] > 0;
    }

    /// <summary>存在するチャンクの座標を、ロケーションテーブルの並び順で列挙する</summary>
    public IEnumerable<ChunkPos> ChunkPositions()
    {
        EnsureOpen();

        // 添字の昇順に走査する（localZ が外、localX が内）
        for (int index = 0; index < ChunkCount; index++)
        {
            if (sectorCounts[index] == 0)
            {
                continue;
            }

            int localX = index % 32;
            int localZ = index / 32;
            yield return new ChunkPos((RegionX * 32) + localX, (RegionZ * 32) + localZ);
        }
    }

    /// <summary>チャンクの最終更新時刻（Unix 秒）
    /// 存在しなければ 0</summary>
    public int Timestamp(int chunkX, int chunkZ)
    {
        EnsureOpen();
        return timestamps[IndexOf(chunkX, chunkZ)];
    }

    /// <summary>チャンクの最終更新時刻を設定する</summary>
    public void SetTimestamp(int chunkX, int chunkZ, int value)
    {
        EnsureOpen();
        EnsureWritable();
        timestamps[IndexOf(chunkX, chunkZ)] = value;
        dirty = true;
    }

    /// <summary>
    /// チャンクを圧縮されたまま取り出す
    /// 存在しなければ null
    /// </summary>
    /// <exception cref="SpringNbtException">格納内容が壊れている場合</exception>
    public RawChunk? ReadChunkRaw(int chunkX, int chunkZ)
    {
        EnsureOpen();
        int index = IndexOf(chunkX, chunkZ);

        if (sectorCounts[index] == 0)
        {
            return null;
        }

        int start = offsets[index] * SectorSize;
        int length = BinaryPrimitives.ReadInt32BigEndian(data.AsSpan(start, 4));
        int schemeByte = data[start + 4];

        if (length < 1)
        {
            throw SpringNbtException.Malformed(
                string.Create(CultureInfo.InvariantCulture,
                    $"チャンク ({chunkX}, {chunkZ}) の length が不正: {length}"));
        }

        if (4 + length > sectorCounts[index] * SectorSize)
        {
            throw SpringNbtException.Malformed(
                string.Create(CultureInfo.InvariantCulture,
                    $"チャンク ({chunkX}, {chunkZ}) の length が確保セクタ数を超えている"));
        }

        bool external = (schemeByte & 0x80) != 0;
        ChunkCompression compression = ChunkCompressionExtensions.FromId(schemeByte & 0x7F);

        if (external)
        {
            // 最上位ビットが立っている場合、本体は c.X.Z.mcc にある
            byte[] payload = ReadExternalFile(chunkX, chunkZ);
            return new RawChunk(compression, payload, external: true);
        }

        byte[] body = data.AsSpan(start + 5, length - 1).ToArray();
        return new RawChunk(compression, body, external: false);
    }

    /// <summary>
    /// チャンクを NBT として読む
    /// 存在しなければ null
    /// </summary>
    /// <exception cref="SpringNbtException">
    /// 対応していない圧縮方式、または NBT として壊れている場合
    /// </exception>
    public NbtCompound? ReadChunk(int chunkX, int chunkZ)
    {
        RawChunk? raw = ReadChunkRaw(chunkX, chunkZ);

        if (raw is null)
        {
            return null;
        }

        byte[] plain = ChunkCodec.Decompress(raw);
        NbtReadOptions options = new NbtReadOptions { Compression = Nbt.Compression.None };
        return NbtIo.ReadBytes(plain, options).Tag;
    }

    /// <summary>チャンクを NBT として書き込む
    /// 圧縮方式は Zlib</summary>
    public void WriteChunk(int chunkX, int chunkZ, NbtCompound tag)
    {
        WriteChunk(chunkX, chunkZ, tag, ChunkCompression.Zlib);
    }

    /// <summary>チャンクを NBT として、圧縮方式を指定して書き込む</summary>
    public void WriteChunk(int chunkX, int chunkZ, NbtCompound tag, ChunkCompression compression)
    {
        ArgumentNullException.ThrowIfNull(tag);

        NbtWriteOptions options = new NbtWriteOptions { Compression = Nbt.Compression.None };
        byte[] plain = NbtIo.WriteBytes(new NamedTag(string.Empty, tag), options);
        WriteChunkRaw(chunkX, chunkZ, new RawChunk(compression, ChunkCodec.Compress(plain, compression)));
    }

    /// <summary>圧縮済みのチャンクをそのまま書き込む</summary>
    public void WriteChunkRaw(int chunkX, int chunkZ, RawChunk raw)
    {
        ArgumentNullException.ThrowIfNull(raw);
        EnsureOpen();
        EnsureWritable();

        int index = IndexOf(chunkX, chunkZ);
        bool useExternal = raw.Data.Length > MaxInlinePayload;

        byte[] payload;
        int schemeByte;

        if (useExternal)
        {
            // 1MiB を超えるチャンクは外部ファイルへ退避し、リージョンには目印だけ残す
            WriteExternalFile(chunkX, chunkZ, raw.Data);
            payload = Array.Empty<byte>();
            schemeByte = (int)raw.Compression | 0x80;
        }
        else
        {
            DeleteExternalFile(chunkX, chunkZ);
            payload = raw.Data;
            schemeByte = (int)raw.Compression;
        }

        int totalLength = 4 + 1 + payload.Length;
        int needed = (totalLength + SectorSize - 1) / SectorSize;

        if (needed > MaxSectors)
        {
            throw SpringNbtException.InvalidArgument(
                $"チャンクが大きすぎる: {needed} セクタ（上限 {MaxSectors}）");
        }

        int start = AllocateSectors(index, needed);

        // 確保した領域をゼロで埋めてから書く（前の内容を残さないため）
        data.AsSpan(start * SectorSize, needed * SectorSize).Clear();

        int position = start * SectorSize;
        BinaryPrimitives.WriteInt32BigEndian(data.AsSpan(position, 4), 1 + payload.Length);
        data[position + 4] = (byte)schemeByte;
        payload.CopyTo(data.AsSpan(position + 5));

        offsets[index] = start;
        sectorCounts[index] = needed;
        timestamps[index] = (int)DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        dirty = true;
    }

    /// <summary>チャンクを削除する
    /// 削除できたら true</summary>
    public bool DeleteChunk(int chunkX, int chunkZ)
    {
        EnsureOpen();
        EnsureWritable();

        int index = IndexOf(chunkX, chunkZ);

        if (sectorCounts[index] == 0)
        {
            return false;
        }

        DeleteExternalFile(chunkX, chunkZ);
        offsets[index] = 0;
        sectorCounts[index] = 0;
        timestamps[index] = 0;
        dirty = true;
        return true;
    }

    /// <summary>
    /// 必要なセクタ数を確保し、開始セクタ番号を返す
    /// </summary>
    /// <remarks>
    /// 既存の割り当てがちょうど同じ大きさならその場を使い、
    /// そうでなければ先頭から空き領域を探し、無ければ末尾へ追加する
    /// </remarks>
    private int AllocateSectors(int index, int needed)
    {
        // 大きさが変わらないなら動かさない
        // 触っていないチャンクの配置を保つため
        if (sectorCounts[index] == needed)
        {
            return offsets[index];
        }

        bool[] used = BuildSectorUsage(index);
        int totalSectors = data.Length / SectorSize;
        int run = 0;

        // 先頭から連続した空き領域を探す
        for (int sector = HeaderSectors; sector < totalSectors; sector++)
        {
            // 使用中のセクタに当たったら、空きの連続はそこで途切れる
            if (used[sector])
            {
                run = 0;
                continue;
            }

            run += 1;

            if (run == needed)
            {
                return sector - needed + 1;
            }
        }

        // 見つからなければ末尾へ追加する
        // 末尾の空きは再利用できる
        int start = totalSectors - run;
        int requiredSectors = start + needed;
        Array.Resize(ref data, requiredSectors * SectorSize);
        return start;
    }

    /// <summary>
    /// セクタの使用状況を作る
    /// <paramref name="ignoreIndex"/> のチャンクは空きとして扱う
    /// </summary>
    private bool[] BuildSectorUsage(int ignoreIndex)
    {
        int totalSectors = data.Length / SectorSize;
        bool[] used = new bool[totalSectors];

        // ヘッダの 2 セクタは常に使用中
        for (int sector = 0; sector < HeaderSectors && sector < totalSectors; sector++)
        {
            used[sector] = true;
        }

        // 他のチャンクが占めているセクタに印を付ける
        for (int other = 0; other < ChunkCount; other++)
        {
            if (other == ignoreIndex || sectorCounts[other] == 0)
            {
                continue;
            }

            // 他のチャンクが占めるセクタに印を付ける
            for (int sector = offsets[other]; sector < offsets[other] + sectorCounts[other]; sector++)
            {
                // ファイル長を超える位置は既に検証で弾いているが、念のため範囲を確かめる
                if (sector < totalSectors)
                {
                    used[sector] = true;
                }
            }
        }

        return used;
    }

    /// <summary>
    /// 全チャンクを隙間なく詰め直す
    /// 断片化したファイルを縮めたいときに使う
    /// </summary>
    public void Optimize()
    {
        EnsureOpen();
        EnsureWritable();

        List<(int Index, RawChunk Raw)> chunks = new List<(int, RawChunk)>();

        // 先に全チャンクを取り出してから、新しい配置で書き直す
        for (int index = 0; index < ChunkCount; index++)
        {
            if (sectorCounts[index] == 0)
            {
                continue;
            }

            int localX = index % 32;
            int localZ = index / 32;
            RawChunk? raw = ReadChunkRaw((RegionX * 32) + localX, (RegionZ * 32) + localZ);

            // 存在するチャンクだけを集める
            if (raw is not null)
            {
                chunks.Add((index, raw));
            }
        }

        int[] savedTimestamps = (int[])timestamps.Clone();
        data = new byte[HeaderSectors * SectorSize];
        Array.Clear(offsets);
        Array.Clear(sectorCounts);

        int nextSector = HeaderSectors;

        // 添字の昇順に、先頭から詰めて配置する
        foreach ((int index, RawChunk raw) in chunks)
        {
            byte[] payload;
            int schemeByte;

            // 外部ファイルへ退避したチャンクは、本体を持たず印だけを書く
            if (raw.External)
            {
                payload = Array.Empty<byte>();
                schemeByte = (int)raw.Compression | 0x80;
            }
            else
            {
                payload = raw.Data;
                schemeByte = (int)raw.Compression;
            }

            int needed = (4 + 1 + payload.Length + SectorSize - 1) / SectorSize;
            Array.Resize(ref data, (nextSector + needed) * SectorSize);

            int position = nextSector * SectorSize;
            BinaryPrimitives.WriteInt32BigEndian(data.AsSpan(position, 4), 1 + payload.Length);
            data[position + 4] = (byte)schemeByte;
            payload.CopyTo(data.AsSpan(position + 5));

            offsets[index] = nextSector;
            sectorCounts[index] = needed;
            nextSector += needed;
        }

        Array.Copy(savedTimestamps, timestamps, ChunkCount);
        dirty = true;
    }

    /// <summary>変更をファイルへ書き出す</summary>
    public void Flush()
    {
        EnsureOpen();

        if (mode == RegionFileMode.ReadOnly)
        {
            return;
        }

        WriteHeader();

        try
        {
            File.WriteAllBytes(path, data);
        }
        catch (IOException error)
        {
            throw new SpringNbtException(ErrorCode.Io, $"ファイルへ書けない: {path}", error);
        }
        catch (UnauthorizedAccessException error)
        {
            throw new SpringNbtException(ErrorCode.Io, $"ファイルへ書けない: {path}", error);
        }

        dirty = false;
    }

    /// <summary>現在の内容をバイト列として組み立てる
    /// ファイルには書かない</summary>
    public byte[] ToBytes()
    {
        EnsureOpen();
        WriteHeader();
        return (byte[])data.Clone();
    }

    /// <summary>ロケーションテーブルとタイムスタンプテーブルを先頭 2 セクタへ書き戻す</summary>
    private void WriteHeader()
    {
        // 位置表とタイムスタンプ表を、添字順に組み立て直す
        for (int index = 0; index < ChunkCount; index++)
        {
            uint entry = ((uint)offsets[index] << 8) | (uint)sectorCounts[index];
            BinaryPrimitives.WriteUInt32BigEndian(data.AsSpan(index * 4, 4), entry);
            BinaryPrimitives.WriteInt32BigEndian(
                data.AsSpan(SectorSize + (index * 4), 4), timestamps[index]);
        }
    }

    /// <summary>変更があれば書き出してから閉じる</summary>
    public void Close()
    {
        if (closed)
        {
            return;
        }

        // 読み書きで開いていて変更があるなら、閉じる前に書き出す
        if (dirty && mode == RegionFileMode.ReadWrite)
        {
            Flush();
        }

        closed = true;
    }

    /// <inheritdoc/>
    public void Dispose() => Close();

    // -- 外部ファイル (.mcc) ------------------------------------------------

    private string ExternalPath(int chunkX, int chunkZ) =>
        Path.Combine(directory, string.Create(CultureInfo.InvariantCulture, $"c.{chunkX}.{chunkZ}.mcc"));

    private byte[] ReadExternalFile(int chunkX, int chunkZ)
    {
        string external = ExternalPath(chunkX, chunkZ);

        try
        {
            return File.ReadAllBytes(external);
        }
        catch (FileNotFoundException error)
        {
            throw new SpringNbtException(
                ErrorCode.MalformedData, $"外部チャンクファイルが無い: {external}", error);
        }
        catch (IOException error)
        {
            throw new SpringNbtException(ErrorCode.Io, $"外部チャンクファイルを読めない: {external}", error);
        }
    }

    private void WriteExternalFile(int chunkX, int chunkZ, byte[] payload)
    {
        string external = ExternalPath(chunkX, chunkZ);

        try
        {
            File.WriteAllBytes(external, payload);
        }
        catch (IOException error)
        {
            throw new SpringNbtException(ErrorCode.Io, $"外部チャンクファイルへ書けない: {external}", error);
        }
    }

    private void DeleteExternalFile(int chunkX, int chunkZ)
    {
        string external = ExternalPath(chunkX, chunkZ);

        // 縮んで内部へ戻ったチャンクの残骸を消す
        if (File.Exists(external))
        {
            try
            {
                File.Delete(external);
            }
            catch (IOException error)
            {
                throw new SpringNbtException(
                    ErrorCode.Io, $"外部チャンクファイルを削除できない: {external}", error);
            }
        }
    }
}

/// <summary>チャンクのペイロードを圧縮方式IDに従って展開・圧縮する</summary>
internal static class ChunkCodec
{
    /// <summary>圧縮済みペイロードを展開する</summary>
    internal static byte[] Decompress(RawChunk raw)
    {
        switch (raw.Compression)
        {
            case ChunkCompression.None:
                return raw.Data;
            case ChunkCompression.Gzip:
                return Inflate(raw.Data, ChunkCompression.Gzip);
            case ChunkCompression.Zlib:
                return Inflate(raw.Data, ChunkCompression.Zlib);
            case ChunkCompression.Lz4:
                throw SpringNbtException.UnsupportedFeature(
                    "LZ4 圧縮のチャンクは扱えない。生バイトAPI (ReadChunkRaw) を使うこと");
            default:
                throw SpringNbtException.UnsupportedFeature(
                    "カスタム圧縮のチャンクは扱えない。生バイトAPI (ReadChunkRaw) を使うこと");
        }
    }

    /// <summary>ペイロードを指定の方式で圧縮する</summary>
    internal static byte[] Compress(byte[] plain, ChunkCompression compression)
    {
        if (compression == ChunkCompression.None)
        {
            return plain;
        }

        if (compression != ChunkCompression.Gzip && compression != ChunkCompression.Zlib)
        {
            throw SpringNbtException.UnsupportedFeature(
                $"この圧縮方式では書き込めない: {compression.AsString()}");
        }

        using MemoryStream destination = new MemoryStream();

        // using を閉じてフッタを書かせてから ToArray する必要がある
        using (Stream encoder = CreateEncoder(destination, compression))
        {
            encoder.Write(plain, 0, plain.Length);
        }

        return destination.ToArray();
    }

    private static byte[] Inflate(byte[] payload, ChunkCompression compression)
    {
        using MemoryStream source = new MemoryStream(payload, writable: false);
        using Stream decoder = CreateDecoder(source, compression);
        using MemoryStream destination = new MemoryStream();

        try
        {
            decoder.CopyTo(destination);
        }
        catch (InvalidDataException error)
        {
            throw new SpringNbtException(
                ErrorCode.MalformedData, "チャンクの圧縮データを展開できない", error);
        }

        return destination.ToArray();
    }

    private static Stream CreateDecoder(Stream source, ChunkCompression compression)
    {
        if (compression == ChunkCompression.Gzip)
        {
            return new GZipStream(source, CompressionMode.Decompress, leaveOpen: true);
        }

        return new ZLibStream(source, CompressionMode.Decompress, leaveOpen: true);
    }

    private static Stream CreateEncoder(Stream destination, ChunkCompression compression)
    {
        if (compression == ChunkCompression.Gzip)
        {
            return new GZipStream(destination, CompressionLevel.Optimal, leaveOpen: true);
        }

        return new ZLibStream(destination, CompressionLevel.Optimal, leaveOpen: true);
    }
}

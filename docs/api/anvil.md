# API 対応表：Anvil

`.mca` リージョンファイルの読み書き。チャンクの中身は解釈せず、NBT として返す。

- 使い方は [ガイド 03](../guide/03-anvil-region.md)
- バイトレベルの仕様は [spec/20](../spec/20-anvil-region.md)
- 命名の変換規則は [概要](overview.md#2-変換規則)

<!-- generated:start -->

| 論理名 | C# | Java | TypeScript | Python | Rust | 概要 |
|---|---|---|---|---|---|---|
| **RegionFile** | `RegionFile` | `RegionFile` | `RegionFile` | `RegionFile` | `RegionFile` | Anvil のリージョンファイル (r.X.Z.mca) |
| `chunk_positions` | `ChunkPositions()` | `chunkPositions()` | `chunkPositions()` | `chunk_positions()` | `chunk_positions()` | 存在するチャンクの座標を、ロケーションテーブルの並び順で列挙する |
| `delete_chunk` | `DeleteChunk()` | `deleteChunk()` | `deleteChunk()` | `delete_chunk()` | `delete_chunk()` |  |
| `flush` | `Flush()` | `flush()` | `flush()` | `flush()` | `flush()` | 変更をファイルへ書き出す |
| `has_chunk` | `HasChunk()` | `hasChunk()` | `hasChunk()` | `has_chunk()` | `has_chunk()` | チャンクが存在するか |
| `open` | `Open()` | `open()` | `open()` | `open()` | `open()` | リージョンファイルを開く |
| `optimize` | `Optimize()` | `optimize()` | `optimize()` | `optimize()` | `optimize()` | 全チャンクを隙間なく詰め直す |
| `read_chunk` | `ReadChunk()` | `readChunk()` | `readChunk()` | `read_chunk()` | `read_chunk()` | チャンクを NBT として読む |
| `read_chunk_raw` | `ReadChunkRaw()` | `readChunkRaw()` | `readChunkRaw()` | `read_chunk_raw()` | `read_chunk_raw()` | チャンクを圧縮されたまま取り出す |
| `region_x` | `RegionX` | `regionX()` | `regionX` | `region_x` | `region_x()` | このリージョンのX座標 |
| `region_z` | `RegionZ` | `regionZ()` | `regionZ` | `region_z` | `region_z()` | このリージョンのZ座標 |
| `sector_size` | `SectorSize` | `SECTOR_SIZE` | `SECTOR_SIZE` | `SECTOR_SIZE` | `SECTOR_SIZE` | セクタ長 |
| `timestamp` | `Timestamp()` | `timestamp()` | `timestamp()` | `timestamp()` | `timestamp()` |  |
| `to_bytes` | `ToBytes()` | `toBytes()` | `toBytes()` | `to_bytes()` | `to_bytes()` |  |
| `write_chunk` | `WriteChunk()` | `writeChunk()` | `writeChunk()` | `write_chunk()` | `write_chunk()` | チャンクを NBT として、圧縮方式を指定して書き込む |
| `write_chunk_raw` | `WriteChunkRaw()` | `writeChunkRaw()` | `writeChunkRaw()` | `write_chunk_raw()` | `write_chunk_raw()` | 圧縮済みのチャンクをそのまま書き込む |
| **RegionFolder** | `RegionFolder` | `RegionFolder` | `RegionFolder` | `RegionFolder` | `RegionFolder` | リージョンファイルが並ぶディレクトリ 1 つ分（region/、entities/、poi/ のいずれか） |
| `cached_region_count` | `CachedRegionCount` | `cachedRegionCount()` | `cachedRegionCount()` | `cached_region_count` | `cached_region_count()` | いま開いているリージョンファイル数 |
| `chunk_positions` | `ChunkPositions()` | `chunkPositions()` | `chunkPositions()` | `chunk_positions()` | `chunk_positions()` | このフォルダに存在する全チャンクの座標を列挙する |
| `default_max_cached_regions` | `DefaultMaxCachedRegions` | `DEFAULT_MAX_CACHED_REGIONS` | `DEFAULT_MAX_CACHED_REGIONS` | `DEFAULT_MAX_CACHED_REGIONS` | `DEFAULT_MAX_CACHED_REGIONS` | 同時に開いておくリージョンファイル数の既定の上限 |
| `delete_chunk` | `DeleteChunk()` | `deleteChunk()` | `deleteChunk()` | `delete_chunk()` | `delete_chunk()` |  |
| `directory` | `Directory` | `directory()` | `directory` | `directory` | `directory()` | このフォルダのパス |
| `flush` | `Flush()` | `flush()` | `flush()` | `flush()` | `flush()` | 開いている全リージョンの変更を書き出す |
| `has_chunk` | `HasChunk()` | `hasChunk()` | `hasChunk()` | `has_chunk()` | `has_chunk()` | チャンクが存在するか |
| `max_cached_regions` | `MaxCachedRegions` | `maxCachedRegions()` | `maxCachedRegions` | `max_cached_regions` | `max_cached_regions()` | 同時に開いておくリージョンファイル数の上限 |
| `open` | `Open()` | `open()` | `open()` | `open()` | `open()` | リージョンフォルダを開く |
| `open_with_limit` | — | — | — | — | `open_with_limit()` |  |
| `read_chunk` | `ReadChunk()` | `readChunk()` | `readChunk()` | `read_chunk()` | `read_chunk()` |  |
| `region` | `Region` | `region()` | `region()` | `region()` | `region()` | リージョンファイルを取得する |
| `region_positions` | `RegionPositions()` | `regionPositions()` | `regionPositions()` | `region_positions()` | `region_positions()` | このフォルダに存在するリージョンの座標を列挙する |
| `write_chunk` | `WriteChunk()` | `writeChunk()` | `writeChunk()` | `write_chunk()` | `write_chunk()` | チャンクを NBT として書き込む |
| `write_chunk_nbt` | — | — | — | — | `write_chunk_nbt()` |  |
| **RegionFileMode** | `RegionFileMode` | `RegionFileMode` | `RegionFileMode` | `RegionFileMode` | `RegionFileMode` | リージョンファイルを開くときの動作 |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `read_only` | `ReadOnly` | `READ_ONLY` | `ReadOnly` | `READ_ONLY` | `ReadOnly` |  |
| `read_write` | `ReadWrite` | `READ_WRITE` | `ReadWrite` | `READ_WRITE` | `ReadWrite` |  |
| **ChunkPos** | `ChunkPos` | `ChunkPos` | `ChunkPos` | `ChunkPos` | `ChunkPos` | チャンクの絶対座標 |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `index` | `Index` | `index()` | `index()` | `index()` | `index()` | ロケーションテーブル内の添字 (0..1023) |
| `local_x` | `LocalX` | `localX()` | `localX()` | `local_x()` | `local_x()` | リージョン内でのX位置 (0..31) |
| `local_z` | `LocalZ` | `localZ()` | `localZ()` | `local_z()` | `local_z()` | リージョン内でのZ位置 (0..31) |
| `region` | `Region` | `region()` | `region()` | `region()` | `region()` | このチャンクを含むリージョンの座標 |
| `x` | `X` | `x()` | `x` | `x` | `x` | 絶対チャンクX座標 |
| `z` | `Z` | `z()` | `z` | `z` | `z` | 絶対チャンクZ座標 |
| **RegionPos** | `RegionPos` | `RegionPos` | `RegionPos` | `RegionPos` | `RegionPos` | リージョンの座標 |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `file_name` | `FileName` | `fileName()` | `fileName()` | `file_name()` | `file_name()` | このリージョンのファイル名（r.X.Z.mca） |
| `from_file_name` | `FromFileName()` | `fromFileName()` | `fromFileName()` | `from_file_name()` | `from_file_name()` | r.X.Z.mca 形式のファイル名から座標を得る |
| `key` | — | — | `key()` | — | — |  |
| `x` | `X` | `x()` | `x` | `x` | `x` | リージョンX座標 |
| `z` | `Z` | `z()` | `z` | `z` | `z` | リージョンZ座標 |
| **ChunkCompression** | `ChunkCompression` | `ChunkCompression` | `ChunkCompression` | `ChunkCompression` | `ChunkCompression` | リージョンファイル内でチャンクに使われる圧縮方式 |
| `as_string` | `AsString()` | `asString()` | `chunkCompressionAsString()` | `as_string()` | `as_str()` | 適合性テストで言語間比較に使う識別子を返す |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `custom` | `Custom` | `CUSTOM` | `Custom` | `CUSTOM` | `Custom` |  |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `from_id` | `FromId()` | `fromId()` | `chunkCompressionFromId()` | `from_id()` | `from_id()` | 圧縮方式IDから ChunkCompression を得る |
| `gzip` | `Gzip` | `GZIP` | `Gzip` | `GZIP` | `Gzip` |  |
| `id` | `Id` | `id()` | `id` | `id()` | `id()` |  |
| `lz4` | `Lz4` | `LZ4` | `Lz4` | `LZ4` | `Lz4` |  |
| `none` | `None` | `NONE` | `None` | `NONE` | `None` |  |
| `zlib` | `Zlib` | `ZLIB` | `Zlib` | `ZLIB` | `Zlib` |  |
| **RawChunk** | `RawChunk` | `RawChunk` | `RawChunk` | `RawChunk` | `RawChunk` | リージョンファイルに格納されたままの、圧縮済みチャンクデータ |
| `compression` | `Compression` | `compression()` | `compression` | `compression` | `compression` | この本体に使われている圧縮方式 |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `data` | `Data` | `data()` | `data` | `data` | `data` | 圧縮されたままの本体 |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `external` | `External` | `external()` | `external` | `external` | `external` | 外部ファイル c.X.Z.mcc に格納されていたか |

<!-- generated:end -->

この表は実装から生成している。手で直さず、
`python3 spec/tools/check_docs_sync.py --write` で更新すること。

# API 対応表：Anvil

`.mca` リージョンファイルの読み書き。チャンクの中身は解釈せず、NBT として返す。

- 使い方は [ガイド 03](../guide/03-anvil-region.md)
- バイトレベルの仕様は [spec/20](../spec/20-anvil-region.md)
- 命名の変換規則は [概要](overview.md#2-変換規則)

<!-- generated:start -->

| 論理名 | C# | Java | TypeScript | Python | Rust | 概要 |
|---|---|---|---|---|---|---|
| **RegionFile** | `RegionFile` | `RegionFile` | `RegionFile` | `RegionFile` | `RegionFile` | Anvil のリージョンファイル (r.X.Z.mca)。 |
| `chunk_positions` | `ChunkPositions()` | `chunkPositions()` | `chunkPositions()` | `chunk_positions()` | `chunk_positions()` | 存在するチャンクの座標を、ロケーションテーブルの並び順で列挙する。 |
| `delete_chunk` | `DeleteChunk()` | `deleteChunk()` | `deleteChunk()` | `delete_chunk()` | `delete_chunk()` | チャンクを削除する。 |
| `flush` | `Flush()` | `flush()` | `flush()` | `flush()` | `flush()` | 変更をファイルへ書き出す。 |
| `has_chunk` | `HasChunk()` | `hasChunk()` | `hasChunk()` | `has_chunk()` | `has_chunk()` | チャンクが存在するか。 |
| `open` | `Open()` | `open()` | `open()` | `open()` | `open()` | リージョンファイルを開く。 |
| `optimize` | `Optimize()` | `optimize()` | `optimize()` | `optimize()` | `optimize()` | 全チャンクを隙間なく詰め直す。 |
| `read_chunk` | `ReadChunk()` | `readChunk()` | `readChunk()` | `read_chunk()` | `read_chunk()` | チャンクを NBT として読む。 |
| `read_chunk_raw` | `ReadChunkRaw()` | `readChunkRaw()` | `readChunkRaw()` | `read_chunk_raw()` | `read_chunk_raw()` | チャンクを圧縮されたまま取り出す。 |
| `region_x` | `RegionX` | `regionX()` | `regionX` | `region_x` | `region_x()` | このリージョンのX座標。 |
| `region_z` | `RegionZ` | `regionZ()` | `regionZ` | `region_z` | `region_z()` | このリージョンのZ座標。 |
| `sector_size` | `SectorSize` | `SECTOR_SIZE` | `SECTOR_SIZE` | `SECTOR_SIZE` | `SECTOR_SIZE` | セクタ長。 |
| `timestamp` | `Timestamp()` | `timestamp()` | `timestamp()` | `timestamp()` | `timestamp()` | チャンクの最終更新時刻（Unix 秒）。 |
| `to_bytes` | `ToBytes()` | `toBytes()` | `toBytes()` | `to_bytes()` | `to_bytes()` | 現在の内容をバイト列として組み立てる。 |
| `write_chunk` | `WriteChunk()` | `writeChunk()` | `writeChunk()` | `write_chunk()` | `write_chunk()` | チャンクを NBT として書き込む。 |
| `write_chunk_raw` | `WriteChunkRaw()` | `writeChunkRaw()` | `writeChunkRaw()` | `write_chunk_raw()` | `write_chunk_raw()` | 圧縮済みのチャンクをそのまま書き込む。 |
| **RegionFolder** | `RegionFolder` | `RegionFolder` | `RegionFolder` | `RegionFolder` | `RegionFolder` | リージョンファイルが並ぶディレクトリ 1 つ分（region/、entities/、poi/ のいずれか）。 |
| `cached_region_count` | `CachedRegionCount` | `cachedRegionCount()` | `cachedRegionCount()` | `cached_region_count` | `cached_region_count()` | いま開いているリージョンファイル数。 |
| `chunk_positions` | `ChunkPositions()` | `chunkPositions()` | `chunkPositions()` | `chunk_positions()` | `chunk_positions()` | このフォルダに存在する全チャンクの座標を列挙する。 |
| `default_max_cached_regions` | `DefaultMaxCachedRegions` | `DEFAULT_MAX_CACHED_REGIONS` | `DEFAULT_MAX_CACHED_REGIONS` | `DEFAULT_MAX_CACHED_REGIONS` | `DEFAULT_MAX_CACHED_REGIONS` | 同時に開いておくリージョンファイル数の既定の上限。 |
| `delete_chunk` | `DeleteChunk()` | `deleteChunk()` | `deleteChunk()` | `delete_chunk()` | `delete_chunk()` | チャンクを削除する。 |
| `directory` | `Directory` | `directory()` | `directory` | `directory` | `directory()` | このフォルダのパス。 |
| `flush` | `Flush()` | `flush()` | `flush()` | `flush()` | `flush()` | 開いている全リージョンの変更を書き出す。 |
| `has_chunk` | `HasChunk()` | `hasChunk()` | `hasChunk()` | `has_chunk()` | `has_chunk()` | チャンクが存在するか。 |
| `max_cached_regions` | `MaxCachedRegions` | `maxCachedRegions()` | `maxCachedRegions` | `max_cached_regions` | `max_cached_regions()` | 同時に開いておくリージョンファイル数の上限。 |
| `open` | `Open()` | `open()` | `open()` | `open()` | `open()` | リージョンフォルダを開く。 |
| `open_with_limit` | — | — | — | — | `open_with_limit()` |  |
| `read_chunk` | `ReadChunk()` | `readChunk()` | `readChunk()` | `read_chunk()` | `read_chunk()` | チャンクを NBT として読む。 |
| `region` | `Region` | `region()` | `region()` | `region()` | `region()` | リージョンファイルを取得する。 |
| `region_positions` | `RegionPositions()` | `regionPositions()` | `regionPositions()` | `region_positions()` | `region_positions()` | このフォルダに存在するリージョンの座標を列挙する。 |
| `write_chunk` | `WriteChunk()` | `writeChunk()` | `writeChunk()` | `write_chunk()` | `write_chunk()` | チャンクを NBT として書き込む。 |
| `write_chunk_nbt` | — | — | — | — | `write_chunk_nbt()` |  |
| **RegionFileMode** | `RegionFileMode` | `RegionFileMode` | `RegionFileMode` | `RegionFileMode` | `RegionFileMode` | リージョンファイルを開くときの動作。 |
| `read_only` | `ReadOnly` | `READ_ONLY` | `ReadOnly` | `read_only` | `read_only` | 読み取り専用。 |
| `read_write` | `ReadWrite` | `READ_WRITE` | `ReadWrite` | `read_write` | `read_write` | 読み書き。 |
| **ChunkPos** | `ChunkPos` | `ChunkPos` | `ChunkPos` | `ChunkPos` | `ChunkPos` | チャンクの絶対座標。 |
| `index` | `Index` | `index()` | `index()` | `index()` | `index()` | ロケーションテーブル内の添字 (0..1023)。 |
| `local_x` | `LocalX` | `localX()` | `localX()` | `local_x()` | `local_x()` | リージョン内でのX位置 (0..31)。 |
| `local_z` | `LocalZ` | `localZ()` | `localZ()` | `local_z()` | `local_z()` | リージョン内でのZ位置 (0..31)。 |
| `region` | `Region` | `region()` | `region()` | `region()` | `region()` | このチャンクを含むリージョンの座標。 |
| `x` | `X` | `x()` | `x` | `x` | `x` | 絶対チャンクX座標。 |
| `z` | `Z` | `z()` | `z` | `z` | `z` | 絶対チャンクZ座標。 |
| **RegionPos** | `RegionPos` | `RegionPos` | `RegionPos` | `RegionPos` | `RegionPos` | リージョンの座標。 |
| `file_name` | `FileName` | `fileName()` | `fileName()` | `file_name()` | `file_name()` | このリージョンのファイル名（r.X.Z.mca）。 |
| `from_file_name` | `FromFileName()` | `fromFileName()` | `fromFileName()` | `from_file_name()` | `from_file_name()` | r.X.Z.mca 形式のファイル名から座標を得る。 |
| `key` | — | — | `key()` | — | — |  |
| `x` | `X` | `x()` | `x` | `x` | `x` | リージョンX座標。 |
| `z` | `Z` | `z()` | `z` | `z` | `z` | リージョンZ座標。 |
| **ChunkCompression** | `ChunkCompression` | `ChunkCompression` | `ChunkCompression` | `ChunkCompression` | `ChunkCompression` | リージョンファイル内でチャンクに使われる圧縮方式。 |
| `as_str` | — | — | — | — | `as_str()` |  |
| `as_string` | — | `asString()` | — | `as_string()` | — |  |
| `custom` | `Custom` | `CUSTOM` | `Custom` | `custom` | `custom` | サードパーティ製サーバのカスタム方式。 |
| `from_id` | — | `fromId()` | — | `from_id()` | `from_id()` |  |
| `gzip` | `Gzip` | `GZIP` | `Gzip` | `gzip` | `gzip` | GZip (RFC 1952)。 |
| `id` | `Id` | `id()` | `id` | `id()` | `id()` |  |
| `lz4` | `Lz4` | `LZ4` | `Lz4` | `lz4` | `lz4` | LZ4（ブロック形式）。 |
| `none` | `None` | `NONE` | `None` | `none` | `none` | 無圧縮。 |
| `zlib` | `Zlib` | `ZLIB` | `Zlib` | `zlib` | `zlib` | Zlib (RFC 1950)。 |
| **RawChunk** | `RawChunk` | `RawChunk` | `RawChunk` | `RawChunk` | `RawChunk` | リージョンファイルに格納されたままの、圧縮済みチャンクデータ。 |
| `compression` | `Compression` | `compression()` | `compression` | `compression` | `compression` | この本体に使われている圧縮方式。 |
| `data` | `Data` | `data()` | `data` | `data` | `data` | 圧縮されたままの本体。 |
| `external` | `External` | `external()` | `external` | `external` | `external` | 外部ファイル c.X.Z.mcc に格納されていたか。 |

<!-- generated:end -->

この表は実装から生成している。手で直さず、
`python3 spec/tools/check_docs_sync.py --write` で更新すること。

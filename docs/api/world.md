# API 対応表：World

ワールド・次元・チャンク・ブロック。ここだけが Minecraft のバージョンに依存する。

- 使い方は [ガイド 04](../guide/04-world-and-level-dat.md) / [ガイド 05](../guide/05-blocks-and-biomes.md)
- 仕様は [spec/30](../spec/30-chunk-format.md) / [spec/31](../spec/31-paletted-container.md) / [spec/40](../spec/40-world-layout.md)
- 命名の変換規則は [概要](overview.md#2-変換規則)

<!-- generated:start -->

| 論理名 | C# | Java | TypeScript | Python | Rust | 概要 |
|---|---|---|---|---|---|---|
| **MinecraftWorld** | `MinecraftWorld` | `MinecraftWorld` | `MinecraftWorld` | `MinecraftWorld` | `MinecraftWorld` | Minecraft Java版のセーブデータ 1 つ分 |
| `data_file` | `DataFile()` | `dataFile()` | `dataFile()` | `data_file()` | `data_file()` | data/minecraft/&lt;name&gt;.dat を読む |
| `dimension` | `Dimension` | `dimension()` | `dimension()` | `dimension()` | `dimension()` | 次元を得る |
| `dimension_ids` | `DimensionIds()` | `dimensionIds()` | `dimensionIds()` | `dimension_ids()` | `dimension_ids()` | 存在する次元のIDを列挙する |
| `directory` | `Directory` | `directory()` | `directory` | `directory` | `directory()` | ワールドディレクトリのパス |
| `level` | `Level` | `level()` | `level` | `level` | `level()` | level.dat の内容 |
| `open` | `Open()` | `open()` | `open()` | `open()` | `open()` | ワールドを開く |
| `player` | `Player()` | `player()` | `player()` | `player()` | `player()` |  |
| `player_ids` | `PlayerIds()` | `playerIds()` | `playerIds()` | `player_ids()` | `player_ids()` | プレイヤーのUUID一覧 |
| `save_level` | `SaveLevel()` | `saveLevel()` | `saveLevel()` | `save_level()` | `save_level()` | level.dat を書き戻す |
| **WorldOpenOptions** | `WorldOpenOptions` | `WorldOpenOptions` | `WorldOpenOptions` | `WorldOpenOptions` | `WorldOpenOptions` | ワールドを開くときの動作 |
| `chunk_read` | `ChunkRead` | `chunkRead()` | `chunkRead` | `chunk_read` | `chunk_read` | チャンク読み込みのオプション |
| `chunk_write` | `ChunkWrite` | `chunkWrite()` | `chunkWrite` | `chunk_write` | `chunk_write` | チャンク書き込みのオプション |
| `ignore_session_lock` | `IgnoreSessionLock` | `ignoreSessionLock()` | `ignoreSessionLock` | `ignore_session_lock` | `ignore_session_lock` | session.lock の確認を飛ばすか |
| `writable` | `Writable` | `writable()` | `writable` | `writable` | `writable` |  |
| **LevelData** | `LevelData` | `LevelData` | `LevelData` | `LevelData` | `LevelData` | level.dat の内容 |
| `data` | `Data` | `data()` | `data` | `data` | `data()` |  |
| `data_version` | `DataVersion` | `dataVersion()` | `dataVersion()` | `data_version` | `data_version()` | チャンク構造のバージョン |
| `difficulty` | `Difficulty` | `difficulty()` | `difficulty()` | `difficulty` | `difficulty()` | 難易度（normal など） |
| `game_type` | `GameType` | `gameType()` | `gameType()` | `game_type` | `game_type()` |  |
| `is_hardcore` | `IsHardcore` | `isHardcore()` | `isHardcore()` | `is_hardcore` | `is_hardcore()` | ハードコアか |
| `level_name` | `LevelName` | `levelName()` | `levelName()` | `level_name` | `level_name()` | ワールド名 |
| `raw` | `Raw` | `raw()` | `raw` | `raw` | `raw()` |  |
| `spawn_dimension` | `SpawnDimension` | `spawnDimension()` | `spawnDimension()` | `spawn_dimension` | `spawn_dimension()` | スポーン地点の次元ID |
| `spawn_pos` | `SpawnPos` | `spawnPos()` | `spawnPos()` | `spawn_pos` | `spawn_pos()` | スポーン地点の [x, y, z] |
| `time` | `Time` | `time()` | `time()` | `time` | `time()` | ワールドの経過時間（tick） |
| `to_named_tag` | `ToNamedTag()` | `toNamedTag()` | `toNamedTag()` | `to_named_tag()` | `to_named_tag()` | 書き出し用の NamedTag を作る |
| `version_name` | `VersionName` | `versionName()` | `versionName()` | `version_name` | `version_name()` | バージョン名（26.2 など） |
| **Dimension** | `Dimension` | `Dimension` | `Dimension` | `Dimension` | `Dimension` | ワールド内の次元 1 つ分 |
| `chunk` | `Chunk` | `chunk()` | `chunk()` | `chunk()` | `chunk()` | チャンクを読む |
| `chunk_mut` | — | — | — | — | `chunk_mut()` |  |
| `chunk_positions` | `ChunkPositions()` | `chunkPositions()` | `chunkPositions()` | `chunk_positions()` | `chunk_positions()` | この次元に存在する全チャンクの座標を列挙する |
| `data_file` | `DataFile()` | `dataFile()` | `dataFile()` | `data_file()` | `data_file()` | data/minecraft/&lt;name&gt;.dat を読む |
| `directory` | `Directory` | `directory()` | `directory` | `directory` | `directory()` | この次元のディレクトリ |
| `entity_folder` | `EntityFolder` | `entityFolder()` | `entityFolder()` | `entity_folder()` | `entity_folder()` |  |
| `flush` | `Flush()` | `flush()` | `flush()` | `flush()` | `flush()` | 変更したチャンクをすべて書き戻し、リージョンをディスクへ反映する |
| `get_biome` | `GetBiome()` | `getBiome()` | `getBiome()` | `get_biome()` | `get_biome()` |  |
| `get_block` | `GetBlock()` | `getBlock()` | `getBlock()` | `get_block()` | `get_block()` | 絶対座標でブロックを取得する |
| `id` | `Id` | `id()` | `id` | `id` | `id()` | 次元ID（minecraft:overworld など） |
| `mark_modified` | — | — | — | — | `mark_modified()` |  |
| `poi_folder` | `PoiFolder` | `poiFolder()` | `poiFolder()` | `poi_folder()` | `poi_folder()` |  |
| `region_folder` | `RegionFolder` | `regionFolder()` | `regionFolder()` | `region_folder()` | `region_folder()` |  |
| `save_chunk` | `SaveChunk()` | `saveChunk()` | `saveChunk()` | `save_chunk()` | — | チャンクを書き戻す |
| `set_biome` | `SetBiome()` | `setBiome()` | `setBiome()` | `set_biome()` | `set_biome()` |  |
| `set_block` | `SetBlock()` | `setBlock()` | `setBlock()` | `set_block()` | `set_block()` | 絶対座標でブロックを設定する |
| **Chunk** | `Chunk` | `Chunk` | `Chunk` | `Chunk` | `Chunk` | チャンク 1 つ分 |
| `biome_index` | `BiomeIndex()` | `biomeIndex()` | `biomeIndex()` | `biome_index()` | `biome_index()` |  |
| `biomes_per_section` | `BiomesPerSection` | `BIOMES_PER_SECTION` | `BIOMES_PER_SECTION` | `BIOMES_PER_SECTION` | `BIOMES_PER_SECTION` | セクション 1 つに入るバイオームのエントリ数（4×4×4 単位） |
| `block_index` | `BlockIndex()` | `blockIndex()` | `blockIndex()` | `block_index()` | `block_index()` | セクション内のブロック添字 |
| `blocks_per_section` | `BlocksPerSection` | `BLOCKS_PER_SECTION` | `BLOCKS_PER_SECTION` | `BLOCKS_PER_SECTION` | `BLOCKS_PER_SECTION` | セクション 1 つに入るブロック数 |
| `clear_heightmaps` | `ClearHeightmaps()` | `clearHeightmaps()` | `clearHeightmaps()` | `clear_heightmaps()` | `clear_heightmaps()` | Heightmaps を削除し、Minecraft に再計算させる |
| `compact` | `Compact()` | `compact()` | `compact()` | `compact()` | `compact()` | 使われていないパレット要素を全セクションから取り除く |
| `data_version` | `DataVersion` | `dataVersion()` | `dataVersion()` | `data_version` | `data_version()` | チャンク構造のバージョン |
| `from_nbt` | `FromNbt()` | `fromNbt()` | `fromNbt()` | `from_nbt()` | `from_nbt()` | NBT からチャンクを読む |
| `get_biome` | `GetBiome()` | `getBiome()` | `getBiome()` | `get_biome()` | `get_biome()` | バイオームを取得する |
| `get_block` | `GetBlock()` | `getBlock()` | `getBlock()` | `get_block()` | `get_block()` | ブロックを取得する |
| `invalidate_lighting` | `InvalidateLighting()` | `invalidateLighting()` | `invalidateLighting()` | `invalidate_lighting()` | `invalidate_lighting()` | isLightOn を 0 にし、光源の再計算を促す |
| `is_fully_generated` | `IsFullyGenerated` | `isFullyGenerated()` | `isFullyGenerated()` | `is_fully_generated` | `is_fully_generated()` |  |
| `min_section_y` | `MinSectionY` | `minSectionY()` | `minSectionY()` | `min_section_y` | `min_section_y()` |  |
| `raw` | `Raw` | `raw()` | `raw` | `raw` | `raw()` |  |
| `section` | `Section` | `section()` | `section()` | `section()` | `section()` |  |
| `section_mut` | — | — | — | — | `section_mut()` |  |
| `section_ys` | `SectionYs` | `sectionYs()` | `sectionYs()` | `section_ys` | `section_ys()` |  |
| `set_biome` | `SetBiome()` | `setBiome()` | `setBiome()` | `set_biome()` | `set_biome()` |  |
| `set_block` | `SetBlock()` | `setBlock()` | `setBlock()` | `set_block()` | `set_block()` | ブロックを設定する |
| `status` | `Status` | `status()` | `status()` | `status` | `status()` | 生成段階（minecraft:full など） |
| `to_nbt` | `ToNbt()` | `toNbt()` | `toNbt()` | `to_nbt()` | `to_nbt()` | NBT へ書き戻す |
| `x` | `X` | `x()` | `x()` | `x` | `x()` | 絶対チャンクX座標 |
| `z` | `Z` | `z()` | `z()` | `z` | `z()` | 絶対チャンクZ座標 |
| **ChunkSection** | `ChunkSection` | `ChunkSection` | `ChunkSection` | `ChunkSection` | `ChunkSection` | チャンクを Y 方向に 16 ブロックずつ区切った 16×16×16 の立方体 |
| `biomes` | `Biomes` | `biomes()` | `biomes()` | `biomes` | `biomes()` |  |
| `biomes_mut` | — | — | — | — | `biomes_mut()` |  |
| `block_states` | `BlockStates` | `blockStates()` | `blockStates()` | `block_states` | `block_states()` |  |
| `block_states_mut` | — | — | — | — | `block_states_mut()` |  |
| `compact` | `Compact()` | `compact()` | `compact()` | `compact()` | `compact()` | 使われていないパレット要素を取り除く |
| `from_nbt` | `FromNbt()` | `fromNbt()` | `fromNbt()` | `from_nbt()` | `from_nbt()` | NBT からセクションを読む |
| `has_biomes` | `HasBiomes` | `hasBiomes()` | `hasBiomes()` | `has_biomes` | `has_biomes()` | バイオームを持つか |
| `has_block_states` | `HasBlockStates` | `hasBlockStates()` | `hasBlockStates()` | `has_block_states` | `has_block_states()` | ブロック状態を持つか |
| `raw` | `Raw` | `raw()` | `raw` | `raw` | `raw()` |  |
| `to_nbt` | `ToNbt()` | `toNbt()` | `toNbt()` | `to_nbt()` | `to_nbt()` |  |
| `y` | `Y` | `y()` | `y` | `y` | `y()` |  |
| **ChunkReadOptions** | `ChunkReadOptions` | `ChunkReadOptions` | `ChunkReadOptions` | `ChunkReadOptions` | `ChunkReadOptions` | チャンク読み込みのオプション |
| `lenient_bit_storage` | `LenientBitStorage` | `lenientBitStorage()` | `lenientBitStorage` | `lenient_bit_storage` | `lenient_bit_storage` | data の長さが期待値と違うとき、長さからビット幅を逆算して読むか |
| `on_version_mismatch` | `OnVersionMismatch` | `onVersionMismatch()` | `onVersionMismatch` | `on_version_mismatch` | `on_version_mismatch` | DataVersion が TargetDataVersion と違うときの動作 |
| `on_warning` | `OnWarning` | `onWarning()` | `onWarning` | `on_warning` | `on_warning` |  |
| **ChunkWriteOptions** | `ChunkWriteOptions` | `ChunkWriteOptions` | `ChunkWriteOptions` | `ChunkWriteOptions` | `ChunkWriteOptions` | チャンク書き込みのオプション |
| `allow_foreign_data_version` | `AllowForeignDataVersion` | `allowForeignDataVersion()` | `allowForeignDataVersion` | `allow_foreign_data_version` | `allow_foreign_data_version` | 対象バージョン以外の DataVersion を持つチャンクの書き戻しを許すか |
| **VersionMismatchAction** | `VersionMismatchAction` | `VersionMismatchAction` | `VersionMismatchAction` | `VersionMismatchAction` | `VersionMismatchAction` | DataVersion が対象と違ったときの動作 |
| `error` | `Error` | `ERROR` | `Error` | `error` | `error` | UnsupportedDataVersion の例外にする |
| `ignore` | `Ignore` | `IGNORE` | `Ignore` | `ignore` | `ignore` | 何もしない |
| `warn` | `Warn` | `WARN` | `Warn` | `warn` | `warn` |  |
| **BlockState** | `BlockState` | `BlockState` | `BlockState` | `BlockState` | `BlockState` | ブロックの状態 |
| `from_nbt` | `FromNbt()` | `fromNbt()` | `fromNbt()` | `from_nbt()` | `from_nbt()` | パレット要素の NBT から作る |
| `name` | `Name` | `name()` | `name()` | `name` | `name()` | ブロックID（名前空間つき） |
| `of` | — | — | — | — | `of()` |  |
| `parse` | `Parse()` | `parse()` | `parse()` | `parse()` | `parse()` | minecraft:oak_stairs[facing=north,half=top] 形式の文字列から作る |
| `properties` | `Properties` | `properties()` | `properties()` | `properties` | `properties()` |  |
| `property` | `Property()` | `property()` | `property()` | `property()` | `property()` |  |
| `to_nbt` | `ToNbt()` | `toNbt()` | `toNbt()` | `to_nbt()` | `to_nbt()` | パレット要素の NBT へ変換する |
| `with` | `With()` | `with()` | `with()` | `with_property()` | `with()` | プロパティを 1 つ差し替えた新しい状態を返す |
| **PalettedContainer** | `PalettedContainer` | `PalettedContainer` | `PalettedContainer` | `PalettedContainer` | `PalettedContainer` | パレットとビットストレージの組 |
| `bits_per_entry` | `BitsPerEntry` | `bitsPerEntry()` | `bitsPerEntry()` | `bits_per_entry` | `bits_per_entry()` |  |
| `ceil_log2` | `CeilLog2()` | `ceilLog2()` | `ceilLog2()` | `ceil_log2()` | `ceil_log2()` |  |
| `compact` | `Compact()` | `compact()` | `compact()` | `compact()` | `compact()` | どのエントリからも参照されていないパレット要素を取り除き、添字を振り直す |
| `entry_count` | `EntryCount` | `entryCount()` | `entryCount()` | `entry_count` | `entry_count()` |  |
| `fill` | `Fill()` | `fill()` | `fill()` | `fill()` | `fill()` |  |
| `filled` | `Filled()` | `filled()` | `filled()` | `filled()` | `filled()` | 単一の値で埋めたコンテナを作る |
| `from_nbt` | `FromNbt()` | `fromNbt()` | `fromNbt()` | `from_nbt()` | `from_nbt()` | NBT から読み込む |
| `get` | `Get()` | `get()` | `get()` | `get()` | `get()` | 添字の値を取り出す |
| `min_bits` | `MinBits` | `minBits()` | `minBits()` | `min_bits` | `min_bits()` |  |
| `palette` | `Palette` | `palette()` | `palette()` | `palette` | `palette()` |  |
| `set` | `Set()` | `set()` | `set()` | `set()` | `set()` |  |
| `to_nbt` | `ToNbt()` | `toNbt()` | `toNbt()` | `to_nbt()` | `to_nbt()` | NBT へ変換する |
| **BitStorage** | `BitStorage` | `BitStorage` | `BitStorage` | `BitStorage` | `BitStorage` | 添字を 64bit 整数の配列へ詰めた表現 |
| `as_longs` | — | — | — | — | `as_longs()` |  |
| `bits_per_entry` | `BitsPerEntry` | `bitsPerEntry()` | `bitsPerEntry()` | `bits_per_entry` | `bits_per_entry()` | 1 エントリあたりのビット数 |
| `create` | `Create()` | `create()` | `create()` | `create()` | `create()` | すべてゼロで初期化した記憶域を作る |
| `entry_count` | `EntryCount` | `entryCount()` | `entryCount()` | `entry_count` | `entry_count()` |  |
| `from_longs` | `FromLongs()` | `fromLongs()` | `fromLongs()` | `from_longs()` | `from_longs()` | 既存の i64 配列から作る |
| `get` | `Get()` | `get()` | `get()` | `get()` | `get()` | 添字の値を取り出す |
| `into_longs` | — | — | — | — | `into_longs()` |  |
| `long_count` | `LongCount()` | `longCount()` | `longCount()` | `long_count()` | `long_count()` | 必要な i64 の個数を求める |
| `resize` | `Resize()` | `resize()` | `resize()` | `resize()` | `resize()` | 別のビット幅へ詰め直した新しい記憶域を返す |
| `set` | `Set()` | `set()` | `set()` | `set()` | `set()` | 添字の値を書き換える |
| `to_longs` | `ToLongs()` | `toLongs()` | `toLongs()` | `to_longs()` | — |  |
| `values_per_long` | `ValuesPerLong` | `valuesPerLong()` | `valuesPerLong()` | `values_per_long` | `values_per_long()` | 1 つの i64 に入るエントリ数 |

<!-- generated:end -->

この表は実装から生成している。手で直さず、
`python3 spec/tools/check_docs_sync.py --write` で更新すること。

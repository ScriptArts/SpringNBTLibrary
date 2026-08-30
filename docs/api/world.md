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
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
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
| `overworld` | `Overworld` | `OVERWORLD` | `OVERWORLD` | `OVERWORLD` | `OVERWORLD` | オーバーワールドの次元ID |
| `poi_folder` | `PoiFolder` | `poiFolder()` | `poiFolder()` | `poi_folder()` | `poi_folder()` |  |
| `region_folder` | `RegionFolder` | `regionFolder()` | `regionFolder()` | `region_folder()` | `region_folder()` |  |
| `save_chunk` | `SaveChunk()` | `saveChunk()` | `saveChunk()` | `save_chunk()` | `save_chunk()` | チャンクを書き戻す |
| `set_biome` | `SetBiome()` | `setBiome()` | `setBiome()` | `set_biome()` | `set_biome()` |  |
| `set_block` | `SetBlock()` | `setBlock()` | `setBlock()` | `set_block()` | `set_block()` | 絶対座標でブロックを設定する |
| `the_end` | `TheEnd` | `THE_END` | `THE_END` | `THE_END` | `THE_END` | エンドの次元ID |
| `the_nether` | `TheNether` | `THE_NETHER` | `THE_NETHER` | `THE_NETHER` | `THE_NETHER` | ネザーの次元ID |
| **Chunk** | `Chunk` | `Chunk` | `Chunk` | `Chunk` | `Chunk` | チャンク 1 つ分 |
| `biome_index` | `BiomeIndex()` | `biomeIndex()` | `biomeIndex()` | `biome_index()` | `biome_index()` |  |
| `biomes_per_section` | `BiomesPerSection` | `BIOMES_PER_SECTION` | `BIOMES_PER_SECTION` | `BIOMES_PER_SECTION` | `BIOMES_PER_SECTION` | セクション 1 つに入るバイオームのエントリ数（4×4×4 単位） |
| `block_index` | `BlockIndex()` | `blockIndex()` | `blockIndex()` | `block_index()` | `block_index()` | セクション内のブロック添字 |
| `blocks_per_section` | `BlocksPerSection` | `BLOCKS_PER_SECTION` | `BLOCKS_PER_SECTION` | `BLOCKS_PER_SECTION` | `BLOCKS_PER_SECTION` | セクション 1 つに入るブロック数 |
| `clear_heightmaps` | `ClearHeightmaps()` | `clearHeightmaps()` | `clearHeightmaps()` | `clear_heightmaps()` | `clear_heightmaps()` | Heightmaps を削除し、Minecraft に再計算させる |
| `compact` | `Compact()` | `compact()` | `compact()` | `compact()` | `compact()` | 使われていないパレット要素を全セクションから取り除く |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `data_version` | `DataVersion` | `dataVersion()` | `dataVersion()` | `data_version` | `data_version()` | チャンク構造のバージョン |
| `from_nbt` | `FromNbt()` | `fromNbt()` | `fromNbt()` | `from_nbt()` | `from_nbt()` | NBT からチャンクを読む |
| `get_biome` | `GetBiome()` | `getBiome()` | `getBiome()` | `get_biome()` | `get_biome()` | バイオームを取得する |
| `get_block` | `GetBlock()` | `getBlock()` | `getBlock()` | `get_block()` | `get_block()` | ブロックを取得する |
| `invalidate_lighting` | `InvalidateLighting()` | `invalidateLighting()` | `invalidateLighting()` | `invalidate_lighting()` | `invalidate_lighting()` | isLightOn を 0 にし、光源の再計算を促す |
| `is_fully_generated` | `IsFullyGenerated` | `isFullyGenerated()` | `isFullyGenerated()` | `is_fully_generated` | `is_fully_generated()` |  |
| `is_modified` | `IsModified` | `isModified()` | `isModified()` | `is_modified` | `is_modified()` | このチャンクに変更が加わったか |
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
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
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
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| **VersionMismatchAction** | `VersionMismatchAction` | `VersionMismatchAction` | `VersionMismatchAction` | `VersionMismatchAction` | `VersionMismatchAction` | DataVersion が対象と違ったときの動作 |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `error` | `Error` | `ERROR` | `Error` | `ERROR` | `Error` | UnsupportedDataVersion の例外にする |
| `ignore` | `Ignore` | `IGNORE` | `Ignore` | `IGNORE` | `Ignore` | 何もしない |
| `warn` | `Warn` | `WARN` | `Warn` | `WARN` | `Warn` |  |
| **BlockState** | `BlockState` | `BlockState` | `BlockState` | `BlockState` | `BlockState` | ブロックの状態 |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `from_nbt` | `FromNbt()` | `fromNbt()` | `fromNbt()` | `from_nbt()` | `from_nbt()` | パレット要素の NBT から作る |
| `name` | `Name` | `name()` | `name()` | `name` | `name()` | ブロックID（名前空間つき） |
| `of` | `Of()` | `of()` | `of()` | `of()` | `of()` |  |
| `parse` | `Parse()` | `parse()` | `parse()` | `parse()` | `parse()` | minecraft:oak_stairs[facing=north,half=top] 形式の文字列から作る |
| `properties` | `Properties` | `properties()` | `properties()` | `properties` | `properties()` |  |
| `property` | `Property()` | `property()` | `property()` | `property()` | `property()` |  |
| `to_nbt` | `ToNbt()` | `toNbt()` | `toNbt()` | `to_nbt()` | `to_nbt()` | パレット要素の NBT へ変換する |
| `to_string` | `ToString()` | `toString()` | `toString()` | `==` | `to_string()` | minecraft:oak_stairs[facing=north,half=top] 形式の文字列を返す |
| `with` | `With()` | `with()` | `with()` | `with_property()` | `with()` | プロパティを 1 つ差し替えた新しい状態を返す |
| **BlockPos** | `BlockPos` | `BlockPos` | `BlockPos` | `BlockPos` | `BlockPos` | ブロックの絶対座標 |
| `chunk_pos` | `ChunkPos` | `chunkPos()` | `chunkPos()` | `chunk_pos` | `chunk_pos()` | この座標を含むチャンクの座標 |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `local_x` | `LocalX` | `localX()` | `localX()` | `local_x` | `local_x()` | チャンク内でのX位置 (0..15) |
| `local_z` | `LocalZ` | `localZ()` | `localZ()` | `local_z` | `local_z()` | チャンク内でのZ位置 (0..15) |
| `offset` | `Offset()` | `offset()` | `offset()` | `offset()` | `offset()` | 各軸へずらした座標を返す |
| `to_string` | `ToString()` | `toString()` | `toString()` | `==` | `to_string()` |  |
| `x` | `X` | `x()` | `x` | `x` | `x` | X座標 |
| `y` | `Y` | `y()` | `y` | `y` | `y` | Y座標 |
| `z` | `Z` | `z()` | `z` | `z` | `z` | Z座標 |
| **Cuboid** | `Cuboid` | `Cuboid` | `Cuboid` | `Cuboid` | `Cuboid` | ブロック座標の直方体な範囲 |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `max_x` | `MaxX` | `maxX()` | `maxX` | `max_x` | `max_x` | X の最大値（含む） |
| `max_y` | `MaxY` | `maxY()` | `maxY` | `max_y` | `max_y` | Y の最大値（含む） |
| `max_z` | `MaxZ` | `maxZ()` | `maxZ` | `max_z` | `max_z` | Z の最大値（含む） |
| `min_x` | `MinX` | `minX()` | `minX` | `min_x` | `min_x` | X の最小値 |
| `min_y` | `MinY` | `minY()` | `minY` | `min_y` | `min_y` | Y の最小値 |
| `min_z` | `MinZ` | `minZ()` | `minZ` | `min_z` | `min_z` | Z の最小値 |
| `of` | `Of()` | `of()` | `of()` | `of()` | `of()` | 両端の座標から作る |
| `positions` | `Positions()` | `positions()` | `positions()` | `positions()` | `positions()` | 範囲内の座標を順に返す |
| `size_x` | `SizeX` | `sizeX()` | `sizeX()` | `size_x` | `size_x()` | X 方向の長さ |
| `size_y` | `SizeY` | `sizeY()` | `sizeY()` | `size_y` | `size_y()` | Y 方向の長さ |
| `size_z` | `SizeZ` | `sizeZ()` | `sizeZ()` | `size_z` | `size_z()` | Z 方向の長さ |
| `to_string` | `ToString()` | `toString()` | `toString()` | `==` | `to_string()` |  |
| `volume` | `Volume` | `volume()` | `volume()` | `volume` | `volume()` | 含まれるブロックの個数 |
| **PalettedContainer** | `PalettedContainer` | `PalettedContainer` | `PalettedContainer` | `PalettedContainer` | `PalettedContainer` | パレットとビットストレージの組 |
| `bits_per_entry` | `BitsPerEntry` | `bitsPerEntry()` | `bitsPerEntry()` | `bits_per_entry` | `bits_per_entry()` |  |
| `ceil_log2` | `CeilLog2()` | `ceilLog2()` | `ceilLog2()` | `ceil_log2()` | `ceil_log2()` |  |
| `compact` | `Compact()` | `compact()` | `compact()` | `compact()` | `compact()` | どのエントリからも参照されていないパレット要素を取り除き、添字を振り直す |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
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
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `create` | `Create()` | `create()` | `create()` | `create()` | `create()` | すべてゼロで初期化した記憶域を作る |
| `entry_count` | `EntryCount` | `entryCount()` | `entryCount()` | `entry_count` | `entry_count()` |  |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `from_longs` | `FromLongs()` | `fromLongs()` | `fromLongs()` | `from_longs()` | `from_longs()` | 既存の i64 配列から作る |
| `get` | `Get()` | `get()` | `get()` | `get()` | `get()` | 添字の値を取り出す |
| `into_longs` | — | — | — | — | `into_longs()` |  |
| `long_count` | `LongCount()` | `longCount()` | `longCount()` | `long_count()` | `long_count()` | 必要な i64 の個数を求める |
| `resize` | `Resize()` | `resize()` | `resize()` | `resize()` | `resize()` | 別のビット幅へ詰め直した新しい記憶域を返す |
| `set` | `Set()` | `set()` | `set()` | `set()` | `set()` | 添字の値を書き換える |
| `to_longs` | `ToLongs()` | `toLongs()` | `toLongs()` | `to_longs()` | `to_longs()` |  |
| `values_per_long` | `ValuesPerLong` | `valuesPerLong()` | `valuesPerLong()` | `values_per_long` | `values_per_long()` | 1 つの i64 に入るエントリ数 |

<!-- generated:end -->

この表は実装から生成している。手で直さず、
`python3 spec/tools/check_docs_sync.py --write` で更新すること。

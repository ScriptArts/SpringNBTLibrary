# 40. ワールドのディレクトリ構成

Java版のセーブデータのディレクトリ構成と `level.dat` の扱い。

> **この章は Java版 26.2 の実データを走査して確認した内容に基づく。**
> 1.21.x までの構成（`region/` が直下、`DIM-1` / `DIM1`、`playerdata/`）とは**大きく異なる**。
> Minecraft Wiki の記述は 1.21.x 時点のものが残っているため、そのままでは使えない。
> 検証方法は [90 適合性](90-conformance.md) の「実ワールド走査」を参照。

---

## 1. ディレクトリ構成

```
<ワールド名>/
├─ level.dat                  gzip 圧縮された NBT。ワールドの基本情報のみ
├─ level.dat_old              1つ前の level.dat（バックアップ）
├─ session.lock               起動中のロック
├─ icon.png
├─ datapacks/
│
├─ data/minecraft/            ★ワールド単位のデータ。用途ごとに別ファイル
│   ├─ game_rules.dat
│   ├─ weather.dat
│   ├─ world_clocks.dat
│   ├─ world_gen_settings.dat
│   ├─ random_sequences.dat
│   ├─ scheduled_events.dat
│   ├─ stopwatches.dat
│   ├─ scoreboard.dat
│   └─ custom_boss_events.dat
│
├─ players/                   ★プレイヤー関連（旧 playerdata/）
│   ├─ data/<uuid>.dat
│   ├─ data/<uuid>.dat_old
│   ├─ advancements/<uuid>.json
│   └─ stats/<uuid>.json
│
└─ dimensions/<名前空間>/<パス>/   ★すべての次元がここに並ぶ
    ├─ region/    r.<X>.<Z>.mca   地形
    ├─ entities/  r.<X>.<Z>.mca   エンティティ
    ├─ poi/       r.<X>.<Z>.mca   POI
    └─ data/minecraft/            次元単位のデータ
        ├─ chunk_tickets.dat
        ├─ raids.dat
        ├─ world_border.dat
        └─ ender_dragon_fight.dat   （the_end のみ）
```

### 1.1 次元の解決

**標準の3次元も `dimensions/` の下に置かれる。** 特別扱いはない。

| 次元ID | ディレクトリ |
|---|---|
| `minecraft:overworld` | `dimensions/minecraft/overworld/` |
| `minecraft:the_nether` | `dimensions/minecraft/the_nether/` |
| `minecraft:the_end` | `dimensions/minecraft/the_end/` |
| `<ns>:<path>` | `dimensions/<ns>/<path>/` |

つまり解決規則は `dimensions/<名前空間>/<パス>/` の**一本だけ**でよい。

> **1.21.x からの変更点**
>
> | 旧 | 新 |
> |---|---|
> | `<world>/region/` | `<world>/dimensions/minecraft/overworld/region/` |
> | `<world>/DIM-1/region/` | `<world>/dimensions/minecraft/the_nether/region/` |
> | `<world>/DIM1/region/` | `<world>/dimensions/minecraft/the_end/region/` |
> | `<world>/playerdata/<uuid>.dat` | `<world>/players/data/<uuid>.dat` |
> | `<world>/advancements/<uuid>.json` | `<world>/players/advancements/<uuid>.json` |
> | `<world>/stats/<uuid>.json` | `<world>/players/stats/<uuid>.json` |
> | `<world>/data/*.dat`（雑多） | `<world>/data/minecraft/<用途>.dat` に整理 |

生成されていない次元のディレクトリは存在しないことがある
（実データでは `the_nether` / `the_end` に `data/` だけがあり `region/` は無かった）。
**ディレクトリの有無で判断し、無い場合は「チャンクが 1 つも無い次元」として扱う。**

---

## 2. level.dat

Gzip 圧縮された NBT。ルートは空名の `TAG_Compound` で、`Data` キーの下に本体がある。

**26.x では大幅に軽量化されている。** ゲームルール・ワールド生成設定・天候・スコアボードなどは
`data/minecraft/` 配下の個別ファイルへ分離された。実データでは 430 バイトしかない。

| キー | 型 | 内容 |
|---|---|---|
| `Data.DataVersion` | `Int` | `4903` |
| `Data.version` | `Int` | NBT 保存形式のバージョン。`19133` |
| `Data.LevelName` | `String` | ワールド名 |
| `Data.Time` | `Long` | ワールドの経過時間（tick） |
| `Data.LastPlayed` | `Long` | 最終プレイ時刻（Unix ミリ秒） |
| `Data.GameType` | `Int` | 0=サバイバル 1=クリエイティブ 2=アドベンチャー 3=スペクテイター |
| `Data.allowCommands` | `Byte` | |
| `Data.initialized` | `Byte` | |
| `Data.WasModded` | `Byte` | |
| `Data.singleplayer_uuid` | `IntArray` | 4 要素 |
| `Data.ServerBrands` | `List<String>` | 例: `["vanilla"]` |
| `Data.difficulty_settings` | `Compound` | `difficulty`(String) / `hardcore`(Byte) / `locked`(Byte) |
| `Data.spawn` | `Compound` | `pos`(IntArray 3要素) / `pitch`(Float) / `yaw`(Float) / `dimension`(String) |
| `Data.Version` | `Compound` | `Id`(Int) / `Name`(String) / `Series`(String) / `Snapshot`(Byte) |
| `Data.DataPacks` | `Compound` | `Enabled` / `Disabled`（どちらも `List<String>`） |

> **1.21.x からの変更点**
>
> | 旧 | 新 |
> |---|---|
> | `Data.SpawnX` / `SpawnY` / `SpawnZ` / `SpawnAngle` | `Data.spawn` の compound に統合 |
> | `Data.Difficulty` / `DifficultyLocked` / `hardcore` | `Data.difficulty_settings` に統合 |
> | `Data.GameRules` | `data/minecraft/game_rules.dat` へ分離 |
> | `Data.WorldGenSettings` | `data/minecraft/world_gen_settings.dat` へ分離 |
> | `Data.raining` / `thundering` / `rainTime` / `thunderTime` | `data/minecraft/weather.dat` へ分離 |
> | `Data.DayTime` | `data/minecraft/world_clocks.dat` へ分離（次元ごとの `total_ticks`） |
> | `Data.ScheduledEvents` | `data/minecraft/scheduled_events.dat` へ分離 |
> | `Data.BorderCenterX` ほか | 次元ごとの `data/minecraft/world_border.dat` へ分離 |
> | `Data.DragonFight` | `the_end` の `data/minecraft/ender_dragon_fight.dat` へ分離 |

`Chunk` と同様、**未知のキーもすべて保持する**。

### 2.1 分離されたデータファイル

`data/minecraft/*.dat` はどれも同じ形をしている。

```
{ data: { …本体… }, DataVersion: 4903 }
```

ルートは空名の `TAG_Compound`、その直下に `data` と `DataVersion` が並ぶ。
`level.dat` だけが大文字の `Data` である点に注意。

| ファイル | `data` の中身 |
|---|---|
| `game_rules.dat` | ゲームルール名（`minecraft:` 付きの名前空間つき）→ 値 |
| `weather.dat` | `raining` / `thundering` / `rain_time` / `thunder_time` / `clear_weather_time` |
| `world_clocks.dat` | 次元ID → `{ total_ticks: Long }` |
| `world_gen_settings.dat` | `seed`(Long) / `generate_structures` / `bonus_chest` / `dimensions` |
| `random_sequences.dat` | `salt` と、シーケンス名 → `{ source: LongArray[2] }` |
| `scheduled_events.dat` | `events`(List) |
| `stopwatches.dat` | `stopwatches`(Compound) |
| `world_border.dat`（次元ごと） | `center_x` / `center_z` / `size` / `damage_per_block` / `safe_zone` / `warning_blocks` / `warning_time` / `lerp_target` / `lerp_time` |
| `chunk_tickets.dat`（次元ごと） | 読み込み維持チケット。未使用なら空 |

ゲームルール名が**名前空間つきになった**（旧 `doFireTick` → `minecraft:fire_spread_radius_around_player` のように、
名前自体が変わっているものもある）ことに注意。

### 2.2 書き込み時の安全策

`level.dat` が壊れるとワールド全体が開けなくなるため、書き込みは次の順で行う。

1. 一時ファイル `level.dat.tmp` へ書く
2. `fsync` 相当でディスクへ確定させる
3. 既存の `level.dat` を `level.dat_old` へ移す
4. `level.dat.tmp` を `level.dat` へリネームする

`players/data/<uuid>.dat` も同じく `.dat_old` を持つので、同じ手順を使う。

---

## 3. session.lock

Minecraft は起動中このファイルを排他ロックする（実データでは 3 バイトだった）。
ロックされたワールドへ書き込むとデータが壊れるため、本ライブラリは
**書き込みモードで開くときに確認する**。

- ロックを取得できない → `IO`（メッセージで「Minecraft が起動中の可能性」を示す）
- `WorldOpenOptions.ignore_session_lock = true` で明示的に無視できる（自己責任）

**ファイルの存在では判定できない。** `session.lock` は Minecraft を終了しても
残り続けるため、「ロックを取れるか」を試すしかない。

### 3.1 言語による差異

排他ロックを標準ライブラリで扱えるかは言語で分かれるため、
**この確認だけは全言語で揃わない**（→ [adr/0008](../adr/0008-session-lock.md)）。

| 言語 | 確認する | 手段 |
|---|:--:|---|
| C# | ✅ | `FileStream` を `FileShare.None` で開く |
| Java | ✅ | `FileChannel.tryLock()` |
| Python | 🔶 | `fcntl.flock`。`fcntl` の無い環境（Windows）では確認しない |
| TypeScript | ❌ | Node に移植性のあるファイルロック API が無い |
| Rust | ❌ | `std` に無い。外部クレートが要る |

確認しない言語でも `ignore_session_lock` は受け取る（API の形を揃えるため。
効果は無い）。**確認しない言語を使う場合、Minecraft が起動していないことは
呼び出し側で担保すること。**

読み取り専用で開く場合はロックを取得しないが、
起動中のワールドは書き込み途中の状態を読む可能性があることを警告する。

---

## 4. 論理API

```
World
    open(dir, options) -> World
    level() -> LevelData                     -- level.dat の内容
    save_level()
    data_file(name) -> Option<NbtCompound>   -- data/minecraft/<name>.dat
    dimension(dimension_id) -> Dimension
    dimensions() -> Iterator<DimensionId>    -- 存在するものだけ
    players() -> Iterator<Uuid>
    player(uuid) -> Option<NbtCompound>
    close()

Dimension
    id() -> DimensionId
    region_folder() -> Option<RegionFolder>  -- region/
    entity_folder() -> Option<RegionFolder>  -- entities/
    poi_folder() -> Option<RegionFolder>     -- poi/
    data_file(name) -> Option<NbtCompound>   -- data/minecraft/<name>.dat
    chunk(chunk_x, chunk_z) -> Option<Chunk>
    save_chunk(chunk)
    get_block(x, y, z) -> Option<BlockState>
    set_block(x, y, z, state)
    get_biome(x, y, z) -> Option<String>
    set_biome(x, y, z, biome)
```

`get_block` / `set_block` は**絶対ワールド座標**を取り、リージョン・チャンク・セクションを
内部で解決する。存在しないチャンクに対する `get_block` は `None`、
`set_block` は `INVALID_ARGUMENT`（チャンクを生成する機能は持たない）。

`region_folder()` などが `Option` を返すのは、
**生成されていない次元にはディレクトリ自体が無い**ため。

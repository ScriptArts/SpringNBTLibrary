# 過去バージョンへの対応の実装計画

> **エージェント向け:** この計画は、superpowers:subagent-driven-development（推奨）かsuperpowers:executing-plansで1タスクずつ実装する。手順は`- [ ]`のチェックボックスで追う。

**目的:** 1.13以降のJava版のワールドを、読んだ形式のまま読み書きできるようにする。

**作り:** チャンクの形式の世代（C1〜C5）とワールドの構成の世代（L1 / L2）を、内部の表で持つ。世代はDataVersionから引き、世代による分岐はその表と、表を使う読み書きの部品の中だけに書く。公開APIは保ち、足すのは数値のバイオームIDの読み書き、世代を指定するオプション、`BlockState`のDataVersion指定の変換だけにする。

**技術:** C# / Java / TypeScript / Python / Rustの5言語。テストベクタは`spec/tools/build_testdata.py`で作り、`spec/run-conformance.sh`で5言語の出力を突き合わせる。

**設計:** [過去バージョンへの対応の設計](legacy-version-support-design.md)。実装する人は計画と設計の両方を読む。

## 全体の決まり

- 対象の下限は`MIN_SUPPORTED_DATA_VERSION = 1519`（1.13の正式版）。段階1と2の間は`2844`にしておき、タスク6で`1519`に下げる
- `TARGET_DATA_VERSION`は`5023`のまま変えない
- チャンクの世代の境界: C1 `1519`、C2 `2203`、C3 `2529`、C4 `2844`、C5 `5006`。構成の世代の境界: L1 `1519`、L2 `4786`
- `DataVersion`は書き換えない。書き戻す形式は読んだときの世代で決まる
- 下限との比較は指定の有無に関わらず、チャンク自身の`DataVersion`で行う。指定できる値は`1519`以上で、それ未満は`INVALID_ARGUMENT`
- 新しく書くコードと書き換えるコードには、利用者のコーディング規約を当てる。三項演算子、`?.`、`??` / `??=`、`&&` / `||`の短絡での呼び出しは使わず、if/elseで書く。要らないelseは書かない。読みやすくなるところではif / forの前後に空行を入れる。条件文・ループ・主なメソッド呼び出しに日本語のコメントを付ける。`spec/tools/check_comments.py`が通ること
- 日本語の文の中で、英単語やコードの名前の前後に半角スペースを入れない。コメントやドキュメントに書く日本語はyomiyasuスキルで推敲する。プロジェクトの規約（コメントの句点の有無など）と食い違えば、プロジェクトの規約を優先する
- 公開APIの名前は[0002](../adr/0002-idiomatic-naming.md)に従って各言語の書き方にする。5言語で論理名がそろっていることを`spec/tools/check_docs_sync.py`で確かめ、API対応表は`python3 spec/tools/check_docs_sync.py --write`で作り直す
- 内部の型（世代の表など）は公開しない。C#は`internal`、Javaはパッケージ内に閉じ、TypeScriptは`index.ts`から出さず、Pythonは先頭に`_`を付けたモジュール、Rustは`pub(crate)`にする
- 各タスクの終わりに、5言語の単体テスト、適合性検証、`check_comments.py` / `check_docs_sync.py` / `check_links.py`が通ること
- コミットは日本語で書き、利用者の指示が無いのでブランチ`research/legacy-version-support`にだけ積む。マージとリリースはしない

## 見落としやすいところ

1. 26.3のワールドに26.2のチャンクが残っている。各チャンクを読んだときの形式（C4 / C5）で書き戻す（タスク2のテスト）
2. 世代を指定で上書きして、実際の構造と合わない。黙って空のチャンクとして読まず、`MALFORMED_DATA`にする（タスク2のテスト）
3. 指定で上書きしても、下限より古いチャンクの書き戻しは`UNSUPPORTED_DATA_VERSION`で止まる（タスク2のテスト）
4. 64bitの境目をまたぐ詰め方で、パレットが育ってビット幅が4から5に変わる。またいだ値が正しく読み書きできる（タスク4のテスト）
5. 1.17以前のチャンクで`set_block`したとき、その位置の`Level.TileEntities` / `Level.TileTicks` / `Level.LiquidTicks`も取り除く（タスク5のテスト）

---

## ファイルの構成

各言語で同じ役割のファイルを足す・直す。パスはPythonで示し、ほかの言語は同じ場所の対応するファイルにする。

| 役割 | Python | ほかの言語 |
|---|---|---|
| チャンクの世代の表と、世代ごとの読み書き（新規） | `python/src/spring_nbt_library/world/_chunk_format.py` | C# `World/ChunkFormat.cs`、Java `world/ChunkFormat.java`、TS `world/chunkFormat.ts`、Rust `world/chunk_format.rs` |
| ワールドの構成の世代（新規） | `python/src/spring_nbt_library/world/_world_layout.py` | C# `World/WorldLayout.cs`、Java `world/WorldLayout.java`、TS `world/worldLayout.ts`、Rust `world/world_layout.rs` |
| ブロック状態 | `world/block_state.py` | 各言語の`BlockState` |
| ビット詰め | `world/bit_storage.py` | 各言語の`BitStorage` |
| パレット付きコンテナ | `world/paletted_container.py` | 各言語の`PalettedContainer` |
| チャンクとセクション | `world/chunk.py` | C# `Chunk.cs` / `ChunkSection.cs`、Java `Chunk.java` / `ChunkSection.java` / `ChunkReadOptions.java` |
| ワールド・次元・`level.dat` | `world/minecraft_world.py` | C# `MinecraftWorld.cs` / `Dimension.cs`、Java `MinecraftWorld.java` / `Dimension.java` / `LevelData.java` / `WorldOpenOptions.java` |
| 定数 | `__init__.py` | C# `SpringNbt.cs`、Java `SpringNbt.java`、TS `index.ts`、Rust `lib.rs` |
| 適合性ツール | `conformance.py` | C# `tests/SpringNBTLibrary.Conformance/ChunkReport.cs`、Java `conformance/ChunkReport.java`、TS `src/conformance.ts`、Rust `examples/conformance.rs` |
| 単体テスト | `python/tests/test_world.py` | C# `WorldTests.cs`、Java `WorldTest.java`、TS `world.test.ts`、Rust `tests/world.rs` |

---

## 段階1: 世代を選ぶ作りと、1.18〜26.2のチャンク

### Task 1: `BlockState`のDataVersion指定の変換

**ファイル:** 各言語の`BlockState`と単体テスト

**インタフェース:**
- 作るもの: `BlockState.from_nbt_for_data_version(tag: NbtTag, data_version: int) -> BlockState`、`BlockState.to_nbt_for_data_version(data_version: int) -> NbtTag`（論理名。各言語の書き方にする）
- いまの`from_nbt(tag)` / `to_nbt()`は`TARGET_DATA_VERSION`を渡したものと同じ動きにする

- [ ] **手順1: 失敗するテストを書く**（5言語。名前はPythonで示す）
  - `test_block_state_v2844_reads_name_properties`: `{Name: "minecraft:oak_stairs", Properties: {facing: "north"}}`を`2844`で読むと`minecraft:oak_stairs[facing=north]`
  - `test_block_state_v2844_rejects_id`: `{id: "minecraft:stone"}`を`2844`で読むと`MALFORMED_DATA`
  - `test_block_state_v2844_rejects_string`: 文字列`"minecraft:stone"`を`2844`で読むと`UNEXPECTED_TAG_TYPE`
  - `test_block_state_v2844_writes_name_properties`: `minecraft:stone`を`2844`で書くと`{Name: "minecraft:stone"}`（`Properties`は無い）。`minecraft:oak_stairs[half=top,facing=north]`は`{Name, Properties: {facing, half}}`で、プロパティは名前の昇順
  - `test_block_state_v5006_matches_from_nbt`: `5006`と`5023`で読み書きした結果がいまの`from_nbt` / `to_nbt`と同じ
  - `test_block_state_rejects_data_version_below_1519`: `1518`を渡すと`INVALID_ARGUMENT`
- [ ] **手順2: テストが失敗することを確かめる**（各言語のテストを流し、上のテストが落ちる）
- [ ] **手順3: 実装する。** `1519`以上`5006`未満は`{Name, Properties}`、`5006`以上はいまの形式。このタスクで`_chunk_format`を作り、境界の定数`PALETTE_ID_FORMAT_DATA_VERSION = 5006`を置く。タスク2で同じファイルに世代の表を足す
- [ ] **手順4: 5言語のテストと`check_docs_sync.py --write`を流し、通ることを確かめる**
- [ ] **手順5: コミットする**（`BlockStateをDataVersionを指定して読み書きできるようにする`）

### Task 2: チャンクの世代の表とC4 / C5の読み書き

**ファイル:** 各言語の`_chunk_format`（新規）、`chunk`、`paletted_container`、定数、適合性ツール、`build_testdata.py`、単体テスト

**インタフェース:**
- 使うもの: タスク1の`BlockState.from_nbt_for_data_version` / `to_nbt_for_data_version`
- 作るもの（内部）: `ChunkFormat`。`ChunkFormat.for_data_version(data_version: int) -> ChunkFormat | None`（`1519`未満で`None`）。項目は次のとおり
  - `min_data_version: int`
  - `wrapped_in_level: bool`（C1〜C3で真）
  - `sections_key: str`（`"Sections"` / `"sections"`）
  - `palette_data_version: int`（パレットの要素の変換に渡す値。C1〜C4は`2844`、C5は`5006`）
  - `spanning_bit_storage: bool`（C1とC2で真）
  - `biome_storage: PALETTED | IDS_2D | IDS_3D`
  - `block_data_keys: (str, str, str)`（C1〜C3は`TileEntities` / `TileTicks` / `LiquidTicks`、C4以降は`block_entities` / `block_ticks` / `fluid_ticks`）
- 作るもの（公開）: `ChunkReadOptions.format_data_version: int | None`（既定は`None`で自動の判別）、`Chunk.format_data_version -> int`（世代を選ぶのに使った値。指定が無ければ`data_version`）

この段階では表にC4とC5だけを入れる。C1〜C3はタスク5と6で足す。

- [ ] **手順1: 失敗するテストを書く**（5言語）
  - `test_chunk_v4903_round_trip`: 26.2の形式（`DataVersion 4903`、`{Name, Properties}`のパレット）のチャンクを読み、`get_block`で状態が読める。無変更で`to_nbt`した結果が元と一致する
  - `test_chunk_v4903_set_block_writes_name_properties`: 26.2のチャンクに`minecraft:oak_stairs[facing=north]`を置くと、パレットに`{Name, Properties}`で入る。`DataVersion`は`4903`のまま
  - `test_chunk_mixed_formats`: `DataVersion 4903`と`5023`のチャンクを同じ手順で編集すると、前者は`{Name, Properties}`、後者は文字列か`{id, properties}`で書き出される
  - `test_chunk_override_mismatch_is_malformed`: ルートに`Level`のある合成チャンクを`format_data_version=5023`で読むと`MALFORMED_DATA`。ルートの直下に`sections`がある`5023`のチャンクを、C1〜C3を指す値で読む試験はタスク5で足す
  - `test_chunk_override_cannot_bypass_write_guard`: `DataVersion 1400`のチャンクを`format_data_version=5023`で読み、`allow_foreign_data_version`なしで`to_nbt`すると`UNSUPPORTED_DATA_VERSION`
  - `test_chunk_override_below_1519_is_invalid`: `format_data_version=1518`は`INVALID_ARGUMENT`
  - `test_chunk_below_lower_bound_is_raw_only`: `DataVersion 1400`のチャンクで`get_block`は`UNSUPPORTED_DATA_VERSION`。`allow_foreign_data_version`ありの`to_nbt`は読んだNBTと一致する
  - `test_chunk_format_data_version`: 指定が無ければ`data_version`と同じ値、指定すればその値
- [ ] **手順2: テストが失敗することを確かめる**
- [ ] **手順3: 実装する。**
  - `Chunk.from_nbt`は`ChunkFormat`を引き、`wrapped_in_level`と`Level`の有無が食い違えば`MALFORMED_DATA`にする
  - `ChunkSection`はC4 / C5で、いまと同じく`block_states` / `biomes`を読む。パレットの要素の変換は`palette_data_version`で`BlockState`に渡す
  - `get_block` / `set_block`は`palette_data_version`で`BlockState`を変換する
  - `1519`未満のチャンク（`ChunkFormat`が無い）は、セクションを解釈せずに元のNBTだけを持つ。ブロックとバイオームのAPIは`UNSUPPORTED_DATA_VERSION`。`x` / `z`は`Level`があればその中、無ければルートから読む
  - `MIN_SUPPORTED_DATA_VERSION`を`2844`にする
- [ ] **手順4: テストベクタを直す。** `build_testdata.py`の`world/palette_old_format`は正常に読める26.2のベクタとして説明を直し、`expect_error`を外す。新しく`world/v4903_edit`（26.2のチャンク。`chunk-edit`で`{Name, Properties}`が書き出される）を足す。`python3 spec/tools/build_testdata.py`のあと`./spec/run-conformance.sh --generate-expect`で期待値を作り直す
- [ ] **手順5: 5言語のテスト、適合性検証、3つの検査を流し、通ることを確かめる**
- [ ] **手順6: コミットする**（`チャンクの形式を世代の表で選び、26.2までの形式も読み書きする`）

---

## 段階2: 26.1より前のワールドの構成と`level.dat`

### Task 3: L1の構成と`level.dat`

**ファイル:** 各言語の`_world_layout`（新規）、`minecraft_world`、単体テスト

**インタフェース:**
- 作るもの（内部）: `WorldLayout.for_data_version(data_version: int) -> WorldLayout`。項目は次元の場所の解決、プレイヤーのフォルダ（`playerdata` / `players/data`）、データファイルの場所（`data/<名前>.dat` / `data/minecraft/<名前>.dat`）、`level.dat`の取得子の読み方
- 作るもの（公開）: `WorldOpenOptions.format_data_version: int | None`。構成の世代と、そのワールドから読むすべてのチャンクの世代に効く。`chunk_read.format_data_version`より優先する

- [ ] **手順1: 失敗するテストを書く**（5言語。一時フォルダに合成のワールドを作る）
  - `test_world_l1_dimensions`: `level.dat`の`DataVersion`が`3953`で、直下に`region/`、`DIM-1/region/`、`DIM1/region/`、`dimensions/mymap/arena/region/`がある。`dimension_ids`は`minecraft:overworld`、`minecraft:the_nether`、`minecraft:the_end`、`mymap:arena`で、`dimension("minecraft:the_nether")`は`DIM-1/`を読む
  - `test_world_l1_players`: `playerdata/<uuid>.dat`が`player_ids`と`player`で読める
  - `test_world_l1_data_file`: `data/scoreboard.dat`が`data_file("scoreboard")`で読める。`DIM-1/data/raids_nether.dat`が`dimension("minecraft:the_nether").data_file("raids_nether")`で読める
  - `test_level_data_l1_getters`: `SpawnX=10, SpawnY=64, SpawnZ=-5`、`Difficulty=2`、`hardcore=1`から、`spawn_pos`は`[10, 64, -5]`、`difficulty`は`normal`、`is_hardcore`は真。`spawn_dimension`は`UNSUPPORTED_FEATURE`。`Difficulty`が0〜3の外なら`MALFORMED_DATA`
  - `test_world_l2_unchanged`: いまの26.xの合成ワールドの試験がそのまま通る
  - `test_world_override_layout`: `level.dat`が`5023`でも、`format_data_version=3953`で開くとL1として読む。`1518`は`INVALID_ARGUMENT`
- [ ] **手順2: テストが失敗することを確かめる**
- [ ] **手順3: 実装する。** `Difficulty`は0 `peaceful`、1 `easy`、2 `normal`、3 `hard`に直す。`MinecraftWorld`と`Dimension`は場所の解決を`WorldLayout`に任せ、ほかの場所でDataVersionを比べない
- [ ] **手順4: 5言語のテストと3つの検査を流し、通ることを確かめる**
- [ ] **手順5: コミットする**（`26.1より前のワールドの構成とlevel.datを読み書きする`）

---

## 段階3: 1.13〜1.17のチャンク

### Task 4: 64bitの境目をまたぐビット詰め

**ファイル:** 各言語の`bit_storage`、`paletted_container`、単体テスト

**インタフェース:**
- 作るもの（内部）: `BitStorage`に`spanning: bool`を持たせる。`long_count(bits, entry_count, spanning)`は、またぐなら`ceil(entry_count * bits / 64)`、またがないならいまの式
- 作るもの（内部）: `PalettedContainer.from_parts(palette: list[NbtTag], data: list[int] | None, entry_count: int, min_bits: int, spanning: bool, always_has_data: bool, lenient_bit_storage: bool)`と、パレットと`data`を返す`to_parts()`。`always_has_data`が真なら、パレットが1要素でも`max(min_bits, ceil_log2(パレットの長さ))`のビット幅で`data`を書く

またぐ詰め方の取り出しと書き込みは次のとおり。

```
bit_index = index * bits
long_index = bit_index >> 6
offset = bit_index & 63
value = data[long_index] >>> offset
if offset + bits > 64:
    value |= data[long_index + 1] << (64 - offset)
value &= (1 << bits) - 1
```

- [ ] **手順1: 失敗するテストを書く**（5言語）
  - `test_bit_storage_spanning_known_layout`: ビット幅5、要素数4096で、添字12（ビット60〜64）に`0b10111`を書くと、`data[0]`の上位4bitが`0b0111`、`data[1]`の最下位bitが`1`。読み戻すと`0b10111`
  - `test_bit_storage_spanning_long_count`: ビット幅5、要素数4096で`long_count`が`320`。ビット幅4で`256`
  - `test_paletted_container_spanning_grows_4_to_5`: またぐ詰め方のコンテナに17種類目の値を入れるとビット幅が5になり、全4096要素が元の値のまま読める
  - `test_paletted_container_always_has_data`: `always_has_data`が真で1要素のパレットなら、`to_parts()`の`data`はビット幅4の長さ（またがないなら256、またぐなら256）
- [ ] **手順2: テストが失敗することを確かめる**
- [ ] **手順3: 実装する**
- [ ] **手順4: 5言語のテストを流し、通ることを確かめる**
- [ ] **手順5: コミットする**（`64bitの境目をまたぐビット詰めを扱う`）

### Task 5: C3（1.16〜1.17）のチャンクと数値のバイオームID

**ファイル:** 各言語の`_chunk_format`、`chunk`、適合性ツール、`build_testdata.py`、単体テスト

**インタフェース:**
- 使うもの: タスク2の`ChunkFormat`、タスク4の`PalettedContainer.from_parts` / `to_parts`
- 作るもの（公開）: `Chunk.get_biome_id(x: int, y: int, z: int) -> int | None`、`Chunk.set_biome_id(x: int, y: int, z: int, biome_id: int)`

C3では次のとおりに扱う。

- チャンクの本体は`Level`。`xPos` / `zPos` / `Status` / `Heightmaps` / `isLightOn` / `TileEntities` / `TileTicks` / `LiquidTicks` / `Biomes`は`Level`の中
- セクションは`Level.Sections`の各要素で、`Y`（Byte）、`Palette`（`{Name, Properties}`のリスト）、`BlockStates`（またがない詰め方、最小のビット幅4、`always_has_data`は真）。`Palette`の無いセクションはブロックを持たない
- `min_section_y`は`0`
- バイオームは`Level.Biomes`の`int[1024]`。添字は`((y >> 2) & 63) * 16 + (z >> 2) * 4 + (x >> 2)`。`y`が0〜255の外なら`get_biome_id`は`None`、`set_biome_id`は`INVALID_ARGUMENT`。`Biomes`が無ければ`get_biome_id`は`None`、`set_biome_id`は`INVALID_ARGUMENT`
- `get_biome` / `set_biome`は`UNSUPPORTED_FEATURE`。C4以降の`get_biome_id` / `set_biome_id`も`UNSUPPORTED_FEATURE`
- `is_fully_generated`は、`Status`から`minecraft:`を外した値が`full`なら真（C2以降すべて同じ判定にする）
- `invalidate_lighting`は、本体に`isLightOn`があれば`0`にし、無ければ`UNSUPPORTED_FEATURE`
- `clear_heightmaps`は`Level.Heightmaps`を消す

- [ ] **手順1: 失敗するテストを書く**（5言語）
  - `test_chunk_v2586_round_trip`: 1.16.5の形式（`DataVersion 2586`）の合成チャンクを読み、無変更で書き戻すと元と一致する
  - `test_chunk_v2586_set_block_removes_level_block_data`: `set_block`した位置の`Level.TileEntities` / `Level.TileTicks` / `Level.LiquidTicks`の要素が消え、ほかの位置の要素は残る
  - `test_chunk_v2586_biome_ids`: `get_biome_id(0, 0, 0)`が`Biomes[0]`、`get_biome_id(5, 70, 9)`が`Biomes[17 * 16 + 2 * 4 + 1]`。`set_biome_id`で書いた値が`Level.Biomes`に入る
  - `test_chunk_v2586_get_biome_unsupported`: `get_biome`が`UNSUPPORTED_FEATURE`。C5のチャンクの`get_biome_id`も`UNSUPPORTED_FEATURE`
  - `test_chunk_v2586_lighting_and_heightmaps`: `invalidate_lighting`で`Level.isLightOn`が0、`clear_heightmaps`で`Level.Heightmaps`が消える。`isLightOn`の無いチャンクの`invalidate_lighting`は`UNSUPPORTED_FEATURE`
  - `test_chunk_override_root_sections_as_c3_is_malformed`: ルートの直下に`sections`がある`5023`のチャンクを`format_data_version=2586`で読むと`MALFORMED_DATA`
- [ ] **手順2: テストが失敗することを確かめる**
- [ ] **手順3: 実装する。** 表にC3を足す
- [ ] **手順4: 適合性ツールを直す。** `chunk-report`は、最初の`get_biome`が`UNSUPPORTED_FEATURE`ならそのチャンクを数値のバイオームIDとして扱い、同じ4ブロックおきの走査を`get_biome_id`で行って`biome-id <ID> <数>`の行をIDの昇順で出す。`chunk-edit`は、同じ判定で`set_biome`の代わりに`set_biome_id(0, base_y, 0, 2)`と`set_biome_id(8, base_y + 8, 8, 21)`を呼ぶ
- [ ] **手順5: テストベクタを足す。** `world/v2586_level`（C3。パレット5種類、`TileEntities`あり、`Level.isLightOn`あり、`Status`は`full`）を作り、期待値を作り直す
- [ ] **手順6: 5言語のテスト、適合性検証、3つの検査を流し、通ることを確かめる**
- [ ] **手順7: コミットする**（`1.16〜1.17のチャンクと数値のバイオームIDを扱う`）

### Task 6: C1 / C2（1.13〜1.15）のチャンクと下限の引き下げ

**ファイル:** タスク5と同じ

**インタフェース:**
- 使うもの: タスク4のまたぐ詰め方、タスク5の数値のバイオームID

C2はC3と同じで、ビット詰めがまたぐ。C1はC2と同じで、バイオームが`int[256]`（添字は`z * 16 + x`、`y`は見ない）。
C1の`is_fully_generated`は`full`に加えて1.13の`postprocessed`も生成済みとみなす。値はタスク7で実データと照らし合わせる。

- [ ] **手順1: 失敗するテストを書く**（5言語）
  - `test_chunk_v2230_spanning_round_trip`: 1.15.2の形式（`DataVersion 2230`、またぐ詰め方、パレット17種類でビット幅5）の合成チャンクを読み、全ブロックが元の添字どおりに読める。無変更で書き戻すと元と一致する
  - `test_chunk_v1976_biome_ids_2d`: 1.14.4の形式（`DataVersion 1976`、`int[256]`）で、`get_biome_id(3, 0, 7)`と`get_biome_id(3, 200, 7)`がどちらも`Biomes[7 * 16 + 3]`
  - `test_chunk_v1519_without_is_light_on`: `isLightOn`の無い1.13の形式の`invalidate_lighting`が`UNSUPPORTED_FEATURE`
  - `test_min_supported_data_version_is_1519`: `MIN_SUPPORTED_DATA_VERSION`が`1519`。`1518`のチャンクは読み込みで警告になる
- [ ] **手順2: テストが失敗することを確かめる**
- [ ] **手順3: 実装する。** 表にC1とC2を足し、`MIN_SUPPORTED_DATA_VERSION`を`1519`にする
- [ ] **手順4: テストベクタを足す。** `world/v2230_spanning`（C2）、`world/v1976_biomes_2d`（C1）、`world/v1343_numeric_ids`（1.12.2の数値IDのチャンク。`chunk-report`が`UNSUPPORTED_DATA_VERSION`になる）を作り、期待値を作り直す
- [ ] **手順5: 5言語のテスト、適合性検証、3つの検査を流し、通ることを確かめる**
- [ ] **手順6: コミットする**（`1.13〜1.15のチャンクを扱い、対応の下限を1.13へ下げる`）

---

## 仕上げ

### Task 7: 実ワールドでの確認と走査ツール

**ファイル:** `spec/tools/scan_world.py`、必要に応じて各言語の`_chunk_format`と`_world_layout`

- [ ] **手順1: `scan_world.py`を直す。** Worldレイヤの検証で、L1のワールドも`MinecraftWorld`で開き、C1〜C3のチャンクは`get_biome_id`でバイオームを数える。チャンクの`DataVersion`ごとの件数と、世代ごとの件数を出す
- [ ] **手順2: 各世代の実ワールドを走査する。** 1.13〜1.17、1.18〜1.21.x、26.1〜26.3のワールドで、読み込みと無変更での書き戻しがバイト単位で一致することを確かめる。実ワールドはリポジトリに入れない
- [ ] **手順3: 走査で分かったことを実装に返す。** 少なくとも次の3つを実データで確かめ、合わなければ表とテストを直す: C1〜C3で1要素のパレットのセクションに`BlockStates`があるか、各世代の`Status`の値、`isLightOn`が入ったDataVersion
- [ ] **手順4: 5言語の結果がそろうことを確かめる。** 各世代の実ワールドから代表のチャンクを取り出して5言語の`chunk-report` / `chunk-edit`に通し、出力が一致することを確かめる
- [ ] **手順5: コミットする**（`走査ツールが過去の形式のワールドを扱う`）

### Task 8: ドキュメント

**ファイル:** `docs/adr/0011-*.md`（新規）、`docs/adr/0003-version-policy.md`、`docs/adr/0010-palette-format-26-3.md`、`docs/README.md`、`docs/spec/00-conventions.md` / `30-chunk-format.md` / `31-paletted-container.md` / `40-world-layout.md` / `90-conformance.md`、`docs/guide/04-world-and-level-dat.md` / `05-blocks-and-biomes.md` / `06-errors-and-limits.md` / `07-version-policy.md`、`docs/features.md`、`README.md`と各言語の`README.md`、`.github/release-common.md`、`CHANGELOG.md`

- [ ] **手順1: ADR 0011を書く。** 設計の8章の内容で、0003と0010の決定1を置き換える。0003と0010の状態を「0011で一部を置き換え」に直す
- [ ] **手順2: 仕様書を直す。** 30に世代ごとのチャンクの構造、31にまたぐ詰め方、40にL1の構成、00に対象の形式を書く。90の検証実績に、タスク7で走査した実ワールドを足す（ワールドを入手した経緯は書かない）
- [ ] **手順3: ガイドと案内を直す。** 「26.3以降」を「1.13以降」に直し、07のバージョンポリシーを世代の考え方で書き直す。05に数値のバイオームIDのAPIを足す。06に`UNSUPPORTED_FEATURE`の新しい使い方を足す
- [ ] **手順4: `CHANGELOG.md`に`## [Unreleased]`の節を作り、変更点と検証を書く**
- [ ] **手順5: yomiyasuで推敲し、`check_links.py` / `check_docs_sync.py`を流す**
- [ ] **手順6: コミットする**（`過去バージョンへの対応をドキュメントに書く`）

### Task 9: 全体の確認とプルリクエスト

- [ ] **手順1: リリース前の確認（`docs/contributing/release.md`の3章）をすべて流す**
- [ ] **手順2: ブランチ全体を別のレビュー役に読ませる**
- [ ] **手順3: ブランチをpushし、mainへのプルリクエストを作る。** 本文は日本語で、yomiyasuで推敲する。マージとリリースはしない

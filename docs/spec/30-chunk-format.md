# 30. チャンク形式

`.mca` 内に格納されるチャンク1つ分の NBT 構造。**ここから先はバージョン依存**である。
本書は **Java版 26.2 (DataVersion 4903)** を対象とする。

前提: [20 Anvil リージョン形式](20-anvil-region.md) / [31 パレット付きコンテナ](31-paletted-container.md)

---

## 1. ルート要素

ルートは名前なし（空文字列）の `TAG_Compound`。
下表は **Java版 26.2 の実ワールド（3,481 チャンク）を走査して確認した**内容である。
「出現」欄は、走査した full／未完成を含む全チャンクのうち何割に現れたかを示す。

| キー | 型 | 出現 | 内容 |
|---|---|---|---|
| `DataVersion` | `Int` | 全部 | チャンク構造のバージョン。26.2 は `4903` |
| `xPos` | `Int` | 全部 | 絶対チャンクX座標 |
| `zPos` | `Int` | 全部 | 絶対チャンクZ座標 |
| `yPos` | `Int` | 全部 | 最下段セクションのY位置。オーバーワールドは `-4` |
| `Status` | `String` | 全部 | 生成段階（→ 1.1） |
| `LastUpdate` | `Long` | 全部 | 最終更新のゲーム内時刻 |
| `InhabitedTime` | `Long` | 全部 | プレイヤー滞在時間（tick） |
| `sections` | `List<Compound>` | 全部 | セクション（→ 2章） |
| `block_entities` | `List<Compound>` | 全部 | ブロックエンティティ |
| `block_ticks` | `List<Compound>` | 全部 | 予約されたブロック更新 |
| `fluid_ticks` | `List<Compound>` | 全部 | 予約された液体更新 |
| `Heightmaps` | `Compound` | 全部 | 高さマップ（→ 3章） |
| `structures` | `Compound` | 全部 | `starts` と `References` を持つ |
| `PostProcessing` | `List<List>` | 全部 | 生成後処理の待ち位置 |
| `isLightOn` | `Byte` | 一部 | 光源計算済みフラグ。実データでは `minecraft:full` のチャンクにのみ現れた |
| `entities` | `List<Compound>` | 一部 | **生成途中のチャンクだけが持つ**。完成すると `entities/` のリージョンへ移る |
| `carving_mask` | `ByteArray` | 一部 | 洞窟の削り取り状況。`minecraft:carvers` 前後の段階でのみ現れる |

### 1.1 Status

実データに現れた値（生成の進行順）。

| 値 | 意味 |
|---|---|
| `minecraft:structure_starts` | 構造物の開始点だけ決まった段階 |
| `minecraft:biomes` | バイオームまで決まった段階 |
| `minecraft:carvers` | 洞窟の削り取りまで済んだ段階 |
| `minecraft:initialize_light` | 光源の初期化まで済んだ段階 |
| `minecraft:full` | 生成完了。ブロック操作の対象になるのはこれ |

**`minecraft:full` 以外のチャンクは構造が不完全**である。
`set_block` は `minecraft:full` のチャンクに対してのみ行うのが安全で、
それ以外は既定でエラーとする（`allow_incomplete_chunk` で明示的に許可できる）。

本ライブラリは**上記以外のキーも含め、読んだ要素をすべて保持する**。
未知のキーを落とさないことで、将来の追加要素があってもデータを壊さない。

`Chunk` 型は解釈済みの値（`sections` など）と、元の `NbtCompound` の両方を持ち、
書き出し時は「解釈して変更した部分だけを元の Compound に反映する」方式をとる。

---

## 2. セクション

`sections` は `List<Compound>`。1要素が 16×16×16 ブロックを表す。

| キー | 型 | 内容 |
|---|---|---|
| `Y` | `Byte` | セクションのY位置。オーバーワールドは `-5`..`20` |
| `block_states` | `Compound` | ブロック状態のパレット付きコンテナ（4096 エントリ） |
| `biomes` | `Compound` | バイオームのパレット付きコンテナ（64 エントリ） |
| `BlockLight` | `ByteArray` | 2048 バイト。1ブロックあたり 4bit |
| `SkyLight` | `ByteArray` | 2048 バイト。1ブロックあたり 4bit |

`Y` が `yPos - 1` や最上段+1 になっている**光源専用セクション**が存在しうる。
これらは `block_states` を持たないため、ブロックAPIから見ると空セクションとして扱う。
（26.2 の実ワールドでは観測されず、全セクションが `block_states` と `biomes` を持っていた。
ただし将来・他の生成条件で現れうるため、`block_states` の有無は必ず確認する。）

`BlockLight` / `SkyLight` は**必要なセクションにしか無い**。
実データでは 83,544 セクションのうち `BlockLight` が 5,103、`SkyLight` が 4,904 だった。

`sections` は `Y` の昇順に並んでいるが、**並び順に依存してはならない**。
読み込み時に `Y` から索引を作る。

### 2.1 ブロック状態のパレット要素

```
{ Name: "minecraft:oak_stairs", Properties: { facing: "north", half: "top", waterlogged: "false" } }
```

- `Name` は必須の `String`。名前空間が省略されていたら `minecraft:` を補う
- `Properties` は任意の `Compound`。値はすべて `String`（数値や真偽値も文字列）
- `Properties` が空の場合、Minecraft はキー自体を出力しない。本ライブラリも同様にする

### 2.1.1 ブロック状態の文字列表現

パレット要素は次の形式で文字列化・解析できる（`BlockState`）。

```
<名前空間>:<パス>[<キー>=<値>,<キー>=<値>,...]
```

- **プロパティは必ず名前の昇順に並べて出力する。** これにより、同じブロック状態は
  内部の並び順に関係なく常に同じ文字列になり、全言語で一致する
- プロパティが空のときは角括弧ごと省略する
- 解析時は名前空間の省略を許し、`minecraft:` を補う
- 解析時のみ、`=` の前後と `,` の直後の空白を読み飛ばす。出力側は空白を入れない

解析の失敗はすべて `INVALID_ARGUMENT`（呼び出し側が渡した文字列の誤りであり、
ファイルの中身の破損ではないため）。

| 入力 | 結果 |
|---|---|
| `stone` | `minecraft:stone` |
| `minecraft:oak_stairs[half=top,facing=north]` | `minecraft:oak_stairs[facing=north,half=top]` |
| `minecraft:oak_stairs[]` | `minecraft:oak_stairs` |
| `` （空文字列） | `INVALID_ARGUMENT` |
| `minecraft:oak_stairs[facing=north` | `INVALID_ARGUMENT`（閉じ括弧が無い） |
| `minecraft:oak_stairs[]extra` | `INVALID_ARGUMENT`（`]` で終わっていない） |
| `minecraft:oak_stairs[facing]` | `INVALID_ARGUMENT`（`=` が無い） |
| `minecraft:oak_stairs[=north]` | `INVALID_ARGUMENT`（キーが空） |
| `minecraft:oak_stairs[facing=north,facing=south]` | `INVALID_ARGUMENT`（キーの重複） |

キーの重複を後勝ちで受け入れないのは、どちらが採用されたのかが呼び出し側から
分からないまま書き込まれてしまうため。

### 2.2 座標とエントリ添字

```
block index = (y & 15) * 256 + (z & 15) * 16 + (x & 15)
biome index = ((y & 15) / 4) * 16 + ((z & 15) / 4) * 4 + ((x & 15) / 4)
```

`& 15` により負の座標でも正しくセクション内相対値になる。
セクションの選択は `sectionY = y >> 4`（算術右シフト）で行う。

### 2.3 ブロックに紐づく付随データ

ブロックそのもの以外に、**特定の座標に結びついたデータ**が
チャンクのルート直下に 3 つある。

| キー | 内容 | 主なキー |
|---|---|---|
| `block_entities` | チェスト・看板・スポナーなどの中身 | `id`, `x`, `y`, `z` |
| `block_ticks` | ブロックのティック予約 | `i`（ブロックID）, `x`, `y`, `z`, `t`, `p` |
| `fluid_ticks` | 液体のティック予約 | 同上 |

いずれも `List<Compound>` で、**座標は絶対ワールド座標の `Int`** で持つ。
チャンク内相対ではないので、チャンク座標から換算して突き合わせる必要がある。

実データの例（Java版 26.2）:

```
block_entities: {id:"minecraft:mob_spawner", x:-318, y:-40, z:-302, SpawnData:{...}, ...}
block_ticks:    {i:"minecraft:acacia_leaves", x:-93, y:75, z:-305, t:0, p:0}
```

### 2.4 ブロックを置き換えたときの掃除

**ブロックを別の種類へ置き換えたら、その座標を指す 2.3 の要素をすべて取り除く。**

取り除かないと、たとえばチェストのあった座標に石を置いたとき
`block_entities` にチェストの中身が残る。ブロックと中身が食い違った状態になり、
Minecraft 側で警告やアイテムの復活といった予期しない挙動を招く。
しかも**利用者からは見えにくい**壊れ方をする。

| 状況 | 動作 |
|---|---|
| 別の種類のブロックを置いた | その座標の要素を 3 つのリストすべてから取り除く |
| **同じブロック状態**を置き直した | 何もしない（状態が変わっていないので掃除する理由がない） |
| 要素が `x` `y` `z` を持たない | 対象か判断できないので触らない |

新しいブロックが本来必要とする `block_entity`（置いたのがチェストなら空のチェスト）は
**生成しない**。どのブロックが block entity を必要とするかの判定には
ブロック定義テーブルが要り、それ自体が別の成果物になるため
（[adr/0004](../adr/0004-defer-heightmap-recalc.md) と同じ理由）。
必要なら利用者が生の NBT へ直接足す。

---

## 3. Heightmaps

`Heightmaps` は `Compound` で、各値は `LongArray`。
256 エントリ（16×16）を **9 ビット幅**の BitStorage（跨ぎなし）で詰めたもの。

```
bits            = 9
values_per_long = 64 / 9 = 7
long_count      = ceil(256 / 7) = 37
index           = z * 16 + x
値              = (そのXZ列で条件を満たす最上位ブロックのY) - yPos*16 + 1
```

| キー | 意味 |
|---|---|
| `WORLD_SURFACE` | 空気でない最上位ブロック |
| `MOTION_BLOCKING` | 移動を妨げるか液体である最上位ブロック |
| `MOTION_BLOCKING_NO_LEAVES` | 上記から葉ブロックを除いたもの |
| `OCEAN_FLOOR` | 移動を妨げる固体の最上位ブロック |

**読み書き（そのまま保持）のみ対応し、再計算は行わない。**
どのブロックが「移動を妨げる」かの判定にはブロック定義テーブルが必要で、
それ自体が別の大きな成果物になるため（→ [adr/0004](../adr/0004-defer-heightmap-recalc.md)）。

ブロックを改変した後は次のいずれかを推奨する。

- `chunk.clear_heightmaps()` — `Heightmaps` を削除する。Minecraft が次回読み込み時に再計算する
- 何もしない — 見た目（草の生成やモブスポーン判定）が一時的にずれる可能性がある

同様に `chunk.invalidate_lighting()` は `isLightOn` を `0` にし、光源の再計算を促す。

---

## 4. entities / poi

`entities/` と `poi/` のリージョンファイルも同じ Anvil 形式だが、中身が異なる。

**entities**（`dimensions/<ns>/<path>/entities/r.X.Z.mca`）

| キー | 型 | 内容 |
|---|---|---|
| `DataVersion` | `Int` | |
| `Position` | `IntArray` | `[chunkX, chunkZ]` の 2 要素 |
| `Entities` | `List<Compound>` | エンティティ。各要素が `id`(String) と `Pos`(List&lt;Double&gt;) を持つ |

**poi**（`dimensions/<ns>/<path>/poi/r.X.Z.mca`）

| キー | 型 | 内容 |
|---|---|---|
| `DataVersion` | `Int` | |
| `Sections` | `Compound` | キーが**セクションYの10進文字列**（`"-1"` など）、値が下記 |

`Sections` の各値:

```
{ Valid: 1b, Records: [ { pos: [I; 279, -16, 182], free_tickets: 1, type: "minecraft:home" } ] }
```

これらは**生の `NbtCompound` として読み書き**できるところまでを対象とし、
型付きの API は提供しない。

---

## 5. バージョン検査

- 読み込み時、`DataVersion` が `4903` 以外なら `ReadOptions.on_version_mismatch` に従う
  - `Warn`（既定）: 警告コールバックを呼んで続行する
  - `Error`: `UNSUPPORTED_DATA_VERSION`
  - `Ignore`: 何もしない
- 書き込み時、`DataVersion` は**常に `4903`** を書く
  - 元の値が `4903` 以外だった場合は既定で `UNSUPPORTED_DATA_VERSION`
  - `WriteOptions.allow_foreign_data_version = true` で明示的に許可できる

詳細は [07 バージョンポリシー](../guide/07-version-policy.md)。

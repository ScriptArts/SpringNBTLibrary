# 30. チャンク形式

`.mca`内に格納されるチャンク1つ分のNBT構造。**ここから先は形式依存**である。
本書は**1.13の正式版（DataVersion 1519）以降の形式**を対象とする。
1〜5章は26.3で導入された形式（DataVersion 5006以降。7章の世代C5）を説明し、記述はJava版26.3（DataVersion 5023）の実データで確認した。
それより前の世代との違いは7章にまとめる。

前提: [20 Anvilリージョン形式](20-anvil-region.md) / [31 パレット付きコンテナ](31-paletted-container.md)

---

## 1. ルート要素

ルートは名前なし（空文字列）の`TAG_Compound`。
下表はJava版26.3の実ワールド（3,481チャンク）を走査して確認した内容である。
「出現」欄は、走査したチャンク（full／未完成の両方を含む）のすべてに現れたキーを「全部」、一部のチャンクにだけ現れたキーを「一部」と示す。

| キー | 型 | 出現 | 内容 |
|---|---|---|---|
| `DataVersion` | `Int` | 全部 | チャンク構造のバージョン。26.2は`4903`、26.3は`5023`。パレットの形式は`5006`で変わった（→ 2.1） |
| `xPos` | `Int` | 全部 | 絶対チャンクX座標 |
| `zPos` | `Int` | 全部 | 絶対チャンクZ座標 |
| `yPos` | `Int` | 全部 | 最下段セクションのY位置。オーバーワールドは`-4` |
| `Status` | `String` | 全部 | 生成段階（→ 1.1） |
| `LastUpdate` | `Long` | 全部 | 最終更新のゲーム内時刻 |
| `InhabitedTime` | `Long` | 全部 | プレイヤー滞在時間（tick） |
| `sections` | `List<Compound>` | 全部 | セクション（→ 2章） |
| `block_entities` | `List<Compound>` | 全部 | ブロックエンティティ |
| `block_ticks` | `List<Compound>` | 全部 | 予約されたブロック更新 |
| `fluid_ticks` | `List<Compound>` | 全部 | 予約された液体更新 |
| `Heightmaps` | `Compound` | 全部 | 高さマップ（→ 3章） |
| `structures` | `Compound` | 全部 | `starts`と`References`を持つ |
| `PostProcessing` | `List<List>` | 全部 | 生成後処理の待ち位置 |
| `isLightOn` | `Byte` | 一部 | 光源計算済みフラグ。実データでは`minecraft:full`のチャンクにのみ現れた |
| `entities` | `List<Compound>` | 一部 | **生成途中のチャンクだけが持つ**。完成すると`entities/`のリージョンへ移る |

### 1.1 Status

実データに現れた値（生成の進行順）。

| 値 | 意味 |
|---|---|
| `minecraft:structure_starts` | 構造物の開始点だけ決まった段階 |
| `minecraft:biomes` | バイオームまで決まった段階 |
| `minecraft:terrain` | 地形まで決まった段階。26.2までの`noise` / `surface` / `carvers`が26.3でまとまった |
| `minecraft:initialize_light` | 光源の初期化まで済んだ段階 |
| `minecraft:full` | 生成完了。ブロック操作の対象になるのはこれ |

**`minecraft:full`以外のチャンクは構造が不完全**である。
`set_block`は`minecraft:full`のチャンクに対してのみ行うのが安全である。
本ライブラリは生成段階を検査せず、それ以外のチャンクにもそのまま書き込む。
生成済みかどうかは`is_fully_generated`で確かめられる。

本ライブラリは**上記以外のキーも含め、読んだ要素をすべて保持する**。
未知のキーを落とさないので、将来の追加要素があってもデータはおかしくならない。

`Chunk`型は解釈済みの値（`sections`など）と元の`NbtCompound`の両方を持ち、書き出し時は「解釈した部分（各セクションの`block_states`と`biomes`）を元のCompoundへ書き戻し、解釈していないキーはそのまま残す」方式をとる。

---

## 2. セクション

`sections`は`List<Compound>`。1要素が16×16×16ブロックを表す。

| キー | 型 | 内容 |
|---|---|---|
| `Y` | `Byte` | セクションのY位置。オーバーワールドは`-5`..`20` |
| `block_states` | `Compound` | ブロック状態のパレット付きコンテナ（4096エントリ） |
| `biomes` | `Compound` | バイオームのパレット付きコンテナ（64エントリ） |
| `BlockLight` | `ByteArray` | 2048バイト。1ブロックあたり4bit |
| `SkyLight` | `ByteArray` | 2048バイト。1ブロックあたり4bit |

`Y`が`yPos - 1`や最上段+1になっている光源専用セクションが存在しうる。
光源専用セクションは`block_states`を持たないため、ブロックAPIでは空セクションとして扱う。
（26.3の実ワールドでは観測されず、全セクションが`block_states`と`biomes`を持っていた。
ただし将来や他の生成条件で現れうるため、`block_states`の有無は必ず確認する。）

`BlockLight` / `SkyLight`は**必要なセクションにしか無い**。
実データでは83,544セクションのうち`BlockLight`が5,016、`SkyLight`が4,209だった。

`sections`は`Y`の昇順に並んでいるが、**並び順に依存してはならない**。
読み込み時に`Y`から索引を作る。

書き戻すときは、**読んだときの並びのまま**`sections`を書く。`Y`の昇順に並べ直さない。
実ワールドには、`Y`が`0`..`15`のあとに`-1`が続く1.13.2のチャンクがあった。
同じ`Y`の要素が2つあれば、後の要素を採り、最初に現れた位置へ書き出す。

### 2.1 ブロック状態のパレット要素

26.3で形式が変わった（DataVersion `5006`）。パレットの要素は次の2通りで入る。

```
"minecraft:stone"
{ id: "minecraft:oak_stairs", properties: { facing: "north", half: "top", shape: "straight", waterlogged: "false" } }
```

- ブロックが**既定の状態**なら、ブロックIDだけの`String`になる
- それ以外は`id`と`properties`を持つ`Compound`になる
  - `id`は必須の`String`。名前空間が省略されていたら`minecraft:`を補う
  - `properties`の値はすべて`String`（数値や真偽値も文字列）。Minecraftはすべてのプロパティを名前の昇順で書く
  - `properties`の無い`Compound`も読む。Minecraftも読める
- 26.2までの`{Name: …, Properties: {…}}`は扱わない。`id`が無ければ`MALFORMED_DATA`
- 文字列でも`Compound`でもなければ`UNEXPECTED_TAG_TYPE`

本ライブラリは`BlockState`を次の形で書き出す。Minecraftと同じ形である。

| `BlockState` | 書き出す形 |
|---|---|
| プロパティが空 | ブロックIDだけの`String` |
| プロパティがある | `id`と`properties`を持つ`Compound`。`properties`は名前の昇順 |

#### 既定の状態とプロパティ

文字列の要素は「そのブロックの既定の状態」を表す。プロパティの値はファイルに書かれていない。
本ライブラリはブロックごとの既定値を持たないので、文字列の要素は**プロパティが空の`BlockState`** として読む。

そのため、次のことが起きる。

- 既定の状態の`minecraft:oak_stairs`を`get_block`で読むと、プロパティは空で返る
- `minecraft:oak_stairs`と、既定値をすべて書いた`minecraft:oak_stairs[facing=north,half=bottom,shape=straight,waterlogged=false]`は等しくない。
  後者を置くと、同じ状態を指す要素がパレットに2つ並ぶことがある
- プロパティが空の`BlockState`を置くと文字列で書き出され、Minecraftは既定の状態として読む

#### 文字列とCompoundが混ざったパレット

パレットのリストの型は要素の型で決まる。

| 要素 | リストの型 | 例 |
|---|---|---|
| すべて同じ型 | その型のリスト | `["minecraft:stone", "minecraft:air"]` |
| 文字列とCompoundが混ざる | `List<Compound>`。文字列は`{"": <値>}`に包む | `[{"": "minecraft:stone"}, {id: "minecraft:oak_stairs", properties: {…}}]` |

これは、Minecraftが異種リストをバイナリNBTへ保存するときのやり方である（[11 SNBT](11-snbt.md#4-リストの異種要素)）。
空のキー1つだけを持つ`Compound`を包みとみなす。包みに見える`Compound`を混ざったリストへ入れるときは、それもさらに包む。

本ライブラリはパレット付きコンテナに限ってこの包みを扱う。

- 読み込み時は包みを外し、文字列の要素として持つ
- 書き出し時は要素の型を調べる。混ざっていれば文字列を包み直して`List<Compound>`にし、そろっていればその型のリストにする

規則はMinecraftと同じなので、触っていないパレットは元とバイト単位で一致する。
NBTレイヤの`NbtList`は包みを扱わない（[adr/0010](../adr/0010-palette-format-26-3.md)）。

### 2.1.1 ブロック状態の文字列表現

パレット要素は次の形式で文字列化・解析できる（`BlockState`）。

```
<名前空間>:<パス>[<キー>=<値>,<キー>=<値>,...]
```

- **プロパティは必ず名前の昇順に並べて出力する。** これにより、同じブロック状態は内部の並び順に関係なく常に同じ文字列になり、全言語で一致する
- プロパティが空のときは角括弧ごと省略する
- 解析時は名前空間の省略を許し、`minecraft:`を補う
- 解析時のみ、`=`の前後と`,`の直後の空白を読み飛ばす。出力側は空白を入れない

解析の失敗はすべて`INVALID_ARGUMENT`（呼び出し側が渡した文字列の誤りであり、ファイルの中身の破損ではないため）。

| 入力 | 結果 |
|---|---|
| `stone` | `minecraft:stone` |
| `minecraft:oak_stairs[half=top,facing=north]` | `minecraft:oak_stairs[facing=north,half=top]` |
| `minecraft:oak_stairs[]` | `minecraft:oak_stairs` |
| `` （空文字列） | `INVALID_ARGUMENT` |
| `minecraft:oak_stairs[facing=north` | `INVALID_ARGUMENT`（閉じ括弧が無い） |
| `minecraft:oak_stairs[]extra` | `INVALID_ARGUMENT`（`]`で終わっていない） |
| `minecraft:oak_stairs[facing]` | `INVALID_ARGUMENT`（`=`が無い） |
| `minecraft:oak_stairs[=north]` | `INVALID_ARGUMENT`（キーが空） |
| `minecraft:oak_stairs[facing=north,facing=south]` | `INVALID_ARGUMENT`（キーの重複） |

キーの重複を後勝ちで受け入れないのは、どちらが採用されたのかが呼び出し側から分からないまま書き込まれてしまうため。

### 2.2 座標とエントリ添字

```
block index = (y & 15) * 256 + (z & 15) * 16 + (x & 15)
biome index = ((y & 15) / 4) * 16 + ((z & 15) / 4) * 4 + ((x & 15) / 4)
```

`& 15`により、負の座標でも正しくセクション内の相対値になる。
セクションの選択は`sectionY = y >> 4`（算術右シフト）で行う。

### 2.3 ブロックに紐づく付随データ

ブロックそのもの以外に、特定の座標に結びついたデータがチャンクのルート直下に3つある。

| キー | 内容 | 主なキー |
|---|---|---|
| `block_entities` | チェスト・看板・スポナーなどの中身 | `id`, `x`, `y`, `z` |
| `block_ticks` | ブロックのティック予約 | `i`（ブロックID）, `x`, `y`, `z`, `t`, `p` |
| `fluid_ticks` | 液体のティック予約 | 同上 |

いずれも`List<Compound>`で、**座標は絶対ワールド座標の`Int`で持つ**。
チャンク内の相対座標ではないので、チャンク座標から換算して比べる必要がある。

1.17までの形式では、同じ役割のリストが`Level`の中の`TileEntities` / `TileTicks` / `LiquidTicks`にある（→ 7.3）。

Java版26.3の実データの例を示す。

```
block_entities: {id:"minecraft:vault", x:-14, y:-7, z:-320, config:{...}, ...}
block_ticks:    {i:"minecraft:cave_air", x:-36, y:55, z:-311, t:0, p:0}
```

### 2.4 ブロックを置き換えたときの掃除

**ブロックを別の種類へ置き換えたら、その座標を指す2.3の要素をすべて取り除く。**

取り除かないと、たとえばチェストのあった座標に石を置いたとき、`block_entities`にチェストの中身が残る。
ブロックと中身が食い違った状態になり、Minecraft側で警告やアイテムの復活といった予期しない挙動を招く。
しかも、**利用者からは見えにくい**形でデータがおかしくなる。

| 状況 | 動作 |
|---|---|
| 別の種類のブロックを置いた | その座標の要素を3つのリストすべてから取り除く |
| **同じブロック状態**を置き直した | 何もしない（状態が変わっていないので掃除する理由がない） |
| 要素が`x` `y` `z`を持たない | 対象か判断できないので触らない |

新しいブロックが本来必要とする`block_entity`（置いたのがチェストなら空のチェスト）は**生成しない**。
どのブロックがblock entityを必要とするかの判定にはブロック定義テーブルが要り、それ自体が別の成果物になるため（[adr/0004](../adr/0004-defer-heightmap-recalc.md)と同じ理由）。
必要なら利用者が生のNBTへ直接足す。

---

## 3. Heightmaps

`Heightmaps`は`Compound`で、各値は`LongArray`。
256エントリ（16×16）を**9ビット幅**のBitStorage（跨ぎなし）で詰めたもの。

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

26.3の実データでは、生成途中のチャンク（`minecraft:terrain` / `minecraft:initialize_light`）に生成用の`OCEAN_FLOOR_WG` / `WORLD_SURFACE_WG`も現れた。
生成完了したチャンクは上の4つだけを持つ。

**読み書き（そのまま保持）のみ対応し、再計算は行わない。**
どのブロックが「移動を妨げる」かの判定にはブロック定義テーブルが必要で、それ自体が別の大きな成果物になるため（→ [adr/0004](../adr/0004-defer-heightmap-recalc.md)）。

ブロックを改変した後は次のいずれかを推奨する。

- `chunk.clear_heightmaps()`で`Heightmaps`を削除する。Minecraftが次回読み込み時に再計算する
- 何もしない。見た目（草の生成やモブスポーン判定）が一時的にずれる可能性がある

同様に`chunk.invalidate_lighting()`は`isLightOn`を`0`にし、光源の再計算を促す。
`isLightOn`の無いチャンクには`isLightOn`を書き足す。
1.17までの形式は扱いが違う（→ 7.3）。

---

## 4. entities / poi

`entities/`と`poi/`のリージョンファイルも同じAnvil形式だが、中身が異なる。

**entities**（`dimensions/<ns>/<path>/entities/r.X.Z.mca`）

| キー | 型 | 内容 |
|---|---|---|
| `DataVersion` | `Int` | |
| `Position` | `IntArray` | `[chunkX, chunkZ]`の2要素 |
| `Entities` | `List<Compound>` | エンティティ。各要素が`id`(String)と`Pos`(List&lt;Double&gt;)を持つ |

**poi**（`dimensions/<ns>/<path>/poi/r.X.Z.mca`）

| キー | 型 | 内容 |
|---|---|---|
| `DataVersion` | `Int` | |
| `Sections` | `Compound` | キーが**セクションYの10進文字列**（`"-1"`など）、値が下記 |

`Sections`の各値は次の形をとる。

```
{ Valid: 1b, Records: [ { pos: [I; 279, -16, 182], free_tickets: 1, type: "minecraft:home" } ] }
```

これらは**生の`NbtCompound`として読み書き**できるところまでを対象とし、型付きのAPIは提供しない。

---

## 5. 座標の型

ブロックの位置と範囲を表す値型を用意する。

```
BlockPos { x, y, z }
    chunk_pos()          この座標を含むチャンクの座標（x >> 4, z >> 4）
    local_x() local_z()  チャンク内での位置 (0..15)
    offset(dx, dy, dz)   各軸へずらした座標

Cuboid { min_x, min_y, min_z, max_x, max_y, max_z }
    of(x1, y1, z1, x2, y2, z2)   両端から作る。大小の順序は問わない
    size_x() size_y() size_z()   各軸の長さ
    volume()                     含まれるブロックの個数
    contains(x, y, z)            範囲に含まれるか
    positions()                  範囲内の座標を順に返す
```

`Cuboid`は**両端を含む**。`of(0, 0, 0, 0, 0, 0)`は1ブロックで、`volume()`は1。

`positions()`の並びは**Y、Z、Xの順**とし、Xをいちばん内側で動かす。
Xはチャンク内で連続するので、同じセクションに続けてアクセスできる。

チャンク座標への変換は**算術右シフト**で行う。
論理右シフトでは負の座標が正しく求まらない。

---

## 6. バージョン検査

対応の判定はワールドの形式で行う。Minecraftのバージョン番号は条件にしない。

チャンクの形式は5つの世代に分かれる（→ 7章）。
本ライブラリは1.13の正式版（DataVersion `1519`）以降の世代を、読んだときの形式のまま読み書きする。
新しいバージョンのチャンクも、形式が変わらない限り、いちばん新しい世代でそのまま読み書きできる。

```
MIN_SUPPORTED_DATA_VERSION = 1519   扱える形式の下限（1.13）
TARGET_DATA_VERSION        = 5023   動作を確かめたバージョン（26.3）
```

- 読み込み時、チャンク自身の`DataVersion`が`1519`**以上なら何もしない**
  - 対象より新しいバージョンでも警告を出さない
  - 形式が同じなら読めるので、知らせる必要がない
- `1519`未満か、`DataVersion`が無ければ`ChunkReadOptions.on_version_mismatch`に従う
  - `Warn`（既定）: 警告コールバックを呼んで続行する
  - `Error`: `UNSUPPORTED_DATA_VERSION`
  - `Ignore`: 何もしない
- 書き込み時、`DataVersion`は**読んだ値をそのまま残す**
  - 書き換えると、そのワールドを開くゲーム側の判断を誤らせる
  - `1519`未満のチャンクと`DataVersion`の無いチャンクは、既定で`UNSUPPORTED_DATA_VERSION`
  - `ChunkWriteOptions.allow_foreign_data_version = true`で明示的に許可できる。このときは読んだNBTをそのまま書き出し、`DataVersion`も書き換えない

下限との比較には`format_data_version`の指定（→ 7.1）を使わず、常にチャンク自身の`DataVersion`を使う。

**形式が変わったら、下限を上げずに世代を足す**（[adr/0011](../adr/0011-format-eras.md)）。

詳細は[07 バージョンポリシー](../guide/07-version-policy.md)。

---

## 7. 形式の世代

### 7.1 世代の表

チャンクの形式は`DataVersion`で次の5つの世代に分かれる。境界の値はMinecraftが形式を変えたDataVersionである。

| 世代 | DataVersion | バージョン | 本体 | セクションのブロック | ビット詰め | バイオーム |
|---|---|---|---|---|---|---|
| C1 | `1519`〜`2202` | 1.13〜1.14.x | `Level`の中 | `Palette` / `BlockStates` | 値が64bitの境目をまたぐ | `Level.Biomes`の`int[256]`（列ごと） |
| C2 | `2203`〜`2528` | 1.15〜1.15.2 | `Level`の中 | `Palette` / `BlockStates` | 値が64bitの境目をまたぐ | `Level.Biomes`の`int[1024]`（4×4×4ブロックごと） |
| C3 | `2529`〜`2843` | 1.16〜1.17.x | `Level`の中 | `Palette` / `BlockStates` | またがない | `Level.Biomes`の`int[1024]`（4×4×4ブロックごと） |
| C4 | `2844`〜`5005` | 1.18〜26.2 | ルート | `block_states`。パレットの要素は`{Name, Properties}` | またがない | セクションの`biomes` |
| C5 | `5006`以降 | 26.3以降 | ルート | `block_states`。パレットの要素は文字列か`{id, properties}`（→ 2.1） | またがない | セクションの`biomes` |

ビット詰めの2つの方式は[31](31-paletted-container.md)で定める。

世代はチャンクを読んだときにチャンク自身の`DataVersion`で決める。
1つのワールドに形式の違うチャンクが混ざりうるためである。26.2で作ったワールドを26.3で開いても、行っていない場所のチャンクは26.2の形式のまま残る。
書き戻すときも読んだときの世代を使い、利用者が書き出す形式を選ぶ手段は設けない。

`ChunkReadOptions.format_data_version`を指定すると、チャンク自身の`DataVersion`の代わりにその値で世代を選ぶ。
ワールドから読むときは`WorldOpenOptions.format_data_version`がこれに優先する（→ [40 5章](40-world-layout.md#5-261より前の構成)）。

- 指定できる値は`1519`以上。それ未満は`INVALID_ARGUMENT`
- 選んだ世代とチャンクの構造が合わなければ、推測で読み進めずにエラーにする。`Level`の有無が合わなければ`MALFORMED_DATA`、パレットの要素の型が合わなければ`UNEXPECTED_TAG_TYPE`か`MALFORMED_DATA`
- チャンク自身の`DataVersion`が`1519`未満なら、指定があってもどの世代でも解釈しない（→ 7.4）

`Chunk.format_data_version`は、世代を選ぶのに使ったDataVersionを返す。
指定していればその値、指定が無ければチャンク自身の`DataVersion`である。`DataVersion`の無いチャンクで指定も無ければ`-1`を返す。

境界の値はMinecraftの資料に基づく。実ワールドで確かめたのは、観測したDataVersionの間に境界があることまでである。

| 境界 | 変わること | 境界の前で観測したDataVersion | 境界の後で観測したDataVersion |
|---|---|---|---|
| `2203` | バイオームが`int[256]`から`int[1024]`になる | 1976 | 2225 |
| `2529` | ビット詰めが値をまたがなくなる | 2230 | 2567 |
| `2844` | `Level`が無くなる | 2730 | 2860 |
| `5006` | パレットの要素が文字列か`{id, properties}`になる | 4903 | 5023 |

### 7.2 1.18〜26.2の形式（C4）

チャンクの構造は1〜5章と同じで、ブロックのパレットの要素だけが違う。

```
{ Name: "minecraft:oak_stairs", Properties: { facing: "north", half: "top", shape: "straight", waterlogged: "false" } }
```

- 要素は`Name`と`Properties`を持つ`Compound`。プロパティの無いブロックは`Properties`を持たない
- 文字列の要素と包み（`{"": <値>}`）は無い
- 本ライブラリは`BlockState`を同じ形で書き出す。プロパティが空なら`Properties`のキーを書かない

`Status`は、1.18と1.19では名前空間の無い値（`full`など）、1.20.1以降は`minecraft:`の付いた値だった。
`is_fully_generated`は`minecraft:`を外してから比べる。

1.18、1.19、1.20.1、1.21 Pre-Release 1、26.1.2、26.2の実ワールドで、本ライブラリが触る範囲の構造が1〜5章と同じことを確かめた。

### 7.3 1.13〜1.17の形式（C1〜C3）

チャンクの本体はルートの`Level`の中にある。`DataVersion`だけはルートの直下に置かれる。
本ライブラリが読み書きするキーは次のとおりで、ほかのキー（`Entities`など）は読んだまま残す。

| キー | 型 | 内容 |
|---|---|---|
| `DataVersion` | `Int` | ルートの直下 |
| `Level.xPos` / `Level.zPos` | `Int` | 絶対チャンク座標 |
| `Level.Status` | `String` | 生成段階 |
| `Level.Sections` | `List<Compound>` | セクション |
| `Level.Biomes` | `IntArray` | 数値のバイオームID |
| `Level.TileEntities` / `Level.TileTicks` / `Level.LiquidTicks` | `List<Compound>` | ブロックに紐づく付随データ（2.3と同じく絶対座標の`x` `y` `z`を持つ） |
| `Level.Heightmaps` | `Compound` | 高さマップ |
| `Level.isLightOn` | `Byte` | 光源計算済みフラグ |

`yPos`は無い。セクションは0段目から始まり、`min_section_y`は`0`を返す。

**セクション**

| キー | 型 | 内容 |
|---|---|---|
| `Y` | `Byte` | セクションのY位置 |
| `Palette` | `List<Compound>` | ブロック状態のパレット。要素は`{Name, Properties}`（7.2と同じ） |
| `BlockStates` | `LongArray` | パレットへの添字を詰めたもの |
| `BlockLight` / `SkyLight` | `ByteArray` | 光源 |

- `BlockStates`は、パレットが1要素のときも必ずある。ビット幅は4以上で、1要素なら4ビット・256 long
- `Palette`と`BlockStates`がそろったセクションだけがブロックを持つ。片方しか無いセクション（光源だけを持つ`Y`が`-1`や`16`のものなど）は、ブロックAPIでは空のセクションとして扱い、元のまま残す
- `Palette`の要素が`Compound`でなければ`UNEXPECTED_TAG_TYPE`
- ビット詰めは、C1とC2が値をまたぐ方式、C3がまたがない方式（[31](31-paletted-container.md)）

実ワールドでは、パレットが1要素のセクション（C1 247,504、C2 1,228、C3 141,984）はすべて256 longの`BlockStates`を持ち、片方しか無いセクションは無かった。

**バイオーム**

`Level.Biomes`の数値のIDを、`get_biome_id` / `set_biome_id`でそのまま読み書きする。IDは名前に直さない。1.16.2以降はデータパックで独自のバイオームを足せるので、固定の表では正しく引けないためである。
この世代では`get_biome` / `set_biome`が`UNSUPPORTED_FEATURE`、1.18以降の世代では`get_biome_id` / `set_biome_id`が`UNSUPPORTED_FEATURE`になる。

| 世代 | 長さ | 添字 |
|---|---|---|
| C1 | `int[256]` | `z * 16 + x`。列ごとに持つので`y`を見ない |
| C2 / C3 | `int[1024]` | `((y >> 2) & 63) * 16 + (z >> 2) * 4 + (x >> 2)`。`y`は絶対Y座標で`0`..`255` |

- C2 / C3で`y`が`0`..`255`の外なら、`get_biome_id`は`None`、`set_biome_id`は`INVALID_ARGUMENT`
- `Biomes`が無い、`IntArray`でない、長さが合わないときは、`get_biome_id`は`None`、`set_biome_id`は`INVALID_ARGUMENT`。元のNBTはそのまま残す。
  実ワールドではC1に`int[0]`（13,488チャンク）と`byte[256]`（482チャンク。`Sections`の無いチャンク）があった

**Status**

| 世代 | 実ワールドに現れた値 | 生成済みとみなす値 |
|---|---|---|
| C1 | `mobs_spawned`、`full`、`structure_starts`、`postprocessed`、`fullchunk`、`features`、`liquid_carvers`、`carved`、`liquid_carved`、`decorated`、`spawn`、`empty`、`light` | `full`、`postprocessed`、`fullchunk` |
| C2 | `full`、`structure_starts`、`liquid_carvers`、`features`、`light`、`heightmaps`、`noise`、`surface`、`carvers` | `full` |
| C3 | `full`、`structure_starts`、`liquid_carvers`、`features`、`heightmaps`、`spawn`、`noise`、`light`、`biomes` | `full` |

`postprocessed`と`fullchunk`は1.13のチャンクにだけ現れた。1.13は生成を終えたチャンクをこの2つの値でも保存する。

**高さマップと光源**

`clear_heightmaps`は`Level.Heightmaps`を削除する。高さマップの中身は解釈しない。

`invalidate_lighting`は`Level.isLightOn`を`0`にする。`isLightOn`の無いチャンクには書き足さず、`UNSUPPORTED_FEATURE`にする。書き足すと、元に無いキーが増えるためである。
実ワールドでは、DataVersion 1631（1.13.2）のチャンクはどれも`isLightOn`を持たず、1968以降の生成済みのチャンクはほぼすべてが持っていた。生成途中のチャンクで持つものは少なかった。

**ブロックの置き換え**

ブロックを置き換えたときは、`Level.TileEntities` / `Level.TileTicks` / `Level.LiquidTicks`から、その座標を指す要素を取り除く（2.4と同じ規則）。

### 7.4 1.13より前のチャンク

`DataVersion`が`1519`未満のチャンクと、`DataVersion`の無いチャンク（1.9より前）は、どの世代でも解釈せず、元のNBTだけを持つ。
ブロックが数値IDなので、1.13以降の世代で読むとブロックが1つも無いように見えてしまうためである。

- 読み込みは`on_version_mismatch`に従う（6章）
- `get_block` / `set_block` / `get_biome` / `set_biome` / `get_biome_id` / `set_biome_id` / `min_section_y` / `clear_heightmaps` / `invalidate_lighting`は`UNSUPPORTED_DATA_VERSION`
- `section_ys`は空になる。`is_fully_generated`は、`Status`が無いか文字列でなければ偽を返す
- `allow_foreign_data_version`で許可したときだけ書き戻せる。書き戻すときは読んだNBTをそのまま返す

1.13より前のチャンクが混ざったワールドでも、ほかのチャンクは読み書きできる。

### 7.5 パレットへの追加

`set_block`は、パレットに同じ`BlockState`を表す要素があればその要素を使う。
要素はチャンクの世代の形式で`BlockState`へ直してから比べるので、キーの並びが違う要素（実ワールドには`{Properties, Name}`の順のものがある）も同じ状態として見つかる。
新しく足す要素はチャンクの世代の形式で書く。

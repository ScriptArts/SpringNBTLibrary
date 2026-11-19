# 30. チャンク形式

`.mca`内に格納されるチャンク1つ分のNBT構造。**ここから先は形式依存**である。
本書は**26.3で導入された形式（DataVersion 5006以降）** を対象とし、記述はJava版26.3（DataVersion 5023）の実データで確認した。

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

いまの形式は26.3（DataVersion `5006`）で入った。ブロックのパレットの形式が変わった（→ 2.1）。
これ以降のバージョンは、形式が変わらない限りそのまま読み書きできる。

```
MIN_SUPPORTED_DATA_VERSION = 5006   扱える形式の下限
TARGET_DATA_VERSION        = 5023   動作を確かめたバージョン（26.3）
```

- 読み込み時、`DataVersion`が`5006`**以上なら何もしない**
  - 対象より新しいバージョンでも警告を出さない
  - 形式が同じなら読めるので、知らせる必要がない
- `5006`未満なら`ChunkReadOptions.on_version_mismatch`に従う
  - `Warn`（既定）: 警告コールバックを呼んで続行する
  - `Error`: `UNSUPPORTED_DATA_VERSION`
  - `Ignore`: 何もしない
- 書き込み時、`DataVersion`は**読んだ値をそのまま残す**
  - 書き換えると、そのワールドを開くゲーム側の判断を誤らせる
  - `5006`未満のチャンクは既定で`UNSUPPORTED_DATA_VERSION`
  - `ChunkWriteOptions.allow_foreign_data_version = true`で明示的に許可できる。このときも`DataVersion`は書き換えない

**形式が変わったときだけ下限を上げる。** 下限を上げると、そのワールドを扱えなくなる利用者が出るので、バージョン番号のいちばん上の桁も上げる。

詳細は[07 バージョンポリシー](../guide/07-version-policy.md)。

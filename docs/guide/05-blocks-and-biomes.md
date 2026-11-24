# 05. ブロックとバイオーム

チャンクの中身を読み書きします。3つのレイヤのいちばん上にあたります。

> コード例は基準実装のC#で示します。他の言語での綴りは[API対応表](../api/world.md)を参照してください。

---

## 1. ブロックを読む

```csharp
BlockState? block = overworld.GetBlock(100, 64, -200);
Console.WriteLine(block);   // minecraft:grass_block
```

座標は絶対ワールド座標です。どのリージョンのどのチャンクのどのセクションかは、すべて内部で解決します。

チャンクが存在しない、またはその高さにセクションが無ければ`null`になります。
「空気」と「そもそも無い」は別のものです。

チャンクを直接持っているなら、チャンク内相対座標（0〜15）でも読めます。

```csharp
Chunk chunk = overworld.Chunk(6, -13)!;
BlockState? block = chunk.GetBlock(4, 64, 10);   // x, zは0..15
```

---

## 2. BlockState

ブロックは名前とプロパティの組で表します。

```csharp
BlockState stairs = BlockState.Parse("minecraft:oak_stairs[facing=north,half=top]");

stairs.Name;                  // "minecraft:oak_stairs"
stairs.Property("facing");    // "north"
stairs.ToString();            // "minecraft:oak_stairs[facing=north,half=top]"
```

- 名前空間を省くと`minecraft:`を補う（`Parse("stone")` → `minecraft:stone`）
- プロパティは必ず名前の昇順で出力する。同じ状態なら同じ文字列になり、全言語で一致する
- プロパティの値はすべて文字列。`"false"`は真偽値ではなく文字列

```csharp
// 並び順が違っても同じブロックとして等しい
BlockState.Parse("minecraft:oak_stairs[facing=north,half=top]")
    .Equals(BlockState.Parse("minecraft:oak_stairs[half=top,facing=north]"));   // true
```

不変オブジェクトなので、一部だけ変えたいときは`With`を使います。

```csharp
BlockState facingSouth = stairs.With("facing", "south");
```

### 既定の状態のブロック

26.3から、Minecraftは**既定の状態のブロックをブロックIDだけで保存します**。
このライブラリはブロックごとの既定値を持たないので、そうしたブロックはプロパティが空の`BlockState`として読みます。

```csharp
// 既定の状態（facing=north,half=bottom,shape=straight,waterlogged=false）の階段
chunk.GetBlock(1, 64, 1);   // minecraft:oak_stairs
```

既定値をすべて書いた`BlockState`とは等しくなりません。

```csharp
BlockState.Parse("minecraft:oak_stairs")
    .Equals(BlockState.Parse("minecraft:oak_stairs[facing=north,half=bottom,shape=straight,waterlogged=false]"));   // false
```

既定の状態を置きたいときは、プロパティを書かずに置いてください。ブロックIDだけで保存され、Minecraftが書くものと同じになります。
詳しくは[30 チャンク形式 2.1](../spec/30-chunk-format.md#21-ブロック状態のパレット要素)。

---

## 3. ブロックを置く

```csharp
overworld.SetBlock(100, 64, -200, "minecraft:stone");
overworld.Flush();
```

`BlockState`を渡すこともできます。同じ状態を何度も置くなら、一度解析したものを使い回すほうが速くなります。

```csharp
BlockState stone = BlockState.Parse("minecraft:stone");
overworld.SetBlock(100, 64, -200, stone);
```

パレットに無いブロックは自動で追加されます。
その結果ビット幅が足りなくなれば、セクション全体が詰め直されます。
利用者が意識する必要はありません。

パレットの要素はそのチャンクを読んだときの形式で書きます。1.18〜26.2のチャンクなら`{Name, Properties}`、26.3以降なら文字列か`{id, properties}`です。
同じ状態のブロックがすでにパレットにあれば、キーの並びが違っていてもその要素を使います。

チャンクの新規生成はしません。
存在しない座標へ置こうとすると`INVALID_ARGUMENT`になります。
ワールド生成はゲーム側の仕事です。

### 付随データは自動で取り除かれる

チェストのあった座標に石を置くと、`block_entities`に残っていたチェストの中身は自動で取り除かれます。
`block_ticks` / `fluid_ticks`も同様です。
1.17までのチャンクでは`Level`の中の`TileEntities` / `TileTicks` / `LiquidTicks`から取り除きます。

```csharp
// この座標にチェストがあったなら、その中身ごと消える
overworld.SetBlock(100, 64, -200, "minecraft:stone");
```

取り除かないと、ブロックと中身が食い違った状態が残り、Minecraft側で警告やアイテムの復活といった予期しない挙動を招きます。
しかも、利用者からは見えにくい形でおかしくなります（→ [spec/30 2.4](../spec/30-chunk-format.md#24-ブロックを置き換えたときの掃除)）。

同じブロック状態を置き直したときは何も起きません。
状態が変わっていない以上、付随データを触る理由がないからです。

逆に、新しいブロックが必要とする`block_entity`（置いたのがチェストなら空のチェスト）は生成しません。必要なら生のNBTへ直接足してください。

### 使わなくなったブロックの掃除

大量に置き換えると、もう誰も参照していないパレット要素が残ります。

```csharp
chunk.Compact();   // 未使用のパレット要素を捨て、必要ならビット幅を縮める
```

`SetBlock`のたびに自動でやると著しく遅くなるので、明示的に呼んだときだけ行います。

---

### 範囲をまとめて書き換える

`Cuboid`は両端を指定した直方体の範囲です。`Positions()`は中の座標を順に返します。

```csharp
Cuboid area = Cuboid.Of(100, 64, -200, 110, 70, -190);

// 並びはY、Z、Xの順
// Xがいちばん内側で動くので、同じセクションを続けて触れる
foreach (BlockPos pos in area.Positions())
{
    overworld.SetBlock(pos.X, pos.Y, pos.Z, "minecraft:stone");
}

overworld.Flush();
```

`BlockPos`からはチャンク座標も引けます。

```csharp
BlockPos pos = new BlockPos(100, 64, -200);
ChunkPos chunk = pos.ChunkPos;   // (6, -13)
int localX = pos.LocalX;         // 4
```

### 書き戻される対象

ブロックやバイオームを書き換えたチャンクには変更フラグが立ち、`Flush`は変更フラグの立ったチャンクだけを書き戻します。

```csharp
Chunk chunk = overworld.Chunk(6, -13)!;
chunk.SetBlock(4, 64, 8, "minecraft:stone");
chunk.IsModified;   // true
```

同じ状態を置き直しただけなら何も起きないので、変更フラグも立ちません。
`Raw`を直接いじったときは変更フラグが立たないので、自分で立ててください。

---

## 4. バイオーム

バイオームは4×4×4ブロックが1単位です。1ブロック単位では設定できません。

```csharp
string? biome = overworld.GetBiome(100, 64, -200);
overworld.SetBiome(100, 64, -200, "minecraft:desert");
```

`SetBiome(100, 64, -200, ...)`は、その座標を含む4×4×4の枠すべてを変えます。

### 1.17までのバイオームID

1.17までのチャンクはバイオームを名前ではなく数値のIDで持っています。
このチャンクでは`GetBiome` / `SetBiome`が`UNSUPPORTED_FEATURE`になるので、`GetBiomeId` / `SetBiomeId`を使います。座標はチャンク内相対のX・Zと、絶対のYです。

```csharp
Chunk chunk = overworld.Chunk(6, -13)!;   // 1.16.5のチャンク
int? biomeId = chunk.GetBiomeId(4, 64, 8);
chunk.SetBiomeId(4, 64, 8, 2);
```

- IDは名前に直さずに、そのまま読み書きします。1.16.2以降はデータパックで独自のバイオームを足せるので、固定の表では正しく引けないためです
- 1.15〜1.17は4×4×4ブロックが1単位で、Yは0〜255の範囲だけを持ちます。範囲外のYでは`GetBiomeId`が`null`になり、`SetBiomeId`は`INVALID_ARGUMENT`になります
- 1.13〜1.14はXZの列ごとに1つの値を持ちます。Yは見ないので、`SetBiomeId`はその列全体を変えます
- `Biomes`が無いチャンクや、長さが合わないチャンクでは、`GetBiomeId`が`null`になり、`SetBiomeId`は`INVALID_ARGUMENT`になります
- 1.18以降のチャンクでは、`GetBiomeId` / `SetBiomeId`が`UNSUPPORTED_FEATURE`になります

`GetBiomeId` / `SetBiomeId`は`Chunk`だけにあり、`Dimension`にはありません。

---

## 5. Heightmapsと光源は再計算されない

ブロックを置き換えても、`Heightmaps`（地表の高さ）と光源データは古いままです。
そのままだと、ゲームで見たときに影や明るさがおかしくなります。

代わりに、ゲーム側へ再計算させます。

```csharp
chunk.ClearHeightmaps();       // Heightmapsを消す
chunk.InvalidateLighting();    // isLightOn = falseにする
```

こうしておくと、Minecraftがそのチャンクを読み込むときに自分で作り直します。
ブロックを書き換えたら、どちらも呼んでおくのが安全です。

1.17までのチャンクには`isLightOn`を持たないものがあります。1.13のチャンクはどれも持っていません。
`isLightOn`を持たない1.17までのチャンクでは、`InvalidateLighting`は`UNSUPPORTED_FEATURE`になり、`isLightOn`を書き足しません。元に無いキーを増やさないためです。
1.18以降のチャンクでは、`isLightOn`が無ければ書き足します。

---

## 6. 内部の仕組み

この節では、知っておくと役に立つ内部の仕組みを説明します。
セクション（16×16×16）のブロックはパレット方式で持ちます。

```
palette: [ air, stone, dirt ]        使われている種類の一覧
data:    [ 0,0,1,1,2,0,... ]         各マスがパレットの何番か
```

`data`は64ビット整数の配列に詰めます。
1.16以降の形式では、1つの値は必ず1つの整数に収まり、境界を跨ぎません。
1.15までの形式では値が整数の境界を跨ぐので、ビット幅によっては`data`の長さが変わります（[仕様31 2.3](../spec/31-paletted-container.md#23-またぐ詰め方115まで)）。
必要ビット数は`max(4, ceil(log2(パレット長)))`で決まります。

| パレット長 | ビット幅 | `data`の長さ |
|---:|---:|---:|
| 1 | — | `data`を持たない |
| 2〜16 | 4 | 256 |
| 17〜32 | 5 | 342 |
| 33〜64 | 6 | 410 |

この式は[実際の26.3ワールドの167,088個のコンテナすべてで一致することを確認済みです](../spec/31-paletted-container.md#21-実データで確認した組み合わせ)。
1.17までの形式では、パレットが1要素でも256個の`data`（`BlockStates`）を持ちます。

パレットの要素は元のNBTのまま保持しています。
そのため、触っていないブロックはプロパティの並び順まで含めて元どおりに書き戻されます。

---

## 7. 次に読むもの

- [06. エラーと安全上限](06-errors-and-limits.md)
- [仕様30: チャンク形式](../spec/30-chunk-format.md)
- [仕様31: パレット付きコンテナ](../spec/31-paletted-container.md)

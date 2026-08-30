# 05. ブロックとバイオーム

チャンクの中身を読み書きする。ここが本ライブラリのいちばん上の層。

> コード例は基準実装の C#。他言語での綴りは [API 対応表](../api/world.md)。

---

## 1. ブロックを読む

```csharp
BlockState? block = overworld.GetBlock(100, 64, -200);
Console.WriteLine(block);   // minecraft:grass_block[snowy=false]
```

座標は絶対ワールド座標。どのリージョンのどのチャンクのどのセクションか、
という解決はすべて内部で行います。

チャンクが存在しない、またはその高さにセクションが無ければ `null` になります。
「空気」と「そもそも無い」は違うことに注意。

チャンクを直接持っているなら、チャンク内相対座標（0〜15）でも読めます。

```csharp
Chunk chunk = overworld.Chunk(6, -13)!;
BlockState? block = chunk.GetBlock(4, 64, 10);   // x, z は 0..15
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

- 名前空間を省くと `minecraft:` を補う（`Parse("stone")` → `minecraft:stone`）
- プロパティは必ず名前の昇順で出力する。 同じ状態なら必ず同じ文字列になり、
  全言語で一致する
- プロパティの値はすべて文字列。`"false"` は真偽値ではなく文字列である

```csharp
// 並び順が違っても同じブロックとして等しい
BlockState.Parse("minecraft:oak_stairs[facing=north,half=top]")
    == BlockState.Parse("minecraft:oak_stairs[half=top,facing=north]");   // true
```

不変オブジェクトなので、一部だけ変えたいときは `With` を使います。

```csharp
BlockState facingSouth = stairs.With("facing", "south");
```

---

## 3. ブロックを置く

```csharp
overworld.SetBlock(100, 64, -200, BlockState.Parse("minecraft:stone"));
overworld.Flush();
```

パレットに無いブロックは自動で追加される。
その結果ビット幅が足りなくなれば、セクション全体が自動で詰め直される。
利用者が意識する必要はありません。

本ライブラリはチャンクを新規生成しません。
存在しない座標へ置こうとすると `INVALID_ARGUMENT` になります。
ワールド生成はゲーム側の仕事であり、本ライブラリの範囲外です。

### 付随データは自動で取り除かれる

チェストのあった座標に石を置くと、`block_entities` に残っていた
チェストの中身は自動で取り除かれる。
`block_ticks` / `fluid_ticks` も同様です。

```csharp
// この座標にチェストがあったなら、その中身ごと消える
overworld.SetBlock(100, 64, -200, BlockState.Parse("minecraft:stone"));
```

取り除かないと、ブロックと中身が食い違った状態が残り、
Minecraft 側で警告やアイテムの復活といった予期しない挙動を招きます。
しかも利用者からは見えにくい壊れ方をする（→ [spec/30 2.4](../spec/30-chunk-format.md#24-ブロックを置き換えたときの掃除)）。

同じブロック状態を置き直したときは何も起きない。
状態が変わっていないので、付随データを触る理由がないため。

逆に、新しいブロックが必要とする `block_entity`（置いたのがチェストなら空のチェスト）は
生成しない。必要なら生の NBT へ直接足すこと。

### 使わなくなったブロックの掃除

大量に置き換えると、もう誰も参照していないパレット要素が残ります。

```csharp
chunk.Compact();   // 未使用のパレット要素を捨て、必要ならビット幅を縮める
```

`SetBlock` のたびに自動でやると著しく遅くなるので、明示的に呼んだときだけ行います。

---

## 4. バイオーム

バイオームは4×4×4 ブロックが 1 単位である。1 ブロック単位では設定できない。

```csharp
string? biome = overworld.GetBiome(100, 64, -200);
overworld.SetBiome(100, 64, -200, "minecraft:desert");
```

`SetBiome(100, 64, -200, ...)` は、その座標を含む 4×4×4 の枠すべてを変える。

---

## 5. Heightmaps と光源は再計算されない

これは重要な制限です。

ブロックを置き換えても、`Heightmaps`（地表の高さ）と光源データは古いままです。
そのままだと、ゲームで見たときに影や明るさがおかしくなります。

代わりに、ゲーム側へ再計算させます。

```csharp
chunk.ClearHeightmaps();       // Heightmaps を消す
chunk.InvalidateLighting();    // isLightOn = false にする
```

こうしておくと、Minecraft がそのチャンクを読み込むときに自分で作り直します。
ブロックを書き換えたら必ずどちらも呼ぶことを勧める。

---

## 6. 内部の仕組み（知っておくと役に立つ）

セクション（16×16×16）のブロックはパレット方式で持ちます。

```
palette: [ air, stone, dirt ]        使われている種類の一覧
data:    [ 0,0,1,1,2,0,... ]         各マスがパレットの何番か
```

`data` は 64 ビット整数の配列に詰める。
1 つの値は必ず 1 つの整数に収まる（境界を跨がない）。
必要ビット数は `max(4, ceil(log2(パレット長)))` で決まります。

| パレット長 | ビット幅 | `data` の長さ |
|---:|---:|---:|
| 1 | — | `data` を持たない |
| 2〜16 | 4 | 256 |
| 17〜32 | 5 | 342 |
| 33〜64 | 6 | 456 |

この式は[実際の 26.2 ワールドの 167,088 個のコンテナすべてで一致を確認済み](../spec/31-paletted-container.md#21-実データで確認した組み合わせ)。

パレットの要素は元の NBT のまま保持しています。
そのため触っていないブロックは、プロパティの並び順まで含めて
元どおりに書き戻される。

---

## 7. 次に読むもの

- [06. エラーと安全上限](06-errors-and-limits.md)
- [仕様 30: チャンク形式](../spec/30-chunk-format.md)
- [仕様 31: パレット付きコンテナ](../spec/31-paletted-container.md)

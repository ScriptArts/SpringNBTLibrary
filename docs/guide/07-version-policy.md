# 07. バージョンポリシー

対応しているかどうかはワールドの形式で判定しています。Minecraftのバージョン番号は条件にしません。

1.13以降のワールドを、**読んだときの形式のまま**読み書きします。バージョン間の変換はしません。
1.12.2で作ったワールドを26.3の形式に直す、といった使い方はできません。

```
MIN_SUPPORTED_DATA_VERSION = 1519   扱える形式の下限（1.13）
TARGET_DATA_VERSION        = 5023   動作を確かめたバージョン（26.3）
```

---

## 1. 形式の世代

チャンクの形式はDataVersionで次の5つの世代に分かれます。

| 世代 | DataVersion | バージョン | 主な違い |
|---|---|---|---|
| C1 | 1519〜2202 | 1.13〜1.14.x | 本体が`Level`の中。ビット詰めの値が64bitの境目をまたぐ。バイオームは列ごとの数値のID |
| C2 | 2203〜2528 | 1.15〜1.15.2 | バイオームが4×4×4ブロックごとの数値のIDになる |
| C3 | 2529〜2843 | 1.16〜1.17.x | ビット詰めの値が境目をまたがなくなる |
| C4 | 2844〜5005 | 1.18〜26.2 | `Level`が無くなる。バイオームが名前のパレットになる。パレットの要素は`{Name, Properties}` |
| C5 | 5006以降 | 26.3以降 | パレットの要素が文字列か`{id, properties}`になる |

ワールドのフォルダの構成と`level.dat`の中身も、1.21.xまで（L1）と26.1以降（L2）の2つの世代に分かれます（[04](04-world-and-level-dat.md#1-26xのディレクトリ構成)）。

チャンクの世代はチャンクごとに、そのチャンクの`DataVersion`で決めます。
1つのワールドに形式の違うチャンクが混ざることがあるためです。26.2で作ったワールドを26.3で開いても、行ったことのない場所のチャンクは26.2の形式のまま残ります。
そうしたチャンクも26.2の形式のまま読み書きできます。

フォルダの構成と`level.dat`の世代はワールドを開いたときに`level.dat`の`DataVersion`で決めます。

書き戻すときは、読んだときの世代の形式で書きます。書き出す形式を選ぶ方法はありません。形式を取り違えてワールドを使えなくすることがないようにするためです。

---

## 2. 読み込み

`DataVersion`が**1519以上なら何もしません。警告も出ません。**

対象より新しいバージョンのワールドでも同じです。
形式が同じなら読めるので、知らせる必要がありません。新しいDataVersionのチャンクはいちばん新しい世代で読みます。

```csharp
// DataVersion 5100のチャンク（対象より新しい）
Chunk chunk = Chunk.FromNbt(nbt);   // 警告なしで読める
```

1519未満のチャンクと`DataVersion`の無いチャンク、つまり1.13より前のチャンクのときだけ、動作を選べます。

| 動作 | 意味 |
|---|---|
| `Warn`（既定） | 警告コールバックを呼んで続行する |
| `Error` | `UNSUPPORTED_DATA_VERSION`にする |
| `Ignore` | 何もしない |

```csharp
ChunkReadOptions options = new ChunkReadOptions
{
    OnVersionMismatch = VersionMismatchAction.Warn,
    OnWarning = message => Console.Error.WriteLine(message),
};
```

1.13より前のチャンクは続行しても中身を解釈しません。ブロックが数値IDで、1.13以降の形式として読むとブロックが1つも無いように見えてしまうためです。
元のNBTだけを持ち、ブロックとバイオームを読み書きするメソッドは`UNSUPPORTED_DATA_VERSION`になります。

構造そのものが想定と違えば（パレットが無い、`data`の長さが合わない、など）、バージョンに関わらず`MALFORMED_DATA`になります。推測で読み進めることはしません。

### 世代を指定して読む

ふつうは指定する必要はありません。
チャンクの`DataVersion`と実際の形式が食い違うデータを扱うときは、世代を選ぶDataVersionを指定できます。

```csharp
// 1.16.5の形式として読む
ChunkReadOptions options = new ChunkReadOptions { FormatDataVersion = 2586 };
Chunk chunk = Chunk.FromNbt(nbt, options);

chunk.FormatDataVersion;   // 2586
```

ワールドを開くときに`WorldOpenOptions.FormatDataVersion`を指定すると、フォルダの構成と、そのワールドから読むすべてのチャンクに効きます。

- 指定できるのは1519以上の値です。それより小さい値は`INVALID_ARGUMENT`になります
- 選んだ世代とチャンクの構造が合わなければ、エラーになります。合わない形式のまま読み進めることはしません
- 指定しても、1.13より前のチャンクを解釈させることはできません。下限との比較には常にチャンク自身の`DataVersion`を使います

### NBTレイヤはバージョンに依存しない

[レイヤ1（NBT）](01-nbt.md)と[レイヤ2（Anvil）](03-anvil-region.md)はバージョン検査を一切しません。どのバージョンのファイルでも読み書きできます。

バージョンを見るのは[レイヤ3（World）](04-world-and-level-dat.md)だけです。
1.13より前のワールドからNBTを取り出すだけなら、何の制約もなく使えます。

---

## 3. 書き込み

**`DataVersion`は読んだ値をそのまま残します。** 書き換えません。

書き換えてしまうと、そのワールドを開いたゲーム側が「このチャンクは新しい形式だ」と判断してしまい、アップグレードの要否を誤ります。

```csharp
// DataVersion 2586（1.16.5）のチャンクを書き戻す
chunk.ToNbt();   // 1.16.5の形式で、DataVersionも2586のまま。許可も要らない
```

1.13より前のチャンクは既定では書き戻せません。

```csharp
Chunk chunk = /* DataVersion 1343（1.12.2）のチャンク */;
chunk.ToNbt();   // UNSUPPORTED_DATA_VERSION
```

意図して書き戻すなら、明示的に許可します。このときは読んだNBTをそのまま書き出し、`DataVersion`も書き換えません。

```csharp
ChunkWriteOptions options = new ChunkWriteOptions { AllowForeignDataVersion = true };
chunk.ToNbt(options);   // 読んだNBTのまま、1343で書き出される
```

> 編集する前に、必ずワールドのバックアップを取ってください。

古いワールドを新しいバージョンで使いたいときは、Minecraftでワールドを開いて公式のアップグレードを済ませてください。
ただし、ワールドを開いただけでは読み込まれたチャンクしか新しい形式になりません。
すべてのチャンクを変換するには、ワールドの編集画面にある「ワールドを最適化」を使います。

---

## 4. 世代によって使えないもの

世代によって持たない値を扱うメソッドは、`UNSUPPORTED_FEATURE`になります。

| メソッド | 使えない世代 | 代わり |
|---|---|---|
| `GetBiome` / `SetBiome` | 1.17まで（C1〜C3） | `GetBiomeId` / `SetBiomeId`（[05](05-blocks-and-biomes.md#117までのバイオームid)） |
| `GetBiomeId` / `SetBiomeId` | 1.18以降（C4・C5） | `GetBiome` / `SetBiome` |
| `InvalidateLighting` | `isLightOn`を持たない1.17までのチャンク | 無い |
| `LevelData.SpawnDimension` | 1.21.xまでの`level.dat`（L1） | 無い |

---

## 5. 対応している形式を確かめる

```csharp
Console.WriteLine(SpringNbt.MinSupportedDataVersion);   // 1519
Console.WriteLine(SpringNbt.TargetDataVersion);         // 5023
```

| 言語 | 下限 | 検証済み |
|---|---|---|
| C# | `SpringNbt.MinSupportedDataVersion` | `SpringNbt.TargetDataVersion` |
| Java | `SpringNbt.MIN_SUPPORTED_DATA_VERSION` | `SpringNbt.TARGET_DATA_VERSION` |
| TypeScript | `MIN_SUPPORTED_DATA_VERSION` | `TARGET_DATA_VERSION` |
| Python | `MIN_SUPPORTED_DATA_VERSION` | `TARGET_DATA_VERSION` |
| Rust | `MIN_SUPPORTED_DATA_VERSION` | `TARGET_DATA_VERSION` |

---

## 6. 新しいバージョンが出たら

形式が変わっていなければ、何もしなくてもそのまま使えます。
ライブラリ側の更新も要りません。

形式が変わったときは、下限を上げずに世代を1つ足して対応します。それまで扱えていたワールドは引き続き扱えます。

---

## 7. 次に読むもの

- [04. ワールドとlevel.dat](04-world-and-level-dat.md)

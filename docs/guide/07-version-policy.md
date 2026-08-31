# 07. バージョンポリシー

見ているのは **ワールドの形式** であって、Minecraft のバージョンそのものではありません
（[adr/0003](../adr/0003-version-policy.md)）。

いまの形式は **26.1（DataVersion 4786）** で導入されたものです。
次元とプレイヤーデータの置き場が変わり、`level.dat` の中身も分割されました。
それ以降のバージョンは、形式が変わらない限りそのまま読み書きできます。

```
MIN_SUPPORTED_DATA_VERSION = 4786   扱える形式の下限（26.1）
TARGET_DATA_VERSION        = 4903   動作を確かめたバージョン（26.2）
```

---

## 1. 読み込み

`DataVersion` が **4786 以上なら何もしません。警告も出ません。**

対象より新しいバージョンのワールドでも同じです。形式が同じなら読めるのですから、
知らせる意味がありません。

```csharp
// DataVersion 5015 のチャンク（対象より新しい）
Chunk chunk = Chunk.FromNbt(nbt);   // 警告なしで読める
```

4786 未満、つまり形式そのものが違うワールドのときだけ、動作を選べます。

| 動作 | 意味 |
|---|---|
| `Warn`（既定） | 警告コールバックを呼んで続行する |
| `Error` | `UNSUPPORTED_DATA_VERSION` にする |
| `Ignore` | 何もしない |

```csharp
ChunkReadOptions options = new ChunkReadOptions
{
    OnVersionMismatch = VersionMismatchAction.Warn,
    OnWarning = message => Console.Error.WriteLine(message),
};
```

構造そのものが想定と違えば（パレットが無い、`data` の長さが合わない、など）、
バージョンに関わらず `MALFORMED_DATA` になります。黙って推測はしません。

### NBT レイヤはバージョンに依存しない

[レイヤ1（NBT）](01-nbt.md)と[レイヤ2（Anvil）](03-anvil-region.md)は
バージョン検査を一切しません。どのバージョンのファイルでも読み書きできます。

バージョンを見るのは[レイヤ3（World）](04-world-and-level-dat.md)だけです。
古いワールドから NBT を取り出すだけなら、何の制約もなく使えます。

---

## 2. 書き込み

**`DataVersion` は読んだ値をそのまま残します。** 書き換えません。

書き換えてしまうと、そのワールドを開いたゲーム側が「このチャンクは新しい形式だ」と
判断してしまい、アップグレードの要否を誤ります。

```csharp
// DataVersion 5015 のチャンクを書き戻す
chunk.ToNbt();   // 5015 のまま。許可も要らない
```

形式の違う古いチャンク（4786 未満）は、既定では書き戻せません。

```csharp
Chunk chunk = /* DataVersion 3700 のチャンク */;
chunk.ToNbt();   // UNSUPPORTED_DATA_VERSION
```

意図してやるなら明示的に許可します。このときも `DataVersion` は書き換えません。

```csharp
ChunkWriteOptions options = new ChunkWriteOptions { AllowForeignDataVersion = true };
chunk.ToNbt(options);   // 3700 のまま書き出される
```

> 古い形式のワールドは、ディレクトリ構成も `level.dat` の中身も違います。
> チャンク単体では書き戻せても、ワールド全体としては噛み合わないことがあります。
> 必ずバックアップを取ってから使ってください。

安全な手順は「先に Minecraft で一度ワールドを開いて公式のアップグレードを済ませ、
そのあとこのライブラリで編集する」です。

---

## 3. 対応している形式を確かめる

```csharp
Console.WriteLine(SpringNbt.MinSupportedDataVersion);   // 4786
Console.WriteLine(SpringNbt.TargetDataVersion);         // 4903
```

| 言語 | 下限 | 検証済み |
|---|---|---|
| C# | `SpringNbt.MinSupportedDataVersion` | `SpringNbt.TargetDataVersion` |
| Java | `SpringNbt.MIN_SUPPORTED_DATA_VERSION` | `SpringNbt.TARGET_DATA_VERSION` |
| TypeScript | `MIN_SUPPORTED_DATA_VERSION` | `TARGET_DATA_VERSION` |
| Python | `MIN_SUPPORTED_DATA_VERSION` | `TARGET_DATA_VERSION` |
| Rust | `MIN_SUPPORTED_DATA_VERSION` | `TARGET_DATA_VERSION` |

---

## 4. 新しいバージョンが出たら

**形式が変わっていなければ、何もしなくてそのまま使えます。**
ライブラリ側の更新も要りません。

形式が変わったときだけ、下限を上げて対応します。
そのときは扱えなくなるワールドが出るので、
[バージョン番号](../../README.md#バージョン番号)のいちばん上の桁も上がります。

対応の手順は [リリース手順](../contributing/release.md) にまとめてあります。

---

## 5. 次に読むもの

- [adr/0003: 見るのは形式であってバージョンではない](../adr/0003-version-policy.md)
- [04. ワールドと level.dat](04-world-and-level-dat.md)

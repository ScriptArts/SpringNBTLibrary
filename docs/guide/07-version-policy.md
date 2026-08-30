# 07. バージョンポリシー

本ライブラリが対象とするのは Minecraft Java版 26.2（DataVersion 4903）。

方針はひとことで言うと「読みは寛容、書きは最新固定」である
（[adr/0003](../adr/0003-version-policy.md)）。

---

## 1. なぜ古いバージョンを書かないのか

チャンクの構造はバージョンごとに変わります。
「1.20 のワールドを 1.20 の形式のまま書き戻す」を正しくやろうとすると、
バージョンごとの構造差をすべて実装し、そのすべてを検証し続けることになります。

1人で対応言語すべてを維持しながら、それを正しく保つのは不可能です。
中途半端に対応すると、**利用者のワールドを静かに壊す**。

そこで「対象は 1 バージョンだけ」と決め、そのぶん正しさに投資しています。

---

## 2. 読み込み

DataVersion が何であっても、構造が解釈できる限り読みます。

`DataVersion != 4903` のときの動作は選べる。

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
バージョンに関わらず `MALFORMED_DATA` になる。黙って推測はしません。

### NBT レイヤはバージョンに依存しない

[レイヤ1（NBT）](01-nbt.md)と[レイヤ2（Anvil）](03-anvil-region.md)は
バージョン検査を一切しません。
どのバージョンのファイルでも読み書きできます。

バージョンを見るのは[レイヤ3（World）](04-world-and-level-dat.md)だけです。
古いワールドから NBT を取り出すだけなら、何の制約もなく使えます。

---

## 3. 書き込み

書き戻すチャンクの `DataVersion` は常に 4903 になります。

対象バージョン以外から読んだチャンクを書き戻そうとすると、
既定では `UNSUPPORTED_DATA_VERSION` で止まる。

```csharp
Chunk chunk = /* DataVersion 3953 のチャンク */;
chunk.ToNbt();   // UNSUPPORTED_DATA_VERSION
```

意図してやるなら明示的に許可します。

```csharp
ChunkWriteOptions options = new ChunkWriteOptions { AllowForeignDataVersion = true };
chunk.ToNbt(options);   // DataVersion は 4903 として書かれる
```

> これは実質的にワールドのアップグレードです。
> 古い構造のまま `DataVersion` だけ新しくなるため、
> Minecraft が正しく読めない可能性があります。
> **必ずワールドのバックアップを取ってから**使うこと。

安全な手順は「先に Minecraft で一度ワールドを開いて
公式のアップグレードを済ませ、そのあと本ライブラリで編集する」です。

---

## 4. 対象バージョンを確かめる

```csharp
Console.WriteLine(SpringNbt.TargetDataVersion);   // 4903
```

| 言語 | 綴り |
|---|---|
| C# | `SpringNbt.TargetDataVersion` |
| Java | `SpringNbt.TARGET_DATA_VERSION` |
| TypeScript | `TARGET_DATA_VERSION` |
| Python | `TARGET_DATA_VERSION` |
| Rust | `TARGET_DATA_VERSION` |

---

## 5. 新しいバージョンが出たら

Minecraft が更新されても、本ライブラリが対応するまでは
そのワールドを書き換えないこと。
読むだけなら警告つきで通るが、書き戻すと新しい構造を古い解釈で上書きしかねない。

対応の手順は [リリース手順](../contributing/release.md) にまとめてあります。

---

## 6. 次に読むもの

- [adr/0003: 読みは寛容・書きは最新固定](../adr/0003-version-policy.md)
- [仕様 30 の5章: バージョン検査](../spec/30-chunk-format.md)

# 03. リージョンファイル (.mca)

Anvil 形式のリージョンファイルは、32×32 = 1024 チャンクをまとめた入れ物です。
`r.<X>.<Z>.mca` という名前で、`region/` `entities/` `poi/` の各ディレクトリに置かれます。

このレイヤはチャンクの中身を解釈しない。NBT として出し入れするだけです。
中身を扱いたい場合は [04](04-world-and-level-dat.md) / [05](05-blocks-and-biomes.md) へ。

> コード例は基準実装の C#。他言語での綴りは [API 対応表](../api/anvil.md)。

---

## 1. 開いて読む

```csharp
using RegionFile region = RegionFile.Open("region/r.0.0.mca", RegionFileMode.ReadOnly);

// 座標は絶対チャンク座標。リージョン内の位置は内部で求める
if (region.HasChunk(5, 12))
{
    NbtCompound chunk = region.ReadChunk(5, 12)!;
    Console.WriteLine(chunk.GetString("Status"));
}
```

存在するチャンクをすべて見るには次のようにします。

```csharp
foreach (ChunkPos pos in region.ChunkPositions())
{
    NbtCompound chunk = region.ReadChunk(pos.X, pos.Z)!;
    // ...
}
```

---

## 2. 書く

```csharp
using RegionFile region = RegionFile.Open(path, RegionFileMode.ReadWrite);

region.WriteChunk(5, 12, chunk);
region.Flush();   // ここでディスクへ反映される
```

`Flush` を呼ぶまでディスクは変わりません。
リージョン全体をメモリ上のセクタ表として持ち、まとめて書き出す設計です。

この設計のおかげで、開いて何も変えずに書き戻すと元とバイト単位で一致します。
触っていないチャンクの配置が動かないので、
1 チャンクだけ書き換えるつもりが他を壊す、という事故が起きません。

---

## 3. ファイルの構造

```
0      4KiB          8KiB                     ファイル末尾
+------+-------------+------------------------+
| 位置 | タイムスタンプ | チャンク本体（4KiB 単位）  |
+------+-------------+------------------------+
```

- 位置表 1024 個 × 4 バイト。上位 3 バイトが開始セクタ、下位 1 バイトがセクタ数
- タイムスタンプ表 1024 個 × 4 バイト。Unix 秒
- 位置とタイムスタンプがどちらも 0 なら、そのチャンクは存在しない

チャンク本体は次の形をしています。

```
length: i32     このあとに続くバイト数（圧縮方式の 1 バイトを含む）
scheme: u8      圧縮方式
data:   ...     圧縮された NBT
```

詳細は [spec/20](../spec/20-anvil-region.md)。

---

## 4. 圧縮方式

| ID | 方式 | 本ライブラリ |
|---:|---|---|
| 1 | GZip | ✅ |
| 2 | Zlib | ✅（書き込みの既定） |
| 3 | 無圧縮 | ✅ |
| 4 | LZ4 | ❌ 生バイトでのみ取得可 |
| 127 | サードパーティ独自 | ❌ 生バイトでのみ取得可 |

扱えない方式のチャンクを `ReadChunk` すると `UNSUPPORTED_FEATURE` になります。
中身が要らない（別のリージョンへ丸ごと移すだけ、など）なら生バイトで扱えます。

```csharp
RawChunk raw = region.ReadChunkRaw(5, 12)!;
other.WriteChunkRaw(5, 12, raw);   // 展開せずそのまま移す
```

---

## 5. 大きすぎるチャンク（.mcc）

1 チャンクは位置表の都合で 255 セクタ（約 1MiB）までしか入りません。
超えると Minecraft は本体を `c.<X>.<Z>.mcc` という別ファイルへ出します。

本ライブラリはこれを自動で処理します。

- 読むとき: `.mcc` があれば透過的に読む
- 書くとき: 1MiB を超えたら自動で `.mcc` へ出す。縮んだら本体へ戻して `.mcc` を消す

利用者が意識する必要はありません。

---

## 6. 断片化の解消

チャンクを書き換え続けるとセクタに隙間ができます。

```csharp
region.Optimize();   // 添字順に詰め直す
region.Flush();
```

必要なとき以外は呼ばなくて構いません。ファイル全体が書き換わるので、
無変更なら元と一致するという性質は失われます。

---

## 7. フォルダ単位で扱う

複数のリージョンにまたがる操作には `RegionFolder` を使います。
`r.X.Z.mca` の名前解決とファイルの開閉をまとめて引き受けます。

```csharp
using RegionFolder folder = RegionFolder.Open("dimensions/minecraft/overworld/region",
                                              RegionFileMode.ReadOnly);

foreach (ChunkPos pos in folder.ChunkPositions())
{
    NbtCompound chunk = folder.ReadChunk(pos.X, pos.Z)!;
    // ...
}
```

---

## 8. 開いたリージョンはいくつまでか

`RegionFile` はファイル全体をメモリへ載せます。
無変更で書き戻したときにバイト単位で一致させるための設計だが、
そのぶん開いたまま貯めるとメモリを食います。

`RegionFolder` は開いたリージョンの数に上限を持ち（既定 8 件）、
超えたら、最も長く使っていないものを書き出してから閉じます。
数千リージョンあるワールドを端から走査しても破綻しません。

```csharp
// 上限を変えたい場合
using RegionFolder folder = RegionFolder.Open(path, RegionFileMode.ReadWrite,
                                              maxCachedRegions: 32);
```

このため `Region()` が返した参照は、
別のリージョンへアクセスすると閉じられている場合があります。

```csharp
RegionFile? a = folder.Region(0, 0);
folder.ReadChunk(9999, 9999);   // 別のリージョンを開く
// a はもう閉じられているかもしれない
```

参照を持ち回らず、必要なたびに取得してください。
`ReadChunk` / `WriteChunk` 経由で使うぶんには意識しなくて構いません。

## 9. 壊れたファイルの検出

開いた時点で次を検査し、問題があれば `MALFORMED_DATA` にします。

- 位置表が指すセクタがファイルの外を指している
- 2 つのチャンクが同じセクタを使っている
- ファイル長が 4KiB の倍数でない

黙って読み進めると、書き戻したときに別のチャンクを破壊しかねないため、
先に止める方針をとっています。

---

## 10. 次に読むもの

- [04. ワールドと level.dat](04-world-and-level-dat.md)
- [仕様 20: Anvil リージョン形式](../spec/20-anvil-region.md)

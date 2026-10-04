# 03. リージョンファイル (.mca)

Anvil形式のリージョンファイルは、32×32 = 1024チャンクをまとめた入れ物です。
`r.<X>.<Z>.mca`という名前で、`region/`、`entities/`、`poi/`の各ディレクトリに置かれます。

このレイヤはチャンクの中身を解釈しません。NBTとして出し入れするだけです。
中身を扱いたい場合は[04](04-world-and-level-dat.md)と[05](05-blocks-and-biomes.md)を参照してください。

> コード例は基準実装のC#で示します。他の言語での綴りは[API対応表](../api/anvil.md)を参照してください。

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

`Flush`を呼ぶまでディスクは変わりません。
リージョン全体をメモリ上のセクタ表として持ち、まとめて書き出す設計です。

この設計のおかげで、開いて何も変えずに書き戻すと元とバイト単位で一致します。
触っていないチャンクの配置は動きません。そのため、1チャンクだけ書き換えるつもりがほかのチャンクまで破損させてしまう、という失敗は起きません。

---

## 3. ファイルの構造

```
0      4KiB          8KiB                     ファイル末尾
+------+-------------+------------------------+
| 位置 | タイムスタンプ | チャンク本体（4KiB 単位）  |
+------+-------------+------------------------+
```

- ロケーションテーブルは1024個 × 4バイト。上位3バイトが開始セクタ、下位1バイトがセクタ数
- タイムスタンプテーブルは1024個 × 4バイト。値はUnix秒
- 位置とタイムスタンプがどちらも0なら、そのチャンクは存在しない

チャンク本体は次の形をしています。

```
length: i32     このあとに続くバイト数（圧縮方式の 1 バイトを含む）
scheme: u8      圧縮方式
data:   ...     圧縮された NBT
```

詳細は[spec/20](../spec/20-anvil-region.md)。

---

## 4. 圧縮方式

| ID | 方式 | 本ライブラリ |
|---:|---|---|
| 1 | GZip | 対応 |
| 2 | Zlib | 対応（書き込みの既定） |
| 3 | 無圧縮 | 対応 |
| 4 | LZ4 | 読み込みのみ |
| 127 | サードパーティ独自 | 未対応（生バイトでのみ取得可） |

LZ4は読めますが、書き出せません。
LZ4のチャンクを書き換えると、そのチャンクだけZlibになります。
圧縮方式はチャンクごとに記録されるので、混在してもゲームは読めます。
触っていないチャンクは生バイトのまま保持するので、LZ4のまま残ります。

扱えない方式のチャンクを`ReadChunk`で読むと`UNSUPPORTED_FEATURE`になります。
中身が要らない場合（別のリージョンへ丸ごと移すだけ、など）は、生バイトで扱えます。

```csharp
RawChunk raw = region.ReadChunkRaw(5, 12)!;
other.WriteChunkRaw(5, 12, raw);   // 展開せずそのまま移す
```

---

## 5. 大きすぎるチャンク（.mcc）

1チャンクはロケーションテーブルの都合で255セクタ（約1MiB）までしか入りません。
これを超えると、Minecraftは本体を`c.<X>.<Z>.mcc`という別ファイルへ出します。

本ライブラリはこれを自動で処理します。

- 読むとき: `.mcc`があれば透過的に読む
- 書くとき: 255セクタに収まらなければ自動で`.mcc`へ出す。縮んだら本体へ戻して`.mcc`を消す

利用者が意識する必要はありません。

---

## 6. 断片化の解消

チャンクを書き換え続けるとセクタに隙間ができます。

```csharp
region.Optimize();   // 添字順に詰め直す
region.Flush();
```

必要なとき以外は呼ばなくて構いません。ファイル全体が書き換わるので、無変更なら元と一致するという性質は失われます。

---

## 7. フォルダ単位で扱う

複数のリージョンにまたがる操作には`RegionFolder`を使います。
`RegionFolder`は`r.X.Z.mca`の名前解決とファイルの開閉をまとめて引き受けます。

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

`RegionFile`はファイル全体をメモリへ載せます。
無変更で書き戻したときにバイト単位で一致させるための設計ですが、そのぶん開いたまま溜めるとメモリを食います。

`RegionFolder`は開いたリージョンの数に上限を持ち（既定8件）、上限を超えたら、最も長く使っていないものを書き出してから閉じます。
数千リージョンあるワールドを端から走査しても問題は起きません。

```csharp
// 上限を変えたい場合
using RegionFolder folder = RegionFolder.Open(path, RegionFileMode.ReadWrite,
                                              maxCachedRegions: 32);
```

このため、`Region()`が返した参照は、別のリージョンへアクセスすると閉じられる場合があります。

```csharp
RegionFile? a = folder.Region(0, 0);
folder.ReadChunk(9999, 9999);   // 別のリージョンを開く
// aはもう閉じられているかもしれない
```

参照を持ち回らず、必要になるたびに取得してください。
`ReadChunk` / `WriteChunk`経由で使うぶんには意識しなくて構いません。

## 9. 破損したファイルの検出

ファイルを開いた時点で次の点を検査し、問題があれば`MALFORMED_DATA`にします。

- ロケーションテーブルの指すセクタがファイルの外にある
- 2つのチャンクが同じセクタを使っている
- ファイル長が4KiBの倍数でない

エラーを出さずに読み進めると、書き戻したときに別のチャンクを破損させかねません。そのため、先に止める方針をとっています。

---

## 10. 次に読むもの

- [04. ワールドとlevel.dat](04-world-and-level-dat.md)
- [仕様20: Anvilリージョン形式](../spec/20-anvil-region.md)

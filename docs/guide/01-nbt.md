# 01. NBT の読み書き

NBT (Named Binary Tag) は Minecraft のあらゆるデータの土台となる形式。
このレイヤは**Minecraft のバージョンに一切依存しない**。

> このガイドのコード例は基準実装の **C#** で示す。
> 他の言語での綴りは [API 対応表](../api/nbt.md) を、
> 最初の一歩は [はじめに](../getting-started/) を参照。

---

## 1. 13 種類のタグ

| ID | タグ | 値 |
|---:|---|---|
| 0 | `TAG_End` | なし（Compound の終端） |
| 1 | `TAG_Byte` | `i8` |
| 2 | `TAG_Short` | `i16` |
| 3 | `TAG_Int` | `i32` |
| 4 | `TAG_Long` | `i64` |
| 5 | `TAG_Float` | `f32` |
| 6 | `TAG_Double` | `f64` |
| 7 | `TAG_Byte_Array` | `i8[]` |
| 8 | `TAG_String` | MUTF-8 の文字列 |
| 9 | `TAG_List` | 同じ型のタグの列 |
| 10 | `TAG_Compound` | 名前つきタグの集まり |
| 11 | `TAG_Int_Array` | `i32[]` |
| 12 | `TAG_Long_Array` | `i64[]` |

真偽値の専用型は無い。`TAG_Byte` の 0 / 1 で表す。
`GetBool` はこれを読みやすくするための糖衣にすぎない。

数値はすべて**ビッグエンディアン**、整数はすべて**符号つき**である。
詳細は [spec/10](../spec/10-nbt-binary.md)。

---

## 2. 読む

```csharp
NamedTag named = NbtIo.ReadFile("level.dat");
NbtCompound root = (NbtCompound)named.Tag;
```

圧縮方式（Gzip / Zlib / 無圧縮）は**先頭バイトから自動判定する**。
指定したい場合だけ `NbtReadOptions.Compression` を設定する。

### 型付き取得子

```csharp
int version = root.GetInt("DataVersion");     // 無い/型違いなら例外
int? maybe  = root.OptInt("DataVersion");     // 無ければ null、型違いなら例外
```

**「無い」と「型が違う」を区別している。** `Opt*` は前者だけを許す。
型が違うのは常にプログラム側の想定違いなので、黙って握りつぶさない。

### 入れ子をたどる

```csharp
NbtCompound data = root.GetCompound("Data");
NbtCompound version = data.GetCompound("Version");
Console.WriteLine(version.GetString("Name"));   // 26.2
```

---

## 3. 書く

```csharp
NbtCompound root = new NbtCompound();
root.Set("name", new NbtString("SpringNBTLibrary"));
root.Set("count", new NbtInt(42));
root.Set("flags", new NbtByteArray(new sbyte[] { 1, 0, 1 }));

NbtIo.WriteFile("out.nbt", new NamedTag("", root));
```

`NbtCompound` は**挿入順を保持する**。
これは飾りではなく、**触っていないデータを書き戻したときに
バイト単位で元と一致させるために必要**である。

### リストは要素型が 1 つ

`TAG_List` は全要素が同じ型でなければならない。
違う型を足そうとすると `UNEXPECTED_TAG_TYPE` になる。

```csharp
NbtList list = new NbtList();
list.Add(new NbtInt(1));
list.Add(new NbtString("x"));   // 例外
```

空のリストは要素型 `TAG_End` で書き出す。
ただし第三者のツールが別の要素型で空リストを書くことがあるので、
読むときはそれも受け入れる。

---

## 4. 圧縮とファイル形式

| 用途 | 圧縮 |
|---|---|
| `level.dat`、プレイヤーデータ | Gzip |
| リージョン内のチャンク | Zlib（既定） |
| ネットワーク経由 | 無圧縮が多い |

```csharp
NbtIo.WriteFile("out.nbt", named,
    new NbtWriteOptions { Compression = Compression.Gzip });
```

### Java 形式と Network 形式

| 形式 | ルート |
|---|---|
| `Java`（既定） | 名前つきの Compound |
| `Network` | **名前を持たない** Compound（1.20.2 以降） |

```csharp
NbtIo.ReadBytes(bytes, new NbtReadOptions { Format = NbtFormat.Network });
```

---

## 5. 文字列は MUTF-8

NBT の文字列は UTF-8 ではなく **MUTF-8**（Modified UTF-8）である。
標準の UTF-8 と 2 点だけ違う。

- `U+0000` を 1 バイトの `00` ではなく **2 バイトの `C0 80`** で書く
- BMP 外の文字（絵文字など）を 4 バイトではなく
  **サロゲートペア 2 つ（3 バイト × 2）**で書く

この差は普通のライブラリでは見落とされやすく、
絵文字を含む看板やアイテム名で壊れる原因になる。本ライブラリは全言語でこれを正しく扱う。

長さは 2 バイトの符号なし整数で表すので、**1 つの文字列は 65535 バイトまで**。

詳細は [spec/10 2章](../spec/10-nbt-binary.md#2-文字列-mutf-8)。

---

## 6. 次に読むもの

- [02. SNBT](02-snbt.md) — 人が読める形式との相互変換
- [03. リージョンファイル](03-anvil-region.md) — `.mca` を扱う
- [06. エラーと安全上限](06-errors-and-limits.md) — 壊れた入力への備え

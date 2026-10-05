# 01. NBTの読み書き

NBT（Named Binary Tag）は、Minecraftのあらゆるデータのもとになる形式です。
このレイヤはMinecraftのバージョンに一切依存しません。

> このガイドのコード例は基準実装のC#で示します。
> 他の言語での綴りは[API対応表](../api/nbt.md)を、
> 最初の一歩は[はじめに](../getting-started/)を参照してください。

---

## 1. 13種類のタグ

| ID | タグ | 値 |
|---:|---|---|
| 0 | `TAG_End` | なし（Compoundの終端） |
| 1 | `TAG_Byte` | `i8` |
| 2 | `TAG_Short` | `i16` |
| 3 | `TAG_Int` | `i32` |
| 4 | `TAG_Long` | `i64` |
| 5 | `TAG_Float` | `f32` |
| 6 | `TAG_Double` | `f64` |
| 7 | `TAG_Byte_Array` | `i8[]` |
| 8 | `TAG_String` | MUTF-8の文字列 |
| 9 | `TAG_List` | 同じ型のタグの列 |
| 10 | `TAG_Compound` | 名前つきタグの集まり |
| 11 | `TAG_Int_Array` | `i32[]` |
| 12 | `TAG_Long_Array` | `i64[]` |

真偽値の専用型はありません。`TAG_Byte`の0 / 1で表します。
`GetBool`はそれを読みやすく書くための糖衣です。

数値はすべてビッグエンディアン、整数はすべて符号つきです。
詳細は[spec/10](../spec/10-nbt-binary.md)。

---

## 2. 読む

```csharp
NamedTag named = NbtIo.ReadFile("level.dat");
NbtCompound root = named.Tag;
```

圧縮方式（Gzip / Zlib / 無圧縮）は先頭バイトから自動判定します。
指定したい場合だけ`NbtReadOptions.Compression`を設定します。

### 型付き取得子

```csharp
int version = root.GetInt("DataVersion");     // 無い/型違いなら例外
int? maybe  = root.OptInt("DataVersion");     // 無ければnull、型違いなら例外
```

「無い」と「型が違う」は区別しています。`Opt*`が許すのは前者だけです。
型が違うのは常にプログラム側の想定違いなので、握りつぶすことはしません。

### 連なったNBTを読む

`ReadBytes`は入力を1つのNBTとして読みます。
後ろにバイトが残っていたらエラーです。読み違えを見逃さないためです。

1つのバイト列にNBTが複数並んでいるなら、位置を指定して読み進めます。

```csharp
int offset = 0;

while (offset < bytes.Length)
{
    NbtReadResult result = NbtIo.ReadBytesAt(bytes, offset);
    Use(result.Tag);
    offset = result.End;   // 次はここから
}
```

全部まとめて受け取ることもできます。

```csharp
IReadOnlyList<NamedTag> tags = NbtIo.ReadBytesAll(bytes);
```

位置は渡したバイト列そのものを指すので、`ReadBytesAt`は圧縮されたデータを扱えません。

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

値を直に渡す設定子もあります。取得子と対になっています。

```csharp
root.SetString("name", "SpringNBTLibrary");
root.SetInt("count", 42);
root.SetBool("enabled", true);        // TAG_Byteの0 / 1になります
root.SetByteArray("flags", new sbyte[] { 1, 0, 1 });
```

`NbtCompound`は挿入順を保持します。
これは飾りではありません。触っていないデータを書き戻したときに、バイト単位で元と一致させるために必要です。

### リストは要素型が1つ

`TAG_List`は全要素が同じ型でなければなりません。
違う型を足そうとすると`UNEXPECTED_TAG_TYPE`になります。

```csharp
NbtList list = new NbtList();
list.Add(new NbtInt(1));
list.Add(new NbtString("x"));   // 例外
```

新しく作った空のリストは要素型`TAG_End`で書き出します。
ただし、第三者のツールが別の要素型で空リストを書くことがあるので、読むときはそれも受け入れ、書き戻すときもその要素型を残します。

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

### Java形式とNetwork形式

| 形式 | ルート |
|---|---|
| `Java`（既定） | 名前つきのCompound |
| `Network` | 名前を持たないCompound（1.20.2以降） |

```csharp
NbtIo.ReadBytes(bytes, new NbtReadOptions { Format = NbtFormat.Network });
```

---

## 5. 文字列はMUTF-8

NBTの文字列はUTF-8ではなくMUTF-8（Modified UTF-8）です。
標準のUTF-8と2点だけ違います。

- `U+0000`を1バイトの`00`ではなく2バイトの`C0 80`で書く
- BMP外の文字（絵文字など）を4バイトではなくサロゲートペア2つ（3バイト × 2）で書く

文字列を標準のUTF-8のまま扱うと、絵文字を含む看板やアイテム名がおかしくなります。
どの言語版もMUTF-8として読み書きします。

長さは2バイトの符号なし整数で表すので、1つの文字列は65535バイトまでです。

詳細は[spec/10 2章](../spec/10-nbt-binary.md#2-文字列-mutf-8)。

---

## 6. 次に読むもの

- [02. SNBT](02-snbt.md)（人が読める形式との相互変換）
- [03. リージョンファイル](03-anvil-region.md)（`.mca`を扱う）
- [06. エラーと安全上限](06-errors-and-limits.md)（不正な入力への備え）

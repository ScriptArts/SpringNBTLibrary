# 10. NBT バイナリ形式

NBT (Named Binary Tag) の読み書き仕様。**このレイヤは Minecraft のバージョンに一切依存しない。**
バージョン検査は [30 チャンク形式](30-chunk-format.md) 以降でのみ行う。

前提: [00 共通規約](00-conventions.md)（ビッグエンディアン、エラー分類、安全上限）

---

## 1. タグ型

| ID | 論理型名 | 型名 (Rust/C#/Java/Python) | ペイロード |
|---:|---|---|---|
| 0  | `End`       | `NbtEnd`       | なし |
| 1  | `Byte`      | `NbtByte`      | `i8` 1 バイト |
| 2  | `Short`     | `NbtShort`     | `i16` 2 バイト |
| 3  | `Int`       | `NbtInt`       | `i32` 4 バイト |
| 4  | `Long`      | `NbtLong`      | `i64` 8 バイト |
| 5  | `Float`     | `NbtFloat`     | `f32` 4 バイト (IEEE 754 binary32) |
| 6  | `Double`    | `NbtDouble`    | `f64` 8 バイト (IEEE 754 binary64) |
| 7  | `ByteArray` | `NbtByteArray` | `i32` 長さ + `i8` × 長さ |
| 8  | `String`    | `NbtString`    | `u16` バイト長 + MUTF-8 バイト列 |
| 9  | `List`      | `NbtList`      | `u8` 要素型ID + `i32` 個数 + ペイロード × 個数 |
| 10 | `Compound`  | `NbtCompound`  | 名前付きタグの並び + `TAG_End` (0x00) |
| 11 | `IntArray`  | `NbtIntArray`  | `i32` 長さ + `i32` × 長さ |
| 12 | `LongArray` | `NbtLongArray` | `i32` 長さ + `i64` × 長さ |

未知のタグID（13以上、または負値）を読んだ場合は `MALFORMED_DATA`。

### 1.1 名前付きタグ

`TAG_Compound` の中身は「名前付きタグ」の並びで、各要素は次の3つ組で表される。

```
u8   タグID
u16  名前のバイト長      -- タグIDが 0 (TAG_End) の場合は名前ごと存在しない
...  MUTF-8 の名前
...  ペイロード
```

`TAG_End` は 1 バイト `0x00` のみで、名前もペイロードも持たない。

### 1.2 長さフィールドの検証

`ByteArray` / `IntArray` / `LongArray` / `List` の長さは `i32`（符号付き）である。

- **負値** → `MALFORMED_DATA`
- 長さ × 要素バイト数が**残り入力バイト数を超える** → 確保する前に `MALFORMED_DATA`

この先行検証により、`0x7FFFFFFF` を宣言しただけの数バイトの入力でメモリを枯渇させられない。

---

## 2. 文字列: MUTF-8

NBT の文字列は UTF-8 ではなく **Modified UTF-8 (MUTF-8)** である。
Java の `DataInput.readUTF` / `DataOutput.writeUTF` と同じ符号化で、標準 UTF-8 と次の2点が異なる。

| 対象 | 標準 UTF-8 | MUTF-8 |
|---|---|---|
| `U+0000` | `00`（1バイト） | `C0 80`（2バイト） |
| `U+10000`〜`U+10FFFF` | 4バイト1シーケンス | サロゲートペアに分解し **3バイト × 2**（CESU-8） |

符号化規則:

```
U+0001 .. U+007F   ->  0xxxxxxx                                  (1 バイト)
U+0000, U+0080 ..
       U+07FF      ->  110xxxxx 10xxxxxx                         (2 バイト)
U+0800 .. U+FFFF   ->  1110xxxx 10xxxxxx 10xxxxxx                (3 バイト)
U+10000 ..         ->  上位/下位サロゲートへ分解し、各々を 3 バイトで符号化
```

長さフィールドは**符号化後のバイト数**を表す `u16` であり、最大 65535 バイト。
文字数ではないことに注意する。書き込み時に 65535 を超えたら `INVALID_ARGUMENT`。

### 2.1 復号時の扱い

- 孤立サロゲート（対にならない `U+D800`〜`U+DFFF`）は**そのまま保持する**。
  Minecraft の実データには通常現れないが、破損データを黙って変換すると
  ラウンドトリップでバイトが変わってしまうため、失われないようにする。
- 冗長な符号化（例: `U+0041` を 2 バイトで表現）は `MALFORMED_DATA` とする。
  ただし `U+0000` の `C0 80` は MUTF-8 として正当なので受理する。
- 継続バイトが `10xxxxxx` でない、途中で入力が尽きた → `MALFORMED_DATA`

### 2.2 Compound のキー

`TAG_Compound` のキーも MUTF-8 の文字列だが、**値と違い孤立サロゲートを許さない**。
UTF-8 へ写せないキーを読んだ場合は `MALFORMED_DATA` とする。

Minecraft が書き出すキーは実際には ASCII の識別子のみであり、
そこに孤立サロゲートが現れるのはデータ破損を意味する。
またキーをすべての言語で「ただの文字列」として扱えることが、
マップ型をそのまま使えるという実装上の大きな利点につながる。

### 2.3 各言語での保持方法

| 言語 | 内部表現 | 孤立サロゲートの扱い |
|---|---|---|
| C# | `string`（UTF-16） | そのまま保持できる |
| Java | `String`（UTF-16） | そのまま保持できる |
| TypeScript | `string`（UTF-16） | そのまま保持できる |
| Python | `str`（コードポイント列） | サロゲートを単独の文字として保持できる |
| Rust | `String`（UTF-8） | UTF-8 に写せないため、専用の表現へ退避する |

**Rust だけは UTF-8 の不変条件がある**ため、`NbtString` を

```
enum NbtString {
    Text(String),         // UTF-8 として表せる通常の文字列。実データはほぼすべてこちら
    Surrogates(Vec<u16>), // UTF-8 に写せない UTF-16 コード単位の列
}
```

という 2 形態の型として定義する。通常の入力では常に `Text` になる。

---

## 3. ファイル形式とルートタグ

`NbtFormat` は2種類。

| 値 | 用途 | ルートの構造 |
|---|---|---|
| `Java` | `level.dat`、チャンク、`.nbt` ファイル全般 | `u8` タグID(=10) + `u16` 名前長 + 名前 + Compound ペイロード |
| `Network` | 1.20.2 以降のネットワークプロトコル | `u8` タグID(=10) + Compound ペイロード（**名前なし**） |

`Java` 形式のルート名は通常空文字列だが、値は保持し、書き込み時にそのまま出力する。
ルートタグが `TAG_Compound` 以外だった場合は `MALFORMED_DATA`。

読み書きの入口は次の論理APIに統一する。

```
NbtIo.read_file(path, options)        -> NamedTag
NbtIo.read_bytes(bytes, options)      -> NamedTag
NbtIo.write_file(path, named_tag, options)
NbtIo.write_bytes(named_tag, options) -> bytes

NamedTag { name: String, tag: NbtCompound }
```

`read_bytes` は入力を 1 つの NBT として読む。
ルートタグの後にバイトが残っていたら `MALFORMED_DATA` とする。
読み違えを黙って見逃さないためである。

### 3.1 連なった NBT を読む

1 つのバイト列に NBT が複数並んでいることがある。
この形は `read_bytes` では読めないので、専用の入口を用意する。

```
NbtIo.read_bytes_at(bytes, offset, options)  -> NbtReadResult
NbtIo.read_bytes_all(bytes, options)         -> NamedTag の一覧

NbtReadResult { tag: NamedTag, end: 整数 }
```

`read_bytes_at` は `offset` から NBT を 1 つ読み、
読み終わった直後の位置を `end` に入れて返す。
`end` を次の `offset` として渡せば、順に読み進められる。

```
offset = 0
while offset < len(bytes):
    result = read_bytes_at(bytes, offset)
    使う(result.tag)
    offset = result.end
```

`read_bytes_all` は入力を使い切るまで読み、読んだ順に並べて返す。
空のバイト列は「0 個」であってエラーではない。

| 条件 | 結果 |
|---|---|
| `offset` が負、または入力長を超える | `INVALID_ARGUMENT` |
| `read_bytes_at` に圧縮を指定した | `INVALID_ARGUMENT` |
| 途中で入力が尽きた | `MALFORMED_DATA` |

**`read_bytes_at` の位置は、渡したバイト列そのものを指す。**
展開すると位置が変わってしまうので、圧縮されたデータは扱えない。
`read_bytes_all` は位置を返さないので、
入力全体に 1 回かかった圧縮であれば展開してから読む。

---

## 4. 圧縮

`Compression` は4値。

| 値 | 内容 | 判定に使う先頭バイト |
|---|---|---|
| `None` | 無圧縮 | `0x0A`（TAG_Compound のID） |
| `Gzip` | RFC 1952 | `1F 8B` |
| `Zlib` | RFC 1950 (zlib ラッパ付き deflate) | `78`（`78 01` / `78 9C` / `78 DA` など） |
| `Auto` | 読み込み時のみ指定可。上記から自動判定 | — |

`Auto` は先頭 2 バイトで判定する。

1. `1F 8B` → `Gzip`
2. 先頭バイトの下位4bit が `8`（=deflate 圧縮法）かつ 先頭2バイトを `u16` ビッグエンディアンとして読んだ値が 31 の倍数 → `Zlib`
3. 先頭バイトが `0x0A` → `None`
4. いずれでもない → `MALFORMED_DATA`

書き込み時に `Auto` を指定した場合は `INVALID_ARGUMENT`。
`level.dat` の既定は `Gzip`、リージョン内チャンクの既定は `Zlib`（→ [20](20-anvil-region.md)）。

---

## 5. 正準書き出し (Canonical Writer)

ラウンドトリップ検証を成立させるため、書き出しは**一意**でなければならない。

- `NbtCompound` は**挿入順**で書き出す。ソートしない
- `NbtList` の要素型IDは、要素が1つ以上あればその型、空なら `End`(0) を書く
- `f32` / `f64` は NaN も含めビットパターンをそのまま書く（正規化しない）
- 圧縮は結果バイト列が実装依存になるため、**ラウンドトリップ検証は展開後のバイト列で行う**

空 `NbtList` の要素型については、読み込んだ値が `End` 以外（例: 実装によっては `Byte`）
だった場合も**読んだ値をそのまま保持して書き戻す**。Minecraft 側が生成した値を壊さないため。

---

## 6. 読み書きオプション

```
ReadOptions {
    format: NbtFormat = Java
    compression: Compression = Auto
    max_depth: i32 = 512
    max_decompressed_size: i64 = -1   // -1 は無制限
}

WriteOptions {
    format: NbtFormat = Java
    compression: Compression = Gzip
}
```

---

## 7. コンテナ型の振る舞い

### 7.1 `NbtCompound`

- **挿入順を保持**するマップ（Rust: `IndexMap` 相当の自前実装 / C#: `OrderedDictionary` 相当 / Java: `LinkedHashMap` / Python: `dict`）
- 同名キーの再設定は**位置を維持したまま値を置き換える**
- 型付き取得子 `get_int(key)` 等は、キーが無い場合と型が違う場合を区別する
  - キーが無い → `None` / `null` を返す取得子（`opt_int`）と、エラーにする取得子（`get_int`）の両方を用意する
  - 型が違う → 常に `UNEXPECTED_TAG_TYPE`
- 型付き設定子 `set_int(key, value)` 等を、取得子と対で用意する
  - `set(key, NbtInt(42))` と書かずに済ませるための糖衣であり、動きは `set` と同じ
  - 真偽値は専用型が無いので、`set_bool` は `TAG_Byte` の 0 / 1 として書く
  - 対象は `byte` `short` `int` `long` `float` `double` `bool` `string`
    `byte_array` `int_array` `long_array` の 11 種

### 7.2 `NbtList`

- 要素型は1つに強制される。異なる型を追加しようとしたら `UNEXPECTED_TAG_TYPE`
- 空リストの要素型は `End`
- 空リストに最初の要素を追加すると、要素型がその型に確定する
- 全要素を削除しても、確定済みの要素型は**維持する**（読み書きの往復で型が消えないように）

### 7.3 等値比較と複製

どのタグ型も、値としての等値比較と深い複製を提供する。
言語ごとの綴りは [API 対応表](../api/nbt.md) を参照。

等値比較の規則は全言語で同じでなければならない。

| 対象 | 規則 |
|---|---|
| タグ型が違うもの同士 | 値が同じでも**等しくない**（`NbtInt(1)` ≠ `NbtShort(1)`） |
| `Float` / `Double` | 値ではなく**ビットパターン**で比べる。`NaN` 同士は等しく、`+0.0` と `-0.0` は等しくない |
| 配列 | 長さと、同じ位置の要素がすべて一致すること |
| `NbtList` | 要素型が一致し、同じ位置の要素がすべて一致すること |
| `NbtCompound` | キーと値が**挿入順も含めて**一致すること |

`Float` / `Double` をビットパターンで比べるのは、
正準書き出し（5章）がビットパターンをそのまま書くためである。
値で比べると「等しいのに書き出すと違うバイト列になる」組み合わせが生じる。

`NbtCompound` の並び順を等価性に含めるのも同じ理由で、
順序が違えば書き出したバイト列も違う。

複製は**深いコピー**とする。複製したタグをいくら書き換えても元に影響しない。

---

## 8. 関連

- SNBT テキスト表現 → [11 SNBT](11-snbt.md)
- 適合性テストベクタ → [90 適合性](90-conformance.md)

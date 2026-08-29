# 00. 共通規約

本書は SpringNBTLibrary の全言語実装が従う共通規約を定める。
各言語の実装は本書と本ディレクトリ配下の仕様書を**唯一の正**として実装される。

- 対象: Minecraft **Java版 26.2**（DataVersion `4903` / Protocol `776`）
- 過去バージョンのワールドデータ改変は非サポート（→ [07 バージョンポリシー](../guide/07-version-policy.md)）

---

## 1. 用語

| 用語 | 意味 |
|---|---|
| タグ (Tag) | NBT の値の単位。13種の型を持つ |
| ルートタグ | ファイル／バイト列の最上位タグ。Java版では常に TAG_Compound |
| リージョン | 32×32 チャンクをまとめた `.mca` ファイル |
| セクタ (Sector) | リージョンファイル内の 4096 バイト単位のブロック |
| チャンク (Chunk) | 16×16 ブロック、Y方向はワールド全高の縦柱 |
| セクション (Section) | チャンクを Y方向に 16 ブロックずつ区切った 16×16×16 の立方体 |
| パレット (Palette) | セクション内で使われるブロック状態／バイオームの一覧 |
| ビットストレージ (BitStorage) | パレット添字を 64bit 整数配列に詰めた表現 |
| 論理名 | 言語をまたいで同一の概念を指す名前。本仕様書での表記 |

---

## 2. バイト順と数値型

NBT および Anvil のすべての多バイト数値は **ビッグエンディアン**、
整数は **2の補数表現の符号付き**、浮動小数点は **IEEE 754** とする。

論理型と各言語の対応は以下で固定する。

| 論理型 | ビット幅 | C# | Java | TypeScript | Python | Rust |
|---|---|---|---|---|---|---|
| `i8`  | 8  | `sbyte`  | `byte`   | `number`（範囲検証あり） | `int`（範囲検証あり） | `i8`  |
| `i16` | 16 | `short`  | `short`  | `number`（範囲検証あり） | `int`（範囲検証あり） | `i16` |
| `i32` | 32 | `int`    | `int`    | `number`（範囲検証あり） | `int`（範囲検証あり） | `i32` |
| `i64` | 64 | `long`   | `long`   | **`bigint`** | `int`（範囲検証あり） | `i64` |
| `f32` | 32 | `float`  | `float`  | `number`（f32 に丸めて保持） | `float`（f32 に丸めて保持） | `f32` |
| `f64` | 64 | `double` | `double` | `number` | `float` | `f64` |

配列型は次のとおり。

| 論理型 | C# | Java | TypeScript | Python | Rust |
|---|---|---|---|---|---|
| `i8[]`  | `sbyte[]` | `byte[]` | `Int8Array`     | `list[int]` | `Vec<i8>`  |
| `i32[]` | `int[]`   | `int[]`  | `Int32Array`    | `list[int]` | `Vec<i32>` |
| `i64[]` | `long[]`  | `long[]` | `BigInt64Array` | `list[int]` | `Vec<i64>` |

**幅を持たない言語での注意点**

- **Python** は整数幅を持たないため、**構築時と書き込み時の双方で範囲検証**を行い、
  範囲外なら `ErrorCode.INVALID_ARGUMENT` を送出する。
  `f32` は `struct.pack('>f', ...)` 相当の丸めを構築時に適用する
- **TypeScript** の `number` は倍精度で、`i32` までは正確だが `i64` を表せない。
  そのため **`i64` だけは `bigint` を使う**（→ [adr/0007](../adr/0007-typescript-bigint.md)）。
  `i8` / `i16` / `i32` は `number` のまま範囲検証を行い、
  `f32` は `Math.fround` で丸める

---

## 3. 命名変換規則

論理名は **型名を `PascalCase`、メンバ名を `snake_case`、定数を `SCREAMING_SNAKE_CASE`** で表記する。
各言語実装はこの論理名から下表の規則で機械的に変換した名前を用いる。
`spec/tools/check_docs_sync.py` はこの規則を使って全言語の公開APIを論理名へ写し、突き合わせる。

| 種別 | 論理名 | C# | Java | TypeScript | Python | Rust |
|---|---|---|---|---|---|---|
| 型・列挙 | `NbtCompound` | `NbtCompound` | `NbtCompound` | `NbtCompound` | `NbtCompound` | `NbtCompound` |
| 列挙の値 | `LongArray` | `LongArray` | `LONG_ARRAY` | `LongArray` | `LONG_ARRAY` | `LongArray` |
| 関数・メソッド | `read_file` | `ReadFile` | `readFile` | `readFile` | `read_file` | `read_file` |
| 取得子 | `data_version` | `DataVersion`（プロパティ） | `dataVersion()` | `dataVersion`（getter） | `data_version`（`@property`） | `data_version()` |
| 設定子 | `set_data_version` | `DataVersion`（setter） | `setDataVersion()` | `dataVersion`（setter） | `data_version`（setter） | `set_data_version()` |
| 定数 | `TARGET_DATA_VERSION` | `TargetDataVersion` | `TARGET_DATA_VERSION` | `TARGET_DATA_VERSION` | `TARGET_DATA_VERSION` | `TARGET_DATA_VERSION` |
| モジュール | `nbt` | `SpringNBTLibrary.Nbt` | `...springnbt.nbt` | `spring-nbt-library/nbt` | `spring_nbt_library.nbt` | `spring_nbt_library::nbt` |

真偽値を返す取得子は論理名を `is_*` / `has_*` で始める。
C# は `Is*` / `Has*` のプロパティ、Java は `is*()` / `has*()` のメソッドとする。

---

## 4. エラー分類

エラーは全言語で**同一の `ErrorCode`** を持つ単一の例外／エラー型で表す。
コード集合が一致していることは docs-sync で検証される。

| `ErrorCode` | 意味 | 典型例 |
|---|---|---|
| `IO` | 下位の入出力失敗 | ファイルが無い、読み取り権限が無い |
| `MALFORMED_DATA` | バイト列が仕様に反する | 未知のタグID、途中で入力が尽きた |
| `UNEXPECTED_TAG_TYPE` | 期待した型と違うタグを取り出した | `get_int("x")` に String が入っていた |
| `UNSUPPORTED_FEATURE` | 仕様上は妥当だが本ビルドで扱えない | LZ4 依存を入れずに圧縮ID=4 を読んだ |
| `LIMIT_EXCEEDED` | 安全上限を超えた | ネスト深さ 512 超、宣言長が入力長を超える |
| `INVALID_ARGUMENT` | 呼び出し側の引数が不正 | 座標がチャンク範囲外、`i8` に 300 を渡した |
| `UNSUPPORTED_DATA_VERSION` | 対象バージョン外のデータ | DataVersion 4903 以外を既定設定で書き戻そうとした |

各言語での表現:

| 言語 | 表現 |
|---|---|
| C# | `SpringNbtException : Exception`（`ErrorCode Code` プロパティ、`InnerException` に原因） |
| Java | `SpringNbtException extends RuntimeException`（`ErrorCode code()`、`getCause()` に原因） |
| TypeScript | `SpringNbtError extends Error`（`code` プロパティ、`cause` に原因） |
| Python | `SpringNbtError(Exception)`（`code` 属性、`__cause__` に原因） |
| Rust | `pub struct Error { code: ErrorCode, message: String, source: Option<...> }` を `Result<T, Error>` で返す |

`IO` は下位の入出力例外を必ず原因として保持し、握り潰さない。
Java は検査例外を使わず、`IOException` を `ErrorCode.IO` でラップして送出する
（全言語でシグネチャを揃えるため。→ [adr/0005](../adr/0005-unified-error-model.md)）。

---

## 5. 安全上限（既定値）

悪意ある／破損した入力で無制限にメモリを確保しないため、読み込み時に上限を設ける。
全言語で同じ既定値を用い、`ReadOptions` で変更できる。

| 項目 | 既定値 | 超過時 |
|---|---|---|
| ネスト深さ | 512 | `LIMIT_EXCEEDED` |
| 配列・リストの要素数 | 制限なし（ただし宣言長 > 残り入力長 なら即エラー） | `MALFORMED_DATA` |
| 展開後の総バイト数 | 制限なし（`max_decompressed_size` で設定可） | `LIMIT_EXCEEDED` |

**宣言長の先行検証**: `TAG_Byte_Array` などの長さフィールドを読んだ時点で、
残り入力バイト数から必要バイト数を満たせないと分かる場合は、確保する前にエラーとする。

### 5.1 深さ上限と実行スタック

読み込み・書き出し・SNBT の処理はいずれも**再帰**で実装されている。
そのため深さ上限は「実行時スタックが尽きる前に必ず `LIMIT_EXCEEDED` を返す」値でなければならない。
既定の 512 はどの言語でも通常の実行環境で安全に扱えるが、言語ごとに事情が違う。

| 言語 | 事情 | 対応 |
|---|---|---|
| C# / Java | 既定のスタック（1MiB 前後）で 512 段を扱える | 対応不要 |
| TypeScript | V8 の既定コールスタックで 512 段を扱える | 対応不要 |
| Python | **既定の再帰上限 1000 が 512 段に届かない** | 読み書きの間だけ再帰上限を一時的に引き上げる |
| Rust | release ビルドは 1 段あたり約 1 KB。**debug ビルドは約 8 KB** | 既定の 512 は release で安全。debug ビルドや小さいスレッドスタックでは注意 |

**`max_depth` を既定より大きくする場合**、Rust では実行スレッドのスタックを増やすこと
（`std::thread::Builder::stack_size(...)`、または環境変数 `RUST_MIN_STACK`）。
Minecraft の実データのネストは 10 段程度なので、既定値を触る必要は通常ない。

---

## 6. 正規化JSON（適合性検証の中間表現）

全言語のデコード結果を機械比較するための言語非依存な表現。
浮動小数点の文字列化やロング整数の精度で差が出ないよう、**厳密に一意な形**に定める。

```json
{
  "format": "java",
  "root_name": "",
  "root": { "type": "compound", "value": [] }
}
```

タグの表現:

| 型 | JSON |
|---|---|
| `byte` `short` `int` | `{"type":"int","value":42}`（JSON 数値） |
| `long` | `{"type":"long","value":"-9223372036854775808"}`（**10進文字列**） |
| `float` | `{"type":"float","value":"0x3f800000"}`（**IEEE754 ビットパターンの16進**） |
| `double` | `{"type":"double","value":"0x3ff0000000000000"}`（同上） |
| `byte_array` `int_array` | `{"type":"int_array","value":[1,2,3]}` |
| `long_array` | `{"type":"long_array","value":["1","2"]}`（10進文字列の配列） |
| `string` | `{"type":"string","value":"あ","mutf8":"e38182"}` |
| `list` | `{"type":"list","element_type":"int","value":[ ... ]}` |
| `compound` | `{"type":"compound","value":[["key",{...}],["key2",{...}]]}` |

設計意図:

- **float/double はビットパターン**で表す。10進表記は言語ごとの丸め・桁数差で不一致になるため
- **long は文字列**で表す。JSON 数値は倍精度に落ちる処理系があるため
- **compound はキーと値の組の配列**で表す。JSON オブジェクトだと挿入順の保持が処理系依存になるため
- **string は `mutf8` を必ず併記**する。孤立サロゲートなど UTF-8 に写せない値を厳密に比較するため

詳細と検証手順は [90 適合性](90-conformance.md) を参照。

---

## 7. 関連文書

- [10 NBT バイナリ形式](10-nbt-binary.md)
- [11 SNBT](11-snbt.md)
- [20 Anvil リージョン形式](20-anvil-region.md)
- [30 チャンク形式](30-chunk-format.md)
- [31 パレット付きコンテナ](31-paletted-container.md)
- [40 ワールドのディレクトリ構成](40-world-layout.md)
- [90 適合性](90-conformance.md)

# 06. エラーと安全上限

エラーの分類は全言語で完全に一致します。
言語ごとに違うのは、エラーを例外で投げるか`Result`で返すかだけです。

---

## 1. ErrorCode

| コード | 意味 | 例 |
|---|---|---|
| `IO` | 入出力の失敗 | ファイルが無い、権限が無い |
| `MALFORMED_DATA` | バイト列が仕様に反する | 未知のタグID、途中で入力が尽きた |
| `UNEXPECTED_TAG_TYPE` | 期待した型と違うタグを取り出した | `GetInt("x")`にStringが入っていた |
| `UNSUPPORTED_FEATURE` | 仕様上は妥当だが本ビルドで扱えない | 圧縮ID=127のチャンクを`ReadChunk`で読んだ、圧縮ID=4（LZ4）を指定してチャンクを書こうとした |
| `LIMIT_EXCEEDED` | 安全上限を超えた | ネスト深さ512超 |
| `INVALID_ARGUMENT` | 呼び出し側の引数が不正 | 座標がチャンク範囲外、`i8`に300を渡した |
| `UNSUPPORTED_DATA_VERSION` | 扱える形式より古いデータ | DataVersion 4786未満のチャンクを既定設定で書き戻そうとした |

### 使い分けの考え方

`MALFORMED_DATA`と`INVALID_ARGUMENT`の境目は「誰の間違いか」で決まります。

- ファイルの中身がおかしい → `MALFORMED_DATA`
- 呼び出し側が渡した値がおかしい → `INVALID_ARGUMENT`

たとえば`BlockState.Parse("minecraft:stone[")`は、呼び出し側が渡した文字列の誤りなので`INVALID_ARGUMENT`になります。

---

## 2. 言語ごとの表現

| 言語 | 表現 |
|---|---|
| C# | `SpringNbtException : Exception`（`Code`プロパティ、`InnerException`に原因） |
| Java | `SpringNbtException extends RuntimeException`（`code()`、`getCause()`に原因） |
| TypeScript | `SpringNbtError extends Error`（`code`、`cause`に原因） |
| Python | `SpringNbtError(Exception)`（`code`属性、`__cause__`に原因） |
| Rust | `Result<T, Error>`（`Error`は`code()`と`message()`を持つ） |

```csharp
try
{
    NbtIo.ReadFile(path);
}
catch (SpringNbtException error) when (error.Code == ErrorCode.MalformedData)
{
    // 破損したファイルとして扱う
}
```

```rust
match read_file(path, &NbtReadOptions::default()) {
    Ok(named) => { /* ... */ }
    Err(error) if error.code() == ErrorCode::MalformedData => { /* ... */ }
    Err(error) => return Err(error),
}
```

### Javaは検査例外を使わない

`IOException`は`ErrorCode.IO`で包んで非検査例外として投げます。
全言語でメソッドのシグネチャを揃えるためです（[adr/0005](../adr/0005-unified-error-model.md)）。
原因の例外は`getCause()`から取れるので、情報は失われません。

---

## 3. 安全上限

信用できないNBTファイルを読むときに、悪意ある入力で無制限にメモリを確保させられないよう、上限を設けています。

| 項目 | 既定値 | 超過時 |
|---|---|---|
| ネスト深さ | 512 | `LIMIT_EXCEEDED` |
| 配列・リストの要素数 | 制限なし（宣言長 > 残り入力長なら即エラー） | `MALFORMED_DATA` |
| 展開後の総バイト数 | 制限なし（設定可） | `LIMIT_EXCEEDED` |

```csharp
NbtReadOptions options = new NbtReadOptions
{
    MaxDepth = 64,
    MaxDecompressedSize = 16 * 1024 * 1024,
};
```

### 宣言長は確保前に検証する

`TAG_Byte_Array`の長さに`0x7FFFFFFF`と書いてあっても、実際の残り入力がそれに足りなければ、確保する前にエラーにします。
「2GB確保してから足りないと気づく」という動きはしません。

---

## 4. Rustのスタックに注意

読み込み・書き出し・SNBTはいずれも再帰で実装しています。
既定の深さ512はどの言語でも安全に扱えますが、Rustだけは事情があります。

debugビルドでは1段あたり約8 KBを使います（releaseでは約1 KB）。
512段で4 MBになり、既定のスレッドスタックによっては足りません。

深いデータを扱うなら、大きめのスタックを持つスレッドで走らせてください。

```rust
std::thread::Builder::new()
    .stack_size(32 * 1024 * 1024)
    .spawn(|| { /* 深いNBTを読む */ })?
    .join()
    .unwrap();
```

Pythonも既定の再帰上限（1000）では深さ512に届きませんが、ライブラリ側で一時的に引き上げているので、利用者の対応は不要です。

詳細は[spec/00 5.1](../spec/00-conventions.md#51-深さ上限と実行スタック)。

---

## 5. 破損したデータを推測で取り繕わない

破損したデータを推測で修復することはしません。

たとえばパレットの添字が範囲外を指しているとき、0番目で代替すれば「読める」ようにはなります。
しかし、それを書き戻すと、破損したデータが破損していないように見える形で保存されてしまいます。

そこで、明示的に`MALFORMED_DATA`を返します。

例外は1つだけで、第三者ツールが書いた非正準な`BitStorage`を救済するための`lenient_bit_storage`オプションがあります。
このオプションは明示的に有効にしたときだけ働きます。

```csharp
ChunkReadOptions options = new ChunkReadOptions { LenientBitStorage = true };
```

---

## 6. 次に読むもの

- [07. バージョンポリシー](07-version-policy.md)
- [仕様00: 共通規約](../spec/00-conventions.md)

# 06. エラーと安全上限

エラーの分類は**全言語で完全に一致する**。
言語ごとに違うのは、それを例外で投げるか `Result` で返すかだけである。

---

## 1. ErrorCode

| コード | 意味 | 例 |
|---|---|---|
| `IO` | 入出力の失敗 | ファイルが無い、権限が無い |
| `MALFORMED_DATA` | バイト列が仕様に反する | 未知のタグID、途中で入力が尽きた |
| `UNEXPECTED_TAG_TYPE` | 期待した型と違うタグを取り出した | `GetInt("x")` に String が入っていた |
| `UNSUPPORTED_FEATURE` | 仕様上は妥当だが本ビルドで扱えない | LZ4 依存を入れずに圧縮ID=4 を読んだ |
| `LIMIT_EXCEEDED` | 安全上限を超えた | ネスト深さ 512 超 |
| `INVALID_ARGUMENT` | 呼び出し側の引数が不正 | 座標がチャンク範囲外、`i8` に 300 を渡した |
| `UNSUPPORTED_DATA_VERSION` | 対象バージョン外のデータ | DataVersion 4903 以外を既定設定で書き戻そうとした |

### 使い分けの考え方

`MALFORMED_DATA` と `INVALID_ARGUMENT` の境目は
**「誰の間違いか」**で決まる。

- ファイルの中身がおかしい → `MALFORMED_DATA`
- 呼び出し側が渡した値がおかしい → `INVALID_ARGUMENT`

たとえば `BlockState.Parse("minecraft:stone[")` は
呼び出し側が渡した文字列の誤りなので `INVALID_ARGUMENT` になる。

---

## 2. 言語ごとの表現

| 言語 | 表現 |
|---|---|
| C# | `SpringNbtException : Exception`（`Code` プロパティ、`InnerException` に原因） |
| Java | `SpringNbtException extends RuntimeException`（`code()`、`getCause()` に原因） |
| TypeScript | `SpringNbtError extends Error`（`code`、`cause` に原因） |
| Python | `SpringNbtError(Exception)`（`code` 属性、`__cause__` に原因） |
| Rust | `Result<T, Error>`（`Error` は `code()` と `message()` を持つ） |

```csharp
try
{
    NbtIo.ReadFile(path);
}
catch (SpringNbtException error) when (error.Code == ErrorCode.MalformedData)
{
    // 壊れたファイルとして扱う
}
```

```rust
match read_file(path, &NbtReadOptions::default()) {
    Ok(named) => { /* ... */ }
    Err(error) if error.code() == ErrorCode::MalformedData => { /* ... */ }
    Err(error) => return Err(error),
}
```

### Java は検査例外を使わない

`IOException` は `ErrorCode.IO` で包んで非検査例外として投げる。
全言語でメソッドのシグネチャを揃えるためである（[adr/0005](../adr/0005-unified-error-model.md)）。
原因の例外は `getCause()` から取れるので、情報は失われない。

---

## 3. 安全上限

信用できない NBT ファイルを読むとき、
悪意ある入力で無制限にメモリを確保させられないよう上限を設けている。

| 項目 | 既定値 | 超過時 |
|---|---|---|
| ネスト深さ | 512 | `LIMIT_EXCEEDED` |
| 配列・リストの要素数 | 制限なし（宣言長 > 残り入力長 なら即エラー） | `MALFORMED_DATA` |
| 展開後の総バイト数 | 制限なし（設定可） | `LIMIT_EXCEEDED` |

```csharp
NbtReadOptions options = new NbtReadOptions
{
    MaxDepth = 64,
    MaxDecompressedSize = 16 * 1024 * 1024,
};
```

### 宣言長は確保前に検証する

`TAG_Byte_Array` の長さに `0x7FFFFFFF` と書いてあっても、
実際の残り入力がそれに足りなければ**確保する前に**エラーにする。
「2GB 確保してから足りないと気づく」という動きはしない。

---

## 4. Rust のスタックに注意

読み込み・書き出し・SNBT はいずれも再帰で実装している。
既定の深さ 512 はどの言語でも安全に扱えるが、Rust だけは事情がある。

**debug ビルドでは 1 段あたり約 8 KB を使う**（release では約 1 KB）。
512 段で 4 MB になり、既定のスレッドスタックによっては足りない。

深いデータを扱うなら、大きめのスタックを持つスレッドで走らせること。

```rust
std::thread::Builder::new()
    .stack_size(32 * 1024 * 1024)
    .spawn(|| { /* 深い NBT を読む */ })?
    .join()
    .unwrap();
```

Python も既定の再帰上限（1000）が深さ 512 に届かないが、
これは**ライブラリ側で一時的に引き上げている**ので利用者の対応は要らない。

詳細は [spec/00 5.1](../spec/00-conventions.md#51-深さ上限と実行スタック)。

---

## 5. 壊れたデータに黙って合わせない

本ライブラリは**推測で修復しない**。

たとえばパレットの添字が範囲外を指しているとき、
0 番目で代替すれば「読める」ようにはなる。
しかしそれを書き戻すと、壊れたデータが
**壊れていないように見える形で**保存されてしまう。

そこで明示的に `MALFORMED_DATA` を返す。

例外は 1 つだけで、第三者ツールが書いた非正準な `BitStorage` を
救済するための `lenient_bit_storage` オプションがある。
これは**明示的に有効にしたときだけ**働く。

```csharp
ChunkReadOptions options = new ChunkReadOptions { LenientBitStorage = true };
```

---

## 6. 次に読むもの

- [07. バージョンポリシー](07-version-policy.md)
- [仕様 00: 共通規約](../spec/00-conventions.md)

# 0005. 全言語で共通のエラーモデルを使う

- 状態: 採用
- 日付: 2026-08-29

## 背景

エラー表現は言語ごとに大きく異なる（Rustの`Result`、Javaの検査例外、C# / TypeScript / Pythonの非検査例外）。
そのままだと、「同じ入力に対して同じエラーになる」ことを検証できない。

## 決定

**共通の`ErrorCode`列挙を全言語に置き、単一のエラー型がそれを持つ。**

| 言語 | 表現 |
|---|---|
| Rust | `Error { code, message, source }`を`Result<T, Error>`で返す |
| C# | `SpringNbtException : Exception`（`Code`プロパティ） |
| Java | `SpringNbtException extends RuntimeException`（`code()`） |
| TypeScript | `SpringNbtError extends Error`（`code`プロパティ） |
| Python | `SpringNbtError(Exception)`（`code`属性） |

Javaは**検査例外を使わない**。`IOException`は`ErrorCode.IO`でラップして送出する。

## 理由

- `ErrorCode`の集合が全言語で一致していることは`docs-sync`で機械検証できる。
  適合性テストで「同じ入力 → 同じ`ErrorCode`」まで検証できるようになる
- Javaで検査例外を使うと、Rustの`Result`やPythonの例外とメソッドシグネチャの形が変わり、[命名変換規則](../spec/00-conventions.md#3-命名変換規則)で対応づけられなくなる
- 原因例外は必ず`source` / `InnerException` / `getCause()` / `cause` / `__cause__`に保持するので、情報は失われない

## 結果として受け入れること

- Java利用者にとっては、`IOException`を明示的に扱う慣習から外れる。
  この理由を[ガイド06](../guide/06-errors-and-limits.md)に記載する
- Rustでは`?`演算子のために`From<std::io::Error>`を実装する必要がある

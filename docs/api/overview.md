# API 対応表：概要と命名規則

同じ概念・同じ機能を全言語に提供している。違うのは**名前の綴りだけ**である。

このページは綴りの変換規則を示す。実際の対応表は次の3つ。

- [NBT](nbt.md) — タグ、読み書き、SNBT
- [Anvil](anvil.md) — リージョンファイル
- [World](world.md) — ワールド、チャンク、ブロック

---

## 1. 論理名という考え方

本ライブラリは、まず**言語に依存しない論理名**で API を定義し、
各言語はそこから機械的に変換した名前を使う。

```
論理名          read_file
    ↓
C#              NbtIo.ReadFile(path)
Java            NbtIo.readFile(path, null)
TypeScript      readFile(path)
Python          read_file(path)
Rust            read_file(path, &NbtReadOptions::default())
```

こうしておくと「C# で `WriteBytes` を足したのに Rust に `write_bytes` が無い」
といった取りこぼしを、[`spec/tools/check_docs_sync.py`](../../spec/tools/check_docs_sync.py)
が機械的に見つけられる（→ [adr/0009](../adr/0009-static-api-extraction.md)）。

対応表の「論理名」列がこれにあたる。

---

## 2. 変換規則

| 種別 | 論理名 | C# | Java | TypeScript | Python | Rust |
|---|---|---|---|---|---|---|
| 型・列挙 | `NbtCompound` | `NbtCompound` | `NbtCompound` | `NbtCompound` | `NbtCompound` | `NbtCompound` |
| 列挙の値 | `long_array` | `LongArray` | `LONG_ARRAY` | `LongArray` | `LONG_ARRAY` | `LongArray` |
| メソッド | `read_file` | `ReadFile()` | `readFile()` | `readFile()` | `read_file()` | `read_file()` |
| 取得子 | `data_version` | `DataVersion` | `dataVersion()` | `dataVersion` | `data_version` | `data_version()` |
| 設定子 | `set_data_version` | `DataVersion` | `setDataVersion()` | `dataVersion` | `data_version` | `set_data_version()` |
| 定数 | `TARGET_DATA_VERSION` | `TargetDataVersion` | `TARGET_DATA_VERSION` | `TARGET_DATA_VERSION` | `TARGET_DATA_VERSION` | `TARGET_DATA_VERSION` |

真偽値を返す取得子は論理名を `is_*` / `has_*` で始める
（`is_fully_generated`、`has_block_states`）。

詳しくは [仕様 00 の3章](../spec/00-conventions.md#3-命名変換規則)。

---

## 3. モジュールと名前空間

| 言語 | 取り込み方 |
|---|---|
| C# | `using SpringNBTLibrary.Nbt;` / `.Anvil` / `.World` |
| Java | `import io.github.scriptarts.springnbt.nbt.*;` / `.anvil` / `.world` |
| TypeScript | `import { ... } from "spring-nbt-library";`（`/nbt` `/anvil` `/world` のサブパスも可） |
| Python | `from spring_nbt_library.nbt import ...` |
| Rust | `use spring_nbt_library::nbt::*;` |

C# と Java には自由関数が無いため、`read_file` のようなモジュール関数は
静的クラス（`NbtIo`、`Snbt`、`Mutf8`、`SpringNbt`）に置いている。
対応表では**（モジュール関数）**の欄にまとめてある。

---

## 4. 言語ごとに揃わないところ

言語の性質上どうしても揃えられない箇所は、[機能一覧の「言語ごとの差異」](../features.md#言語ごとの差異)に
理由つきで集約している。要点だけ挙げると次のとおり。

| 箇所 | 差異 |
|---|---|
| `TAG_Long` の値 | TypeScript のみ `bigint` |
| `TAG_String` の値 | Rust のみ 2 形態の列挙（孤立サロゲートを保持するため） |
| タグの表現 | Rust は `NbtTag` 列挙のバリアント、TypeScript は型の合併。個別の `NbtByte` 型は無い |
| エラー | Rust のみ `Result<T, Error>`。他4言語は例外 |
| 例外の型名 | C# / Java は `SpringNbtException`、TypeScript / Python / Rust は `SpringNbtError` / `Error` |
| `session.lock` | C# / Java / Python(POSIX) のみ確認する（[adr/0008](../adr/0008-session-lock.md)） |

`ErrorCode` の値は全言語で一致する。分類と使い分けは
[ガイド 06](../guide/06-errors-and-limits.md) を参照。

---

## 5. この対応表の作られ方

各ページの表は**実装から自動生成している**。
人手で書くと必ず実装から遅れるため、
[`spec/tools/extract_api.py`](../../spec/tools/extract_api.py) が
全言語のソースから公開APIを抜き出し、
[`check_docs_sync.py`](../../spec/tools/check_docs_sync.py) が表を組み立てる。

```bash
# 実装に合わせて表を書き直す
python3 spec/tools/check_docs_sync.py --write

# ずれていないか確かめる（CI で実行）
python3 spec/tools/check_docs_sync.py
```

説明文は**基準実装である C# のドキュメントコメント**から取っている。
説明を直したいときは C# のソースを直す。

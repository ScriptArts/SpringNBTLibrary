# SpringNBTLibrary

[![CI](https://github.com/ScriptArts/SpringNBTLibrary/actions/workflows/ci.yml/badge.svg)](https://github.com/ScriptArts/SpringNBTLibrary/actions/workflows/ci.yml)
[![lint](https://github.com/ScriptArts/SpringNBTLibrary/actions/workflows/lint.yml/badge.svg)](https://github.com/ScriptArts/SpringNBTLibrary/actions/workflows/lint.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Minecraft Java版 26.2（DataVersion `4903`）のワールドデータ・NBTファイルを読み書きするライブラリです。
複数の言語に、同じ概念モデルと同じ挙動のものを用意しています。

## 対応言語

[Releases](https://github.com/ScriptArts/SpringNBTLibrary/releases) から落として、自分のプロジェクトに組み込んでください。

| 言語 | 必要環境 | 入手するもの | 組み込み方 |
|---|---|---|---|
| [C#](docs/getting-started/csharp.md) | .NET 8 / C# 12 | `SpringNBTLibrary-<版>-dotnet8.zip` | 展開して `.dll` を参照に追加 |
| [Java](docs/getting-started/java.md) | Java 21 (LTS) | `spring-nbt-library-<版>.jar` | クラスパスへ追加 |
| [TypeScript](docs/getting-started/typescript.md) | Node.js 20+ | `spring-nbt-library-<版>.tgz` | `npm install ./<ファイル>` |
| [Python](docs/getting-started/python.md) | Python 3.10+ | `spring_nbt_library-<版>-py3-none-any.whl` | `pip install <ファイル>` |
| [Rust](docs/getting-started/rust.md) | Rust 1.75+ | — | `Cargo.toml` で git 参照 |

同梱の `SHA256SUMS.txt` でファイルの整合を確認できます。

対応言語は今後も増やします。手順は [移植ガイド](docs/contributing/porting-guide.md) にあります。

## 何が違うのか

NBT や Anvil を扱うライブラリは各言語にあります。
このライブラリは、同じ仕様書と同じテストベクタから対応言語すべてを同時に作っています。

Rust のツールと Java のプラグインで同じワールドを触るとき、
言語ごとに挙動の違うライブラリを組み合わせて悩まずに済むことを狙っています。

そのために次を守っています。

- `docs/spec/` を唯一の正とし、各言語はその実装にすぎない
- 挙動の一致は目視ではなく[適合性テスト](docs/spec/90-conformance.md)で確かめる
- [機能一覧](docs/features.md)が実装からずれないよう CI で検査する

## ドキュメント

[目次](docs/README.md)から辿れます。

| 読みたいこと | 場所 |
|---|---|
| 何ができるか | [機能一覧](docs/features.md) |
| とりあえず動かす | [はじめに](docs/getting-started/) |
| 使い方 | [ガイド](docs/guide/) |
| 他言語版との対応 | [API対応表](docs/api/overview.md) |
| 自分で実装・移植する | [仕様](docs/spec/00-conventions.md) |
| 設計の理由 | [ADR](docs/adr/) |

## 検証

NBT・Anvil・World の3レイヤを Java版 26.2 の実ワールドで確かめています。
`.dat` 23個とチャンク 3,717個のすべてで、読み込みとバイト一致の書き戻しが通りました。
World レイヤでも 3,481 チャンク（83,544 セクション）の再エンコードが原本と一致し、
393万ブロックの読み出しに成功しています。

自分のワールドで試すこともできます。読み取りしかしません。

```bash
python3 spec/tools/scan_world.py "<ワールドのパス>"
```

## 開発

```bash
# ツールチェーンへ PATH を通す（Homebrew 前提）
source spec/tools/env.sh

# 各言語のテスト
(cd csharp     && dotnet test)
(cd java       && mvn test)
(cd typescript && npm test)
(cd python     && python -m pytest tests)
(cd rust       && cargo test)

# 対応言語すべての挙動が一致することの検証（このライブラリの核）
./spec/run-conformance.sh

# ドキュメントと実装の一致検証
python3 spec/tools/check_docs_sync.py
python3 spec/tools/check_links.py

# コメントと禁止記法の規約適合
python3 spec/tools/check_comments.py
```

## ライセンス

MIT License — Copyright (c) 2026 ScriptArts

詳細は [LICENSE](LICENSE) を参照。

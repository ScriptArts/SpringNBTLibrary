# SpringNBTLibrary

Minecraft **Java版 26.2**（DataVersion `4903`）のワールドデータ・NBTファイルを読み書きするライブラリ。

**C# / Java / TypeScript / Python / Rust の5言語**で、同じ概念モデルと同じ挙動のものを提供する。

```
C#          Java            TypeScript      Python              Rust
SpringNBT   spring-nbt-     spring-nbt-     spring-nbt-         spring-nbt-
Library     library         library         library             library
```

## このライブラリの立ち位置

NBT や Anvil を扱うライブラリは各言語に既に存在する。
本ライブラリの違いは、**同じ設計者が、同じ仕様書と同じテストベクタから、
5言語分を同時に提供している**点にある。

複数言語が絡むプロジェクト（Rust のツールと Java のプラグインで同じワールドを扱う、など）で、
言語ごとに挙動の違うライブラリを組み合わせて悩む必要をなくすことを狙っている。

そのため次を最優先で維持している。

1. `docs/spec/` が唯一の正であり、各言語実装はその実装であること
2. 全言語の挙動一致を、人手のレビューではなく**適合性テストで機械的に保証**すること
3. [機能一覧](docs/features.md)が実装と乖離しないよう CI で検証すること

## ドキュメント

**[ドキュメントの目次はこちら](docs/README.md)**

| 目的 | 読むもの |
|---|---|
| 何ができるのか知りたい | [機能一覧](docs/features.md) |
| とりあえず動かしたい | [はじめに](docs/getting-started/) |
| 使い方を調べたい | [ガイド](docs/guide/) |
| 他の言語版の対応するAPIを知りたい | [API対応表](docs/api/overview.md) |
| 自分で実装・移植したい | [仕様](docs/spec/00-conventions.md) |
| なぜその設計なのか知りたい | [設計判断の記録](docs/adr/) |

## 対応状況

| レイヤ | 内容 | 状態 |
|---|---|---|
| 1. NBT | 全13タグ・MUTF-8・圧縮・SNBT | ✅ 5言語すべて完成 |
| 2. Anvil | `.mca` リージョンファイルの読み書き | ✅ 5言語すべて完成 |
| 3. World / Block | `level.dat`・チャンク・ブロック操作 | ✅ 5言語すべて完成 |

詳細は [機能一覧](docs/features.md) を参照。

3レイヤすべて **Java版 26.2 の実ワールドで検証済み**。
`.dat` 23個 + チャンク 3,717個 = 3,740件すべてで読み込みとバイト一致のラウンドトリップに成功し、
World レイヤでも 3,481 チャンク（83,544 セクション）の再エンコードが原本と一致、
393万ブロックの読み出しも通っています。
代表ファイルは5言語すべてで出力が完全一致することも確認済みです。
自分のワールドで試すには:

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

# 全言語の挙動が一致することの検証（このライブラリの核）
./spec/run-conformance.sh

# ドキュメントと実装の一致検証
python3 spec/tools/check_docs_sync.py
python3 spec/tools/check_links.py
```

## ライセンス

MIT License — Copyright (c) 2026 ScriptArts

詳細は [LICENSE](LICENSE) を参照。

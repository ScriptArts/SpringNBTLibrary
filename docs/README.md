# SpringNBTLibrary ドキュメント

Minecraft Java版 26.1 以降のワールド／NBTファイルを
複数の言語で同一に読み書きするライブラリのドキュメントです。

まずどこを読むか:

| 目的 | 読むもの |
|---|---|
| 何ができるのか知りたい | [機能一覧](features.md) |
| とりあえず動かしたい | [はじめに](getting-started/) |
| 使い方を調べたい | [ガイド](guide/) |
| 他の言語版の対応するAPIを知りたい | [API対応表](api/overview.md) |
| 自分で実装・移植したい | [仕様](spec/00-conventions.md) |
| なぜその設計なのか知りたい | [設計判断の記録](adr/) |

---

## 目次

### 機能

- [機能一覧](features.md) — 機能 × 全言語の対応マトリクス

### はじめに

- [C#](getting-started/csharp.md)
- [Java](getting-started/java.md)
- [TypeScript](getting-started/typescript.md)
- [Python](getting-started/python.md)
- [Rust](getting-started/rust.md)

### ガイド

- [01. NBT の読み書き](guide/01-nbt.md)
- [02. SNBT](guide/02-snbt.md)
- [03. リージョンファイル (.mca)](guide/03-anvil-region.md)
- [04. ワールドと level.dat](guide/04-world-and-level-dat.md)
- [05. ブロックとバイオーム](guide/05-blocks-and-biomes.md)
- [06. エラーと安全上限](guide/06-errors-and-limits.md)
- [07. バージョンポリシー](guide/07-version-policy.md)

### API 対応表

- [概要と命名規則](api/overview.md)
- [NBT](api/nbt.md)
- [Anvil](api/anvil.md)
- [World](api/world.md)

### 仕様（実装者向け）

- [00. 共通規約](spec/00-conventions.md)
- [10. NBT バイナリ形式](spec/10-nbt-binary.md)
- [11. SNBT](spec/11-snbt.md)
- [20. Anvil リージョン形式](spec/20-anvil-region.md)
- [30. チャンク形式](spec/30-chunk-format.md)
- [31. パレット付きコンテナと BitStorage](spec/31-paletted-container.md)
- [40. ワールドのディレクトリ構成](spec/40-world-layout.md)
- [90. 適合性](spec/90-conformance.md)

### 開発

- [実ワールドで検証する](spec/90-conformance.md#24-実ワールド走査) — `spec/tools/scan_world.py`
- [新しい言語を追加する](contributing/porting-guide.md)
- [リリース手順](contributing/release.md)
- [変更履歴](../CHANGELOG.md)

### 設計判断の記録 (ADR)

- [0001. モノレポにする](adr/0001-monorepo.md)
- [0002. 命名は各言語のイディオムに従う](adr/0002-idiomatic-naming.md)
- [0003. ワールド形式で対応を判定する](adr/0003-version-policy.md)
- [0004. Heightmap と光源の再計算は行わない](adr/0004-defer-heightmap-recalc.md)
- [0005. 全言語で共通のエラーモデルを使う](adr/0005-unified-error-model.md)
- [0006. SNBT はバイナリへ写せる範囲だけを扱う](adr/0006-snbt-scope.md)
- [0007. TypeScript では i64 に bigint を使う](adr/0007-typescript-bigint.md)
- [0008. `session.lock` の確認は言語ごとにベストエフォートとする](adr/0008-session-lock.md)
- [0009. 公開APIの抽出は静的解析で行い、API 対応表は生成する](adr/0009-static-api-extraction.md)

---

## 仕様が先にある

実装より先に [`spec/`](spec/00-conventions.md) に仕様を書き、各言語はそれを実装しています。
どの言語版でも同じ入力から同じバイト列が出るかは[適合性テスト](spec/90-conformance.md)が確かめていて、
[機能一覧](features.md)が実装からずれていないかも CI で見ています。

Rust のツールで書いたワールドを Java のプラグインで読む、といった場面で、
ライブラリごとの違いに悩まされずに済むのが狙いです。

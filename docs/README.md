# SpringNBTLibrary ドキュメント

Minecraft **Java版 26.2**（DataVersion `4903`）のワールド／NBTファイルを
**C# / Java / TypeScript / Python / Rust の5言語**で同一に読み書きするライブラリ。

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
- [0003. 読みは寛容・書きは最新固定](adr/0003-version-policy.md)
- [0004. Heightmap 再計算は v0.1.0 では行わない](adr/0004-defer-heightmap-recalc.md)
- [0005. 全言語で共通のエラーモデルを使う](adr/0005-unified-error-model.md)
- [0006. SNBT はバイナリへ写せる範囲だけを扱う](adr/0006-snbt-scope.md)
- [0007. TypeScript では i64 に bigint を使う](adr/0007-typescript-bigint.md)
- [0008. `session.lock` の確認は言語ごとにベストエフォートとする](adr/0008-session-lock.md)
- [0009. 公開APIの抽出は静的解析で行い、API 対応表は生成する](adr/0009-static-api-extraction.md)

---

## このライブラリの立ち位置

NBT や Anvil を扱うライブラリは各言語に既に存在する。
本ライブラリの違いは、**同じ設計者が、同じ仕様書と同じテストベクタから、
全言語分を同時に提供している**点にある。

そのため次を維持することを最優先とする。

1. `docs/spec/` が唯一の正であり、全言語はその実装であること
2. 全言語の挙動一致を、人手のレビューではなく
   [適合性テスト](spec/90-conformance.md)で機械的に保証すること
3. [機能一覧](features.md)が実装と乖離しないよう CI で検証すること

複数言語が絡むプロジェクト（例: Rust のツールと Java のプラグインで同じワールドを扱う）で、
言語ごとに挙動の違うライブラリを組み合わせて悩む必要をなくすことを狙っている。

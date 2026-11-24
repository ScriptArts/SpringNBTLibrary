# SpringNBTLibraryドキュメント

Minecraft Java版1.13以降のワールド／NBTファイルを、複数の言語で同じように読み書きするライブラリのドキュメントです。

まずどこを読むかは次のとおりです。

| 目的 | 読むもの |
|---|---|
| 何ができるのか知りたい | [機能一覧](features.md) |
| とりあえず動かしたい | [はじめに](getting-started/) |
| 使い方を調べたい | [ガイド](guide/) |
| 他の言語版の対応するAPIを知りたい | [API対応表](api/overview.md) |
| 自分で実装・移植したい | [仕様](spec/00-conventions.md) |

---

## 目次

### 機能

- [機能一覧](features.md): 機能 × 全言語の対応マトリクス

### はじめに

- [C#](getting-started/csharp.md)
- [Java](getting-started/java.md)
- [TypeScript](getting-started/typescript.md)
- [Python](getting-started/python.md)
- [Rust](getting-started/rust.md)

### ガイド

- [01. NBTの読み書き](guide/01-nbt.md)
- [02. SNBT](guide/02-snbt.md)
- [03. リージョンファイル (.mca)](guide/03-anvil-region.md)
- [04. ワールドとlevel.dat](guide/04-world-and-level-dat.md)
- [05. ブロックとバイオーム](guide/05-blocks-and-biomes.md)
- [06. エラーと安全上限](guide/06-errors-and-limits.md)
- [07. バージョンポリシー](guide/07-version-policy.md)

### API対応表

- [概要と命名規則](api/overview.md)
- [NBT](api/nbt.md)
- [Anvil](api/anvil.md)
- [World](api/world.md)

### 仕様（実装者向け）

- [00. 共通規約](spec/00-conventions.md)
- [10. NBTバイナリ形式](spec/10-nbt-binary.md)
- [11. SNBT](spec/11-snbt.md)
- [20. Anvilリージョン形式](spec/20-anvil-region.md)
- [30. チャンク形式](spec/30-chunk-format.md)
- [31. パレット付きコンテナとBitStorage](spec/31-paletted-container.md)
- [40. ワールドのディレクトリ構成](spec/40-world-layout.md)

### 開発

- [テストの回し方](testing.md)
- [変更履歴](../CHANGELOG.md)

---

## 仕様と実装

実装より先に[`spec/`](spec/00-conventions.md)に仕様を書き、各言語はそれを実装しています。
どの言語版でも同じ入力から同じバイト列が出るかは[適合性テスト](testing.md)が確かめていて、[機能一覧](features.md)が実装からずれていないかもCIで見ています。

Rustのツールで書いたワールドをJavaのプラグインで読む、といった場面で、ライブラリごとの違いに悩まされずに済むのが狙いです。

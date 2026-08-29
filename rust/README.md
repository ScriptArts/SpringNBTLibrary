# SpringNBTLibrary（Rust 版）

Minecraft **Java版 26.2**（DataVersion `4903`）のワールド／NBTファイルを読み書きするライブラリ。

**Rust 2021 edition / MSRV 1.75**

## これは多言語版のうちの1つです

SpringNBTLibrary は複数の言語へ、同じ設計者が**同一の概念・同一の挙動**で
提供しているライブラリです。
言語をまたぐプロジェクトで、実装ごとの挙動差に悩まされないことを狙っています。

対応言語は今後も追加していきます。現在対応しているのは
**C# / Java / TypeScript / Python / Rust**（→ [対応言語の一覧](../README.md#対応言語)）。

対応言語すべての挙動一致は人手のレビューではなく
[適合性テスト](../docs/spec/90-conformance.md)で機械的に保証しています。

## 導入

```toml
[dependencies]
spring-nbt-library = "0.1"
```

> crates.io へはまだ公開していない。現時点ではパス参照する。

## 使い方

- **[はじめに（Rust）](../docs/getting-started/rust.md)** — まずここから
- [ガイド](../docs/guide/01-nbt.md) — 目的別の使い方
- [API 対応表](../docs/api/overview.md) — 他言語版との対応
- [機能一覧](../docs/features.md) — 何ができて何ができないか

**ドキュメントの実体は [`docs/`](../docs/README.md) にあります。**
言語ごとに説明を重複させず、一箇所で管理しています。

## ライセンス

MIT License — Copyright (c) 2026 ScriptArts

- [LICENSE](../LICENSE) — 英語の原文（**法的効力を持つのはこちら**）
- [LICENSE.ja.md](../LICENSE.ja.md) — 日本語の参考訳

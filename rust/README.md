# SpringNBTLibrary（Rust 版）

Minecraft Java版 26.2（DataVersion `4903`）のワールド・NBTファイルを読み書きするライブラリです。
Rust 2021 edition、MSRV 1.75 です。

C# / Java / TypeScript / Python / Rust 版があり、どれも同じ仕様書から作っています。
同じ入力からは同じ結果が出ます（[対応言語の一覧](../README.md#対応言語)）。
揃っているかは[適合性テスト](../docs/spec/90-conformance.md)で毎回確かめています。

## 導入

Cargo.toml に git 参照を書きます。

```toml
[dependencies]
spring-nbt-library = { git = "https://github.com/ScriptArts/SpringNBTLibrary", tag = "v1.0.0" }
```

ネットワークに繋がらない環境向けに、[Releases](https://github.com/ScriptArts/SpringNBTLibrary/releases) へ `.crate` も置いています。

## 使い方

- [はじめに（Rust）](../docs/getting-started/rust.md) — まずここから
- [ガイド](../docs/guide/01-nbt.md) — 目的別の使い方
- [API 対応表](../docs/api/overview.md) — 他言語版との対応
- [機能一覧](../docs/features.md) — 何ができて何ができないか

説明は [`docs/`](../docs/README.md) にまとめてあります。

## ライセンス

MIT License — Copyright (c) 2026 ScriptArts

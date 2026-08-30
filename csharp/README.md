# SpringNBTLibrary（C# 版）

Minecraft Java版 26.2（DataVersion `4903`）のワールド・NBTファイルを読み書きするライブラリです。
.NET 8 / C# 12 以上で動きます。

C# / Java / TypeScript / Python / Rust 版があり、どれも同じ仕様書から作っています。
同じ入力からは同じ結果が出ます（[対応言語の一覧](../README.md#対応言語)）。
揃っているかは[適合性テスト](../docs/spec/90-conformance.md)で毎回確かめています。

## 導入

[Releases](https://github.com/ScriptArts/SpringNBTLibrary/releases) から
`SpringNBTLibrary.<版>.nupkg` を落とし、置いたフォルダをソースに登録します。

```bash
dotnet nuget add source ./packages -n springnbt
dotnet add package SpringNBTLibrary --version 1.0.0
```

dll を直接参照したいときは `SpringNBTLibrary-<版>-dotnet8.zip` のほうを使います。
同梱の `.xml` を dll と同じ場所に置くと、IDE の補完に説明が出ます。

## 使い方

- [はじめに（C#）](../docs/getting-started/csharp.md) — まずここから
- [ガイド](../docs/guide/01-nbt.md) — 目的別の使い方
- [API 対応表](../docs/api/overview.md) — 他言語版との対応
- [機能一覧](../docs/features.md) — 何ができて何ができないか

説明は [`docs/`](../docs/README.md) にまとめてあります。

## ライセンス

MIT License — Copyright (c) 2026 ScriptArts

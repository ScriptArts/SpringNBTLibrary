# SpringNBTLibrary（TypeScript 版）

Minecraft Java版 26.2（DataVersion `4903`）のワールド・NBTファイルを読み書きするライブラリです。
Node.js 20 以上、TypeScript 5.7 以上で動きます。ESM 専用です。

C# / Java / TypeScript / Python / Rust 版があり、どれも同じ仕様書から作っています。
同じ入力からは同じ結果が出ます（[対応言語の一覧](../README.md#対応言語)）。
揃っているかは[適合性テスト](../docs/spec/90-conformance.md)で毎回確かめています。

## 導入

[Releases](https://github.com/ScriptArts/SpringNBTLibrary/releases) から `spring-nbt-library-<版>.tgz` を落として入れます。

```bash
npm install ./spring-nbt-library-0.1.0.tgz
```

型定義（`.d.ts`）も含まれています。

## 使い方

- [はじめに（TypeScript）](../docs/getting-started/typescript.md) — まずここから
- [ガイド](../docs/guide/01-nbt.md) — 目的別の使い方
- [API 対応表](../docs/api/overview.md) — 他言語版との対応
- [機能一覧](../docs/features.md) — 何ができて何ができないか

説明は [`docs/`](../docs/README.md) にまとめてあります。

## ライセンス

MIT License — Copyright (c) 2026 ScriptArts

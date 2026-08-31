# SpringNBTLibrary（Python 版）

Minecraft Java版 26.1 以降のワールド・NBTファイルを読み書きするライブラリです。
Python 3.10 以上で動きます。依存パッケージはありません。

いまのワールド形式は 26.1 で入ったものです。
それ以降のバージョンなら、形式が変わらない限りそのまま扱えます。

C# / Java / TypeScript / Python / Rust 版があり、どれも同じ仕様書から作っています。
同じ入力からは同じ結果が出ます（[対応言語の一覧](../README.md#対応言語)）。
揃っているかは[適合性テスト](../docs/spec/90-conformance.md)で毎回確かめています。

## 導入

[Releases](https://github.com/ScriptArts/SpringNBTLibrary/releases) から wheel を落として入れます。

```bash
pip install spring_nbt_library-1.0.0-py3-none-any.whl
```

## 使い方

- [はじめに（Python）](../docs/getting-started/python.md) — まずここから
- [ガイド](../docs/guide/01-nbt.md) — 目的別の使い方
- [API 対応表](../docs/api/overview.md) — 他言語版との対応
- [機能一覧](../docs/features.md) — 何ができて何ができないか

説明は [`docs/`](../docs/README.md) にまとめてあります。

## ライセンス

MIT License — Copyright (c) 2026 ScriptArts

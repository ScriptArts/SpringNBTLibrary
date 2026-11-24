# SpringNBTLibrary（Python版）

Minecraft Java版1.13以降のワールド・NBTファイルを読み書きするライブラリです。
Python 3.10以上で動きます。依存パッケージはありません。

1.13から26.3までのワールドを、読んだときの形式のまま読み書きします。
これより新しいバージョンでも、形式が変わらない限りそのまま扱えます。

C# / Java / TypeScript / Python / Rust版があり（[対応言語の一覧](../README.md#対応言語)）、どれも同じ仕様書から作っています。
同じ入力からは同じ結果が出ます。
結果が揃っているかは[適合性テスト](../docs/testing.md)で毎回確かめています。

## 導入

PyPIから入れます。

```bash
pip install spring-nbt-library
```

[Releases](https://github.com/ScriptArts/SpringNBTLibrary/releases)から落としたwheelを、`pip install`で入れることもできます。

## 使い方

- [はじめに（Python）](../docs/getting-started/python.md): まずここから
- [ガイド](../docs/guide/01-nbt.md): 目的別の使い方
- [API対応表](../docs/api/overview.md): 他言語版との対応
- [機能一覧](../docs/features.md): 何ができて何ができないか

説明は[`docs/`](../docs/README.md)にまとめてあります。

## ライセンス

MIT License

Copyright (c) 2026 ScriptArts

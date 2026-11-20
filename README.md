# SpringNBTLibrary

[![CI](https://github.com/ScriptArts/SpringNBTLibrary/actions/workflows/ci.yml/badge.svg)](https://github.com/ScriptArts/SpringNBTLibrary/actions/workflows/ci.yml)
[![lint](https://github.com/ScriptArts/SpringNBTLibrary/actions/workflows/lint.yml/badge.svg)](https://github.com/ScriptArts/SpringNBTLibrary/actions/workflows/lint.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Minecraft Java版1.13以降のワールドデータ・NBTファイルを読み書きするライブラリです。
複数の言語に、同じ概念モデルと同じ挙動のものを用意しています。

1.13から26.3までのワールドを、読んだときの形式のまま読み書きします。バージョン間の変換はしません。
これより新しいバージョンでも、形式が変わらない限りそのまま扱えます。
動作は1.13.2から26.3までの各バージョンの実ワールドで確かめています。

## 対応言語

C#・TypeScript・Pythonは、それぞれのパッケージレジストリから入れられます。
Javaは[Releases](https://github.com/ScriptArts/SpringNBTLibrary/releases)から`.jar`を落として、Rustはgitで参照して使ってください。

| 言語 | 必要環境 | 入れ方 |
|---|---|---|
| [C#](docs/getting-started/csharp.md) | .NET 8 / C# 12 | `dotnet add package SpringNBTLibrary`（NuGet） |
| [Java](docs/getting-started/java.md) | Java 21 (LTS) | Releasesの`spring-nbt-library-<版>.jar`をクラスパスへ追加 |
| [TypeScript](docs/getting-started/typescript.md) | Node.js 20+ | `npm install spring-nbt-library` |
| [Python](docs/getting-started/python.md) | Python 3.10+ | `pip install spring-nbt-library` |
| [Rust](docs/getting-started/rust.md) | Rust 1.75+ | `Cargo.toml`でgit参照（オフライン用に`spring-nbt-library-<版>.crate`もReleasesにある） |

Releasesには全言語の成果物を置いています。同梱の`SHA256SUMS.txt`で、ファイルの整合性を確認できます。

## バージョン番号

`x.y.z`の各桁は次を表します。

| 桁 | 上がるとき | 例 |
|---|---|---|
| `x` | ワールドの保存形式が変わったとき | ディメンションフォルダの構成が変わった |
| `y` | 機能を足した、または外したとき | ブロック設置のメソッドを追加した |
| `z` | 不具合を直したとき | ブロックが設置されない不具合を修正した |

対応言語はすべて同じ番号で公開します。

**Minecraftが更新されても、ワールドの保存形式が変わらなければ`x`は上がりません。**
新しいバージョンのワールドはそのまま読み書きできます。

## ドキュメント

[目次](docs/README.md)から辿れます。

| 読みたいこと | 場所 |
|---|---|
| 何ができるか | [機能一覧](docs/features.md) |
| とりあえず動かす | [はじめに](docs/getting-started/) |
| 使い方 | [ガイド](docs/guide/) |
| 他言語版との対応 | [API対応表](docs/api/overview.md) |

## ライセンス

MIT License — Copyright (c) 2026 ScriptArts

詳細は[LICENSE](LICENSE)を参照。

# SpringNBTLibrary

[![CI](https://github.com/ScriptArts/SpringNBTLibrary/actions/workflows/ci.yml/badge.svg)](https://github.com/ScriptArts/SpringNBTLibrary/actions/workflows/ci.yml)
[![lint](https://github.com/ScriptArts/SpringNBTLibrary/actions/workflows/lint.yml/badge.svg)](https://github.com/ScriptArts/SpringNBTLibrary/actions/workflows/lint.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Minecraft Java版 26.1 以降のワールドデータ・NBTファイルを読み書きするライブラリです。
複数の言語に、同じ概念モデルと同じ挙動のものを用意しています。

いまのワールド形式は 26.1 で入ったものです。
それ以降のバージョンなら、形式が変わらない限りそのまま扱えます。
動作は 26.2 の実ワールドで確かめています。

## 対応言語

[Releases](https://github.com/ScriptArts/SpringNBTLibrary/releases) から落として、自分のプロジェクトに組み込んでください。

| 言語 | 必要環境 | 入手するもの | 組み込み方 |
|---|---|---|---|
| [C#](docs/getting-started/csharp.md) | .NET 8 / C# 12 | `SpringNBTLibrary.<版>.nupkg` | 置き場所を `nuget.config` で教えて `dotnet add package`（`.zip` で dll 直参照も可） |
| [Java](docs/getting-started/java.md) | Java 21 (LTS) | `spring-nbt-library-<版>.jar` | クラスパスへ追加 |
| [TypeScript](docs/getting-started/typescript.md) | Node.js 20+ | `spring-nbt-library-<版>.tgz` | `npm install ./<ファイル>` |
| [Python](docs/getting-started/python.md) | Python 3.10+ | `spring_nbt_library-<版>-py3-none-any.whl` | `pip install <ファイル>` |
| [Rust](docs/getting-started/rust.md) | Rust 1.75+ | — | `Cargo.toml` で git 参照 |

同梱の `SHA256SUMS.txt` でファイルの整合を確認できます。

## バージョン番号

`x.y.z` の各桁は次を表します。

| 桁 | 上がるとき | 例 |
|---|---|---|
| `x` | ワールドの保存形式が変わったとき | ディメンションフォルダの構成が変わった |
| `y` | 機能を足した、または外したとき | ブロック設置のメソッドを追加した |
| `z` | 不具合を直したとき | ブロックが設置されない不具合を修正した |

対応言語はすべて同じ番号で公開します。

**Minecraft が更新されても、ワールドの保存形式が変わらなければ `x` は上がりません。**
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

詳細は [LICENSE](LICENSE) を参照。

# SpringNBTLibrary（Java版）

Minecraft Java版1.13以降のワールド・NBTファイルを読み書きするライブラリです。
Java 21 (LTS)以上で動きます。

1.13から26.3までのワールドを、読んだときの形式のまま読み書きします。
これより新しいバージョンでも、形式が変わらない限りそのまま扱えます。

C# / Java / TypeScript / Python / Rust版があり、どれも同じ仕様書から作っています。
同じ入力からは同じ結果が出ます（[対応言語の一覧](../README.md#対応言語)）。
結果が揃っているかは[適合性テスト](../docs/spec/90-conformance.md)で毎回確かめています。

## 導入

[Releases](https://github.com/ScriptArts/SpringNBTLibrary/releases)から`spring-nbt-library-<版>.jar`を落として、クラスパスへ追加します。
以下の`<版>`は、使うリリースの版（Releasesのタグ名から先頭の`v`を除いたもの）に読み替えてください。

```groovy
dependencies {
    implementation files("libs/spring-nbt-library-<版>.jar")
}
```

## 使い方

- [はじめに（Java）](../docs/getting-started/java.md): まずここから
- [ガイド](../docs/guide/01-nbt.md): 目的別の使い方
- [API対応表](../docs/api/overview.md): 他言語版との対応
- [機能一覧](../docs/features.md): 何ができて何ができないか

説明は[`docs/`](../docs/README.md)にまとめてあります。

## ライセンス

MIT License — Copyright (c) 2026 ScriptArts

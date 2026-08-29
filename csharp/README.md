# SpringNBTLibrary（C# 版）

Minecraft **Java版 26.2**（DataVersion `4903`）のワールド／NBTファイルを読み書きするライブラリ。

**.NET 8 / C# 12 以上**

## これは多言語版のうちの1つです

SpringNBTLibrary は複数の言語へ、同じ設計者が**同一の概念・同一の挙動**で
提供しているライブラリです。
言語をまたぐプロジェクトで、実装ごとの挙動差に悩まされないことを狙っています。

対応言語は今後も追加していきます。現在対応しているのは
**C# / Java / TypeScript / Python / Rust**（→ [対応言語の一覧](../README.md#対応言語)）。

対応言語すべての挙動一致は人手のレビューではなく
[適合性テスト](../docs/spec/90-conformance.md)で機械的に保証しています。

## 導入

[Releases](https://github.com/ScriptArts/SpringNBTLibrary/releases) から `SpringNBTLibrary-<版>-dotnet8.zip` を落として、
中の `.dll` を参照に追加します。

```xml
<Reference Include="SpringNBTLibrary">
  <HintPath>lib/SpringNBTLibrary.dll</HintPath>
</Reference>
```

同梱の `.xml` を dll と同じ場所に置くと、IDE の補完に説明が出ます。

## 使い方

- **[はじめに（C#）](../docs/getting-started/csharp.md)** — まずここから
- [ガイド](../docs/guide/01-nbt.md) — 目的別の使い方
- [API 対応表](../docs/api/overview.md) — 他言語版との対応
- [機能一覧](../docs/features.md) — 何ができて何ができないか

**ドキュメントの実体は [`docs/`](../docs/README.md) にあります。**
言語ごとに説明を重複させず、一箇所で管理しています。

## ライセンス

MIT License — Copyright (c) 2026 ScriptArts

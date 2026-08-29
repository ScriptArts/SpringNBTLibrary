# リリース手順

---

## 1. バージョン番号

[セマンティックバージョニング](https://semver.org/lang/ja/)に従う。
**全言語で同じ番号を使う。** ある言語だけ 0.2.0 ということはしない。

| 変更 | 上げる桁 |
|---|---|
| 公開APIの破壊的変更 | メジャー |
| 機能追加、対象 Minecraft バージョンの更新 | マイナー |
| 不具合修正のみ | パッチ |

**対象 Minecraft バージョンの更新はマイナー扱い**とする。
書き込み時の `DataVersion` が変わるため、利用者にとっては挙動の変化にあたる。

---

## 2. Minecraft の新バージョンへ対応する

1. **実ワールドを用意する。** 新バージョンで新規ワールドを作り、
   ネザーとエンドにも行って各次元を生成させる
2. **走査する。**

   ```bash
   python3 spec/tools/scan_world.py "<新しいワールド>" --verbose
   ```

   ルート直下キー・セクションキー・`Status` の出現数が出るので、
   [spec/30](../spec/30-chunk-format.md) / [spec/40](../spec/40-world-layout.md)
   の記述と突き合わせる
3. **仕様書を直す。** 構成が変わっていたら、**推測ではなく実データを根拠に**書き直す。
   Minecraft Wiki は数バージョン遅れていることがある
4. **`TARGET_DATA_VERSION` を全言語で更新する。**

   ```
   csharp/src/SpringNBTLibrary/SpringNbt.cs
   java/src/main/java/io/github/scriptarts/springnbt/SpringNbt.java
   typescript/src/index.ts
   python/src/spring_nbt_library/__init__.py
   rust/src/lib.rs
   ```
5. **テストベクタを作り直す。**

   ```bash
   python3 spec/tools/build_testdata.py
   ```
6. 全言語のテストと適合性検証を通す

---

## 3. リリース前の確認

```bash
source spec/tools/env.sh

# 各言語のテスト
(cd csharp     && dotnet test)
(cd java       && mvn test)
(cd typescript && npm test)
(cd python     && python -m pytest tests)
(cd rust       && cargo test)

# 全言語の挙動一致（このライブラリの核）
./spec/run-conformance.sh

# ドキュメントと実装の一致
python3 spec/tools/check_docs_sync.py

# 実ワールドでの検証
python3 spec/tools/scan_world.py "<ワールドのパス>"
```

**すべて通ることがリリースの条件である。**
1 つでも落ちている状態で出すと、「全言語で挙動が同じ」という
本ライブラリ唯一の売りが嘘になる。

---

## 4. バージョン番号を上げる場所

| 言語 | ファイル |
|---|---|
| C# | `csharp/src/SpringNBTLibrary/SpringNBTLibrary.csproj` |
| Java | `java/pom.xml` |
| TypeScript | `typescript/package.json` |
| Python | `python/pyproject.toml` |
| Rust | `rust/Cargo.toml` |

あわせて `CHANGELOG.md` に変更点を書く。

---

## 5. 公開

| 言語 | 公開先 |
|---|---|
| C# | NuGet |
| Java | Maven Central |
| TypeScript | npm |
| Python | PyPI |
| Rust | crates.io |

**5 つすべてが揃ってからリリースとする。**
一部だけ新しい状態は、利用者にとって最も困る形である。

各パッケージには `LICENSE`（MIT）を同梱する。

---

## 6. タグを打つ

```bash
git tag -a v0.1.0 -m "v0.1.0"
git push origin v0.1.0
```

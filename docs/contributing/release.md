# リリース手順

---

## 1. バージョン番号

`x.y.z` の各桁は次を表す。

| 桁 | 上がるとき | 例 |
|---|---|---|
| `x` | ワールドの保存形式が変わったとき | 次元フォルダの構成が変わった |
| `y` | 機能を足した、または外したとき | LZ4 を読めるようにした |
| `z` | 不具合を直したとき | パレットの並び順を直した |

全言語で同じ番号を使う。ある言語だけ 1.1.0 ということはしない。

**Minecraft が更新されても、保存形式が変わらなければ `x` は上がらない。**
形式が同じなら新しいバージョンのワールドもそのまま扱えるので、
ライブラリ側で対応することが無い（[adr/0003](../adr/0003-version-policy.md)）。

`x` が上がるのは、扱える形式の下限
（`MIN_SUPPORTED_DATA_VERSION`）を引き上げるときである。
それまで使えていたワールドが使えなくなるため、いちばん上の桁で知らせる。

`x` を上げるときは `y` と `z` を 0 に戻す。

---

## 2. Minecraft の新バージョンが出たら

**まず、形式が変わったかどうかを確かめる。** 変わっていなければ何もしなくてよい。

1. 実ワールドを用意する。 新バージョンで新規ワールドを作り、
   ネザーとエンドにも行って各次元を生成させる
2. 走査する。

   ```bash
   python3 spec/tools/scan_world.py "<新しいワールド>" --verbose
   ```

   ルート直下キー・セクションキー・`Status` の出現数が出るので、
   [spec/30](../spec/30-chunk-format.md) / [spec/40](../spec/40-world-layout.md)
   の記述と突き合わせる
3. 差が無ければここで終わり。 そのバージョンのワールドはすでに扱える。
   確認した記録として `TARGET_DATA_VERSION` を上げてもよいが、必須ではない

形式が変わっていた場合だけ、次へ進む。

4. 仕様書を直す。 推測ではなく実データを根拠に書き直す
5. 実装を新しい形式へ合わせる
6. `MIN_SUPPORTED_DATA_VERSION` を新しい形式が入ったバージョンへ上げ、
   `TARGET_DATA_VERSION` も更新する。

   ```
   csharp/src/SpringNBTLibrary/SpringNbt.cs
   java/src/main/java/io/github/scriptarts/springnbt/SpringNbt.java
   typescript/src/index.ts
   python/src/spring_nbt_library/__init__.py
   rust/src/lib.rs
   ```
7. テストベクタを作り直す。

   ```bash
   python3 spec/tools/build_testdata.py
   ```
8. 全言語のテストと適合性検証を通す
9. バージョン番号の `x` を上げる

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
python3 spec/tools/check_links.py

# コメントと禁止記法の規約適合
python3 spec/tools/check_comments.py

# 実ワールドでの検証
python3 spec/tools/scan_world.py "<ワールドのパス>"
```

すべて通ることがリリースの条件である。
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

**これはリリースの必須条件である。** 本文はここから組み立てるので、
節が無いとワークフローが落ちて公開まで進まない。

---

## 5. 公開

GitHub Releases へビルド済みの成果物を置く。
利用者はそれを落として自分のプロジェクトへ組み込む。

### 5.1 タグを打つと自動で公開される

```bash
git tag -a v1.0.0 -m "v1.0.0"
git push origin v1.0.0
```

`v` で始まるタグを push すると
[`release` ワークフロー](../../.github/workflows/release.yml)が動き、次を行う。

1. 全対応言語のテストと[適合性検証](../spec/90-conformance.md)を通す
   （落ちたら公開しない。壊れたものを配らないため）
2. 言語ごとの成果物を組み立てる
3. `SHA256SUMS.txt` を作る
4. Releases を作って成果物を添付する

### 5.2 成果物

| 言語 | ファイル | 中身 |
|---|---|---|
| C# | `SpringNBTLibrary-<版>-dotnet8.zip` | `.dll` と `.xml`（補完用）、LICENSE、README |
| Java | `spring-nbt-library-<版>.jar` | |
| TypeScript | `spring-nbt-library-<版>.tgz` | ビルド済み JS と型定義 |
| Python | `spring_nbt_library-<版>-py3-none-any.whl` / `.tar.gz` | wheel と sdist |
| Rust | `spring-nbt-library-<版>.crate` | ソースの tar.gz |

Rust は git 参照が主な使い方になる。 Cargo は git リポジトリを直接
依存にできるので、ファイルを落とす必要がない。`.crate` は
ネットワークに繋がらない環境向けの控えである。

### 5.3 タグを打つ前に試す

`release` ワークフローは手動でも起動できる。
Actions の画面から `Run workflow` を選ぶと、
成果物の組み立てまでを行い、Releases は作らずに artifacts として残す。

中身を確かめてからタグを打てる。

### 5.4 リリースの本文

本文は 2 つを継いで作る。

| 部分 | 出どころ |
|---|---|
| 変更点 | `CHANGELOG.md` の `## [<版>]` の節 |
| 案内文 | [`.github/release-common.md`](../../.github/release-common.md) |

組み立てるのは
[`spec/tools/release_notes.py`](../../spec/tools/release_notes.py) で、
リリースのワークフローが呼ぶ。手元でも確かめられる。

```bash
python3 spec/tools/release_notes.py 1.1.0
```

変更点の実体を `CHANGELOG.md` 側に置いているのは、同じ内容を 2 か所へ
書かせないためである。**節が無ければ組み立てが失敗する**ので、
変更点を書き忘れたまま公開することがない。

リポジトリ内への相対リンクは、そのタグを指す絶対URLへ書き換える。
リリースのページからは相対リンクを辿れないため。

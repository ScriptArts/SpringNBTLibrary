# テストの回し方

各言語の単体テストと、全言語の挙動が同じかを確かめる適合性テストは、CIでも動きます。
手元で動かすときは、リポジトリの直下で次を実行します。

```bash
# Homebrewで入れたツールチェーンへPATHを通す（必要なときだけ）
source spec/tools/env.sh

# 各言語の単体テスト
(cd csharp     && dotnet test)
(cd java       && mvn test)
(cd typescript && npm test)
(cd python     && python -m pytest tests)
(cd rust       && cargo test)

# 全言語の挙動が同じか（適合性テスト）
./spec/run-conformance.sh

# ドキュメントと実装の一致、リンク切れ、コメントの規約
python3 spec/tools/check_docs_sync.py
python3 spec/tools/check_links.py
python3 spec/tools/check_comments.py
```

適合性テストは`spec/testdata/`のテストベクタを全言語の検証ツールに通し、出力を突き合わせます。

手元のワールドで確かめるときは、Minecraftを終了させてから次を実行します。
このツールはワールドに書き込みません。

```bash
python3 spec/tools/scan_world.py "<ワールドのパス>"
```

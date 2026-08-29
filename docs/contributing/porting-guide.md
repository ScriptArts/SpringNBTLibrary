# 新しい言語を追加する

本ライブラリは「1人が全言語へ同一の API を提供する」ことを価値としている。
新しい言語を足すときも、その性質を壊さない手順で進める。

---

## 0. 前提

**`docs/spec/` が唯一の正である。**
既存の言語実装を写経するのではなく、仕様書を実装する。
既存実装は「仕様書の解釈が合っているか」を照らし合わせる参考にとどめる。

C# を基準実装としているので、迷ったら
[`csharp/src/SpringNBTLibrary/`](../../csharp/src/SpringNBTLibrary/) を見る
（[adr/0002](../adr/0002-idiomatic-naming.md)）。

---

## 1. 進める順番

**レイヤ1 → レイヤ2 → レイヤ3 の順に、各レイヤを完成させてから次へ進む。**

| 順 | レイヤ | 仕様 |
|---:|---|---|
| 1 | NBT（タグ・MUTF-8・圧縮・SNBT） | [10](../spec/10-nbt-binary.md) / [11](../spec/11-snbt.md) |
| 2 | Anvil（リージョンファイル） | [20](../spec/20-anvil-region.md) |
| 3 | World（ワールド・チャンク・ブロック） | [30](../spec/30-chunk-format.md) / [31](../spec/31-paletted-container.md) / [40](../spec/40-world-layout.md) |

各レイヤの完了条件は「適合性検証がそのレイヤのベクタで全件通ること」である。

---

## 2. 命名

[命名変換規則](../spec/00-conventions.md#3-命名変換規則)に従い、
**その言語で自然な綴り**にする。他言語の綴りをそのまま持ち込まない。

```
論理名 read_file
  -> Go なら ReadFile / Kotlin なら readFile / Swift なら readFile
```

概念・型構成・機能は完全に揃える。変えてよいのは綴りだけである。

---

## 3. 適合性検証ツールを実装する

これが**移植で最初に効く成果物**である。
次のインターフェースを持つ CLI を用意する。

```
<runner> decode         <入力パス> <出力JSONパス>
<runner> encode         <入力パス> <出力バイナリパス>
<runner> snbt           <入力パス> <出力SNBTパス>
<runner> region-list    <入力.mcaパス> <出力テキストパス>
<runner> region-rewrite <入力.mcaパス> <出力ディレクトリ>
<runner> chunk-report   <入力チャンクnbtパス> <出力テキストパス>
<runner> chunk-edit     <入力チャンクnbtパス> <出力nbtパス>
<runner> version
```

`spec/tools/run_conformance.py` の `LANGUAGES` に起動方法を足すと、
既存言語との突き合わせが自動で始まる。

**まだ実装していない言語は自動的に検証対象から外れる**ので、
1 コマンドずつ増やしながら進められる。

---

## 4. つまずきやすいところ

移植のたびに実際に踏んだ箇所を挙げる。

| 箇所 | 内容 |
|---|---|
| MUTF-8 | `U+0000` は `C0 80`。BMP 外は 4 バイトではなくサロゲートペア 2 つ（3+3 バイト） |
| 孤立サロゲート | UTF-8 に写せない文字列をどう保持するか。Rust は 2 形態の列挙にした（[spec/10 2.3](../spec/10-nbt-binary.md)） |
| 小数の表記 | 言語の既定書式は使えない。[正準な10進表記](../spec/11-snbt.md#51-浮動小数点の正準10進表記)を実装する |
| `-0.0` | 符号を落とす言語がある（JavaScript の `toExponential` など） |
| `i64` | 64bit 整数を持たない言語では専用の型が要る（[adr/0007](../adr/0007-typescript-bigint.md)） |
| 論理右シフト | `BitStorage` では符号なしとして扱う。算術シフトだと上位ビットが埋まる |
| 再帰の深さ | 深さ 512 を安全に扱えるか確かめる（[spec/00 5.1](../spec/00-conventions.md)） |
| キーの並び | `Compound` は挿入順を保持する。ハッシュマップで実装すると書き戻しが一致しない |
| `data` と `palette` の順 | 実データは `data` が先（[spec/31 4.1](../spec/31-paletted-container.md)） |

---

## 5. 単体テストを書く

適合性検証はバイト列の一致を見るが、API の振る舞いまでは見ない。
既存言語のテストと**同じ検証項目**を用意する。

```
tests/nbt      NBT レイヤ
tests/anvil    Anvil レイヤ
tests/world    World レイヤ
```

各言語のテストファイルを見比べれば、項目は対応が付くようにしてある。

---

## 6. ドキュメントに載せる

1. `spec/tools/extract_api.py` に抽出器を足す
   （その言語のソースから公開型・公開メンバを拾う）
2. `LANGUAGE_ORDER` と `LANGUAGE_LABELS` に言語を足す
3. `python3 spec/tools/check_docs_sync.py --write` で
   [API 対応表](../api/overview.md)を再生成する
4. `docs/features.md` に列を足す
5. `docs/getting-started/<言語>.md` を書く

**5 が済むまで「対応した」とは言わない。**
実装があってもドキュメントから辿れなければ、利用者には存在しないのと同じである。

---

## 7. 実ワールドで確かめる

最後に、自分の Minecraft ワールドで検証する。
合成のテストベクタでは実データの網羅性に届かない。

```bash
python3 spec/tools/scan_world.py "<ワールドのパス>"
```

このツールは Python 実装を使うので、
新しい言語では `run-conformance.sh` の実ワールドモードで確かめる。

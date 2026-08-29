# 90. 適合性

全言語の実装が同一に振る舞うことを機械的に検証する仕組み。
本ライブラリの存在意義そのものなので、実装より先にこの枠組みを作る。

---

## 1. テストベクタの構成

```
spec/testdata/
├─ nbt/                入力バイナリ (.nbt) と、対応する SNBT (.snbt)
├─ anvil/              .mca / .mcc
├─ world/              最小ワールド一式
└─ expect/             正規化JSON の期待値（入力と同じ相対パス + .json）
```

`spec/testdata/manifest.json` が全ベクタの一覧と、各々が検証する内容を持つ。

```json
{
  "vectors": [
    {
      "id": "nbt/all_tags",
      "input": "nbt/all_tags.nbt",
      "expect": "expect/nbt/all_tags.json",
      "snbt": "nbt/all_tags.snbt",
      "format": "java",
      "compression": "none",
      "roundtrip": true,
      "description": "全13タグを1つずつ含む"
    }
  ]
}
```

`roundtrip: false` のベクタは「読めるが、書き戻すとバイトが変わる」ことが
仕様上正しいもの（第三者ツールが書いた非正準なデータなど）を表す。

---

## 2. 検証の3種類

### 2.1 デコード一致

入力バイナリを読み、[00 共通規約 6章](00-conventions.md#6-正規化json適合性検証の中間表現)の
正規化JSON へ変換し、`expect/` のファイルと**文字列として完全一致**することを確認する。

JSON の出力規則（全言語で一致させるため厳密に定める）:

- キーの順序は本仕様に書かれた順（`type` → `element_type` → `value` → `mutf8`）
- 区切りは `,` と `:`（**空白なし**）
- 非 ASCII 文字は `\uXXXX` へエスケープする
- 末尾に改行を1つ付ける

### 2.2 ラウンドトリップ

`read(bytes) -> write() -> bytes'` で `bytes == bytes'` を確認する。

- 圧縮ありのベクタは、**展開後のバイト列**で比較する（圧縮結果は zlib 実装のバージョンで変わるため）
- `roundtrip: false` のベクタはこの検証をスキップする

### 2.3 クロス言語一致

`spec/run-conformance.sh` が全言語それぞれの CLI 検証ツールを起動し、
同じ入力に対する出力（正規化JSON と再書き出しバイト列）を相互に diff する。

各言語は次のインターフェースを持つ検証ツールを提供する。

```
<runner> decode  <入力パス> <出力JSONパス>
<runner> encode  <入力パス> <出力バイナリパス>
<runner> snbt    <入力パス> <出力SNBTパス>
<runner> region-list    <入力.mcaパス> <出力テキストパス>
<runner> region-rewrite <入力.mcaパス> <出力ディレクトリ>
<runner> chunk-report   <入力チャンクnbtパス> <出力テキストパス>
<runner> chunk-edit     <入力チャンクnbtパス> <出力nbtパス>
<runner> version
```

`chunk-report` はチャンクの全 4096 ブロック（と 4×4×4 のバイオーム）を
1 つずつ読み出して種類ごとに数え上げる。パレットとビット詰めの取り出しを
端から端まで通すので、どこか 1 か所でも境界の扱いを誤れば集計値が変わる。

`chunk-edit` は決まった手順（パレット拡張・ビット幅の再計算・`compact()`・
高さマップの無効化）でチャンクを編集し、無圧縮 NBT として書き出す。
全言語で**バイト単位に一致**しなければならない。

| 言語 | 起動方法 |
|---|---|
| C# | `dotnet csharp/tests/SpringNBTLibrary.Conformance/bin/Release/net8.0/springnbt-conformance.dll` |
| Java | `java -cp java/target/classes:java/target/test-classes io.github.scriptarts.springnbt.conformance.Conformance` |
| TypeScript | `node typescript/dist/src/conformance.js` |
| Python | `python -m spring_nbt_library.conformance` |
| Rust | `rust/target/release/examples/conformance` |

`spec/tools/run_conformance.py` が各言語のビルドと起動を引き受ける。
**まだ実装されていない言語は自動的に検証対象から外れる**ので、
言語を 1 つずつ追加していく途中でも走らせられる。

---

## 2.4 実ワールド走査

合成ベクタだけでは、実際の Minecraft が書き出すデータの網羅性に届かない。
`spec/tools/scan_world.py` が手元のワールドを丸ごと読んで、次を確認する。

```bash
python3 spec/tools/scan_world.py "<ワールドのパス>" --verbose
```

やること:

1. すべての `.dat` / `.nbt` を読み、ラウンドトリップ（読む→書く→バイト一致）を検証
2. すべての `.mca` のヘッダを解析し、全チャンクを展開して NBT として読み、同じく検証
3. セクタの重複・不正オフセット・ファイル長の非整列を検出
4. パレット長から求めたビット幅と、実際の `data` 長が一致するかを検証（[31](31-paletted-container.md)）
5. ルート直下キー・セクションキー・`Status` の出現数を集計し、**仕様書とのズレを見つける**
6. World レイヤで全チャンクを解釈し直し、書き戻したバイト列が原本と一致するかを検証。
   さらに一部のチャンクは全ブロック・全バイオームを 1 つずつ読み出す
   （`--block-sample` で件数を変えられる）

**このツールは一切書き込まない。** ただし Minecraft を終了させてから実行すること。

ワールドのデータ自体はリポジトリに取り込まない（個人のセーブデータであるため）。
検証したい人が自分のワールドを指定して走らせる形にしてある。

### 検証実績

| 日付 | 対象 | 結果 |
|---|---|---|
| 2026-08-29 | Java版 26.2 の実ワールド（DataVersion 4903） | `.dat` 23個 + チャンク 3,717個 = **3,740件すべて読み込み・バイト一致のラウンドトリップ成功**。失敗 0 |
| 2026-08-29 | 同ワールドから抽出した代表14ファイル × 5言語 | 正規化JSON と SNBT が**全言語で完全一致**。書き戻したバイト列も**70件すべて原本と一致** |
| 2026-08-29 | 同ワールドのリージョンファイル 12個 × 5言語 | チャンク一覧と詰め直したバイト列が**全言語で完全一致**（3,717チャンク）。開いて無変更で書き戻すと**バイト単位で原本と一致** |
| 2026-08-29 | 同ワールドを World レイヤ（`MinecraftWorld` / `Chunk` / `PalettedContainer`）で解釈 | 3,481 チャンク・83,544 セクションを解釈し、NBT へ書き戻したバイト列が**全件原本と一致**。うち 40 チャンクは全ブロックを 1 つずつ読み出し（**393万ブロック**、79 種類）、バイオームも含めて成功。失敗 0 |

パレット付きコンテナ（[31](31-paletted-container.md)）については、
83,544 セクション = **167,088 個のコンテナすべて**で、
パレット長から求めたビット幅と実際の `data` 長が一致することを確認した。

この走査により、**[40 ワールドのディレクトリ構成](40-world-layout.md) が 26.x で大きく変わっていること**
（`dimensions/` への集約、`players/` への改名、`level.dat` からのデータ分離）が判明し、仕様書を全面的に書き直した。

---

## 3. ベクタ一覧（v0.1.0 で用意するもの）

### NBT

| ID | 検証内容 |
|---|---|
| `nbt/hello_world` | 最小の Compound |
| `nbt/all_tags` | 全13タグを1つずつ |
| `nbt/nested_deep` | ネスト深さ 500（上限 512 の直下） |
| `nbt/nested_too_deep` | ネスト深さ 513 → `LIMIT_EXCEEDED` |
| `nbt/empty_list` | 空リスト（要素型 End） |
| `nbt/empty_list_typed` | 空リストだが要素型が Byte（第三者ツール由来） |
| `nbt/numeric_bounds` | 各整数型の最小値・最大値 |
| `nbt/float_specials` | `+0.0` `-0.0` `Infinity` `-Infinity` `NaN` |
| `nbt/mutf8_nul` | `U+0000` を含む文字列 |
| `nbt/mutf8_supplementary` | 補助文字（絵文字）を含む文字列 |
| `nbt/mutf8_lone_surrogate` | 孤立サロゲート |
| `nbt/mutf8_max_length` | 65535 バイトちょうどの文字列 |
| `nbt/gzip` / `nbt/zlib` / `nbt/uncompressed` | 3種の圧縮を自動判定して読む |
| `nbt/network_format` | 無名ルート（1.20.2+） |
| `nbt/truncated` | 途中で切れた入力 → `MALFORMED_DATA` |
| `nbt/huge_declared_length` | 長さ `0x7FFFFFFF` の宣言 → `MALFORMED_DATA` |
| `nbt/unknown_tag_id` | タグID 13 → `MALFORMED_DATA` |

### Anvil

| ID | 検証内容 |
|---|---|
| `anvil/empty` | 全エントリ 0 のリージョン |
| `anvil/single_chunk` | チャンク1つ |
| `anvil/fragmented` | 隙間のある配置。読み書き後も他チャンクを壊さない |
| `anvil/external_mcc` | `.mcc` へ退避されたチャンク |
| `anvil/mixed_compression` | 圧縮ID 1 / 2 / 3 が混在 |
| `anvil/bad_offset` | ヘッダ領域を指すオフセット → `MALFORMED_DATA` |
| `anvil/overlapping_sectors` | 2チャンクが同じセクタを指す → `MALFORMED_DATA` |

### World / Block

| ID | 検証内容 |
|---|---|
| `world/minimal` | level.dat + region 1ファイルの最小ワールド |
| `world/palette_1` | パレット1要素（`data` なし）のセクション |
| `world/palette_5` | ビット幅 4、端数なし |
| `world/palette_17` | ビット幅 5、最後の long に端数 |
| `world/palette_grow` | `set_block` でビット幅が 4→5 へ拡張される |
| `world/palette_compact` | `compact()` で未使用要素が消えビット幅が縮む |
| `world/biome_rw` | 4×4×4 解像度のバイオーム読み書き |

---

## 4. ベクタの生成方針

期待値が生成器のバグを写してしまわないよう、次の順で作る。

1. **手書きの16進**で最小ベクタ（`hello_world`、`all_tags`）を定義する。
   `spec/tools/build_testdata.py` にバイト列を直接書き下し、
   仕様書の記述だけを根拠に組み立てる
2. その最小ベクタで Rust 実装を検証する
3. 検証済みの Rust 実装を使って、大きなベクタ（`nested_deep` など）を生成する
4. 生成されたベクタを他3言語で読み、一致することを確認する

つまり **手書きベクタが信頼の起点**であり、生成器は増幅にのみ使う。

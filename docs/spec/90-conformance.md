# 90. 適合性

全言語の実装が同一に振る舞うことを機械的に検証する仕組み。
本ライブラリの存在意義そのものなので、実装より先にこの枠組みを作る。

---

## 1. テストベクタの構成

```
spec/testdata/
├─ nbt/                入力バイナリ (.nbt)
├─ concat/             NBTが複数連なったバイナリ (.nbt)
├─ anvil/              ベクタごとのディレクトリに .mca / .mcc
├─ world/              チャンク1つ分のNBT (.nbt)
└─ expect/             正規化JSONの期待値（ベクタID + .json）
```

`spec/testdata/manifest.json`は、全ベクタの一覧と、各ベクタが検証する内容を持つ。

```json
{
  "vectors": [
    {
      "id": "nbt/all_tags",
      "kind": "nbt",
      "input": "nbt/all_tags.nbt",
      "format": "java",
      "compression": "none",
      "description": "全13タグを1つずつ含む",
      "expect": "expect/nbt/all_tags.json",
      "roundtrip": true
    }
  ]
}
```

読み込みが失敗することを確かめるベクタは、`expect`の代わりに`expect_error`（期待する`ErrorCode`）を持つ。

`roundtrip: false`のベクタは、「読めるが、書き戻すとバイトが変わる」ことが仕様上正しいもの（第三者ツールが書いた非正準なデータなど）を表す。
読み込みが失敗するベクタと、連なったNBTのベクタも`roundtrip: false`になる。

---

## 2. 検証の種類

### 2.1 デコード一致

入力バイナリを読み、[00 共通規約 6章](00-conventions.md#6-正規化json適合性検証の中間表現)の正規化JSONへ変換し、`expect/`のファイルと**文字列として完全一致**することを確認する。

全言語で一致させるため、JSONの出力規則を次のように厳密に定める。

- キーの順序は本仕様に書かれた順（`type` → `element_type` → `value` → `mutf8`）
- 区切りは`,`と`:`（**空白なし**）
- 非ASCII文字は`\uXXXX`へエスケープする
- 末尾に改行を1つ付ける

期待値ファイルを持つのは、読み込みに成功するNBTのベクタだけである。
Anvil・World・連なったNBTのベクタは、2.3のクロス言語一致で確かめる。

### 2.2 ラウンドトリップ

`read(bytes) -> write() -> bytes'`で`bytes == bytes'`を確認する。

- 圧縮ありのベクタは、**展開後のバイト列**で比較する（圧縮結果はzlib実装のバージョンで変わるため）
- `roundtrip: false`のベクタはこの検証をスキップする

### 2.3 クロス言語一致

`spec/run-conformance.sh`が全言語それぞれのCLI検証ツールを起動し、同じ入力に対する出力（正規化JSONと再書き出しバイト列）を相互にdiffする。

各言語は次のインターフェースを持つ検証ツールを提供する。

```
<runner> decode         <入力パス> <出力JSONパス> [--format network]
<runner> encode         <入力パス> <出力バイナリパス> [--format network]
<runner> snbt           <入力パス> <出力SNBTパス> [--format network]
<runner> nbt-list       <入力パス> <出力テキストパス> [--format network]
<runner> region-list    <入力.mcaパス> <出力テキストパス>
<runner> region-rewrite <入力.mcaパス> <出力.mcaパス>
<runner> chunk-report   <入力チャンクnbtパス> <出力テキストパス>
<runner> chunk-edit     <入力チャンクnbtパス> <出力nbtパス>
<runner> version
```

`nbt-list`は連なったNBT（[10 3.1](10-nbt-binary.md#31-連なったnbtを読む)）を`read_bytes_all`と`read_bytes_at`の両方で読み、個数と各NBTの開始・終了位置を書き出す。

`chunk-report`は、チャンクの全4096ブロック（と4×4×4のバイオーム）を1つずつ読み出して種類ごとに数え上げる。パレットとビット詰めの取り出しを端から端まで通すので、どこか1か所でも境界の扱いを誤れば集計値が変わる。

`chunk-edit`は決まった手順（パレット拡張・ビット幅の再計算・`compact()`・高さマップの無効化）でチャンクを編集し、無圧縮NBTとして書き出す。全言語で**バイト単位に一致**しなければならない。

| 言語 | 起動方法 |
|---|---|
| C# | `dotnet csharp/tests/SpringNBTLibrary.Conformance/bin/Release/net8.0/springnbt-conformance.dll` |
| Java | `java -cp java/target/classes:java/target/test-classes io.github.scriptarts.springnbt.conformance.Conformance` |
| TypeScript | `node typescript/dist/src/conformance.js` |
| Python | `python -m spring_nbt_library.conformance` |
| Rust | `rust/target/release/examples/conformance` |

`spec/tools/run_conformance.py`が各言語のビルドと起動を引き受ける。実装が無い言語は自動的に検証対象から外れるので、言語を1つずつ追加していく途中でも走らせられる。

### 2.4 実ワールド走査

合成ベクタだけでは、実際のMinecraftが書き出すデータを網羅しきれない。
`spec/tools/scan_world.py`が手元のワールドを丸ごと読んで、次を確認する。

```bash
python3 spec/tools/scan_world.py "<ワールドのパス>" --verbose
```

`scan_world.py`は次の処理を行う。

1. すべての`.dat` / `.nbt`を読み、ラウンドトリップ（読む→書く→バイト一致）を検証
2. すべての`.mca`のヘッダを解析し、全チャンクを展開してNBTとして読み、同じく検証
3. セクタの重複・不正オフセット・ファイル長の非整列を検出
4. パレット長から求めたビット幅と、実際の`data`長が一致するかを検証（[31](31-paletted-container.md)）
5. ルート直下キー・セクションキー・`Status`の出現数を集計し、仕様書とのズレを見つける
6. Worldレイヤで全チャンクを解釈し直し、書き戻したバイト列が原本と一致するかを検証。さらに一部のチャンクは全ブロック・全バイオームを1つずつ読み出す（`--block-sample`で件数を変えられる）

**このツールは一切書き込まない。** ただし、Minecraftを終了させてから実行すること。

ワールドのデータ自体は、個人のセーブデータであるためリポジトリに取り込まない。
検証したい人が自分のワールドを指定して走らせる形にしてある。

#### 検証実績

| 日付 | 対象 | 結果 |
|---|---|---|
| 2026-08-29 | Java版26.2の実ワールド（DataVersion 4903） | `.dat` 23個 + チャンク3,717個 = 3,740件すべてで読み込みとバイト一致のラウンドトリップに成功。失敗0 |
| 2026-08-29 | 同ワールドから抽出した代表14ファイル × 5言語 | 正規化JSONとSNBTが全言語で完全一致。書き戻したバイト列も70件すべて原本と一致 |
| 2026-08-29 | 同ワールドのリージョンファイル12個 × 5言語 | チャンク一覧と詰め直したバイト列が全言語で完全一致（3,717チャンク）。開いて無変更で書き戻すと、バイト単位で原本と一致 |
| 2026-08-29 | 同ワールドをWorldレイヤ（`MinecraftWorld` / `Chunk` / `PalettedContainer`）で解釈 | 3,481チャンク・83,544セクションを解釈し、NBTへ書き戻したバイト列が全件原本と一致。うち40チャンクは全ブロックを1つずつ読み出し（393万ブロック、79種類）、バイオームも含めて成功。失敗0 |

パレット付きコンテナ（[31](31-paletted-container.md)）については、83,544セクション = 167,088個のコンテナすべてで、パレット長から求めたビット幅と実際の`data`長が一致することを確認した。

この走査で、[40 ワールドのディレクトリ構成](40-world-layout.md)が26.xで大きく変わっていること（`dimensions/`への集約、`players/`への改名、`level.dat`からのデータ分離）が分かり、仕様書を全面的に書き直した。

---

## 3. ベクタ一覧

### NBT

| ID | 検証内容 |
|---|---|
| `nbt/hello_world` | 最小のCompound。ルート名が空でない |
| `nbt/all_tags` | 全13タグを1つずつ |
| `nbt/nested_deep` | ネスト深さ500（上限512の直下） |
| `nbt/nested_too_deep` | ネスト深さ600 → `LIMIT_EXCEEDED` |
| `nbt/empty_list` | 空リスト（要素型End） |
| `nbt/empty_list_typed` | 空リストだが要素型がByte（第三者ツール由来） |
| `nbt/numeric_bounds` | 各整数型の最小値・最大値 |
| `nbt/float_specials` | `+0.0` `-0.0` `Infinity` `-Infinity` `NaN` |
| `nbt/mutf8_nul` | `U+0000`を含む文字列 |
| `nbt/mutf8_supplementary` | 補助文字（絵文字）を含む文字列 |
| `nbt/mutf8_lone_surrogate` | 孤立サロゲート |
| `nbt/mutf8_max_length` | 65535バイトちょうどの文字列 |
| `nbt/gzip` / `nbt/zlib` / `nbt/uncompressed` | 3種の圧縮を自動判定して読む |
| `nbt/network_format` | 無名ルート（1.20.2+） |
| `nbt/truncated` | 途中で切れた入力 → `MALFORMED_DATA` |
| `nbt/huge_declared_length` | 長さ`0x7FFFFFFF`の宣言 → `MALFORMED_DATA` |
| `nbt/unknown_tag_id` | タグID 13 → `MALFORMED_DATA` |
| `nbt/negative_length` | 長さフィールドが負値 → `MALFORMED_DATA` |
| `nbt/trailing_bytes` | ルートの後に余分なバイトがある → `MALFORMED_DATA` |
| `nbt/mutf8_lone_surrogate_key` | Compoundのキーが孤立サロゲート → `MALFORMED_DATA` |
| `nbt/mutf8_raw_nul` | MUTF-8に反する素の`0x00`を含む文字列 → `MALFORMED_DATA` |

### 連なったNBT

| ID | 検証内容 |
|---|---|
| `concat/three_tags` | 同じNBTが3つ連なっている |
| `concat/mixed` | 大きさの違うNBTが3つ連なっている |
| `concat/single` | NBTが1つだけ |

### Anvil

| ID | 検証内容 |
|---|---|
| `anvil/empty` | 全エントリ0のリージョン |
| `anvil/single_chunk` | チャンク1つ |
| `anvil/fragmented` | 隙間のある配置。読み書き後も他チャンクのデータがおかしくならない |
| `anvil/external_mcc` | `.mcc`へ退避されたチャンク |
| `anvil/mixed_compression` | 圧縮ID 1 / 2 / 3が混在 |
| `anvil/lz4` | 圧縮ID 4（LZ4）。1ブロック / 2ブロック連結 / 無圧縮ブロック / 重なりのあるマッチ |
| `anvil/lz4_bad_magic` | LZ4Blockのマジックがおかしい → `MALFORMED_DATA` |
| `anvil/bad_offset` | ヘッダ領域を指すオフセット → `MALFORMED_DATA` |
| `anvil/overlapping_sectors` | 2チャンクが同じセクタを指す → `MALFORMED_DATA` |
| `anvil/unaligned_length` | ファイル長が4096の倍数でない → `MALFORMED_DATA` |
| `anvil/offset_out_of_file` | オフセットがファイル末尾より後ろを指す → `MALFORMED_DATA` |

### World / Block

| ID | 検証内容 |
|---|---|
| `world/palette_1` | パレット1要素（`data`なし）のセクション |
| `world/palette_5` | ビット幅4、端数なし |
| `world/palette_17` | ビット幅5、最後のlongに端数 |
| `world/multi_section` | セクション3個。バイオームも2種（ビット幅1） |
| `world/palette_unused` | 参照されていないパレット要素が2つある。`compact()`で減る |
| `world/block_entities` | `block_entities` / `block_ticks` / `fluid_ticks`を持つチャンク |
| `world/proto_chunk` | 生成途中のチャンク（`Status`が`minecraft:full`でない） |
| `world/palette_index_out_of_range` | 添字がパレットの範囲外を指す → `MALFORMED_DATA` |
| `world/bitstorage_wrong_length` | `data`の長さがパレット長から求めたビット幅と合わない → `MALFORMED_DATA` |

---

## 4. ベクタの生成方針

ライブラリのバグがそのまま期待値にならないよう、次の順で作る。

1. `spec/tools/build_testdata.py`が、入力ベクタ（NBT・連なったNBT・Anvil・World）と`manifest.json`をすべて生成する。このスクリプトはライブラリを使わず、仕様書の記述だけを根拠にした独立の最小NBTライタでバイト列を組み立てる。大きなベクタ（`nested_deep`など）もここで作る
2. `nbt/hello_world`の期待値（`expect/nbt/hello_world.json`）だけは手で書く
3. `spec/tools/run_conformance.py --generate-expect`で、基準実装（C#）の出力からNBTベクタの`expect/`を生成する。手書きの`hello_world`は上書きせず、基準実装の出力と一致するかを確かめる
4. 生成した期待値と全言語の出力を比べ、一致することを確認する（2章）

つまり、**ライブラリを使わずに作った入力ベクタと手書きの期待値が信頼の起点**であり、基準実装の出力は期待値を増やすためにだけ使う。

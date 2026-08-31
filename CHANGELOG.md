# 変更履歴

このファイルの書式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) に従う。

## バージョン番号の付け方

`x.y.z` の各桁は次を表す。

| 桁 | 上がるとき |
|---|---|
| `x` | ワールドの保存形式が変わったとき |
| `y` | 機能を足した、または外したとき |
| `z` | 不具合を直したとき |

対応言語はすべて、常に同じバージョン番号で公開する。

## [未リリース]

### 変更

- **バージョン判定を「形式」に変えた** — これまでは `DataVersion` が 4903 ちょうどか
  どうかを見ていたため、Minecraft が更新されるたび、中身が何も変わっていなくても
  警告が出ていた。いまのワールド形式は 26.1 で導入されたものなので、
  `MIN_SUPPORTED_DATA_VERSION = 4786` を下限とし、**それ以降なら警告を出さない**
  （[adr/0003](docs/adr/0003-version-policy.md)）
- **書き戻すとき `DataVersion` を書き換えないようにした** — これまでは常に 4903 を
  書いていた。新しいバージョンのワールドを編集すると、古い番号を上書きしてしまい、
  ゲーム側がアップグレードの要否を誤る
- **Rust の `set_block` から複製を取り除いた** — `&BlockState` を渡しても 1 回ごとに
  複製していた。1 チャンク分（98,304 ブロック）を 1 つずつ置く計測で、
  石が 28.4ms → 25.1ms、プロパティ 2 個のブロックが 70.4ms → 55.8ms になった

## [1.0.0]

最初のリリース。対象は **Minecraft Java版 26.2（DataVersion 4903）**。

対応言語は **C# / Java / TypeScript / Python / Rust**。
標準ライブラリだけで動き、外部の依存は要らない（Rust の `flate2` を除く）。

### NBT

[ガイド](docs/guide/01-nbt.md) / [仕様](docs/spec/10-nbt-binary.md)

- 全13タグの読み書き
- MUTF-8 の文字列（`U+0000` の 2 バイト表現、補助文字のサロゲートペア表現、孤立サロゲートの保持）
- 圧縮 Gzip / Zlib / 無圧縮と、先頭バイトからの自動判定
- Java 形式（名前付きルート）と Network 形式（1.20.2 以降の無名ルート）
- 挿入順を保持する `NbtCompound`
- 型付き取得子 `get_int` / `opt_int`。「キーが無い」と「型が違う」を区別する
- 型付き設定子 `set_int(key, 42)`。取得子と対になる
- 位置を指定した読み込み `read_bytes_at` / `read_bytes_all`。連なった NBT を順に読める
- 等値比較と深い複製。浮動小数点はビットパターンで、`NbtCompound` は挿入順も含めて比べる
- SNBT のパースと出力（1行 / 整形）。1.21.5 以降の拡張構文に対応
- 浮動小数点の正準10進表記
- 安全上限。ネスト深さ 512、宣言長の先行検証、展開後サイズの上限

### Anvil

[ガイド](docs/guide/03-anvil-region.md) / [仕様](docs/spec/20-anvil-region.md)

- `.mca` リージョンファイルの読み書き
- 無変更で書き戻すと、原本とバイト単位で一致する
- セクタの再配置と、解放したセクタの再利用
- 圧縮ID 1 (GZip) / 2 (Zlib) / 3 (無圧縮) の読み書き
- 圧縮ID 4 (LZ4) の読み込み。書き込みは Zlib になる
- 外部ファイル `.mcc` への自動退避と復帰
- 生バイトでのチャンク入出力。扱えない圧縮方式でもそのまま移せる
- 断片化解消 `optimize()`
- セクタ重複・不正オフセット・ファイル長の整列検査
- `region/` `entities/` `poi/` の横断アクセス
- 同時に開くリージョンの上限管理（既定 8 件）

### World / Block

[ガイド](docs/guide/05-blocks-and-biomes.md) / [仕様](docs/spec/30-chunk-format.md)

- `level.dat` の読み込みと、一時ファイル経由の安全な書き込み
- 26.x のディレクトリ構成（`dimensions/` への集約、`players/` への改名、`data/minecraft/*.dat` への分離）
- 標準3次元とカスタム次元の解決。次元IDは定数で参照できる
- 絶対座標でのブロック・バイオームの取得と設定
- ブロックは `BlockState` でも `"minecraft:oak_stairs[facing=north]"` の文字列でも置ける
- 置き換え時に、その座標を指す `block_entities` / `block_ticks` / `fluid_ticks` を取り除く
- ブロック座標 `BlockPos` と範囲 `Cuboid`。範囲内の座標を順に走査できる
- チャンクの変更フラグ `is_modified`。書き戻す対象を決める
- パレットの自動拡張とビット幅の再計算、未使用パレットの掃除 `compact()`
- 非正準な BitStorage の救済読み

### 共通

- 全言語で一致する `ErrorCode`
- DataVersion 不一致時の警告／エラー切り替え
- クロス言語適合性検証（`spec/run-conformance.sh`）
- 実ワールド走査ツール（`spec/tools/scan_world.py`）
- 実装から生成する [API 対応表](docs/api/overview.md)

### 対応していないもの

- `Heightmaps` と光源の再計算（無効化のみ提供。[adr/0004](docs/adr/0004-defer-heightmap-recalc.md)）
- 圧縮ID 4 (LZ4) での書き込み、圧縮ID 127（カスタム方式）の展開
- SNBT の異種リストと `\N{文字名}` エスケープ
- `entities` / `poi` の型付きAPI（生NBTとしてなら読み書きできる）
- チャンクの新規生成（ワールド生成は本ライブラリの範囲外）
- 過去バージョンのワールド改変（[adr/0003](docs/adr/0003-version-policy.md)）
- Bedrock版（LevelDB形式）

### 言語ごとの差異

言語の性質上どうしても揃えられない箇所は
[機能一覧の「言語ごとの差異」](docs/features.md#言語ごとの差異)にまとめてある。

- `session.lock` の確認は C# / Java / Python(POSIX) のみ（[adr/0008](docs/adr/0008-session-lock.md)）
- TypeScript は `i64` に `bigint` を使う（[adr/0007](docs/adr/0007-typescript-bigint.md)）
- TypeScript にストリーム入出力は無い。Node のストリームは非同期しか無いため
- Rust のみ例外ではなく `Result<T, Error>` を返す（[adr/0005](docs/adr/0005-unified-error-model.md)）
- Rust の `NbtString` は 2 形態の列挙。孤立サロゲートを保持するため

### 検証

- 各言語の単体テスト 873 件
- クロス言語適合性 834 件（全言語で出力バイト列が一致）
- 実ワールド（Java版 26.2）: `.dat` 23個 + チャンク 3,717個 すべてラウンドトリップ成功。
  World レイヤでも 3,481 チャンク・83,544 セクションの再エンコードが原本と一致し、
  393万ブロックの読み出しに成功

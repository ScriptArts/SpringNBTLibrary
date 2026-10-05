# 変更履歴

このファイルの書式は[Keep a Changelog](https://keepachangelog.com/ja/1.1.0/)に従う。

## バージョン番号の付け方

`x.y.z`の各桁は次を表す。

| 桁 | 上がるとき |
|---|---|
| `x` | ワールドの保存形式が変わったとき |
| `y` | 機能を足した、または外したとき |
| `z` | 不具合を直したとき |

対応言語はすべて、常に同じバージョン番号で公開する。

## [未リリース]

### 修正

- Rust: ワールド経由でチャンクを読むと、`WorldOpenOptions`に渡した警告の通知先が呼ばれなかった
- Python: binary32の範囲を超える値を`NbtFloat`に渡すと`OverflowError`が出ていた。他の言語と同じく符号付きの無限大にする
- Python: 途中で切れたGZipや中身の壊れた圧縮データを読むと、`MALFORMED_DATA`ではなく標準の例外がそのまま出ていた
- Python / TypeScript: `TAG_Float`のシグナリングNaNを読んで書き戻すと、ビットパターンが変わっていた
- Python: SNBTの`"😀"`のように対になったサロゲートが、補助文字1文字と別の文字列として扱われていた
- SNBTの`\U`でサロゲートの範囲を書いたときの扱いが言語ごとに違っていた（C#は想定外の例外が漏れていた）。`\u`と同じく孤立サロゲートとして読む
- C# / Java / TypeScript / Python: SNBTやAPIで、孤立サロゲートを含むCompoundのキーを受け付けていた。書き出すと読み戻せないため、SNBTでは`MALFORMED_DATA`、APIでは`INVALID_ARGUMENT`にする
- TypeScript: `NbtList`の`get` / `set` / `insert` / `removeAt`が位置を検査せず、範囲外へ`set`すると配列が伸びていた。`RangeError`にする
- C# / Java / Python / TypeScript / Rust: リストの範囲外の位置へ`set` / `insert`して失敗したときに、空のリストの要素型が確定していた
- Rust: `NbtList::insert`で範囲外の位置を渡すとパニックしていた。`INVALID_ARGUMENT`にする
- 読み書きモードで存在しないリージョンフォルダを開くと、書き出しの時点でディレクトリが無く失敗していた。書き出すときにディレクトリを作る
- `level.dat`の保存で、一時ファイルの内容をディスクへ書き出してから置き換えるようにした（fsync）
- TypeScript / Rust: SNBTの`\N{…}`のエラーメッセージで波括弧が抜けていた

## [1.0.0]

最初のリリース。対象は**26.1で導入されたワールド形式**（DataVersion 4786以降）。
動作はJava版26.2（DataVersion 4903）の実ワールドで確かめている。

対応言語は**C# / Java / TypeScript / Python / Rust**。
標準ライブラリだけで動き、外部の依存は要らない（Rustの`flate2`を除く）。

### NBT

[ガイド](docs/guide/01-nbt.md) / [仕様](docs/spec/10-nbt-binary.md)

- 全13タグの読み書き
- MUTF-8の文字列（`U+0000`の2バイト表現、補助文字のサロゲートペア表現、孤立サロゲートの保持）
- 圧縮Gzip / Zlib / 無圧縮と、先頭バイトからの自動判定
- Java形式（名前付きルート）とNetwork形式（1.20.2以降の無名ルート）
- 挿入順を保持する`NbtCompound`
- 型付き取得子`get_int` / `opt_int`。「キーが無い」と「型が違う」を区別する
- 型付き設定子`set_int(key, 42)`。取得子と対になる
- 位置を指定した読み込み`read_bytes_at` / `read_bytes_all`。連なったNBTを順に読める
- 等値比較と深い複製。浮動小数点はビットパターンで、`NbtCompound`は挿入順も含めて比べる
- SNBTのパースと出力（1行 / 整形）。1.21.5以降の拡張構文に対応
- 浮動小数点の正準10進表記
- 安全上限。ネスト深さ512、宣言長の先行検証、展開後サイズの上限

### Anvil

[ガイド](docs/guide/03-anvil-region.md) / [仕様](docs/spec/20-anvil-region.md)

- `.mca`リージョンファイルの読み書き
- 無変更で書き戻すと、原本とバイト単位で一致する
- セクタの再配置と、解放したセクタの再利用
- 圧縮ID 1 (GZip) / 2 (Zlib) / 3 (無圧縮)の読み書き
- 圧縮ID 4 (LZ4)の読み込み。書き込みはZlibになる
- 外部ファイル`.mcc`への自動退避と復帰
- 生バイトでのチャンク入出力。扱えない圧縮方式でもそのまま移せる
- 断片化解消`optimize()`
- セクタ重複・不正オフセット・ファイル長の整列検査
- `region/` `entities/` `poi/`の横断アクセス
- 同時に開くリージョンの上限管理（既定8件）

### World / Block

[ガイド](docs/guide/05-blocks-and-biomes.md) / [仕様](docs/spec/30-chunk-format.md)

- `level.dat`の読み込みと、一時ファイル経由の安全な書き込み
- 26.xのディレクトリ構成（`dimensions/`への集約、`players/`への改名、`data/minecraft/*.dat`への分離）
- 標準3次元とカスタム次元の解決。次元IDは定数で参照できる
- 絶対座標でのブロック・バイオームの取得と設定
- ブロックは`BlockState`でも`"minecraft:oak_stairs[facing=north]"`の文字列でも置ける
- 置き換え時に、その座標を指す`block_entities` / `block_ticks` / `fluid_ticks`を取り除く
- ブロック座標`BlockPos`と範囲`Cuboid`。範囲内の座標を順に走査できる
- チャンクの変更フラグ`is_modified`。書き戻す対象を決める
- パレットの自動拡張とビット幅の再計算、未使用パレットの掃除`compact()`
- 非正準なBitStorageの救済読み

### 共通

- 全言語で一致する`ErrorCode`
- ワールド形式による対応判定。下限（26.1）以降なら警告を出さず、書き戻すときも`DataVersion`を書き換えない（[adr/0003](docs/adr/0003-version-policy.md)）
- 扱えない形式を見つけたときの警告／エラー切り替え
- クロス言語適合性検証（`spec/run-conformance.sh`）
- 実ワールド走査ツール（`spec/tools/scan_world.py`）
- 実装から生成する[API対応表](docs/api/overview.md)

### 対応していないもの

- `Heightmaps`と光源の再計算（無効化のみ提供。[adr/0004](docs/adr/0004-defer-heightmap-recalc.md)）
- 圧縮ID 4 (LZ4)での書き込み、圧縮ID 127（カスタム方式）の展開
- SNBTの異種リストと`\N{文字名}`エスケープ
- `entities` / `poi`の型付きAPI（生NBTとしてなら読み書きできる）
- チャンクの新規生成（ワールド生成は本ライブラリの範囲外）
- 過去バージョンのワールド改変（[adr/0003](docs/adr/0003-version-policy.md)）
- Bedrock版（LevelDB形式）

### 言語ごとの差異

言語の性質上どうしても揃えられない箇所は、[機能一覧の「言語ごとの差異」](docs/features.md#言語ごとの差異)にまとめてある。

- `session.lock`の確認はC# / Java / Python(POSIX)のみ（[adr/0008](docs/adr/0008-session-lock.md)）
- TypeScriptは`i64`に`bigint`を使う（[adr/0007](docs/adr/0007-typescript-bigint.md)）
- TypeScriptにストリーム入出力は無い。Nodeのストリームは非同期しか無いため
- Rustのみ例外ではなく`Result<T, Error>`を返す（[adr/0005](docs/adr/0005-unified-error-model.md)）
- Rustの`NbtString`は2形態の列挙。孤立サロゲートを保持するため

### 検証

- 各言語の単体テスト888件
- クロス言語適合性834件（全言語で出力バイト列が一致）
- 実ワールド（Java版26.2）: `.dat` 23個 + チャンク3,717個すべてラウンドトリップ成功。
  Worldレイヤでも3,481チャンク・83,544セクションの再エンコードが原本と一致し、393万ブロックの読み出しに成功

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

## [3.0.1]

ライブラリの中身は3.0.0と同じで、配り方だけを変えた。

### 変更

- C#・TypeScript・Pythonを、NuGet・npm・PyPIへも公開するようにした。`dotnet add package SpringNBTLibrary`、`npm install spring-nbt-library`、`pip install spring-nbt-library`で入れられる（[リリース手順 5.5](docs/contributing/release.md#55-パッケージレジストリへの公開)）
- パッケージに同梱するREADMEの相対リンクを、そのタグを指す絶対URLへ直してから組み立てる。パッケージのページからもリンクを辿れるようにするため

## [3.0.0]

Java版1.13以降のワールドを扱えるようにした。チャンクとワールドの構成を形式の世代に分け、読んだときの形式のまま読み書きする。バージョン間の変換はしない（[adr/0011](docs/adr/0011-format-eras.md)）。
26.2で作ったワールドを26.3で開いたときに残る26.2の形式のチャンクも、読み書きできる。
動作はJava版1.13.2から26.3までの実ワールドで確かめている。

Rustの公開APIに互換性の崩れる変更（下の「互換性の崩れる変更（Rust）」）があるので、`x`を上げた。ワールドの保存形式は変わっていない。

### 追加

- チャンクの形式を5つの世代（1.13〜1.14.x、1.15、1.16〜1.17.x、1.18〜26.2、26.3以降）に分け、チャンクごとに自身の`DataVersion`で選ぶ。書き戻すときも読んだときの世代の形式で書き、`DataVersion`は書き換えない（[仕様30 7章](docs/spec/30-chunk-format.md#7-形式の世代)）
- 1.21.xまでのワールドの構成（直下の`region/`、`DIM-1/` / `DIM1/`、`playerdata/`、`data/<名前>.dat`）を読む。構成は`level.dat`の`DataVersion`で選ぶ（[仕様40 5章](docs/spec/40-world-layout.md#5-261より前の構成)）
- 1.21.xまでの`level.dat`では、`spawn_pos`が`SpawnX` / `SpawnY` / `SpawnZ`を、`difficulty`が数値の`Difficulty`を、`is_hardcore`が`hardcore`を読む。`difficulty`は数値を名前に直して返し、`spawn_dimension`は`UNSUPPORTED_FEATURE`になる
- `ChunkReadOptions.format_data_version`と`WorldOpenOptions.format_data_version`: 世代を選ぶDataVersionを指定する。指定できる値は`1519`以上
- `Chunk.format_data_version`: 世代を選ぶのに使ったDataVersionを返す。`DataVersion`の無いチャンクで指定も無ければ`-1`
- `Chunk.get_biome_id` / `set_biome_id`: 1.17までの形式の数値のバイオームIDを、名前に直さずに読み書きする。1.14までの形式では`y`を見ない。1.18以降の形式では`UNSUPPORTED_FEATURE`になる
- `BlockState.from_nbt_for_data_version` / `to_nbt_for_data_version`: DataVersionを指定して、パレットの要素を読み書きする。26.2までの形式は`{Name, Properties}`
- 1.15までの、値が64bitの境目をまたぐビット詰めを読み書きする（[仕様31 2.3](docs/spec/31-paletted-container.md#23-またぐ詰め方115まで)）

### 変更

- 扱える形式の下限`MIN_SUPPORTED_DATA_VERSION`を`5006`（26.3）から`1519`（1.13）へ下げた。`TARGET_DATA_VERSION`は`5023`のまま
- 新しい形式が出たら、下限を上げずに世代を足して対応する（[adr/0011](docs/adr/0011-format-eras.md)。[adr/0003](docs/adr/0003-version-policy.md)の下限の決め方と、[adr/0010](docs/adr/0010-palette-format-26-3.md)の決定1を置き換えた）
- 1.13より前（DataVersionが`1519`未満か、無い）のチャンクは解釈せず、元のNBTだけを持つ。ブロックとバイオームのAPI、`min_section_y`、`clear_heightmaps`、`invalidate_lighting`は`UNSUPPORTED_DATA_VERSION`になる
- 1.17までの形式のチャンクでは、`get_biome` / `set_biome`が`UNSUPPORTED_FEATURE`になる。`isLightOn`の無いチャンクでは、`invalidate_lighting`も`UNSUPPORTED_FEATURE`になる
- DataVersionが`5006`未満のチャンクのパレット（`{Name, Properties}`）を、`MALFORMED_DATA`にせず、その形式のまま読み書きする
- `is_fully_generated`は、`Status`から`minecraft:`を外して比べる。1.13の`postprocessed`と`fullchunk`も生成済みとみなす
- `Chunk.to_nbt`は、セクションの並びと、`block_states` / `biomes`のキーの並びを、読んだときのまま書き戻す。以前は`Y`の昇順と、`data`、`palette`の順に並べ直していた（[仕様31 4.1](docs/spec/31-paletted-container.md#41-キーの並び順)）
- `set_block`は、パレットに同じ`BlockState`を表す要素があれば、キーの並びが違ってもその要素を使う
- Python / TypeScript: `Dimension`のコンストラクタに、内部の型を受け取る必須の引数が増えた。利用者は直接作らず、`MinecraftWorld.dimension()`で得る
- 実ワールド走査ツール（`spec/tools/scan_world.py`）が、1.21.xまでの構成のワールドを開き、世代ごとに集計する。`uid.dat`と0バイトの`.mca`は失敗に数えずに飛ばす
- `RegionFile`の`flush()`は、開いてから変更が無く、ファイルが既にあれば何もしないようにした。これまでは同じ内容で書き直していた。そのままでは、長さが4096の倍数でないファイルが読んだだけで末尾を埋めて書き直されてしまう。ワールドと`RegionFolder`の`flush()`も読んだだけのリージョンを書き出さなくなる

### 修正

- C# / Java / TypeScript / Python: `is_fully_generated`が、`Status`の無いチャンクと`Status`が文字列でないチャンクで例外を投げていた。Rustと同じく偽を返す
- `block_states` / `biomes`に`data`と`palette`のほかのキーがあると、書き戻すときに落としていた。読んだまま残す
- 長さが4096の倍数でないリージョンファイルを`MALFORMED_DATA`にしていた。最後のチャンクのデータの直後でファイルが終わっているものが実ワールドにあり、そのリージョンのチャンクが1つも読めなかった。末尾をゼロで埋めたものとして読み、書き出すときは4096の倍数にする（[仕様20 2.3](docs/spec/20-anvil-region.md#23-長さが4096の倍数でないファイル)）
  - 最後のチャンクのデータがファイルの終わりで切れているものは、開いた時点で`MALFORMED_DATA`にする
  - 埋めるのはメモリの上だけで、変更しなければファイルは元のまま残る。変更して書き出すときに、末尾をゼロで埋める

### 互換性の崩れる変更（Rust）

- `ChunkReadOptions`と`WorldOpenOptions`に、公開の項目`format_data_version`が増えた。構造体リテラルですべての項目を書いて作っているコードは、`..Default::default()`を足す必要がある
- `Chunk::clear_heightmaps` / `invalidate_lighting`が`Result<()>`を返すようになった
- `LevelData::spawn_pos`の戻り値の型が`Result<&[i32]>`から`Result<Vec<i32>>`になった

### 知っておくこと

- バージョン間の変換はしない。1.12.2で作ったワールドを26.3の形式に直す、といった使い方はできない
- バイオームの数値のIDは名前に直さない。1.16.2以降はデータパックで独自のバイオームを足せるので、固定の表では正しく引けないため
- 世代の境界のDataVersionは、実ワールドでは観測したDataVersionの間にあることまでしか確かめていない（[仕様30 7.1](docs/spec/30-chunk-format.md#71-世代の表)）
- 開発版（スナップショット）で書かれたチャンクのうち、正式版と形式が違うものは扱わない

### 検証

- 各言語の単体テスト: C# 323件、Java 306件、TypeScript 256件、Python 325件、Rust 239件
- クロス言語適合性1133件（全言語で出力バイト列が一致）。1.12.2、1.14.4、1.15.2、1.16.5、26.2の形式のチャンクのベクタと、読んだときの並びを保って書き戻すことを確かめるベクタを足した
- 実ワールド（Java版1.12.2から26.3までの33ワールド）: NBTファイル884個とリージョンのチャンク374,006個のすべてでラウンドトリップ成功。
  Worldレイヤでも地形チャンク359,078個の再エンコードが原本と一致し、7,315万ブロックの読み出しに成功（[仕様90 2.4](docs/spec/90-conformance.md#検証実績)）
- 代表のチャンク326個・リージョンファイル78個・NBTファイル54個を5言語に通し、出力が全言語で一致した
- 適合性検証のベクタ`anvil/unaligned_length`（4096の倍数の長さに1バイト足したファイルを`MALFORMED_DATA`にする）を、読めることを確かめる`anvil/unaligned_extra_byte`に変えた。最後のチャンクのデータの直後で終わるファイル（`anvil/unaligned_tail`）と、データが途中で切れたファイル（`anvil/truncated_chunk`、`anvil/truncated_length`）のベクタを足した

## [2.0.0]

Java版26.3のワールド形式に対応した。26.3でブロックのパレットの形式が変わったため、26.1 / 26.2のワールドは扱わなくなる。
動作はJava版26.3（DataVersion 5023）の実ワールドで確かめている（[adr/0010](docs/adr/0010-palette-format-26-3.md)）。

### 変更

- 扱える形式の下限`MIN_SUPPORTED_DATA_VERSION`を`4786`（26.1）から`5006`（26.3）へ上げた。動作を確かめたバージョン`TARGET_DATA_VERSION`は`5023`（26.3）にした
- ブロックのパレット要素を26.3の形式で読み書きする（[仕様30 2.1](docs/spec/30-chunk-format.md#21-ブロック状態のパレット要素)）
  - 既定の状態のブロックはブロックIDだけの文字列、それ以外は`{id, properties}`。26.2までの`{Name, Properties}`は`MALFORMED_DATA`
  - 文字列とCompoundが混ざったパレットの包み`{"": <値>}`を、読むときに外し、書くときにMinecraftと同じ規則で包み直す
- `BlockState`の`from_nbt`は`NbtTag`を受け取り、`to_nbt`は`NbtTag`を返すようにした。プロパティが空なら`NbtString`、それ以外は`NbtCompound`になる
- `PalettedContainer`の`palette`は包みを外した要素を返す
- 実ワールド走査ツール（`spec/tools/scan_world.py`）が、パレットの要素の形を数えて出すようにした

### 知っておくこと

- 文字列で保存された既定の状態のブロックは、プロパティが空の`BlockState`として読む。ブロックごとの既定値は持たないので、`minecraft:oak_stairs`と、既定値をすべて書いた`minecraft:oak_stairs[facing=north,…]`は等しくならない（[ガイド05](docs/guide/05-blocks-and-biomes.md#既定の状態のブロック)）
- 26.2で作ったワールドを26.3で開いても、読み込まれなかったチャンクは古い形式のまま残る。ゲームの「ワールドを最適化」で変換してから使う

### 検証

- 各言語の単体テストに、26.3のパレット形式のテストを足した（各言語11件）
- クロス言語適合性893件（全言語で出力バイト列が一致）。文字列だけ・Compoundだけ・混ざったパレット、26.2までの形式のベクタを足した
- 実ワールド（Java版26.3）: `.dat` 23個 + チャンク3,654個すべてラウンドトリップ成功。
  Worldレイヤでも3,481チャンク・83,544セクションの再エンコードが原本と一致し、393万ブロックの読み出しに成功
- 同じワールドの`.dat` 21個・リージョンファイル11個・チャンク32個を5言語に通し、出力が全言語で一致した

## [1.0.1]

不具合の修正のみ。公開APIの型・メソッドと、保存形式は変わらない。

### 変更

- ドキュメントとコメントを読みやすく書き直し、実装と食い違っていた記述を直した（SNBTの異種リストの扱い、書き戻しを止めるDataVersionの条件など）
- 版をリリースのタグだけで決めるようにした。リポジトリ内のパッケージ設定の版は常に`0.0.0`で、Releasesの成果物にはタグの版が入る。gitのタグで参照したRustのクレートは、版が`0.0.0`と表示される（中身はそのタグのもの）

### 修正

- Rust: ワールド経由でチャンクを読むと、`WorldOpenOptions`に渡した警告の通知先が呼ばれなかった
- Python: binary32の範囲を超える値を`NbtFloat`に渡すと`OverflowError`が出ていた。他の言語と同じく符号付きの無限大にする
- Python: 途中で切れたGZipや中身の壊れた圧縮データを読むと、`MALFORMED_DATA`ではなく標準の例外がそのまま出ていた
- Python / TypeScript: `TAG_Float`のシグナリングNaNを読んで書き戻すと、ビットパターンが変わっていた
- Python: SNBTの`"\uD83D\uDE00"`のように対になったサロゲートが、補助文字1文字と別の文字列として扱われていた
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

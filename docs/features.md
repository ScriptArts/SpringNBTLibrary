# 機能一覧

何ができて何ができないかの一覧です。

凡例

| 記号 | 意味 |
|---|---|
| ✅ | 対応済み |
| 🔶 | 条件つきで対応（右端の「備考」に条件を記載） |
| ⏳ | 実装中 |
| ❌ | 未対応 |

対応している言語はC# / Java / TypeScript / Python / Rustで、今後も増やします。
対象は**1.13以降のワールド形式**（DataVersion 1519以降）です。
1.13から26.3までの形式を、読んだときの形式のまま読み書きします。バージョン間の変換はしません。
動作はJava版26.3 / DataVersion 5023と、1.13.2から26.2までの各バージョンの実ワールドで確かめています。
形式が同じであれば、これより新しいバージョンのワールドもそのまま読み書きできます。
1.13より前のワールド改変には対応していません（→ [07 バージョンポリシー](guide/07-version-policy.md)）。

この表は、CIの`lint`ワークフローが`spec/tools/check_docs_sync.py`で各言語の公開APIと照らし合わせています。
表と実装が食い違うとCIが落ちます。

---

## レイヤ1: NBT

| 機能 | C# | Java | TS | Py | Rust | 仕様 | 備考 |
|---|:--:|:--:|:--:|:--:|:--:|---|---|
| 全13タグの読み込み | ✅ | ✅ | ✅ | ✅ | ✅ | [10](spec/10-nbt-binary.md#1-タグ型) | |
| 全13タグの書き込み | ✅ | ✅ | ✅ | ✅ | ✅ | [10](spec/10-nbt-binary.md#5-正準書き出し-canonical-writer) | 出力は一意（正準ライタ） |
| MUTF-8文字列（U+0000・補助文字・孤立サロゲート） | ✅ | ✅ | ✅ | ✅ | ✅ | [10](spec/10-nbt-binary.md#2-文字列-mutf-8) | |
| 圧縮Gzip / Zlib / 無圧縮 | ✅ | ✅ | ✅ | ✅ | ✅ | [10](spec/10-nbt-binary.md#4-圧縮) | |
| 圧縮方式の自動判定 | ✅ | ✅ | ✅ | ✅ | ✅ | [10](spec/10-nbt-binary.md#4-圧縮) | 読み込みの既定 |
| Java形式（名前付きルート） | ✅ | ✅ | ✅ | ✅ | ✅ | [10](spec/10-nbt-binary.md#3-ファイル形式とルートタグ) | |
| Network形式（無名ルート1.20.2+） | ✅ | ✅ | ✅ | ✅ | ✅ | [10](spec/10-nbt-binary.md#3-ファイル形式とルートタグ) | |
| ネスト深さ上限による保護 | ✅ | ✅ | ✅ | ✅ | ✅ | [00](spec/00-conventions.md#5-安全上限既定値) | 既定は512 |
| 宣言長の先行検証 | ✅ | ✅ | ✅ | ✅ | ✅ | [10](spec/10-nbt-binary.md#12-長さフィールドの検証) | 巨大な長さの宣言によるメモリ枯渇を防ぐ |
| 展開後サイズの上限 | ✅ | ✅ | ✅ | ✅ | ✅ | [00](spec/00-conventions.md#5-安全上限既定値) | 既定は無制限 |
| 挿入順を保持するCompound | ✅ | ✅ | ✅ | ✅ | ✅ | [10](spec/10-nbt-binary.md#71-nbtcompound) | ラウンドトリップの前提 |
| 型付き取得子（キー欠落と型不一致の区別） | ✅ | ✅ | ✅ | ✅ | ✅ | [10](spec/10-nbt-binary.md#71-nbtcompound) | `get_*` / `opt_*` |
| 型付き設定子 | ✅ | ✅ | ✅ | ✅ | ✅ | [10](spec/10-nbt-binary.md#71-nbtcompound) | `set_int(key, 42)`のように値を直に渡せる |
| 位置を指定した読み込み | ✅ | ✅ | ✅ | ✅ | ✅ | [10](spec/10-nbt-binary.md#31-連なったnbtを読む) | 連なったNBTを順に読み進める |
| SNBT パース | ✅ | ✅ | ✅ | ✅ | ✅ | [11](spec/11-snbt.md) | 1.21.5+ 構文 |
| SNBT出力（1行 / 整形） | ✅ | ✅ | ✅ | ✅ | ✅ | [11](spec/11-snbt.md#5-出力) | |
| 浮動小数点の正準10進表記 | ✅ | ✅ | ✅ | ✅ | ✅ | [11](spec/11-snbt.md#51-浮動小数点の正準10進表記) | 言語標準の書式に依存しない |
| SNBTの異種リスト | ❌ | ❌ | ❌ | ❌ | ❌ | [11](spec/11-snbt.md#4-リストの異種要素) | バイナリNBTへ写せないため受理しない |
| SNBTの`\N{文字名}`エスケープ | ❌ | ❌ | ❌ | ❌ | ❌ | [11](spec/11-snbt.md#3-文字列とエスケープ) | 実装間で名前表が揃わない |

## レイヤ2: Anvil (.mca)

| 機能 | C# | Java | TS | Py | Rust | 仕様 | 備考 |
|---|:--:|:--:|:--:|:--:|:--:|---|---|
| リージョンの読み込み | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#2-ファイル構造) | |
| 無変更なら書き戻してもバイトが変わらない | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#4-セクタ確保) | 触っていないチャンクの配置を保つ |
| リージョンの書き込み（セクタ再配置つき） | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#4-セクタ確保) | 同サイズならその場、拡大時のみ移動 |
| 解放セクタの再利用 | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#4-セクタ確保) | 先頭から空きを探す |
| チャンクの削除 | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#4-セクタ確保) | |
| タイムスタンプの読み書き | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#22-タイムスタンプテーブル) | |
| 圧縮ID 1 (GZip) / 2 (Zlib) / 3 (無圧縮) | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#31-圧縮方式id) | 書き込みの既定は2 |
| 圧縮ID 4 (LZ4) | 🔶 | 🔶 | 🔶 | 🔶 | 🔶 | [20](spec/20-anvil-region.md#31-圧縮方式id) | 読み込みのみ。書き戻すとZlibになる（LZ4を指定した書き込みは`UNSUPPORTED_FEATURE`） |
| 圧縮ID 127 (カスタム) | ❌ | ❌ | ❌ | ❌ | ❌ | [20](spec/20-anvil-region.md#31-圧縮方式id) | 方式が実装依存。生バイトAPIでのみ取得可 |
| 外部ファイル`.mcc`の読み込み | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#32-外部ファイルへの退避-mcc) | |
| 外部ファイル`.mcc`への自動退避と復帰 | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#32-外部ファイルへの退避-mcc) | 255セクタ（約1MiB）を超えたら退避、縮めば内部へ戻す |
| 生バイトでのチャンク入出力 | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#5-論理api) | 未対応の圧縮方式でも取り出せる |
| 断片化解消`optimize()` | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#4-セクタ確保) | 添字順に詰め直す |
| セクタ重複・不正オフセットの検出 | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#21-ロケーションテーブル) | 開いた時点で弾く |
| 長さが4096の倍数でないファイルの読み込み | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#23-長さが4096の倍数でないファイル) | 末尾をゼロで埋めて読む。データが途中で切れたチャンクは開いた時点で弾く。書き出すときは4096の倍数にする |
| `region/` `entities/` `poi/` の横断アクセス | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#5-論理api) | `RegionFolder` |
| 開いたリージョンの上限管理 | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#51-開いたリージョンの上限) | 既定は8件。溢れたら書き出して閉じる |

## レイヤ3: World / Block

| 機能 | C# | Java | TS | Py | Rust | 仕様 | 備考 |
|---|:--:|:--:|:--:|:--:|:--:|---|---|
| `level.dat` の読み込み | ✅ | ✅ | ✅ | ✅ | ✅ | [40](spec/40-world-layout.md#2-leveldat) | |
| `level.dat`の安全な書き込み | ✅ | ✅ | ✅ | ✅ | ✅ | [40](spec/40-world-layout.md#22-書き込み時の安全策) | 一時ファイル経由 + `level.dat_old` |
| `session.lock`の確認 | ✅ | ✅ | ❌ | 🔶 | ❌ | [40](spec/40-world-layout.md#31-言語による差異) | 起動中のワールドへの書き込みを防ぐ。排他ロックを扱える言語のみ。PyはPOSIXのみ |
| 標準3次元 + カスタム次元の解決 | ✅ | ✅ | ✅ | ✅ | ✅ | [40](spec/40-world-layout.md#1-ディレクトリ構成) | 1.21.xまでの構成（直下の`region/`、`DIM-1/` / `DIM1/`）も読む |
| 1.21.xまでの`level.dat`とプレイヤーデータ | ✅ | ✅ | ✅ | ✅ | ✅ | [40](spec/40-world-layout.md#5-261より前の構成) | `SpawnX`などの古いキーを読む。`spawn_dimension`は`UNSUPPORTED_FEATURE` |
| チャンクの解釈（未知キーの保持つき） | ✅ | ✅ | ✅ | ✅ | ✅ | [30](spec/30-chunk-format.md#1-ルート要素) | 読んだ要素をすべて残す |
| ブロックの取得・設定 | ✅ | ✅ | ✅ | ✅ | ✅ | [30](spec/30-chunk-format.md#22-座標とエントリ添字) | 絶対座標／チャンク相対の両方 |
| 置き換え時の付随データの掃除 | ✅ | ✅ | ✅ | ✅ | ✅ | [30](spec/30-chunk-format.md#24-ブロックを置き換えたときの掃除) | `block_entities` / `block_ticks` / `fluid_ticks`から同じ座標の要素を取り除く。1.17までは`TileEntities` / `TileTicks` / `LiquidTicks` |
| バイオームの取得・設定（4×4×4） | ✅ | ✅ | ✅ | ✅ | ✅ | [30](spec/30-chunk-format.md#22-座標とエントリ添字) | 1.18以降の形式 |
| 数値のバイオームIDの取得・設定 | ✅ | ✅ | ✅ | ✅ | ✅ | [30](spec/30-chunk-format.md#73-113117の形式c1c3) | 1.17までの形式。`get_biome_id` / `set_biome_id`。IDは名前に直さない |
| `BlockState` の文字列表現 | ✅ | ✅ | ✅ | ✅ | ✅ | [30](spec/30-chunk-format.md#21-ブロック状態のパレット要素) | `minecraft:oak_stairs[facing=north]` |
| ブロック座標と範囲の型 | ✅ | ✅ | ✅ | ✅ | ✅ | [30](spec/30-chunk-format.md#5-座標の型) | `BlockPos` / `Cuboid`。範囲内の走査つき |
| チャンクの変更フラグ | ✅ | ✅ | ✅ | ✅ | ✅ | [30](spec/30-chunk-format.md#5-座標の型) | `is_modified`。書き戻す対象を決める |
| パレット自動拡張とビット幅の再計算 | ✅ | ✅ | ✅ | ✅ | ✅ | [31](spec/31-paletted-container.md#4-書き込み時のビット幅再計算) | |
| 未使用パレットの掃除`compact()` | ✅ | ✅ | ✅ | ✅ | ✅ | [31](spec/31-paletted-container.md#4-書き込み時のビット幅再計算) | 明示的に呼び出したときのみ |
| 非正準なBitStorageの救済読み | ✅ | ✅ | ✅ | ✅ | ✅ | [31](spec/31-paletted-container.md#3-読み込み時の検証) | `lenient_bit_storage` |
| `Heightmaps`の保持 | ✅ | ✅ | ✅ | ✅ | ✅ | [30](spec/30-chunk-format.md#3-heightmaps) | 値をそのまま残す |
| `Heightmaps`の再計算 | ❌ | ❌ | ❌ | ❌ | ❌ | [30](spec/30-chunk-format.md#3-heightmaps) | ブロックの定義が要るため行わない。`clear_heightmaps()`で消してMinecraftに再計算させる |
| 光源の再計算 | ❌ | ❌ | ❌ | ❌ | ❌ | [30](spec/30-chunk-format.md#3-heightmaps) | 計算が重く、誤ると見た目がおかしくなるため行わない。`invalidate_lighting()`で無効化のみ提供 |
| `entities` / `poi`の型付きAPI | ❌ | ❌ | ❌ | ❌ | ❌ | [30](spec/30-chunk-format.md#4-entities--poi) | 生NBTとしてなら読み書き可 |
| チャンクの新規生成 | ❌ | ❌ | ❌ | ❌ | ❌ | — | ワールド生成は本ライブラリの範囲外 |
| Bedrock版（LevelDB形式） | ❌ | ❌ | ❌ | ❌ | ❌ | — | 対象外 |

## 共通

| 機能 | C# | Java | TS | Py | Rust | 仕様 | 備考 |
|---|:--:|:--:|:--:|:--:|:--:|---|---|
| 共通`ErrorCode`による分類 | ✅ | ✅ | ✅ | ✅ | ✅ | [00](spec/00-conventions.md#4-エラー分類) | 全言語でコード集合が一致 |
| 扱えない形式の検出（警告／エラー切替） | ✅ | ✅ | ✅ | ✅ | ✅ | [30](spec/30-chunk-format.md#6-バージョン検査) | 1.13より前のチャンクが対象 |
| 形式の世代の判別と指定 | ✅ | ✅ | ✅ | ✅ | ✅ | [30](spec/30-chunk-format.md#7-形式の世代) | チャンクごとに自身のDataVersionで判別し、読んだ形式のまま書き戻す。`format_data_version`で指定もできる |
| 適合性検証ツール（CLI） | ✅ | ✅ | ✅ | ✅ | ✅ | — | 全言語の出力を相互diff |
| 実ワールド走査ツール | — | — | — | ✅ | — | — | `spec/tools/scan_world.py`。検証用のためPythonのみ |
| ドキュメント同期検証 | — | — | — | ✅ | — | — | `spec/tools/check_docs_sync.py`。全言語のソースを静的解析して照らし合わせる |

---

## 言語ごとの差異

概念と機能はどの言語でも同じですが、言語の性質上どうしても表現が変わる箇所があります。
移植のときに迷わないよう、ここに集めてあります。

| 箇所 | 差異 | 理由 |
|---|---|---|
| `TAG_Long`の値型 | TypeScriptのみ`bigint` | `number`では2^53超の整数を表せない |
| `TAG_String`の値型 | Rustのみ2形態のenum | `String`がUTF-8に限られ、孤立サロゲートを保持できない（[spec/10 2.3](spec/10-nbt-binary.md#23-各言語での保持方法)） |
| 整数の範囲検証 | Python / TypeScriptは構築時に実行時検査 | 言語に整数幅が無いため、型では守れない |
| 例外 / 戻り値 | Rustのみ`Result<T, Error>` | 他4言語は例外。`ErrorCode`の集合は一致 |
| `set_block`の引数 | Rustのみ`IntoBlockState`トレイト | 他4言語は`BlockState`と文字列の両方を受ける。C# / Javaはオーバーロード、TypeScript / Pythonは合併型の引数で表す |
| リストの範囲外の位置 | 各言語の標準の例外を使う。C# `ArgumentOutOfRangeException` / Java `IndexOutOfBoundsException` / Python `IndexError` / TypeScript `RangeError`。Rustは`get`が`None`、`insert`が`INVALID_ARGUMENT` | リストは各言語の標準のコレクションの約束事に合わせる。失敗したときに要素型は確定させない |
| `TAG_Float`のビットパターン | Python / TypeScriptは読み込んだビットを別に持つ | 値を倍精度で持つため、シグナリングNaNのビットが変わってしまう。値を変えていなければ読んだビットのまま書き戻す |
| Javaの検査例外 | 使わない | シグネチャを他言語と揃えるため |
| Pythonの再帰上限 | 読み書き時に一時的に引き上げる | 既定の上限1000が仕様の深さ上限512に届かないため |
| ストリーム入出力 | TypeScriptには無い | Nodeのストリームは非同期しか無く、同期APIで揃えられないため。ファイルとバイト列の入出力は同じ |
| `session.lock`の確認 | C# / Java / Python(POSIX)のみ実施 | 標準ライブラリでファイルの排他ロックを扱えない言語があるため |

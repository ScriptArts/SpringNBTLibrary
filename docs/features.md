# 機能一覧

何ができて何ができないかの一覧です。

凡例

| 記号 | 意味 |
|---|---|
| ✅ | 対応済み |
| 🔶 | 条件つきで対応（右端の「備考」に条件を記載） |
| ⏳ | 実装中 |
| ❌ | 未対応 |

対応しているのは C# / Java / TypeScript / Python / Rust で、今後も増やします。
対象は Java版 26.2 / DataVersion 4903 です。
過去バージョンのワールド改変には対応していません（→ [07 バージョンポリシー](guide/07-version-policy.md)）。

この表は CI の `docs-sync` ジョブが各言語の公開APIと突き合わせていて、
表と実装が食い違うとビルドが落ちます。

実データでの検証: Java版 26.2 の実ワールドを走査し、`.dat` 23個 + チャンク 3,717個 の
すべてで読み込みとバイト一致の書き戻しが通りました。
リージョンファイル 12 個は、開いて無変更で書き戻すと原本とバイト単位で一致します。
代表ファイルは対応言語すべてに通していて、正規化JSON・SNBT・チャンク一覧・詰め直したバイト列が
全言語で一致することも確かめました（→ [90 適合性 2.4](spec/90-conformance.md#24-実ワールド走査)）。

---

## レイヤ1: NBT

| 機能 | C# | Java | TS | Py | Rust | 仕様 | 備考 |
|---|:--:|:--:|:--:|:--:|:--:|---|---|
| 全13タグの読み込み | ✅ | ✅ | ✅ | ✅ | ✅ | [10](spec/10-nbt-binary.md#1-タグ型) | |
| 全13タグの書き込み | ✅ | ✅ | ✅ | ✅ | ✅ | [10](spec/10-nbt-binary.md#5-正準書き出し-canonical-writer) | 出力は一意（正準ライタ） |
| MUTF-8 文字列（U+0000・補助文字・孤立サロゲート） | ✅ | ✅ | ✅ | ✅ | ✅ | [10](spec/10-nbt-binary.md#2-文字列-mutf-8) | |
| 圧縮 Gzip / Zlib / 無圧縮 | ✅ | ✅ | ✅ | ✅ | ✅ | [10](spec/10-nbt-binary.md#4-圧縮) | |
| 圧縮方式の自動判定 | ✅ | ✅ | ✅ | ✅ | ✅ | [10](spec/10-nbt-binary.md#4-圧縮) | 読み込みの既定 |
| Java形式（名前付きルート） | ✅ | ✅ | ✅ | ✅ | ✅ | [10](spec/10-nbt-binary.md#3-ファイル形式とルートタグ) | |
| Network形式（無名ルート 1.20.2+） | ✅ | ✅ | ✅ | ✅ | ✅ | [10](spec/10-nbt-binary.md#3-ファイル形式とルートタグ) | |
| ネスト深さ上限による保護 | ✅ | ✅ | ✅ | ✅ | ✅ | [00](spec/00-conventions.md#5-安全上限既定値) | 既定 512 |
| 宣言長の先行検証 | ✅ | ✅ | ✅ | ✅ | ✅ | [10](spec/10-nbt-binary.md#12-長さフィールドの検証) | 巨大長宣言によるメモリ枯渇を防ぐ |
| 展開後サイズの上限 | ✅ | ✅ | ✅ | ✅ | ✅ | [00](spec/00-conventions.md#5-安全上限既定値) | 既定は無制限 |
| 挿入順を保持する Compound | ✅ | ✅ | ✅ | ✅ | ✅ | [10](spec/10-nbt-binary.md#71-nbtcompound) | ラウンドトリップの前提 |
| 型付き取得子（キー欠落と型不一致の区別） | ✅ | ✅ | ✅ | ✅ | ✅ | [10](spec/10-nbt-binary.md#71-nbtcompound) | `get_*` / `opt_*` |
| SNBT パース | ✅ | ✅ | ✅ | ✅ | ✅ | [11](spec/11-snbt.md) | 1.21.5+ 構文 |
| SNBT 出力（1行 / 整形） | ✅ | ✅ | ✅ | ✅ | ✅ | [11](spec/11-snbt.md#5-出力) | |
| 浮動小数点の正準10進表記 | ✅ | ✅ | ✅ | ✅ | ✅ | [11](spec/11-snbt.md#51-浮動小数点の正準10進表記) | 言語標準の書式に依存しない |
| SNBT の異種リスト | ❌ | ❌ | ❌ | ❌ | ❌ | [11](spec/11-snbt.md#4-リストの異種要素) | バイナリNBTへ写せないため受理しない（[adr/0006](adr/0006-snbt-scope.md)） |
| SNBT の `\N{文字名}` エスケープ | ❌ | ❌ | ❌ | ❌ | ❌ | [11](spec/11-snbt.md#3-文字列とエスケープ) | 実装間で名前表が揃わない |

## レイヤ2: Anvil (.mca)

| 機能 | C# | Java | TS | Py | Rust | 仕様 | 備考 |
|---|:--:|:--:|:--:|:--:|:--:|---|---|
| リージョンの読み込み | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#2-ファイル構造) | |
| 無変更なら書き戻してもバイトが変わらない | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#4-セクタ確保) | 触っていないチャンクの配置を保つ |
| リージョンの書き込み（セクタ再配置つき） | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#4-セクタ確保) | 同サイズならその場、拡大時のみ移動 |
| 解放セクタの再利用 | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#4-セクタ確保) | 先頭から空きを探す |
| チャンクの削除 | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#4-セクタ確保) | |
| タイムスタンプの読み書き | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#22-タイムスタンプテーブル) | |
| 圧縮ID 1 (GZip) / 2 (Zlib) / 3 (無圧縮) | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#31-圧縮方式id) | 書き込み既定は 2 |
| 圧縮ID 4 (LZ4) | ❌ | ❌ | ❌ | ❌ | ❌ | [20](spec/20-anvil-region.md#31-圧縮方式id) | 生バイトAPIでのみ取得可 |
| 圧縮ID 127 (カスタム) | ❌ | ❌ | ❌ | ❌ | ❌ | [20](spec/20-anvil-region.md#31-圧縮方式id) | 方式が実装依存。生バイトAPIでのみ取得可 |
| 外部ファイル `.mcc` の読み込み | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#32-外部ファイルへの退避-mcc) | |
| 外部ファイル `.mcc` への自動退避と復帰 | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#32-外部ファイルへの退避-mcc) | 1MiB超で退避、縮めば内部へ戻す |
| 生バイトでのチャンク入出力 | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#5-論理api) | 未対応圧縮方式でも取り出せる |
| 断片化解消 `optimize()` | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#4-セクタ確保) | 添字順に詰め直す |
| セクタ重複・不正オフセットの検出 | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#21-ロケーションテーブル) | 開いた時点で弾く |
| ファイル長のセクタ整列検査 | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#2-ファイル構造) | |
| `region/` `entities/` `poi/` の横断アクセス | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#5-論理api) | `RegionFolder` |
| 開いたリージョンの上限管理 | ✅ | ✅ | ✅ | ✅ | ✅ | [20](spec/20-anvil-region.md#51-開いたリージョンの上限) | 既定 8 件。溢れたら書き出して閉じる |

## レイヤ3: World / Block

| 機能 | C# | Java | TS | Py | Rust | 仕様 | 備考 |
|---|:--:|:--:|:--:|:--:|:--:|---|---|
| `level.dat` の読み込み | ✅ | ✅ | ✅ | ✅ | ✅ | [40](spec/40-world-layout.md#2-leveldat) | |
| `level.dat` の安全な書き込み | ✅ | ✅ | ✅ | ✅ | ✅ | [40](spec/40-world-layout.md#22-書き込み時の安全策) | 一時ファイル経由 + `level.dat_old` |
| `session.lock` の確認 | ✅ | ✅ | ❌ | 🔶 | ❌ | [40](spec/40-world-layout.md#31-言語による差異) | 起動中ワールドへの書き込みを防ぐ。排他ロックを扱える言語のみ。Py は POSIX のみ（[adr/0008](adr/0008-session-lock.md)） |
| 標準3次元 + カスタム次元の解決 | ✅ | ✅ | ✅ | ✅ | ✅ | [40](spec/40-world-layout.md#1-ディレクトリ構成) | |
| チャンクの解釈（未知キーの保持つき） | ✅ | ✅ | ✅ | ✅ | ✅ | [30](spec/30-chunk-format.md#1-ルート要素) | 読んだ要素をすべて残す |
| ブロックの取得・設定 | ✅ | ✅ | ✅ | ✅ | ✅ | [30](spec/30-chunk-format.md#22-座標とエントリ添字) | 絶対座標／チャンク相対の両方 |
| 置き換え時の付随データの掃除 | ✅ | ✅ | ✅ | ✅ | ✅ | [30](spec/30-chunk-format.md#24-ブロックを置き換えたときの掃除) | `block_entities` / `block_ticks` / `fluid_ticks` から同じ座標の要素を取り除く |
| バイオームの取得・設定（4×4×4） | ✅ | ✅ | ✅ | ✅ | ✅ | [30](spec/30-chunk-format.md#22-座標とエントリ添字) | |
| `BlockState` の文字列表現 | ✅ | ✅ | ✅ | ✅ | ✅ | [30](spec/30-chunk-format.md#21-ブロック状態のパレット要素) | `minecraft:oak_stairs[facing=north]` |
| パレット自動拡張とビット幅の再計算 | ✅ | ✅ | ✅ | ✅ | ✅ | [31](spec/31-paletted-container.md#4-書き込み時のビット幅再計算) | |
| 未使用パレットの掃除 `compact()` | ✅ | ✅ | ✅ | ✅ | ✅ | [31](spec/31-paletted-container.md#4-書き込み時のビット幅再計算) | 明示呼び出し時のみ |
| 非正準な BitStorage の救済読み | ✅ | ✅ | ✅ | ✅ | ✅ | [31](spec/31-paletted-container.md#3-読み込み時の検証) | `lenient_bit_storage` |
| `Heightmaps` の保持 | ✅ | ✅ | ✅ | ✅ | ✅ | [30](spec/30-chunk-format.md#3-heightmaps) | 値をそのまま残す |
| `Heightmaps` の再計算 | ❌ | ❌ | ❌ | ❌ | ❌ | [30](spec/30-chunk-format.md#3-heightmaps) | [adr/0004](adr/0004-defer-heightmap-recalc.md) |
| 光源の再計算 | ❌ | ❌ | ❌ | ❌ | ❌ | [30](spec/30-chunk-format.md#3-heightmaps) | 同上。`invalidate_lighting()` で無効化のみ提供 |
| `entities` / `poi` の型付きAPI | ❌ | ❌ | ❌ | ❌ | ❌ | [30](spec/30-chunk-format.md#4-entities--poi) | 生NBTとしてなら読み書き可 |
| チャンクの新規生成 | ❌ | ❌ | ❌ | ❌ | ❌ | — | ワールド生成は本ライブラリの範囲外 |
| Bedrock版（LevelDB形式） | ❌ | ❌ | ❌ | ❌ | ❌ | — | 対象外 |

## 共通

| 機能 | C# | Java | TS | Py | Rust | 仕様 | 備考 |
|---|:--:|:--:|:--:|:--:|:--:|---|---|
| 共通 `ErrorCode` による分類 | ✅ | ✅ | ✅ | ✅ | ✅ | [00](spec/00-conventions.md#4-エラー分類) | 全言語でコード集合が一致 |
| DataVersion 不一致時の警告／エラー切替 | ✅ | ✅ | ✅ | ✅ | ✅ | [30](spec/30-chunk-format.md#5-バージョン検査) | |
| 適合性検証ツール（CLI） | ✅ | ✅ | ✅ | ✅ | ✅ | [90](spec/90-conformance.md#23-クロス言語一致) | 全言語の出力を相互diff |
| 実ワールド走査ツール | — | — | — | ✅ | — | [90](spec/90-conformance.md#24-実ワールド走査) | `spec/tools/scan_world.py`。検証用のため Python のみ |
| ドキュメント同期検証 | — | — | — | ✅ | — | [adr/0009](adr/0009-static-api-extraction.md) | `spec/tools/check_docs_sync.py`。全言語のソースを静的解析して突き合わせる |

---

## 言語ごとの差異

概念と機能はどの言語でも同じですが、言語の性質上どうしても表現が変わる箇所があります。
移植のときに迷わないよう、ここに集めてあります。

| 箇所 | 差異 | 理由 |
|---|---|---|
| `TAG_Long` の値型 | TypeScript のみ `bigint` | `number` では 2^53 超の整数を表せない（[adr/0007](adr/0007-typescript-bigint.md)） |
| `TAG_String` の値型 | Rust のみ 2 形態の enum | `String` が UTF-8 に限られ、孤立サロゲートを保持できない（[spec/10 2.3](spec/10-nbt-binary.md#23-各言語での保持方法)） |
| 整数の範囲検証 | Python / TypeScript は構築時に実行時検査 | 言語に整数幅が無いため、型では守れない |
| 例外 / 戻り値 | Rust のみ `Result<T, Error>` | 他4言語は例外。`ErrorCode` の集合は一致（[adr/0005](adr/0005-unified-error-model.md)） |
| Java の検査例外 | 使わない | シグネチャを他言語と揃えるため（[adr/0005](adr/0005-unified-error-model.md)） |
| Python の再帰上限 | 読み書き時に一時的に引き上げる | 既定の上限 1000 が仕様の深さ上限 512 に届かないため |
| `session.lock` の確認 | C# / Java / Python(POSIX) のみ実施 | 標準ライブラリでファイルの排他ロックを扱えない言語があるため（[adr/0008](adr/0008-session-lock.md)） |

# 変更履歴

このファイルの書式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) に、
バージョン番号は [セマンティックバージョニング](https://semver.org/lang/ja/) に従う。

**対応言語はすべて、常に同じバージョン番号で公開する。**

## [未リリース]

### 追加

- **ブロック置き換え時に付随データを掃除する** — `set_block` で別のブロックへ
  置き換えたとき、同じ座標を指す `block_entities` / `block_ticks` / `fluid_ticks` の
  要素を取り除くようにした。チェストのあった座標に石を置いても中身が残らない
  （[spec/30 2.4](docs/spec/30-chunk-format.md#24-ブロックを置き換えたときの掃除)）
- **開いたリージョンファイルの上限管理** — `RegionFolder` が同時に開くリージョンを
  既定 8 件までに制限し、超えたら最も長く使っていないものを書き出してから閉じる。
  数千リージョンあるワールドを走査してもメモリを使い切らない
  （[spec/20 5.1](docs/spec/20-anvil-region.md#51-開いたリージョンの上限)）

### 修正

- **圧縮ID 4 (LZ4) の仕様記述を実態に合わせた** — 「ブロック形式、フレーム無し」と
  していたが、実際は独自ヘッダ付きのブロック連結（`LZ4Block` マジック +
  21 バイトのリトルエンディアンヘッダ + ブロック連結）だった。
  v0.2.0 の実装前に判明した（[spec/20 3.1.1](docs/spec/20-anvil-region.md#311-圧縮id-4-の中身)）

## [0.1.0]

最初のリリース。対象は **Minecraft Java版 26.2（DataVersion 4903）**。

### 追加

**レイヤ1: NBT**（[ガイド](docs/guide/01-nbt.md) / [仕様](docs/spec/10-nbt-binary.md)）

- 全13タグの読み書き
- MUTF-8（`U+0000` の 2 バイト表現、補助文字のサロゲートペア表現）
- 圧縮の自動判定（Gzip / Zlib / 無圧縮）
- Java 形式と Network 形式（1.20.2+ の無名ルート）
- SNBT のパースと出力。1.21.5+ の拡張構文に対応
- 安全上限（ネスト深さ 512、宣言長の先行検証）

**レイヤ2: Anvil**（[ガイド](docs/guide/03-anvil-region.md) / [仕様](docs/spec/20-anvil-region.md)）

- `.mca` リージョンファイルの読み書き
- 圧縮ID 1 (GZip) / 2 (Zlib) / 3 (無圧縮)
- 外部ファイル `.mcc` への自動退避と復帰
- 生バイトでのチャンク入出力（未対応の圧縮方式でも取り出せる）
- 断片化解消 `optimize()`
- セクタ重複・不正オフセットの検出
- `region/` `entities/` `poi/` の横断アクセス

**レイヤ3: World / Block**（[ガイド](docs/guide/05-blocks-and-biomes.md) / [仕様](docs/spec/30-chunk-format.md)）

- `level.dat` の読み書き（一時ファイル経由の安全な書き込み）
- 26.x のディレクトリ構成に対応（`dimensions/` への集約、`players/` への改名、
  `data/minecraft/*.dat` への分離）
- 標準3次元とカスタム次元の解決
- 絶対座標でのブロック・バイオームの取得と設定
- `BlockState` の文字列表現（プロパティは常に名前の昇順）
- パレットの自動拡張とビット幅の再計算、未使用パレットの掃除

**共通**

- 全言語で一致する `ErrorCode`
- クロス言語適合性検証（`spec/run-conformance.sh`）
- 実ワールド走査ツール（`spec/tools/scan_world.py`）
- 実装から生成する [API 対応表](docs/api/overview.md)

### 非対応（v0.2.0 以降を予定）

- `Heightmaps` と光源の再計算（無効化のみ提供。[adr/0004](docs/adr/0004-defer-heightmap-recalc.md)）
- 圧縮ID 4 (LZ4) / 127 (カスタム) の展開
- `entities` / `poi` の型付きAPI
- チャンクの新規生成（ワールド生成は本ライブラリの範囲外）
- 過去バージョンのワールド改変（[adr/0003](docs/adr/0003-version-policy.md)）

### 既知の差異

言語の性質上どうしても揃えられない箇所は
[機能一覧の「言語ごとの差異」](docs/features.md#言語ごとの差異)にまとめてある。

- `session.lock` の確認は C# / Java / Python(POSIX) のみ（[adr/0008](docs/adr/0008-session-lock.md)）
- TypeScript は `i64` に `bigint` を使う（[adr/0007](docs/adr/0007-typescript-bigint.md)）
- Rust のみ例外ではなく `Result<T, Error>` を返す（[adr/0005](docs/adr/0005-unified-error-model.md)）

### 検証

- 各言語の単体テスト 718 件
- クロス言語適合性 752 件（全言語で出力バイト列が一致）
- 実ワールド（Java版 26.2）: `.dat` 23個 + チャンク 3,717個 すべてラウンドトリップ成功。
  World レイヤでも 3,481 チャンク・83,544 セクションの再エンコードが原本と一致し、
  393万ブロックの読み出しに成功

# 過去バージョンへの対応の調査

- 状態: 調査済み。設計は[過去バージョンへの対応の設計](legacy-version-support-design.md)へ
- 日付: 2026-11-20
- ブランチ: `research/legacy-version-support`（2.0.0のコミットから切った）

Amulet Editorのように、26.3より前のJava版のワールドも扱えるようにするのが現実的かを調べた。

「過去バージョンに対応する」には、次の3つの意味がある。費用と方針への影響がそれぞれ違うので、分けて判断する。

| 記号 | 意味 |
|---|---|
| A | 古いワールドを読み、各チャンクをそのチャンクの形式のまま書き戻す |
| B | 1.13より前（数値IDの時代）のワールドも扱う |
| C | バージョンをまたいで変換する（26.3のワールドを1.20で開ける形にする、など） |

---

## 1. 結論（暫定）

| 意味 | 判断 | 理由 |
|---|---|---|
| A（1.13以降） | 現実的 | 1.13以降のパレットはブロックIDが名前なので、ブロックの定義を持たずに済む。費用は形式の世代ごとの分岐とテストで、5言語ぶん要る |
| B | 費用が高く、方針にも反する | 数値IDとメタデータから名前への表が要る。ブロックの定義を持たないという方針（[0004](../adr/0004-defer-heightmap-recalc.md)、[0010](../adr/0010-palette-format-26-3.md)の決定5）に反する |
| C | 現実的でない | ブロック・バイオーム・ブロックエンティティ・エンティティ・アイテムを双方向に変換する表と、Minecraftの新しいバージョンが出るたびの保守が要る。Amuletでもエンティティとアイテムは変換していない |

Aに進むなら、[0003](../adr/0003-version-policy.md)と[0010](../adr/0010-palette-format-26-3.md)を置き換えるADRが要る（7章）。

26.4で形式がまた変わる予定なので、Aに進まなくても、形式の世代をDataVersionで選ぶ作りは要る見込みである（8章）。

---

## 2. Amuletのやり方

ここは調査の結果で、このリポジトリでは確かめていない。

### 2.1 Amulet-Core 1.x（Python）

- 読む形式はチャンクごとの`DataVersion`で選ぶ。`level.dat`のバージョンでは選ばない。
  1つのワールドに、変換されていない古いチャンクが混ざりうるためである
- 形式の世代ごとに読み書きの部品（interface）を持ち、前の世代を継承して差分だけを書く。
  境界は`0`、`1444`、`1466`、`1467`、`1484`、`1503`、`1519`、`1901`、`1908`、`1912`、`1934`、`2203`、`2529`、`2681`、`2709`、`2844`、`3463`、`5006`、`5013`で、上限は`5100`。上限を超えるチャンクは読まない
- 多くの部品は1KB未満で、大きいのは`DataVersion`の無いもの（22KB）、`1444`（11KB）、`2844`（10KB）。
  `5006`は26.3のパレットの読み書きだけを持つ。`5013`はチャンクの`Status`の値（`minecraft:terrain`）だけを変える
- 読んだブロックはPyMCTranslateで共通の形式（universal）へ変換して持ち、保存するときにワールドのバージョンの形式へ戻す。
  編集したチャンクは元の形式ではなくワールドのバージョンの形式で書き直される
- PyMCTranslateの変換表は、Java版だけで約9.4万ファイル・67MBある。1バージョンあたり1〜2.3MBで、1.12.2は3.9MB。Minecraftの新しいバージョンが出るたびに更新している
- 作者自身が、変換の仕組みが生のデータを扱いにくくしていると述べ、2.xで書き直している。
  エンティティとアイテムは変換せずにそのまま写すので、古いバージョンへ移すとアイテムが消える不具合が報告されている

### 2.2 Amulet 2.x（C++、alpha版）

- チャンクを元の形式のまま持ち、変換は必要なときだけ行う作りに変えた
- 1.13より前のブロックの読み込みは、まだ実装されていない

### 2.3 ほかのライブラリ

| ライブラリ | 対応範囲 | 作り |
|---|---|---|
| MCA Selector（Java） | 1.9より前〜26.3 Snapshot 7 | 機能ごとの部品にDataVersionを付け、チャンクのDataVersion以下で最も新しい部品を選ぶ。生のNBTのまま扱い、変換しない |
| fastanvil（Rust） | 1.2以降を読む（上限は未確認）。読み取り専用 | 1.13より前・1.18より前・1.18以降の3つの型を順に試す。数値IDの表を持つ |
| anvil-parser2（Python） | 読み込みは全バージョン。書き込みは`Level`の形式だけ | 1つのクラスの中でバージョンごとに分岐する |
| Hephaistos（Kotlin、開発終了） | 1.15〜1.20 | 1つの型にまとめ、書き出すときに構造とキー名を切り替える。ブロックIDは変換しない |

---

## 3. Java版の保存形式の変遷

DataVersionはminecraft.wikiの値。「未確定」としたものは、調べた資料の間で値が食い違うか、出典が見つからなかったものである。

| バージョン | DataVersion | 変わったこと | 影響する層 |
|---|---|---|---|
| 1.2.1 | なし | `.mcr`から`.mca`へ。ブロックは数値IDとメタデータ | Anvil / World |
| 1.9 | 100 | `DataVersion`が入った。これより前のチャンクには無い | World |
| 1.13 | 1444または1451（未確定） | ブロックIDが名前になり、セクションごとの`Palette`と`BlockStates`になった | World |
| 1.13のスナップショット | 1466 | `Heightmaps`と文字列の`Status` | World |
| 1.14 | 1937 | `poi/`が増えた | World |
| 1.15 | 2203 | バイオームが`int[1024]`（4×4×4ごと）になった | World |
| 時期は未確定 | 未確定 | `.mcc`（外部チャンク） | Anvil |
| 1.16 | 2529 | ビット詰めで、値が64bitの境目をまたがなくなった | World |
| 1.17 | 2681 | エンティティが`entities/`の別のリージョンファイルへ移った | Anvil / World |
| 1.18 | 2836〜2844 | `block_states` / `biomes`のパレット付きコンテナ、`Level`の撤去、`yPos`、負のY | World |
| 1.20.5のスナップショット | 3806 / 3809 | LZ4（圧縮方式4）とcustom（127） | Anvil |
| 1.20.5 | 3819（未確定） | アイテムのcomponents。ブロックエンティティやエンティティの中のアイテムのNBTが変わった | Worldの中身 |
| 26.1 | 4786 | `dimensions/`、`players/`、`level.dat`の中身の`data/minecraft/`への分割 | World |
| 26.3 | 5006 | パレットの要素が文字列か`{id, properties}`になった | World |

26.3の`5006`は0010で採った境界である。Amuletも同じ値で区切っているが、どちらにも出典は書かれていない。
公開されたバージョンには5006〜5008が無く（Snapshot 6が5005、Snapshot 7が5009）、5006〜5009のどれを境界にしても公開されたバージョンの扱いは変わらない。

---

## 4. このライブラリでバージョンに依存しているところ

この章は2.0.0のコードを読んで確かめた。

| 箇所 | いまの前提 | 古い形式との違い |
|---|---|---|
| `Chunk` | `sections`などがルートの直下にある。`yPos`、`Status`を読む | 1.18より前は`Level`の中にあり、`yPos`が無い |
| `ChunkSection` | `block_states` / `biomes`のパレット付きコンテナ | 1.18より前はセクションの`Palette` / `BlockStates`と、チャンクの`Biomes`（数値の配列） |
| `BitStorage` | 値が64bitの境目をまたがない詰め方だけ | 1.16より前はまたぐ |
| `BlockState.from_nbt` / `to_nbt` | 文字列か`{id, properties}` | 26.2までは`{Name, Properties}` |
| `get_biome` / `set_biome` | セクションあたり64要素で、要素は名前の文字列 | 1.18より前は数値のバイオームID。数値を名前にするには表が要る |
| `MinecraftWorld` / `Dimension` | `dimensions/<名前空間>/<名前>/`と`players/data/` | 26.1より前は`region/`、`DIM-1/`、`DIM1/`と`playerdata/` |
| `LevelData` | `spawn`、`difficulty_settings`のcompound | 26.1より前は`SpawnX` / `SpawnY` / `SpawnZ`、`Difficulty`、`hardcore`。ゲームルールや天気も`level.dat`の中 |
| バージョンの判定 | `MIN_SUPPORTED_DATA_VERSION`未満は読み込みで警告、書き込みで`UNSUPPORTED_DATA_VERSION`（[0003](../adr/0003-version-policy.md)） | 対応するなら、判定を「世代を選ぶ」に置き換える |

NBTレイヤとAnvilレイヤは、いまでもバージョンに依存しない。対応の範囲はWorldレイヤに閉じる。

---

## 5. 費用

### 5.1 実測

26.3のパレットの形式1つに対応したときの差分（`git diff --stat v1.0.1 v2.0.0`）は次のとおりである。

| 範囲 | ファイル | 行 |
|---|---|---|
| 全体 | 86 | +1,792 / -377 |
| 5言語の実装 | 27 | +662 / -187 |
| 5言語のテスト | 7 | +721 / -86 |
| `docs/` | 18 | +221 / -73 |

形式の世代を1つ足すたびに、この規模の作業が要ると見ておく。
Aでは世代の分岐を足すので、パレットを差し替えるだけだった今回より、作りを変える分が上乗せになる。

### 5.2 世代ごとの見積もり

| 世代 | DataVersion | 要るもの | 見積もり |
|---|---|---|---|
| 26.1〜26.2 | 4786〜5005 | パレットの要素の`{Name, Properties}`。1.0.1の実装が残っている | 小 |
| 1.18〜1.21.x | 2844〜4785 | 26.1より前のフォルダ構成と`level.dat`のキー。チャンクの構造は26.1と同じと見ているが、確かめていない | 中 |
| 1.13〜1.17 | 1444または1451〜2843 | `Level`の包み、セクションの`Palette` / `BlockStates`、またぐビット詰め、数値のバイオーム配列（2種類の長さ）、チャンクの中のエンティティ。バイオームが数値になるのでAPIが分かれる | 大 |
| 1.13より前 | 1444または1451未満 | 数値IDの表（B） | 対象外にするのがよい |

### 5.3 テスト用のワールド

形式の世代ごとに、実際のMinecraftが書き出したワールドが要る。
手元にあるのは26.1（DataVersion 4790）、26.2（4903）、26.3（5023）のワールドで、オーバーワールドしか生成されていないものもある。

1.18〜1.21.xまで対応するなら、少なくとも1.18.2と1.20.4、1.21.4のワールドを作る必要がある。
1.13〜1.17まで広げるなら、1.13.2、1.15.2、1.16.5、1.17.1も要る。どれもネザーとエンドまで生成させる。

---

## 6. 0003と0010との関係

0010は理由1で、古い形式も扱わない理由を2つ挙げた。

- 5言語すべてに分岐とテストが要る
- 書き出す形式を取り違えれば、ワールドを使えなくする

Aに進むなら、この2つに答えられる作りが要る。

- 形式の世代ごとの読み書きを1か所にまとめ、DataVersionから引く。バージョンによる分岐をほかの場所に書かない
- 書き出す形式はそのチャンクを読んだときのDataVersionで決め、利用者が形式を選べるようにはしない。これで取り違えが構造上起きなくなる
- 世代ごとに実ワールドのテストデータと適合性ベクタを持ち、5言語で同じ結果になることを確かめる

Aには、いま扱えないワールドを扱えるようになる利点もある。
26.2で作ったワールドを26.3で開くと、読み込まれなかったチャンクは古い形式のまま残り、2.0.0ではそのチャンクのブロックを読めない。

---

## 7. 決め直すADR

| ADR | いまの決定 | Aに進む場合 |
|---|---|---|
| [0003](../adr/0003-version-policy.md) | 下限未満は読み込みで警告、書き込みでエラー | 世代を選んで読み書きする。対応する世代より古いものだけを警告・エラーにする |
| [0010](../adr/0010-palette-format-26-3.md) | 26.2までの形式は扱わない | 26.2までの`{Name, Properties}`も読み書きする |

ブロックの定義を持たない方針（0004、0010の決定5）は、Aでは変えずに済む。BとCでは変える必要がある。

---

## 8. 26.4で予定されている変更

minecraft.wikiによると、26.4 Snapshot 1（DataVersion 5119）で次の2つが変わる。公式の変更履歴とは照らし合わせておらず、26.4の実ワールドでも確かめていない。

- バイオームがブロック単位になり、セクションあたり64要素から4096要素になる
- チャンクの`Status`が`status`になる

2.0.0のまま26.4のチャンクを読むと次のようになる（コードを読んで確かめた）。
DataVersionは下限より新しいので、警告は出ない。

- パレットに2つ以上のバイオームがあるセクションは、`data`の長さが64要素ぶんと合わず`MALFORMED_DATA`になる。
  ただし`lenient_bit_storage`を有効にすると、長さから`bits`を逆算して読み進めるので、誤った値を返しうる
- `Status`が無いので、`status`と`is_fully_generated`は失敗する

26.4のワールドを扱うには、過去バージョンに対応するかどうかに関わらず、世代をDataVersionで選ぶ作りが要る見込みである。
この2つの変更は26.4のスナップショットで作ったワールドで確かめられる。

---

## 9. 決まったこと

- Aで進める。バージョン間の変換（C）はしない
- 対象は1.13以降とし、1.13より前（B）は扱わない
- 作り方と進める順番は[設計](legacy-version-support-design.md)にまとめた

---

## 出典

ここに挙げたものは、調査を任せたエージェントが読んだもので、このリポジトリでは中身を確かめていない。

- Amulet-Core 1.9.52: https://github.com/Amulet-Team/Amulet-Core/tree/1.9.52/amulet/level/interfaces/chunk/anvil
- Amulet-Core 1.9.52の読み手の選び方: https://github.com/Amulet-Team/Amulet-Core/blob/1.9.52/amulet/level/loader.py
- PyMCTranslate: https://github.com/Amulet-Team/PyMCTranslate/tree/main/PyMCTranslate/json/versions
- Amulet Map Editorのissue: https://github.com/Amulet-Team/Amulet-Map-Editor/issues/171 、 https://github.com/Amulet-Team/Amulet-Map-Editor/issues/1050
- Amulet 2.x: https://github.com/Amulet-Team/Amulet-Level/blob/1.0/src/amulet/level/java/chunk_decode.cpp
- MCA Selector: https://github.com/Querz/mcaselector/tree/master/src/main/java/net/querz/mcaselector/version
- fastanvil: https://github.com/owengage/fastnbt/blob/master/fastanvil/src/java/mod.rs
- anvil-parser2: https://github.com/0xTiger/anvil-parser2
- Hephaistos: https://github.com/Minestom/Hephaistos
- minecraft.wiki: https://minecraft.wiki/w/Chunk_format 、 https://minecraft.wiki/w/Data_version 、 https://minecraft.wiki/w/Java_Edition_level_format
- 26.3の変更履歴（Mojangのランチャーの変更履歴）: https://launchercontent.mojang.com/v2/javaPatchNotes.json

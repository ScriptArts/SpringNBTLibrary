# 0007. TypeScriptではi64にbigintを使う

- 状態: 採用
- 日付: 2026-08-29

## 背景

TypeScript / JavaScriptの`number`はIEEE 754の倍精度で、整数として正確に表せるのは`±2^53 - 1`までである。
NBTの`TAG_Long`は64bit符号付き整数なので、`number`では表しきれない。

実際に困る例として、`world_gen_settings.dat`のワールドシード、`LastUpdate`、`InhabitedTime`、そしてブロック配置を格納する`LongArray`がある。
どれも`number`で受けると、値が気づかないうちに変わる。

## 決定

**`TAG_Long`は`bigint`、`TAG_Long_Array`は`BigInt64Array`で保持する。**

`i8` / `i16` / `i32`は`number`のまま扱い、構築時に範囲検証を行う。
`f32`は`Math.fround`で丸めてから保持する。

## 理由

- **気づかないうちにおかしくなるのが最悪**だから。`number`で受けると例外も警告も出ないままシード値が別の値になり、利用者はワールドを書き戻すまで気づけない
- `bigint`はES2020以降の標準で、Node.js 20以上・現行ブラウザで使える。
  対象環境を絞る理由にはならない
- `DataView.getBigInt64` / `setBigInt64`がそのまま使えるので、読み書きのコードもむしろ素直になる

## 結果として受け入れること

- 利用者は`tag.value`に`1n`のようなリテラルを書く必要がある。
  `number`と`bigint`は暗黙に混ぜられないため、`Number(...)` / `BigInt(...)`の変換を明示することになる
- JSONへそのまま渡せない（`JSON.stringify`は`bigint`で例外になる）。
  この点は[ガイド01](../guide/01-nbt.md)に明記する
- 型の対応表では、TypeScriptだけ`i64`の行の見た目が他言語と変わる。
  [spec/00-conventions.md](../spec/00-conventions.md#2-バイト順と数値型)に理由を併記する

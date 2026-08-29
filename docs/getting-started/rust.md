# はじめに（Rust）

**Rust 2021 edition / MSRV 1.75。**

## 導入

まだ crates.io へは公開していない。パスかリポジトリで参照する。

```toml
[dependencies]
spring-nbt-library = { path = "../SpringNBTLibrary/rust" }
```

## 例外ではなく `Result`

Rust 版だけは例外ではなく `Result<T, Error>` を返す。
`ErrorCode` の集合は他言語と完全に一致している（[adr/0005](../adr/0005-unified-error-model.md)）。

```rust
use spring_nbt_library::error::{ErrorCode, Result};
```

## NBT ファイルを読む

```rust
use spring_nbt_library::nbt::{read_file, NbtReadOptions};

// 圧縮方式（Gzip / Zlib / 無圧縮）は自動で判定される
let named = read_file("level.dat", &NbtReadOptions::default())?;
let data = named.tag.get_compound("Data")?;

println!("{}", data.get_string("LevelName")?);
println!("{}", data.get_int("DataVersion")?);
```

型が違えば `ErrorCode::UnexpectedTagType` が返る。
キーが無いかもしれないときは `opt_*` を使う（無ければ `Ok(None)`）。

## 書く

```rust
use spring_nbt_library::nbt::tag::{NbtCompound, NbtString, NbtTag};
use spring_nbt_library::nbt::{write_file, Compression, NamedTag, NbtWriteOptions};

let mut root = NbtCompound::new();
root.set("name", NbtTag::String(NbtString::new("SpringNBTLibrary")));
root.set("count", NbtTag::Int(42));

let options = NbtWriteOptions { compression: Compression::Gzip, ..Default::default() };
write_file("out.nbt", &NamedTag::new("", root), &options)?;
```

## 文字列は 2 形態

Rust の `String` は UTF-8 に限られるため、NBT に現れうる孤立サロゲートを保持できない。
そこで `NbtString` を列挙にしている（[spec/10 2.3](../spec/10-nbt-binary.md#23-各言語での保持方法)）。

```rust
pub enum NbtString {
    Text(String),          // 通常の文字列。実データはほぼすべてこちら
    Surrogates(Vec<u16>),  // UTF-8 に写せない UTF-16 コード単位の列
}
```

## ワールドのブロックを読む

```rust
use spring_nbt_library::world::{MinecraftWorld, WorldOpenOptions};

let mut world = MinecraftWorld::open(world_path, WorldOpenOptions::default())?;

if let Some(overworld) = world.dimension("minecraft:overworld")? {
    // 絶対座標。リージョンとチャンクの解決は内部で行う
    if let Some(block) = overworld.get_block(100, 64, -200)? {
        println!("{block}");   // minecraft:grass_block[snowy=false]
    }
}

world.close()?;
```

## ブロックを書き換える

```rust
let options = WorldOpenOptions { writable: true, ..Default::default() };
let mut world = MinecraftWorld::open(world_path, options)?;

if let Some(overworld) = world.dimension("minecraft:overworld")? {
    let stone = BlockState::parse("minecraft:stone")?;
    overworld.set_block(100, 64, -200, &stone)?;
    overworld.flush()?;   // ここで初めてディスクへ書かれる
}

world.close()?;
```

> **Minecraft を終了してから実行すること。**
> Rust 版は `std` にファイルロックが無いため
> **`session.lock` を確認しない**（[adr/0008](../adr/0008-session-lock.md)）。
> 起動していないことは呼び出し側で担保すること。

> ブロックを置き換えても **Heightmaps と光源は再計算されない**（[adr/0004](../adr/0004-defer-heightmap-recalc.md)）。

## スタックの深さに注意

NBT のネストは既定で深さ 512 まで許す。
**debug ビルドでは 1 段あたり約 8 KB を使う**ため、
深いデータを扱うなら大きめのスタックを持つスレッドで走らせること
（[spec/00 5.1](../spec/00-conventions.md#51-深さ上限と実行スタック)）。

## 次に読むもの

- [ガイド](../guide/01-nbt.md) — 目的別の使い方
- [API 対応表](../api/overview.md) — 他言語版との対応
- [エラーと安全上限](../guide/06-errors-and-limits.md)

# はじめに（Rust）

Rust 2021 edition、MSRV 1.75です。

## 導入

Cargo.tomlにgit参照を書きます。
以下の`<版>`は、使うリリースの版（Releasesのタグ名から先頭の`v`を除いたもの）に読み替えてください。

```toml
[dependencies]
spring-nbt-library = { git = "https://github.com/ScriptArts/SpringNBTLibrary", tag = "v<版>" }
```

Cargoが自分で取得します。

ネットワークに繋がらない環境なら、[Releases](https://github.com/ScriptArts/SpringNBTLibrary/releases)の`spring-nbt-library-<版>.crate`（拡張子が違うだけのtar.gz）を展開してパス参照します。

```bash
tar xzf spring-nbt-library-<版>.crate
```

```toml
[dependencies]
spring-nbt-library = { path = "spring-nbt-library-<版>" }
```

## 例外ではなく`Result`

Rust版だけは例外ではなく`Result<T, Error>`を返します。
`ErrorCode`の集合は他言語と完全に一致します（[adr/0005](../adr/0005-unified-error-model.md)）。

```rust
use spring_nbt_library::error::{ErrorCode, Result};
```

## NBTファイルを読む

```rust
use spring_nbt_library::nbt::{read_file, NbtReadOptions};

// 圧縮方式（Gzip / Zlib / 無圧縮）は自動で判定される
let named = read_file("level.dat", &NbtReadOptions::default())?;
let data = named.tag.get_compound("Data")?;

println!("{}", data.get_string("LevelName")?);
println!("{}", data.get_int("DataVersion")?);
```

型が違えば`ErrorCode::UnexpectedTagType`が返ります。
キーが無いかもしれないときは`opt_*`を使います（無ければ`Ok(None)`）。

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

## 文字列は2形態

Rustの`String`はUTF-8に限られるので、NBTに現れうる孤立サロゲートを保持できません。
そこで`NbtString`を列挙にしています（[spec/10 2.3](../spec/10-nbt-binary.md#23-各言語での保持方法)）。

```rust
pub enum NbtString {
    Text(String),          // 通常の文字列。実データはほぼすべてこちら
    Surrogates(Vec<u16>),  // UTF-8に写せないUTF-16コード単位の列
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
use spring_nbt_library::world::{BlockState, MinecraftWorld, WorldOpenOptions};

let options = WorldOpenOptions { writable: true, ..Default::default() };
let mut world = MinecraftWorld::open(world_path, options)?;

if let Some(overworld) = world.dimension("minecraft:overworld")? {
    let stone = BlockState::parse("minecraft:stone")?;
    overworld.set_block(100, 64, -200, &stone)?;
    overworld.flush()?;   // ここで初めてディスクへ書かれる
}

world.close()?;
```

> **Minecraftを終了してから実行してください。**
> Rust版は`std`にファイルロックが無いため、`session.lock`は確認しません（[adr/0008](../adr/0008-session-lock.md)）。
> 起動していないことは呼び出し側で保証してください。

> ブロックを置き換えてもHeightmapsと光源は再計算されません（[adr/0004](../adr/0004-defer-heightmap-recalc.md)）。

## スタックの深さに注意

NBTのネストは既定で深さ512まで許します。
debugビルドでは1段あたり約8 KB使うので、深いデータを扱うなら大きめのスタックを持つスレッドで走らせてください（[spec/00 5.1](../spec/00-conventions.md#51-深さ上限と実行スタック)）。

## 次に読むもの

- [ガイド](../guide/01-nbt.md): 目的別の使い方
- [API対応表](../api/overview.md): 他言語版との対応
- [エラーと安全上限](../guide/06-errors-and-limits.md)

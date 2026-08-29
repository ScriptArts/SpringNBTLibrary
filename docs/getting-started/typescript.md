# はじめに（TypeScript）

**Node.js 20 以上 / TypeScript 5.7 以上。ESM 専用。**

## 導入

npm へは公開していない。[Releases](https://github.com/ScriptArts/SpringNBTLibrary/releases) から
`spring-nbt-library-<版>.tgz` を落として組み込む。

```bash
npm install ./spring-nbt-library-0.1.0.tgz
```

これで `node_modules` へ入り、通常のパッケージと同じように import できる。
型定義（`.d.ts`）も含まれているので補完が効く。

取り込み方は 2 通りある。どちらでもよい。

```ts
// まとめて取る
import { NbtCompound, RegionFile, BlockState } from "spring-nbt-library";

// レイヤごとに取る（他言語のモジュール構成に対応する）
import { NbtCompound } from "spring-nbt-library/nbt";
import { RegionFile } from "spring-nbt-library/anvil";
import { BlockState } from "spring-nbt-library/world";
```

`package.json` には次のように記録される。

```json
{
  "dependencies": {
    "spring-nbt-library": "file:spring-nbt-library-0.1.0.tgz"
  }
}
```

## `i64` は bigint

TypeScript の `number` は 2^53 を超える整数を表せない。
`TAG_Long` と `TAG_Long_Array` だけ **`bigint`** を使う（[adr/0007](../adr/0007-typescript-bigint.md)）。
他の整数型は `number` のままである。

```ts
compound.set("time", new NbtLong(449n));   // n を付ける
```

## NBT ファイルを読む

```ts
import { readFile, NbtCompound } from "spring-nbt-library";

// 圧縮方式（Gzip / Zlib / 無圧縮）は自動で判定される
const named = readFile("level.dat");
const data = named.tag.getCompound("Data");

console.log(data.getString("LevelName"));
console.log(data.getInt("DataVersion"));
```

型が違えば `UNEXPECTED_TAG_TYPE` の例外になる。
キーが無いかもしれないときは `opt*` を使う（無ければ `undefined`）。

## 書く

```ts
import { writeFile, NamedTag, NbtCompound, NbtInt, NbtString, Compression } from "spring-nbt-library";

const root = new NbtCompound();
root.set("name", new NbtString("SpringNBTLibrary"));
root.set("count", new NbtInt(42));

writeFile("out.nbt", new NamedTag("", root), { compression: Compression.Gzip });
```

## ワールドのブロックを読む

```ts
import { MinecraftWorld } from "spring-nbt-library";

const world = MinecraftWorld.open(worldPath);

try {
  const overworld = world.dimension("minecraft:overworld");

  if (overworld !== undefined) {
    // 絶対座標。リージョンとチャンクの解決は内部で行う
    const block = overworld.getBlock(100, 64, -200);
    console.log(String(block));   // minecraft:grass_block[snowy=false]
  }
} finally {
  world.close();
}
```

## ブロックを書き換える

```ts
const world = MinecraftWorld.open(worldPath, { writable: true });

try {
  const overworld = world.dimension("minecraft:overworld")!;
  overworld.setBlock(100, 64, -200, BlockState.parse("minecraft:stone"));
  overworld.flush();   // ここで初めてディスクへ書かれる
} finally {
  world.close();
}
```

> **Minecraft を終了してから実行すること。**
> TypeScript 版は Node にファイルロックの手段が無いため
> **`session.lock` を確認しない**（[adr/0008](../adr/0008-session-lock.md)）。
> 起動中でないことは呼び出し側で担保すること。

> ブロックを置き換えても **Heightmaps と光源は再計算されない**（[adr/0004](../adr/0004-defer-heightmap-recalc.md)）。

## 次に読むもの

- [ガイド](../guide/01-nbt.md) — 目的別の使い方
- [API 対応表](../api/overview.md) — 他言語版との対応
- [エラーと安全上限](../guide/06-errors-and-limits.md)

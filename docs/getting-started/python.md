# はじめに（Python）

Python 3.10 以上が必要です。依存パッケージはありません。

## 導入

[Releases](https://github.com/ScriptArts/SpringNBTLibrary/releases) から `spring_nbt_library-<版>-py3-none-any.whl` を落とします。

```bash
pip install spring_nbt_library-0.1.0-py3-none-any.whl
```

wheel なのでビルドは不要です。

## NBT ファイルを読む

```python
from spring_nbt_library.nbt import read_file

# 圧縮方式（Gzip / Zlib / 無圧縮）は自動で判定される
named = read_file("level.dat")
data = named.tag.get_compound("Data")

print(data.get_string("LevelName"))
print(data.get_int("DataVersion"))
```

型が違えば `UNEXPECTED_TAG_TYPE` の例外になります。
キーが無いかもしれないときは `opt_*` を使います（無ければ `None`）。

## 書く

```python
from spring_nbt_library.nbt import (
    Compression, NamedTag, NbtCompound, NbtInt, NbtString, NbtWriteOptions, write_file,
)

root = NbtCompound()
root.set("name", NbtString("SpringNBTLibrary"))
root.set("count", NbtInt(42))

write_file("out.nbt", NamedTag("", root),
           NbtWriteOptions(compression=Compression.GZIP))
```

整数型の範囲は構築時に検査します。Python には整数の幅が無いので、
型で守れないぶんを実行時に見ています。

```python
NbtByte(300)   # INVALID_ARGUMENT
```

## ワールドのブロックを読む

```python
from spring_nbt_library.world import MinecraftWorld

with MinecraftWorld.open(world_path) as world:
    overworld = world.dimension("minecraft:overworld")

    if overworld is not None:
        # 絶対座標。リージョンとチャンクの解決は内部で行う
        block = overworld.get_block(100, 64, -200)
        print(block)   # minecraft:grass_block[snowy=false]
```

## ブロックを書き換える

```python
from spring_nbt_library.world import MinecraftWorld, WorldOpenOptions

with MinecraftWorld.open(world_path, WorldOpenOptions(writable=True)) as world:
    overworld = world.dimension("minecraft:overworld")
    overworld.set_block(100, 64, -200, BlockState.parse("minecraft:stone"))
    overworld.flush()   # ここで初めてディスクへ書かれる
```

> **Minecraft を終了してから実行すること。**
> Python 版が `session.lock` を確認するのは POSIX 環境だけです
> （Windows には `fcntl` がありません。[adr/0008](../adr/0008-session-lock.md)）。

> ブロックを置き換えても Heightmaps と光源は再計算されません（[adr/0004](../adr/0004-defer-heightmap-recalc.md)）。

## 自分のワールドで検証する

実ワールドを読み取り専用で走査する検証ツールが付いています。

```bash
python3 spec/tools/scan_world.py "<ワールドのパス>"
```

全チャンクを読み、書き戻したバイト列が原本と一致するかまで確かめます。
書き込みは一切しません。

## 次に読むもの

- [ガイド](../guide/01-nbt.md) — 目的別の使い方
- [API 対応表](../api/overview.md) — 他言語版との対応
- [エラーと安全上限](../guide/06-errors-and-limits.md)

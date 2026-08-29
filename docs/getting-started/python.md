# はじめに（Python）

**Python 3.10 以上。依存パッケージなし（標準ライブラリのみ）。**

## 導入

PyPI へは公開していない。[Releases](https://github.com/ScriptArts/SpringNBTLibrary/releases) から
`spring_nbt_library-<版>-py3-none-any.whl` を落として入れる。

```bash
pip install spring_nbt_library-0.1.0-py3-none-any.whl
```

wheel なのでビルドは要らない。依存パッケージも無い。

ソースから入れたい場合は `spring_nbt_library-<版>.tar.gz` でもよい。

```bash
pip install spring_nbt_library-0.1.0.tar.gz
```

## NBT ファイルを読む

```python
from spring_nbt_library.nbt import read_file

# 圧縮方式（Gzip / Zlib / 無圧縮）は自動で判定される
named = read_file("level.dat")
data = named.tag.get_compound("Data")

print(data.get_string("LevelName"))
print(data.get_int("DataVersion"))
```

型が違えば `UNEXPECTED_TAG_TYPE` の例外になる。
キーが無いかもしれないときは `opt_*` を使う（無ければ `None`）。

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

整数型の範囲は**構築時に検査する**。Python には整数の幅が無いため、
型では守れないぶんを実行時に見ている。

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
> Python 版は POSIX 環境でのみ `session.lock` を確認する
> （Windows には `fcntl` が無い。[adr/0008](../adr/0008-session-lock.md)）。

> ブロックを置き換えても **Heightmaps と光源は再計算されない**（[adr/0004](../adr/0004-defer-heightmap-recalc.md)）。

## 自分のワールドで検証する

Python 版には実ワールドを読み取り専用で走査する検証ツールが付属している。

```bash
python3 spec/tools/scan_world.py "<ワールドのパス>"
```

全チャンクを読み、書き戻したバイト列が原本と一致するかまで確かめる。
**一切書き込まない。**

## 次に読むもの

- [ガイド](../guide/01-nbt.md) — 目的別の使い方
- [API 対応表](../api/overview.md) — 他言語版との対応
- [エラーと安全上限](../guide/06-errors-and-limits.md)

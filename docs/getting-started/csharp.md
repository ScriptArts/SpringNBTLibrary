# はじめに（C#）

**.NET 8 / C# 12 以上。**

C# は本ライブラリの[基準実装](../adr/0002-idiomatic-naming.md)なので、
仕様の解釈に迷ったときはまずここを見るとよい。

## 導入

NuGet へは公開していない。[Releases](https://github.com/ScriptArts/SpringNBTLibrary/releases) から
`SpringNBTLibrary-<版>-dotnet8.zip` を落として組み込む。

1. zip を展開する。中身は次のとおり

   ```
   SpringNBTLibrary.dll   ライブラリ本体
   SpringNBTLibrary.xml   ドキュメント（IDE の補完に出る）
   LICENSE / README.md
   ```

2. プロジェクトの適当な場所（`lib/` など）へ **dll と xml を隣り合わせで**置く。
   xml が無いと補完に説明が出ない
3. `.csproj` から参照する

   ```xml
   <ItemGroup>
     <Reference Include="SpringNBTLibrary">
       <HintPath>lib/SpringNBTLibrary.dll</HintPath>
     </Reference>
   </ItemGroup>
   ```

ソースから使いたい場合は、リポジトリを取得して `ProjectReference` で参照してもよい。

```xml
<ProjectReference Include="../SpringNBTLibrary/csharp/src/SpringNBTLibrary/SpringNBTLibrary.csproj" />
```

## NBT ファイルを読む

```csharp
using SpringNBTLibrary.Nbt;

// 圧縮方式（Gzip / Zlib / 無圧縮）は自動で判定される
NamedTag named = NbtIo.ReadFile("level.dat");
NbtCompound data = ((NbtCompound)named.Tag).GetCompound("Data");

Console.WriteLine(data.GetString("LevelName"));
Console.WriteLine(data.GetInt("DataVersion"));
```

型が違えば `UNEXPECTED_TAG_TYPE` の例外になる。
キーが無いかもしれないときは `Opt*` を使う。

```csharp
// 無ければ null。あるが型違いなら例外
string? name = data.OptString("LevelName");
```

## 書く

```csharp
NbtCompound root = new NbtCompound();
root.Set("name", new NbtString("SpringNBTLibrary"));
root.Set("count", new NbtInt(42));

NbtIo.WriteFile("out.nbt", new NamedTag("", root),
    new NbtWriteOptions { Compression = Compression.Gzip });
```

## ワールドのブロックを読む

```csharp
using SpringNBTLibrary.World;

using MinecraftWorld world = MinecraftWorld.Open(worldPath);
Dimension? overworld = world.Dimension("minecraft:overworld");

if (overworld is not null)
{
    // 絶対座標。リージョンとチャンクの解決は内部で行う
    BlockState? block = overworld.GetBlock(100, 64, -200);
    Console.WriteLine(block);   // minecraft:grass_block[snowy=false]
}
```

## ブロックを書き換える

書き込みは**明示的に許可したときだけ**行える。

```csharp
WorldOpenOptions options = new WorldOpenOptions { Writable = true };

using MinecraftWorld world = MinecraftWorld.Open(worldPath, options);
Dimension overworld = world.Dimension("minecraft:overworld")!;

overworld.SetBlock(100, 64, -200, BlockState.Parse("minecraft:stone"));
overworld.Flush();   // ここで初めてディスクへ書かれる
```

> **Minecraft を終了してから実行すること。**
> 起動中のワールドへ書き込むとデータが壊れる。
> C# 版は `session.lock` を確認して防ぐ（[adr/0008](../adr/0008-session-lock.md)）。

> ブロックを置き換えても **Heightmaps と光源は再計算されない**（[adr/0004](../adr/0004-defer-heightmap-recalc.md)）。
> `Chunk.ClearHeightmaps()` / `InvalidateLighting()` でゲーム側に再計算させる。

## 次に読むもの

- [ガイド](../guide/01-nbt.md) — 目的別の使い方
- [API 対応表](../api/overview.md) — 他言語版との対応
- [エラーと安全上限](../guide/06-errors-and-limits.md)

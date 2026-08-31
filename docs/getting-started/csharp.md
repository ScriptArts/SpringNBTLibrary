# はじめに（C#）

.NET 8 / C# 12 以上が必要です。

C# は[基準実装](../adr/0002-idiomatic-naming.md)です。
仕様の解釈に迷ったら、まずここを見てください。

## 導入

[Releases](https://github.com/ScriptArts/SpringNBTLibrary/releases) に 2 通り置いてあります。
どちらでも中身は同じです。

### `.nupkg` を使う（おすすめ）

NuGet へは公開していないので、落としたファイルを置いたフォルダを
ソースとして教えます。

1. `SpringNBTLibrary.<版>.nupkg` を、プロジェクト直下の `packages/` へ置きます
2. `.csproj` と同じ場所に `nuget.config` を作ります

   ```xml
   <?xml version="1.0" encoding="utf-8"?>
   <configuration>
     <packageSources>
       <add key="springnbt" value="packages" />
     </packageSources>
   </configuration>
   ```

3. 参照に足します

   ```bash
   dotnet add package SpringNBTLibrary --version 1.0.0
   ```

ドキュメントの置き場所は NuGet が面倒を見るので、補完に説明が出ます。
`nuget.config` をプロジェクトに置くのは、この設定をリポジトリで共有できるからです
（`dotnet nuget add source` は利用者ごとの設定を書き換えるので、
他の人の手元では動きません）。

### `.zip` を使う

dll を直接参照したいときはこちらです。

1. `SpringNBTLibrary-<版>-dotnet8.zip` を展開します。中身は次のとおりです

   ```
   SpringNBTLibrary.dll   ライブラリ本体
   SpringNBTLibrary.xml   ドキュメント（IDE の補完に出る）
   LICENSE / README.md
   ```

2. プロジェクトの適当な場所（`lib/` など）へ dll と xml を隣り合わせで置きます。
   xml が無いと補完に説明が出ません
3. `.csproj` から参照します

   ```xml
   <ItemGroup>
     <Reference Include="SpringNBTLibrary">
       <HintPath>lib/SpringNBTLibrary.dll</HintPath>
     </Reference>
   </ItemGroup>
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

型が違えば `UNEXPECTED_TAG_TYPE` の例外になります。
キーが無いかもしれないときは `Opt*` を使います。

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

書き込みは明示的に許可したときだけ行えます。

```csharp
WorldOpenOptions options = new WorldOpenOptions { Writable = true };

using MinecraftWorld world = MinecraftWorld.Open(worldPath, options);
Dimension overworld = world.Dimension("minecraft:overworld")!;

overworld.SetBlock(100, 64, -200, BlockState.Parse("minecraft:stone"));
overworld.Flush();   // ここで初めてディスクへ書かれる
```

> **Minecraft を終了してから実行すること。**
> 起動中のワールドへ書き込むとデータが壊れます。
> C# 版は `session.lock` を確認して防いでいます（[adr/0008](../adr/0008-session-lock.md)）。

> ブロックを置き換えても Heightmaps と光源は再計算されません（[adr/0004](../adr/0004-defer-heightmap-recalc.md)）。
> `Chunk.ClearHeightmaps()` / `InvalidateLighting()` でゲーム側に再計算させてください。

## 次に読むもの

- [ガイド](../guide/01-nbt.md) — 目的別の使い方
- [API 対応表](../api/overview.md) — 他言語版との対応
- [エラーと安全上限](../guide/06-errors-and-limits.md)

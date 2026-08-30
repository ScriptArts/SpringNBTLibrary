# 04. ワールドと level.dat

ワールド全体を開き、`level.dat` と次元を扱います。

> コード例は基準実装の C#。他言語での綴りは [API 対応表](../api/world.md)。

---

## 1. 26.x のディレクトリ構成

1.21.x から大きく変わっています。

```
<ワールド名>/
├─ level.dat                  ワールドの基本情報のみ（軽量化された）
├─ level.dat_old              1つ前のバックアップ
├─ session.lock               起動中のロック
│
├─ data/minecraft/            ★ level.dat から分離されたデータ
│   ├─ game_rules.dat
│   ├─ weather.dat
│   ├─ world_gen_settings.dat
│   ├─ scoreboard.dat
│   └─ ...
│
├─ players/                   ★ 旧 playerdata/ から改名
│   ├─ data/<uuid>.dat
│   ├─ advancements/<uuid>.json
│   └─ stats/<uuid>.json
│
└─ dimensions/<名前空間>/<パス>/   ★ 標準3次元もここに並ぶ
    ├─ region/    地形
    ├─ entities/  エンティティ
    ├─ poi/       POI
    └─ data/minecraft/
```

変更点のまとめ

| 1.21.x | 26.x |
|---|---|
| `region/`（オーバーワールドは直下） | `dimensions/minecraft/overworld/region/` |
| `DIM-1/` `DIM1/` | `dimensions/minecraft/the_nether/` `.../the_end/` |
| `playerdata/` | `players/data/` |
| `level.dat` にゲームルール等を同梱 | `data/minecraft/*.dat` へ分離 |

この構成は[実際の 26.2 ワールドを走査して確かめた](../spec/40-world-layout.md)。

---

## 2. 開く

```csharp
using MinecraftWorld world = MinecraftWorld.Open(worldPath);

Console.WriteLine(world.Level.LevelName);
Console.WriteLine(world.Level.VersionName);      // 26.2
Console.WriteLine(world.Level.DataVersion);      // 4903
```

既定は読み取り専用。 書き込むには明示的に許可します。

```csharp
WorldOpenOptions options = new WorldOpenOptions { Writable = true };
using MinecraftWorld world = MinecraftWorld.Open(worldPath, options);
```

> 書き込みで開くと `session.lock` を確認する（C# / Java / Python(POSIX) のみ）。
> TypeScript と Rust は確認しないので、
> Minecraft が起動していないことを呼び出し側で担保すること（[adr/0008](../adr/0008-session-lock.md)）。

---

## 3. level.dat の中身

よく使う項目には名前つきの取得子があります。

```csharp
LevelData level = world.Level;

level.LevelName;         // ワールド名
level.DataVersion;       // 4903
level.VersionName;       // "26.2"
level.Time;              // 経過 tick
level.GameType;          // 0=サバイバル 1=クリエイティブ 2=アドベンチャー 3=スペクテイター
level.SpawnPos;          // [x, y, z]
level.SpawnDimension;    // "minecraft:overworld"
level.Difficulty;        // "normal"
level.IsHardcore;
```

それ以外は生の NBT を直接たどる。

```csharp
NbtCompound data = level.Data;
```

### 分離されたデータファイル

ゲームルールなどは `level.dat` にはもう入っていない。

```csharp
NbtCompound? rules = world.DataFile("game_rules");
NbtCompound? weather = world.DataFile("weather");
```

---

## 4. 次元

```csharp
foreach (string id in world.DimensionIds())
{
    Console.WriteLine(id);
    // minecraft:overworld / minecraft:the_nether / minecraft:the_end
}

Dimension? overworld = world.Dimension("minecraft:overworld");
```

名前空間を省くと `minecraft:` を補う。`world.Dimension("overworld")` でも構いません。
存在しない次元（まだ生成されていない、など）は `null` になります。

カスタム次元も同じように扱える。データパックが作った
`dimensions/mypack/mydim/` は `"mypack:mydim"` で開ける。

### 次元の中身

```csharp
foreach (ChunkPos pos in overworld.ChunkPositions())
{
    Chunk? chunk = overworld.Chunk(pos.X, pos.Z);
    Console.WriteLine($"{pos.X},{pos.Z} {chunk!.Status}");
}
```

`entities/` と `poi/` は生の NBT として読めます。

```csharp
RegionFolder? entities = overworld.EntityFolder;
NbtCompound? entityChunk = entities?.ReadChunk(pos.X, pos.Z);
```

---

## 5. プレイヤー

```csharp
foreach (string uuid in world.PlayerIds())
{
    NbtCompound? player = world.Player(uuid);
    Console.WriteLine(player?.GetString("Dimension"));
}
```

---

## 6. 保存

```csharp
overworld.Flush();     // 変更したチャンクを書き戻す
world.SaveLevel();     // level.dat を書き戻す
```

`SaveLevel` は一時ファイルへ書いてから置き換える。
書き込み中に落ちても `level.dat` が壊れないようにするためで、
直前の内容は `level.dat_old` へ退避される。

`using`（Java は try-with-resources、Python は `with`）を抜けるときに
`Close` が呼ばれ、書き込みモードなら自動で `Flush` される。

---

## 7. バージョンが違うワールド

読み込みは寛容、書き込みは対象バージョン固定というのが本ライブラリの方針
（[adr/0003](../adr/0003-version-policy.md)）。詳しくは [07](07-version-policy.md)。

---

## 8. 次に読むもの

- [05. ブロックとバイオーム](05-blocks-and-biomes.md)
- [07. バージョンポリシー](07-version-policy.md)
- [仕様 40: ワールドのディレクトリ構成](../spec/40-world-layout.md)

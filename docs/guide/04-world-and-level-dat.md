# 04. ワールドとlevel.dat

ワールド全体を開き、`level.dat`と次元を扱います。

> コード例は基準実装のC#で示します。他の言語での綴りは[API対応表](../api/world.md)を参照してください。

---

## 1. 26.xのディレクトリ構成

1.21.xから大きく変わっています。

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

変更点をまとめると次のとおりです。

| 1.21.x | 26.x |
|---|---|
| `region/`（オーバーワールドは直下） | `dimensions/minecraft/overworld/region/` |
| `DIM-1/` `DIM1/` | `dimensions/minecraft/the_nether/` `.../the_end/` |
| `playerdata/` | `players/data/` |
| `level.dat`にゲームルール等を同梱 | `data/minecraft/*.dat`へ分離 |

この構成は、[実際の26.2と26.3のワールドを走査して確かめました](../spec/40-world-layout.md)。

### 1.21.xまでの構成

1.21.xまでのワールドも同じAPIで開けます。
どちらの構成かはワールドを開いたときに`level.dat`の`DataVersion`で決まります（4786以上なら26.xの構成）。

| 扱うもの | 1.21.xまでのワールドで読む場所 |
|---|---|
| `minecraft:overworld` | ワールドの直下（`region/`など） |
| `minecraft:the_nether` / `minecraft:the_end` | `DIM-1/` / `DIM1/` |
| データパックが足した次元 | `dimensions/<名前空間>/<パス>/` |
| プレイヤー | `playerdata/<uuid>.dat` |
| `DataFile` | `<次元のフォルダ>/data/<名前>.dat` |

詳しくは[仕様40 5章](../spec/40-world-layout.md#5-261より前の構成)。

---

## 2. 開く

```csharp
using MinecraftWorld world = MinecraftWorld.Open(worldPath);

Console.WriteLine(world.Level.LevelName);
Console.WriteLine(world.Level.VersionName);      // 26.3
Console.WriteLine(world.Level.DataVersion);      // 5023
```

既定は読み取り専用です。書き込むには明示的に許可します。

```csharp
WorldOpenOptions options = new WorldOpenOptions { Writable = true };
using MinecraftWorld world = MinecraftWorld.Open(worldPath, options);
```

> 書き込みで開くと`session.lock`を確認します（C# / Java / Python(POSIX)のみ）。
> TypeScriptとRustは確認しないので、Minecraftが起動していないことを呼び出し側で確かめてください（[adr/0008](../adr/0008-session-lock.md)）。

---

## 3. level.datの中身

よく使う項目には名前つきの取得子があります。

```csharp
LevelData level = world.Level;

level.LevelName;         // ワールド名
level.DataVersion;       // 5023
level.VersionName;       // "26.3"
level.Time;              // 経過tick
level.GameType;          // 0=サバイバル 1=クリエイティブ 2=アドベンチャー 3=スペクテイター
level.SpawnPos;          // [x, y, z]
level.SpawnDimension;    // "minecraft:overworld"
level.Difficulty;        // "normal"
level.IsHardcore;
```

それ以外は生のNBTを直接たどります。

```csharp
NbtCompound data = level.Data;
```

1.21.xまでの`level.dat`では、取得子が古いキーを読みます。

- `SpawnPos`は`SpawnX` / `SpawnY` / `SpawnZ`を読みます
- `Difficulty`は数値の`Difficulty`を読み、`"peaceful"` / `"easy"` / `"normal"` / `"hard"`に直して返します
- `IsHardcore`は`hardcore`を読みます
- `SpawnDimension`は、スポーン地点の次元を持つキーが無いので`UNSUPPORTED_FEATURE`になります

### 分離されたデータファイル

26.xでは、ゲームルールなどは`level.dat`にはもう入っていません。

```csharp
NbtCompound? rules = world.DataFile("game_rules");
NbtCompound? weather = world.DataFile("weather");
```

1.21.xまでのワールドでは、ゲームルールなどは`level.dat`の中（`level.Data`）にあります。`DataFile`は`data/<名前>.dat`を読みます。

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

名前空間を省くと`minecraft:`を補います。`world.Dimension("overworld")`でも構いません。
存在しない次元（まだ生成されていない、など）は`null`になります。

カスタム次元も同じように扱えます。データパックが作った`dimensions/mypack/mydim/`は`"mypack:mydim"`で開けます。

### 次元の中身

```csharp
foreach (ChunkPos pos in overworld.ChunkPositions())
{
    Chunk? chunk = overworld.Chunk(pos.X, pos.Z);
    Console.WriteLine($"{pos.X},{pos.Z} {chunk!.Status}");
}
```

`entities/`と`poi/`は生のNBTとして読めます。

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
world.SaveLevel();     // level.datを書き戻す
```

`SaveLevel`は一時ファイルへ書き、内容をディスクへ確実に書き出してから置き換えます。
書き込み中に落ちても`level.dat`が破損しないようにするためです。直前の内容は`level.dat_old`へ退避されます。

`using`（Javaはtry-with-resources、Pythonは`with`）を抜けるときに`Close`が呼ばれ、書き込みモードなら自動で`Flush`されます。

---

## 7. バージョンが違うワールド

1.13以降のワールドは読んだときの形式のまま読み書きします。
チャンクの形式はチャンクごとに、そのチャンクの`DataVersion`で決まるので、形式の違うチャンクが混ざったワールドもそのまま扱えます（[adr/0011](../adr/0011-format-eras.md)）。

書き込みを既定で止めるのは、1.13より前のチャンク（DataVersion 1519未満か、`DataVersion`の無いもの）だけです。`DataVersion`は読んだ値のまま残します。

世代を自分で選びたいときは、開くときに指定します。フォルダの構成と、そのワールドから読むすべてのチャンクに効きます。

```csharp
WorldOpenOptions options = new WorldOpenOptions { FormatDataVersion = 3465 };   // 1.20.1の形式として開く
using MinecraftWorld world = MinecraftWorld.Open(worldPath, options);
```

詳しくは[07](07-version-policy.md)。

---

## 8. 次に読むもの

- [05. ブロックとバイオーム](05-blocks-and-biomes.md)
- [07. バージョンポリシー](07-version-policy.md)
- [仕様40: ワールドのディレクトリ構成](../spec/40-world-layout.md)

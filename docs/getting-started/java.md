# はじめに（Java）

Java 21 (LTS) 以上が必要です。

## 導入

[Releases](https://github.com/ScriptArts/SpringNBTLibrary/releases) から `spring-nbt-library-<版>.jar` を落とします。

Gradle なら jar を `libs/` へ置いて読み込みます。

```groovy
dependencies {
    implementation files("libs/spring-nbt-library-1.0.0.jar")
}
```

Maven ならローカルリポジトリへ入れてから依存に書きます。

```bash
mvn install:install-file \
  -Dfile=spring-nbt-library-1.0.0.jar \
  -DgroupId=io.github.scriptarts \
  -DartifactId=spring-nbt-library \
  -Dversion=1.0.0 -Dpackaging=jar
```

```xml
<dependency>
  <groupId>io.github.scriptarts</groupId>
  <artifactId>spring-nbt-library</artifactId>
  <version>1.0.0</version>
</dependency>
```

クラスパスへ直接置くこともできます。

```bash
java -cp spring-nbt-library-1.0.0.jar:. YourApp
```

## NBT ファイルを読む

```java
import io.github.scriptarts.springnbt.nbt.*;
import java.nio.file.Path;

// 圧縮方式（Gzip / Zlib / 無圧縮）は自動で判定される
NamedTag named = NbtIo.readFile(Path.of("level.dat"), null);
NbtCompound data = ((NbtCompound) named.tag()).getCompound("Data");

System.out.println(data.getString("LevelName"));
System.out.println(data.getInt("DataVersion"));
```

型が違えば `UNEXPECTED_TAG_TYPE` の例外になります。
キーが無いかもしれないときは `opt*` を使います（無ければ `null`）。

本ライブラリの例外 `SpringNbtException` は**非検査例外**です。
シグネチャを他言語版と揃えるため、検査例外は使いません（[adr/0005](../adr/0005-unified-error-model.md)）。

## 書く

```java
NbtCompound root = new NbtCompound();
root.set("name", new NbtString("SpringNBTLibrary"));
root.set("count", new NbtInt(42));

NbtIo.writeFile(Path.of("out.nbt"), new NamedTag("", root),
        new NbtWriteOptions().setCompression(Compression.GZIP));
```

## ワールドのブロックを読む

```java
import io.github.scriptarts.springnbt.world.*;

try (MinecraftWorld world = MinecraftWorld.open(worldPath)) {
    Dimension overworld = world.dimension("minecraft:overworld");

    if (overworld != null) {
        // 絶対座標。リージョンとチャンクの解決は内部で行う
        BlockState block = overworld.getBlock(100, 64, -200);
        System.out.println(block);   // minecraft:grass_block[snowy=false]
    }
}
```

## ブロックを書き換える

書き込みは明示的に許可したときだけ行えます。

```java
WorldOpenOptions options = new WorldOpenOptions().setWritable(true);

try (MinecraftWorld world = MinecraftWorld.open(worldPath, options)) {
    Dimension overworld = world.dimension("minecraft:overworld");
    overworld.setBlock(100, 64, -200, BlockState.parse("minecraft:stone"));
    overworld.flush();   // ここで初めてディスクへ書かれる
}
```

> **Minecraft を終了してから実行すること。**
> 起動中のワールドへ書き込むとデータが壊れます。
> Java 版は `session.lock` を確認して防いでいます（[adr/0008](../adr/0008-session-lock.md)）。

> ブロックを置き換えても Heightmaps と光源は再計算されません（[adr/0004](../adr/0004-defer-heightmap-recalc.md)）。
> `Chunk.clearHeightmaps()` / `invalidateLighting()` でゲーム側に再計算させてください。

## 次に読むもの

- [ガイド](../guide/01-nbt.md) — 目的別の使い方
- [API 対応表](../api/overview.md) — 他言語版との対応
- [エラーと安全上限](../guide/06-errors-and-limits.md)

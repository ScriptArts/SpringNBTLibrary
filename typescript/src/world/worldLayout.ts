/**
 * ワールドの構成の世代
 * ライブラリの内部だけで使う
 * `index.ts`からは出さない
 *
 * 世代ごとの違いはこの表に集める
 * ワールドと`level.dat`の読み書きは表の値に従い、DataVersionによる分岐をほかの場所に書かない
 */

import { existsSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { SpringNbtError } from "../errors.js";
import type { NbtCompound } from "../nbt/index.js";
import { OLDEST_FORMAT_DATA_VERSION } from "./chunkFormat.js";

/** L2（26.1以降）が始まるDataVersion */
export const L2_MIN_DATA_VERSION = 4786;

/**
 * 標準の次元のIDと、L1でのワールド直下からの相対ディレクトリ
 * 並びがL1の`dimensionIds`の並びになる
 */
const L1_STANDARD_DIMENSIONS: ReadonlyArray<readonly [string, string]> = [
  ["minecraft:overworld", ""],
  ["minecraft:the_nether", "DIM-1"],
  ["minecraft:the_end", "DIM1"],
];

/** L1の`Difficulty`の数値に対応する名前 */
const L1_DIFFICULTIES: readonly string[] = ["peaceful", "easy", "normal", "hard"];

/** ディレクトリか */
function isDirectory(path: string): boolean {
  return existsSync(path) && statSync(path).isDirectory();
}

/** L1の標準の次元のIDか */
function isL1Standard(dimensionId: string): boolean {
  // 標準の次元のIDと一致するものがあれば真
  return L1_STANDARD_DIMENSIONS.some(([standardId]) => standardId === dimensionId);
}

/** ワールドの構成の世代1つ分 */
export class WorldLayout {
  private constructor(
    /** 標準の次元が直下と`DIM-1/` `DIM1/`に置かれ、`level.dat`にスポーンなどが直に入る構成か */
    readonly legacy: boolean,
    /** ワールド直下からプレイヤーデータのフォルダまでの道 */
    readonly playerFolder: readonly string[],
    /** 次元のフォルダから付随データのフォルダまでの道 */
    readonly dataFolder: readonly string[],
  ) {}

  /** L1: 1.13〜1.21.x */
  static readonly #L1 = new WorldLayout(true, ["playerdata"], ["data"]);

  /** L2: 26.1以降 */
  static readonly #L2 = new WorldLayout(false, ["players", "data"], ["data", "minecraft"]);

  /**
   * DataVersionから世代を引く
   * L1より古い値もL1として扱う
   */
  static forDataVersion(dataVersion: number): WorldLayout {
    // 境界以上ならL2、それ未満はL1
    if (dataVersion >= L2_MIN_DATA_VERSION) {
      return WorldLayout.#L2;
    }

    return WorldLayout.#L1;
  }

  /**
   * `level.dat`の`Data`と、利用者の指定から世代を決める
   *
   * 指定があればそれを使い、無ければ`Data.DataVersion`で決める
   * `DataVersion`が無い古いワールドはL1として扱う
   *
   * @throws SpringNbtError 指定が扱える下限より小さい場合
   */
  static detect(data: NbtCompound, requested: number | undefined): WorldLayout {
    if (requested !== undefined) {
      // 指定は下限より小さいと解釈のしようがない
      if (requested < OLDEST_FORMAT_DATA_VERSION) {
        throw SpringNbtError.invalidArgument(
          `世代を選ぶDataVersionは${OLDEST_FORMAT_DATA_VERSION}以上でなければならない: ${requested}`,
        );
      }

      return WorldLayout.forDataVersion(requested);
    }

    const found = data.optInt("DataVersion");

    // DataVersionが無いのは1.9より前のワールドなのでL1
    if (found === undefined) {
      return WorldLayout.#L1;
    }

    return WorldLayout.forDataVersion(found);
  }

  /**
   * 次元のフォルダのパス
   * 次元のIDは名前空間つきで渡す
   */
  dimensionDirectory(worldDirectory: string, dimensionId: string): string {
    // L1の標準の次元は、ワールド直下かDIM-1/ DIM1/に置かれる
    if (this.legacy) {
      for (const [standardId, relative] of L1_STANDARD_DIMENSIONS) {
        // 標準の次元ならその専用の場所を返す
        if (dimensionId === standardId) {
          // オーバーワールドはワールドのフォルダそのもの
          if (relative === "") {
            return worldDirectory;
          }

          return join(worldDirectory, relative);
        }
      }
    }

    const colon = dimensionId.indexOf(":");
    return join(worldDirectory, "dimensions", dimensionId.slice(0, colon), dimensionId.slice(colon + 1));
  }

  /** 次元が存在するか */
  hasDimension(worldDirectory: string, dimensionId: string): boolean {
    const directory = this.dimensionDirectory(worldDirectory, dimensionId);

    // L1のオーバーワールドはワールド直下なので、region/の有無で判断する
    if (this.legacy && dimensionId === L1_STANDARD_DIMENSIONS[0]![0]) {
      return isDirectory(join(directory, "region"));
    }

    return isDirectory(directory);
  }

  /**
   * 存在する次元のIDを返す
   * L1では標準の3つを固定の順に並べ、そのあとにデータパックの次元をIDの順に並べる
   */
  dimensionIds(worldDirectory: string): string[] {
    const found: string[] = [];

    // L1の標準の次元は固定の順で先に並べる
    if (this.legacy) {
      for (const [standardId] of L1_STANDARD_DIMENSIONS) {
        // 存在する標準の次元だけを数える
        if (this.hasDimension(worldDirectory, standardId)) {
          found.push(standardId);
        }
      }
    }

    const extra: string[] = [];
    const root = join(worldDirectory, "dimensions");

    if (existsSync(root)) {
      // dimensions/<名前空間>/<パス>/の2段を辿る
      for (const namespaceName of readdirSync(root)) {
        const namespaceDir = join(root, namespaceName);

        if (!statSync(namespaceDir).isDirectory()) {
          continue;
        }

        // 2段目が次元のパス
        for (const pathName of readdirSync(namespaceDir)) {
          const dimensionId = `${namespaceName}:${pathName}`;

          // ディレクトリだけを次元として数える
          // L1では標準の次元をdimensions/の下からは探さない
          if (statSync(join(namespaceDir, pathName)).isDirectory() && !(this.legacy && isL1Standard(dimensionId))) {
            extra.push(dimensionId);
          }
        }
      }
    }

    // 走査順がファイルシステム依存にならないよう並べる
    extra.sort();
    return found.concat(extra);
  }

  /** プレイヤーデータのフォルダのパス */
  playerDirectory(worldDirectory: string): string {
    return join(worldDirectory, ...this.playerFolder);
  }

  /** 次元のフォルダの下の付随データのファイルのパス */
  dataFilePath(dimensionDirectory: string, name: string): string {
    return join(dimensionDirectory, ...this.dataFolder, `${name}.dat`);
  }

  /** スポーン地点の`[x, y, z]` */
  spawnPos(data: NbtCompound): Int32Array {
    // L1は3つの整数に分かれて入っている
    if (this.legacy) {
      return Int32Array.of(data.getInt("SpawnX"), data.getInt("SpawnY"), data.getInt("SpawnZ"));
    }

    return data.getCompound("spawn").getIntArray("pos");
  }

  /**
   * スポーン地点の次元ID
   *
   * @throws SpringNbtError この世代の`level.dat`に無い場合（`UnsupportedFeature`）
   */
  spawnDimension(data: NbtCompound): string {
    // L1にはスポーン地点の次元を持つキーが無い
    if (this.legacy) {
      throw SpringNbtError.unsupportedFeature("26.1より前のlevel.datにはスポーン地点の次元が無い");
    }

    return data.getCompound("spawn").getString("dimension");
  }

  /**
   * 難易度（`normal`など）
   *
   * @throws SpringNbtError 数値が0〜3の外の場合（`MalformedData`）
   */
  difficulty(data: NbtCompound): string {
    // L1は0〜3の数値で入っている
    if (this.legacy) {
      const number = data.getByte("Difficulty");
      const name = L1_DIFFICULTIES[number];

      if (name === undefined) {
        throw SpringNbtError.malformed(`Difficultyが0〜3の外: ${number}`);
      }

      return name;
    }

    return data.getCompound("difficulty_settings").getString("difficulty");
  }

  /** ハードコアか */
  isHardcore(data: NbtCompound): boolean {
    // L1はDataの直下に入っている
    if (this.legacy) {
      return data.getBool("hardcore");
    }

    return data.getCompound("difficulty_settings").getBool("hardcore");
  }
}

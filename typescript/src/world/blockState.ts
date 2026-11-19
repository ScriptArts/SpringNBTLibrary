/**
 * ブロックの状態
 * 名前と、任意のプロパティの組
 *
 * プロパティは**常に名前の昇順で保持する**
 * こうしておくと文字列表現が一意になり、全言語で同じ出力になる
 * Minecraftが書き出した並び順は、`PalettedContainer`がパレットを生のNBTのまま持つことで守られる
 * そのため、触っていないブロックの並びが崩れることはない
 */

import { TARGET_DATA_VERSION } from "../index.js";
import { SpringNbtError } from "../errors.js";
import { NbtCompound, NbtString, NbtTag, TagType, tagTypeAsString } from "../nbt/index.js";
import { OLDEST_FORMAT_DATA_VERSION, PALETTE_ID_FORMAT_DATA_VERSION } from "./chunkFormat.js";

/**
 * ブロックの状態
 * 名前と、任意のプロパティの組
 *
 * プロパティは**常に名前の昇順で保持する**
 * こうしておくと文字列表現が一意になり、全言語で同じ出力になる
 */
export class BlockState {
  readonly #name: string;
  readonly #properties: Map<string, string>;

  constructor(name: string, properties?: Iterable<readonly [string, string]>) {
    this.#name = normalize(name);
    this.#properties = new Map();

    if (properties !== undefined) {
      // 与えられたプロパティを取り込む
      for (const [key, value] of properties) {
        this.#properties.set(key, value);
      }
    }

    this.#sort();
  }

  /** ブロックID（名前空間つき） */
  get name(): string {
    return this.#name;
  }

  /**
   * プロパティ
   * 名前の昇順
   */
  get properties(): ReadonlyMap<string, string> {
    return this.#properties;
  }

  /**
   * プロパティを取得する
   * 無ければundefined
   */
  property(key: string): string | undefined {
    return this.#properties.get(key);
  }

  /** プロパティを1つ差し替えた新しい状態を返す */
  with(key: string, value: string): BlockState {
    const entries = [...this.#properties];
    entries.push([key, value]);
    return new BlockState(this.#name, entries);
  }

  /** `minecraft:oak_stairs[facing=north,half=top]`形式の文字列から作る */
  static parse(text: string): BlockState {
    const bracket = text.indexOf("[");

    if (bracket < 0) {
      if (text.length === 0) {
        throw SpringNbtError.invalidArgument("ブロック名が空");
      }

      return new BlockState(text);
    }

    if (!text.endsWith("]")) {
      throw SpringNbtError.invalidArgument(`角括弧が閉じられていない: ${text}`);
    }

    const body = text.slice(bracket + 1, -1);
    const entries: Array<[string, string]> = [];
    const seen = new Set<string>();

    if (body.length > 0) {
      // "key=value"をカンマ区切りで読む
      for (const pair of body.split(",")) {
        const equals = pair.indexOf("=");

        if (equals < 0) {
          throw SpringNbtError.invalidArgument(`プロパティに '=' が無い: ${pair}`);
        }

        const key = pair.slice(0, equals).trim();

        if (key.length === 0) {
          throw SpringNbtError.invalidArgument(`プロパティ名が空: ${pair}`);
        }

        // どちらが採用されたか分からないまま書き込まれるのを避けるため、重複は弾く
        if (seen.has(key)) {
          throw SpringNbtError.invalidArgument(`プロパティ名が重複している: ${key}`);
        }

        seen.add(key);
        entries.push([key, pair.slice(equals + 1).trim()]);
      }
    }

    return new BlockState(text.slice(0, bracket), entries);
  }

  /**
   * パレット要素のNBTから作る
   *
   * `TARGET_DATA_VERSION`の形式で読む
   * DataVersionを指定するときは`fromNbtForDataVersion`を使う
   *
   * @throws SpringNbtError 文字列でもCompoundでもない、`id`が無い、または`properties`の値が文字列でない場合
   */
  static fromNbt(nbt: NbtTag): BlockState {
    return BlockState.fromNbtForDataVersion(nbt, TARGET_DATA_VERSION);
  }

  /**
   * DataVersionを指定して、パレット要素のNBTから作る
   *
   * 26.3（DataVersion 5006）以降は、既定の状態がブロックIDだけの文字列で、それ以外は`id`と`properties`を持つCompoundで入っている
   * 異種リストの要素を包む`{"": <値>}`は外してから読む
   * 1519以上5006未満は、`Name`と`Properties`を持つCompoundを読む
   * 文字列は受け付けない
   *
   * @param nbt パレット要素
   * @param dataVersion パレット要素を含むチャンクのDataVersion（1519以上）
   * @throws SpringNbtError `dataVersion`が1519未満の場合（INVALID_ARGUMENT）、
   * 要素が形式に合うタグでない場合、`id` / `Name`が無い場合、またはプロパティの値が文字列でない場合
   */
  static fromNbtForDataVersion(nbt: NbtTag, dataVersion: number): BlockState {
    checkDataVersion(dataVersion);

    // 26.3より前は、Name / Propertiesの形式で入っている
    if (dataVersion < PALETTE_ID_FORMAT_DATA_VERSION) {
      return fromNameProperties(nbt);
    }

    return fromPaletteId(nbt);
  }

  /**
   * パレット要素のNBTへ変換する
   *
   * `TARGET_DATA_VERSION`の形式で書く
   * DataVersionを指定するときは`toNbtForDataVersion`を使う
   */
  toNbt(): NbtTag {
    return this.toNbtForDataVersion(TARGET_DATA_VERSION);
  }

  /**
   * DataVersionを指定して、パレット要素のNBTへ変換する
   *
   * 26.3（DataVersion 5006）以降は、プロパティが空ならブロックIDだけの文字列にし、それ以外は`id`と`properties`を持つCompoundにする
   * 1519以上5006未満は、`Name`を持つCompoundにし、プロパティが空なら`Properties`キー自体を出力しない
   * いずれもMinecraftと同じ振る舞い
   *
   * @param dataVersion 書き込み先のチャンクのDataVersion（1519以上）
   * @throws SpringNbtError `dataVersion`が1519未満の場合（INVALID_ARGUMENT）
   */
  toNbtForDataVersion(dataVersion: number): NbtTag {
    checkDataVersion(dataVersion);

    // 26.3より前は、Name / Propertiesの形式で書く
    if (dataVersion < PALETTE_ID_FORMAT_DATA_VERSION) {
      return this.#toNameProperties();
    }

    return this.#toPaletteId();
  }

  /** 26.3以降の`id` / `properties`の形式へ変換する */
  #toPaletteId(): NbtTag {
    // プロパティが無ければ、Minecraftが既定の状態を書くときと同じく文字列にする
    if (this.#properties.size === 0) {
      return new NbtString(this.#name);
    }

    const result = new NbtCompound();
    result.set("id", new NbtString(this.#name));
    const propertiesTag = new NbtCompound();

    // 名前の昇順で並ぶ
    for (const [key, value] of this.#properties) {
      propertiesTag.set(key, new NbtString(value));
    }

    result.set("properties", propertiesTag);
    return result;
  }

  /** 26.2までの`Name` / `Properties`の形式へ変換する */
  #toNameProperties(): NbtCompound {
    const result = new NbtCompound();
    result.set("Name", new NbtString(this.#name));

    // プロパティが無ければ、Propertiesキー自体を出力しない
    if (this.#properties.size === 0) {
      return result;
    }

    const propertiesTag = new NbtCompound();

    // 名前の昇順で並ぶ
    for (const [key, value] of this.#properties) {
      propertiesTag.set(key, new NbtString(value));
    }

    result.set("Properties", propertiesTag);
    return result;
  }

  /** 同じ名前・同じプロパティか */
  equals(other: BlockState): boolean {
    if (other.#name !== this.#name || other.#properties.size !== this.#properties.size) {
      return false;
    }

    // 名前と値がすべて一致するかを見る
    for (const [key, value] of this.#properties) {
      if (other.#properties.get(key) !== value) {
        return false;
      }
    }

    return true;
  }

  /** `minecraft:oak_stairs[facing=north,half=top]`形式の文字列を返す */
  toString(): string {
    if (this.#properties.size === 0) {
      return this.#name;
    }

    const parts: string[] = [];

    // 名前の昇順で並べるので、同じ状態なら必ず同じ文字列になる
    for (const [key, value] of this.#properties) {
      parts.push(`${key}=${value}`);
    }

    return `${this.#name}[${parts.join(",")}]`;
  }

  /** プロパティを名前の昇順へ並べ直す */
  #sort(): void {
    const sorted = [...this.#properties].sort((left, right) => {
      if (left[0] < right[0]) {
        return -1;
      }

      if (left[0] > right[0]) {
        return 1;
      }

      return 0;
    });

    this.#properties.clear();

    // 昇順に並べ直したものを入れ直す
    for (const [key, value] of sorted) {
      this.#properties.set(key, value);
    }
  }
}

/**
 * 異種リストの包みを外す
 * 包みでなければそのまま返す
 *
 * 空のキー1つだけを持つCompoundが包みに当たる（MinecraftのListTagと同じ判定）
 * `PalettedContainer`の同名の関数と同じ処理で、公開APIを増やさないためにここにも置く
 */
function unwrapListElement(tag: NbtTag): NbtTag {
  if (tag instanceof NbtCompound && tag.size === 1 && tag.containsKey("")) {
    return tag.get("");
  }

  return tag;
}

/** 名前空間が省略されていたら`minecraft:`を補う */
function normalize(name: string): string {
  if (name.includes(":")) {
    return name;
  }

  return `minecraft:${name}`;
}

/** 指定されたDataVersionが、読み書きできる下限以上であることを確かめる */
function checkDataVersion(dataVersion: number): void {
  if (dataVersion < OLDEST_FORMAT_DATA_VERSION) {
    throw SpringNbtError.invalidArgument(
      `DataVersionは${OLDEST_FORMAT_DATA_VERSION}以上でなければならない: ${dataVersion}`,
    );
  }
}

/** 26.3以降の`id` / `properties`の形式から読む */
function fromPaletteId(nbt: NbtTag): BlockState {
  const entry = unwrapListElement(nbt);

  // 既定の状態は、ブロックIDだけの文字列で入っている
  if (entry instanceof NbtString) {
    return new BlockState(entry.value);
  }

  if (!(entry instanceof NbtCompound)) {
    throw SpringNbtError.unexpectedTagType(
      `ブロックのパレット要素が string でも compound でもない: ${tagTypeAsString(entry.type)}`,
    );
  }

  const name = entry.optString("id");

  if (name === undefined) {
    // Name / Propertiesは26.2までの形式で、読み替えると誤った状態を返しかねない
    if (entry.containsKey("Name")) {
      throw SpringNbtError.malformed(
        "ブロックのパレット要素にidが無い。NameはDataVersion 5006より前の形式なので、5006未満のDataVersionで読むこと",
      );
    }

    throw SpringNbtError.malformed("ブロックのパレット要素に id が無い");
  }

  const entries: Array<[string, string]> = [];
  const propertiesTag = entry.optCompound("properties");

  if (propertiesTag !== undefined) {
    // propertiesの値はすべて文字列（数値や真偽値も文字列で入る）
    for (const [key, value] of propertiesTag.entries()) {
      if (value.type !== TagType.String) {
        throw SpringNbtError.unexpectedTagType(
          `properties の "${key}" が文字列でない`,
        );
      }

      entries.push([key, (value as NbtString).value]);
    }
  }

  return new BlockState(name, entries);
}

/** 26.2までの`Name` / `Properties`の形式から読む */
function fromNameProperties(nbt: NbtTag): BlockState {
  // 26.2までは文字列のパレット要素も、異種リストの包みも無い
  if (!(nbt instanceof NbtCompound)) {
    throw SpringNbtError.unexpectedTagType(
      `ブロックのパレット要素が compound でない: ${tagTypeAsString(nbt.type)}`,
    );
  }

  const name = nbt.optString("Name");

  if (name === undefined) {
    throw SpringNbtError.malformed("ブロックのパレット要素に Name が無い");
  }

  const entries: Array<[string, string]> = [];
  const propertiesTag = nbt.optCompound("Properties");

  if (propertiesTag !== undefined) {
    // Propertiesの値はすべて文字列（数値や真偽値も文字列で入る）
    for (const [key, value] of propertiesTag.entries()) {
      if (value.type !== TagType.String) {
        throw SpringNbtError.unexpectedTagType(
          `Properties の "${key}" が文字列でない`,
        );
      }

      entries.push([key, (value as NbtString).value]);
    }
  }

  return new BlockState(name, entries);
}

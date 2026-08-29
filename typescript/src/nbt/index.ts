/**
 * NBT (Named Binary Tag) の読み書き
 *
 * このレイヤは Minecraft のバージョンに一切依存しない
 *
 * 仕様: `docs/spec/10-nbt-binary.md`
 */

export * as mutf8 from "./mutf8.js";
export * as canonical from "./canonical.js";
export * as snbt from "./snbt.js";

export {
  NbtByte,
  NbtByteArray,
  NbtCompound,
  NbtDouble,
  NbtFloat,
  NbtInt,
  NbtIntArray,
  NbtList,
  NbtLong,
  NbtLongArray,
  NbtShort,
  NbtString,
  TagType,
  tagTypeAsString,
  tagTypeFromId,
} from "./tag.js";
export type { NbtTag } from "./tag.js";

export {
  Compression,
  NamedTag,
  NbtFormat,
  detectCompression,
  readBytes,
  readFile,
  writeBytes,
  writeFile,
} from "./io.js";
export type { NbtReadOptions, NbtWriteOptions } from "./io.js";

/**
 * NBT (Named Binary Tag) の読み書き
 *
 * このレイヤはMinecraftのバージョンに一切依存しない
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
  readBytesAll,
  readBytesAt,
  readFile,
  writeBytes,
  writeFile,
} from "./io.js";
export type { NbtReadOptions, NbtReadResult, NbtWriteOptions } from "./io.js";

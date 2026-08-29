/**
 * Anvil のリージョンファイル (.mca) の読み書き
 *
 * 仕様: `docs/spec/20-anvil-region.md`
 */

export { ChunkPos, RegionPos } from "./pos.js";
export {
  ChunkCompression,
  RawChunk,
  chunkCompressionAsString,
  chunkCompressionFromId,
} from "./compression.js";
export { RegionFile, RegionFileMode, SECTOR_SIZE } from "./regionFile.js";
export { DEFAULT_MAX_CACHED_REGIONS, RegionFolder } from "./regionFolder.js";

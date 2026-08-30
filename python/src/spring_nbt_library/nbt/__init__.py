"""NBT (Named Binary Tag) の読み書き

このレイヤは Minecraft のバージョンに一切依存しない

仕様: ``docs/spec/10-nbt-binary.md``
"""

from . import canonical, mutf8, snbt
from .io import (
    Compression,
    NamedTag,
    NbtFormat,
    NbtReadOptions,
    NbtReadResult,
    NbtWriteOptions,
    detect_compression,
    read_bytes,
    read_bytes_all,
    read_bytes_at,
    read_file,
    read_stream,
    write_bytes,
    write_file,
    write_stream,
)
from .tag import (
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
    NbtTag,
    TagType,
)

__all__ = [
    "mutf8",
    "snbt",
    "canonical",
    "TagType",
    "NbtTag",
    "NbtByte",
    "NbtShort",
    "NbtInt",
    "NbtLong",
    "NbtFloat",
    "NbtDouble",
    "NbtByteArray",
    "NbtString",
    "NbtList",
    "NbtCompound",
    "NbtIntArray",
    "NbtLongArray",
    "NbtFormat",
    "Compression",
    "NamedTag",
    "NbtReadOptions",
    "NbtReadResult",
    "NbtWriteOptions",
    "read_file",
    "read_bytes",
    "read_bytes_at",
    "read_bytes_all",
    "read_stream",
    "write_file",
    "write_bytes",
    "write_stream",
    "detect_compression",
]

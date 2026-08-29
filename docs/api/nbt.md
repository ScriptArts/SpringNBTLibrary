# API 対応表：NBT

NBT のタグ型・読み書き・SNBT。バージョンに依存しない純粋なコーデック。

- 使い方は [ガイド 01](../guide/01-nbt.md) / [ガイド 02](../guide/02-snbt.md)
- バイトレベルの仕様は [spec/10](../spec/10-nbt-binary.md) / [spec/11](../spec/11-snbt.md)
- 命名の変換規則は [概要](overview.md#2-変換規則)

「—」はその言語に対応するものが無いことを示す。
理由は [概要 4章](overview.md#4-言語ごとに揃わないところ) にまとめてある。

<!-- generated:start -->

| 論理名 | C# | Java | TypeScript | Python | Rust | 概要 |
|---|---|---|---|---|---|---|
| **TagType** | `TagType` | `TagType` | `TagType` | `TagType` | `TagType` | NBT のタグ型。 |
| `as_str` | — | — | — | — | `as_str()` |  |
| `as_string` | — | `asString()` | — | `as_string()` | — |  |
| `byte` | `Byte` | `BYTE` | `Byte` | `byte` | `byte` | TAG_Byte (1)。 |
| `byte_array` | `ByteArray` | `BYTE_ARRAY` | `ByteArray` | `byte_array` | `byte_array` | TAG_Byte_Array (7)。 |
| `compound` | `Compound` | `COMPOUND` | `Compound` | `compound` | `compound` | TAG_Compound (10)。 |
| `double` | `Double` | `DOUBLE` | `Double` | `double` | `double` | TAG_Double (6)。 |
| `end` | `End` | `END` | `End` | `end` | `end` | TAG_End (0)。 |
| `float` | `Float` | `FLOAT` | `Float` | `float` | `float` | TAG_Float (5)。 |
| `from_id` | — | `fromId()` | — | `from_id()` | `from_id()` |  |
| `id` | `Id` | `id()` | `id` | `id()` | `id()` |  |
| `int` | `Int` | `INT` | `Int` | `int` | `int` | TAG_Int (3)。 |
| `int_array` | `IntArray` | `INT_ARRAY` | `IntArray` | `int_array` | `int_array` | TAG_Int_Array (11)。 |
| `list` | `List` | `LIST` | `List` | `list` | `list` | TAG_List (9)。 |
| `long` | `Long` | `LONG` | `Long` | `long` | `long` | TAG_Long (4)。 |
| `long_array` | `LongArray` | `LONG_ARRAY` | `LongArray` | `long_array` | `long_array` | TAG_Long_Array (12)。 |
| `short` | `Short` | `SHORT` | `Short` | `short` | `short` | TAG_Short (2)。 |
| `string` | `String` | `STRING` | `String` | `string` | `string` | TAG_String (8)。 |
| **NbtTag** | `NbtTag` | `NbtTag` | — | `NbtTag` | `NbtTag` | NBT のタグ。 |
| `byte` | `Byte` | `BYTE` | `Byte` | `byte` | `byte` |  |
| `byte_array` | `ByteArray` | `BYTE_ARRAY` | `ByteArray` | `byte_array` | `byte_array` |  |
| `compound` | `Compound` | `COMPOUND` | `Compound` | `compound` | `compound` |  |
| `double` | `Double` | `DOUBLE` | `Double` | `double` | `double` |  |
| `float` | `Float` | `FLOAT` | `Float` | `float` | `float` |  |
| `int` | `Int` | `INT` | `Int` | `int` | `int` |  |
| `int_array` | `IntArray` | `INT_ARRAY` | `IntArray` | `int_array` | `int_array` |  |
| `list` | `List` | `LIST` | `List` | `list` | `list` |  |
| `long` | `Long` | `LONG` | `Long` | `long` | `long` |  |
| `long_array` | `LongArray` | `LONG_ARRAY` | `LongArray` | `long_array` | `long_array` |  |
| `short` | `Short` | `SHORT` | `Short` | `short` | `short` |  |
| `string` | `String` | `STRING` | `String` | `string` | `string` |  |
| `tag_type` | — | — | — | — | `tag_type()` |  |
| `type` | `Type` | `type()` | `type` | `type` | — | このタグの型。 |
| **NbtByte** | `NbtByte` | `NbtByte` | `NbtByte` | `NbtByte` | — | TAG_Byte。 |
| `type` | `Type` | `type()` | `type` | `type` | — |  |
| `value` | `Value` | `value()` | `value()` | — | — | 保持している値。 |
| **NbtShort** | `NbtShort` | `NbtShort` | `NbtShort` | `NbtShort` | — | TAG_Short。 |
| `type` | `Type` | `type()` | `type` | `type` | — |  |
| `value` | `Value` | `value()` | `value()` | — | — | 保持している値。 |
| **NbtInt** | `NbtInt` | `NbtInt` | `NbtInt` | `NbtInt` | — | TAG_Int。 |
| `type` | `Type` | `type()` | `type` | `type` | — |  |
| `value` | `Value` | `value()` | `value()` | — | — | 保持している値。 |
| **NbtLong** | `NbtLong` | `NbtLong` | `NbtLong` | `NbtLong` | — | TAG_Long。 |
| `type` | `Type` | `type()` | `type` | `type` | — |  |
| `value` | `Value` | `value()` | `value()` | — | — | 保持している値。 |
| **NbtFloat** | `NbtFloat` | `NbtFloat` | `NbtFloat` | `NbtFloat` | — | TAG_Float。 |
| `type` | `Type` | `type()` | `type` | `type` | — |  |
| `value` | `Value` | `value()` | `value()` | — | — | 保持している値。 |
| **NbtDouble** | `NbtDouble` | `NbtDouble` | `NbtDouble` | `NbtDouble` | — | TAG_Double。 |
| `type` | `Type` | `type()` | `type` | `type` | — |  |
| `value` | `Value` | `value()` | `value()` | — | — | 保持している値。 |
| **NbtByteArray** | `NbtByteArray` | `NbtByteArray` | `NbtByteArray` | `NbtByteArray` | — | TAG_Byte_Array。 |
| `type` | `Type` | `type()` | `type` | `type` | — |  |
| `value` | `Value` | `value()` | `value()` | — | — | 保持している配列。 |
| **NbtIntArray** | `NbtIntArray` | `NbtIntArray` | `NbtIntArray` | `NbtIntArray` | — | TAG_Int_Array。 |
| `type` | `Type` | `type()` | `type` | `type` | — |  |
| `value` | `Value` | `value()` | `value()` | — | — | 保持している配列。 |
| **NbtLongArray** | `NbtLongArray` | `NbtLongArray` | `NbtLongArray` | `NbtLongArray` | — | TAG_Long_Array。 |
| `type` | `Type` | `type()` | `type` | `type` | — |  |
| `value` | `Value` | `value()` | `value()` | — | — | 保持している配列。 |
| **NbtString** | `NbtString` | `NbtString` | `NbtString` | `NbtString` | `NbtString` | TAG_String。 |
| `as_str` | — | — | — | — | `as_str()` |  |
| `from_utf16` | — | — | — | — | `from_utf16()` |  |
| `mutf8_len` | — | — | — | — | `mutf8_len()` |  |
| `surrogates` | — | — | — | — | `surrogates` |  |
| `text` | — | — | — | — | `text` |  |
| `to_mutf8` | — | — | — | — | `to_mutf8()` |  |
| `to_utf16` | — | — | — | — | `to_utf16()` |  |
| `type` | `Type` | `type()` | `type` | `type` | — |  |
| `value` | `Value` | `value()` | `value()` | — | — |  |
| **NbtList** | `NbtList` | `NbtList` | `NbtList` | `NbtList` | `NbtList` | TAG_List。 |
| `clear` | `Clear()` | `clear()` | `clear()` | `clear()` | `clear()` | 全要素を削除する。 |
| `element_type` | `ElementType` | `elementType()` | `elementType()` | `element_type` | `element_type()` | 要素の型。 |
| `get` | `Get()` | `get()` | `get()` | `get()` | `get()` |  |
| `remove` | `Remove()` | `remove()` | `remove()` | `remove()` | `remove()` |  |
| `set` | `Set()` | `set()` | `set()` | `set()` | `set()` |  |
| `type` | `Type` | `type()` | `type` | `type` | — |  |
| `with_element_type` | — | — | — | — | `with_element_type()` |  |
| **NbtCompound** | `NbtCompound` | `NbtCompound` | `NbtCompound` | `NbtCompound` | `NbtCompound` | TAG_Compound。 |
| `clear` | `Clear()` | `clear()` | `clear()` | `clear()` | `clear()` | 全要素を削除する。 |
| `contains_key` | `ContainsKey()` | `containsKey()` | `containsKey()` | `contains_key()` | `contains_key()` | キーが存在するか。 |
| `get` | `Get()` | `get()` | `get()` | `get()` | `get()` | キーに対応するタグを返す。 |
| `get_bool` | `GetBool()` | `getBool()` | `getBool()` | `get_bool()` | `get_bool()` | TAG_Byte を真偽値として取得する。 |
| `get_byte` | `GetByte()` | `getByte()` | `getByte()` | `get_byte()` | `get_byte()` | TAG_Byte を取得する。 |
| `get_byte_array` | `GetByteArray()` | `getByteArray()` | `getByteArray()` | `get_byte_array()` | `get_byte_array()` | TAG_Byte_Array を取得する。 |
| `get_compound` | `GetCompound()` | `getCompound()` | `getCompound()` | `get_compound()` | `get_compound()` | TAG_Compound を取得する。 |
| `get_double` | `GetDouble()` | `getDouble()` | `getDouble()` | `get_double()` | `get_double()` | TAG_Double を取得する。 |
| `get_float` | `GetFloat()` | `getFloat()` | `getFloat()` | `get_float()` | `get_float()` | TAG_Float を取得する。 |
| `get_int` | `GetInt()` | `getInt()` | `getInt()` | `get_int()` | `get_int()` | TAG_Int を取得する。 |
| `get_int_array` | `GetIntArray()` | `getIntArray()` | `getIntArray()` | `get_int_array()` | `get_int_array()` | TAG_Int_Array を取得する。 |
| `get_list` | `GetList()` | `getList()` | `getList()` | `get_list()` | `get_list()` | TAG_List を取得する。 |
| `get_long` | `GetLong()` | `getLong()` | `getLong()` | `get_long()` | `get_long()` | TAG_Long を取得する。 |
| `get_long_array` | `GetLongArray()` | `getLongArray()` | `getLongArray()` | `get_long_array()` | `get_long_array()` | TAG_Long_Array を取得する。 |
| `get_short` | `GetShort()` | `getShort()` | `getShort()` | `get_short()` | `get_short()` | TAG_Short を取得する。 |
| `get_string` | `GetString()` | `getString()` | `getString()` | `get_string()` | `get_string()` | TAG_String を取得する。 |
| `get_string_tag` | — | — | — | — | `get_string_tag()` |  |
| `opt` | `Opt()` | `opt()` | `opt()` | `opt()` | `opt()` | キーに対応するタグを返す。 |
| `opt_bool` | `OptBool()` | `optBool()` | `optBool()` | `opt_bool()` | `opt_bool()` | TAG_Byte を真偽値として取得する。 |
| `opt_byte` | `OptByte()` | `optByte()` | `optByte()` | `opt_byte()` | `opt_byte()` | TAG_Byte を取得する。 |
| `opt_byte_array` | `OptByteArray()` | `optByteArray()` | `optByteArray()` | `opt_byte_array()` | `opt_byte_array()` | TAG_Byte_Array を取得する。 |
| `opt_compound` | `OptCompound()` | `optCompound()` | `optCompound()` | `opt_compound()` | `opt_compound()` | TAG_Compound を取得する。 |
| `opt_double` | `OptDouble()` | `optDouble()` | `optDouble()` | `opt_double()` | `opt_double()` | TAG_Double を取得する。 |
| `opt_float` | `OptFloat()` | `optFloat()` | `optFloat()` | `opt_float()` | `opt_float()` | TAG_Float を取得する。 |
| `opt_int` | `OptInt()` | `optInt()` | `optInt()` | `opt_int()` | `opt_int()` | TAG_Int を取得する。 |
| `opt_int_array` | `OptIntArray()` | `optIntArray()` | `optIntArray()` | `opt_int_array()` | `opt_int_array()` | TAG_Int_Array を取得する。 |
| `opt_list` | `OptList()` | `optList()` | `optList()` | `opt_list()` | `opt_list()` | TAG_List を取得する。 |
| `opt_long` | `OptLong()` | `optLong()` | `optLong()` | `opt_long()` | `opt_long()` | TAG_Long を取得する。 |
| `opt_long_array` | `OptLongArray()` | `optLongArray()` | `optLongArray()` | `opt_long_array()` | `opt_long_array()` | TAG_Long_Array を取得する。 |
| `opt_short` | `OptShort()` | `optShort()` | `optShort()` | `opt_short()` | `opt_short()` | TAG_Short を取得する。 |
| `opt_string` | `OptString()` | `optString()` | `optString()` | `opt_string()` | `opt_string()` | TAG_String を取得する。 |
| `opt_string_tag` | — | — | — | — | `opt_string_tag()` |  |
| `remove` | `Remove()` | `remove()` | `remove()` | `remove()` | `remove()` | キーを削除する。 |
| `set` | `Set()` | `set()` | `set()` | `set()` | `set()` | 値を設定する。 |
| `type` | `Type` | `type()` | `type` | `type` | — |  |
| **NamedTag** | `NamedTag` | `NamedTag` | `NamedTag` | `NamedTag` | `NamedTag` | ルート名とルートタグの組。 |
| `name` | `Name` | `name()` | `name` | `name` | `name` | ルート名。 |
| `tag` | `Tag` | `tag()` | `tag` | `tag` | `tag` | ルートタグ。 |
| **Compression** | `Compression` | `Compression` | `Compression` | `Compression` | `Compression` | 圧縮方式。 |
| `auto` | `Auto` | `AUTO` | `Auto` | `auto` | `auto` | 先頭バイトから自動判定する。 |
| `gzip` | `Gzip` | `GZIP` | `Gzip` | `gzip` | `gzip` | GZip (RFC 1952)。 |
| `none` | `None` | `NONE` | `None` | `none` | `none` | 無圧縮。 |
| `zlib` | `Zlib` | `ZLIB` | `Zlib` | `zlib` | `zlib` | Zlib (RFC 1950)。 |
| **NbtFormat** | `NbtFormat` | `NbtFormat` | `NbtFormat` | `NbtFormat` | `NbtFormat` | NBT のルートタグの並び方。 |
| `java` | `Java` | `JAVA` | `Java` | `java` | `java` | ファイル形式。 |
| `network` | `Network` | `NETWORK` | `Network` | `network` | `network` | ネットワーク形式 (1.20.2 以降)。 |
| **NbtReadOptions** | `NbtReadOptions` | `NbtReadOptions` | `NbtReadOptions` | `NbtReadOptions` | `NbtReadOptions` | NBT 読み込みのオプション。 |
| `compression` | `Compression` | `compression()` | `compression` | `compression` | `compression` | 圧縮方式。 |
| `default_max_depth` | — | `DEFAULT_MAX_DEPTH` | — | — | — |  |
| `format` | `Format` | `format()` | `format` | `format` | `format` | ルートタグの並び方。 |
| `max_decompressed_size` | `MaxDecompressedSize` | `maxDecompressedSize()` | `maxDecompressedSize` | `max_decompressed_size` | `max_decompressed_size` | 展開後の総バイト数の上限。 |
| `max_depth` | `MaxDepth` | `maxDepth()` | `maxDepth` | `max_depth` | `max_depth` | ネストの深さ上限。 |
| **NbtWriteOptions** | `NbtWriteOptions` | `NbtWriteOptions` | `NbtWriteOptions` | `NbtWriteOptions` | `NbtWriteOptions` | NBT 書き込みのオプション。 |
| `compression` | `Compression` | `compression()` | `compression` | `compression` | `compression` | 圧縮方式。 |
| `format` | `Format` | `format()` | `format` | `format` | `format` | ルートタグの並び方。 |
| `uncompressed` | `Uncompressed` | `uncompressed()` | — | — | `uncompressed()` | 無圧縮で書き出すオプション。 |
| （モジュール関数） | — | — | — | — | — | 自由関数。C# / Java には自由関数が無いので静的クラスに置く |
| `biome_index` | `BiomeIndex()` | `biomeIndex()` | `biomeIndex()` | `biome_index()` | `biome_index()` |  |
| `biomes_per_section` | `BiomesPerSection` | `BIOMES_PER_SECTION` | `BIOMES_PER_SECTION` | `BIOMES_PER_SECTION` | `BIOMES_PER_SECTION` |  |
| `block_index` | `BlockIndex()` | `blockIndex()` | `blockIndex()` | `block_index()` | `block_index()` |  |
| `blocks_per_section` | `BlocksPerSection` | `BLOCKS_PER_SECTION` | `BLOCKS_PER_SECTION` | `BLOCKS_PER_SECTION` | `BLOCKS_PER_SECTION` |  |
| `byte_length` | `ByteLength()` | `byteLength()` | `byteLength()` | `byte_length()` | — | 文字列を MUTF-8 で符号化したときのバイト長を求める。 |
| `ceil_log2` | `CeilLog2()` | `ceilLog2()` | `ceilLog2()` | `ceil_log2()` | `ceil_log2()` |  |
| `chunk_compression_as_string` | — | — | `chunkCompressionAsString()` | — | — |  |
| `chunk_compression_from_id` | — | — | `chunkCompressionFromId()` | — | — |  |
| `decode` | `Decode()` | `decode()` | `decode()` | `decode()` | — | MUTF-8 バイト列を文字列へ復号する。 |
| `decode_to_utf16` | — | — | — | — | `decode_to_utf16()` |  |
| `detect_compression` | `DetectCompression()` | `detectCompression()` | `detectCompression()` | `detect_compression()` | `detect_compression()` | 先頭バイトから圧縮方式を判定する。 |
| `encode` | `Encode()` | `encode()` | `encode()` | `encode()` | — | 文字列を MUTF-8 バイト列へ符号化する。 |
| `encode_from_utf16` | — | — | — | — | `encode_from_utf16()` |  |
| `encode_str` | — | — | — | — | `encode_str()` |  |
| `error_code_as_string` | — | — | `errorCodeAsString()` | — | — |  |
| `from_double` | — | — | `fromDouble()` | `from_double()` | — |  |
| `from_f32` | — | — | — | — | `from_f32()` |  |
| `from_f64` | — | — | — | — | `from_f64()` |  |
| `from_float` | — | — | `fromFloat()` | `from_float()` | — |  |
| `is_bare_char` | — | — | — | `is_bare_char()` | — |  |
| `max_byte_length` | `MaxByteLength` | `MAX_BYTE_LENGTH` | `MAX_BYTE_LENGTH` | `MAX_BYTE_LENGTH` | — | MUTF-8 の文字列が取りうる最大バイト長（長さフィールドが u16 のため）。 |
| `parse` | `Parse()` | `parse()` | `parse()` | `parse()` | `parse()` | SNBT 文字列をタグへ変換する。 |
| `parse_compound` | `ParseCompound()` | `parseCompound()` | `parseCompound()` | `parse_compound()` | `parse_compound()` | SNBT 文字列を Compound へ変換する。 |
| `read_bytes` | `ReadBytes()` | `readBytes()` | `readBytes()` | `read_bytes()` | `read_bytes()` | バイト列から NBT を読む。 |
| `read_file` | `ReadFile()` | `readFile()` | `readFile()` | `read_file()` | `read_file()` | ファイルから NBT を読む。 |
| `read_reader` | — | — | — | — | `read_reader()` |  |
| `read_stream` | `ReadStream()` | `readStream()` | — | `read_stream()` | — | ストリームから NBT を読む。 |
| `sector_size` | `SectorSize` | `SECTOR_SIZE` | `SECTOR_SIZE` | `SECTOR_SIZE` | `SECTOR_SIZE` |  |
| `tag_type_as_string` | — | — | `tagTypeAsString()` | — | — |  |
| `tag_type_from_id` | — | — | `tagTypeFromId()` | — | — |  |
| `target_data_version` | `TargetDataVersion` | `TARGET_DATA_VERSION` | `TARGET_DATA_VERSION` | `TARGET_DATA_VERSION` | `TARGET_DATA_VERSION` | 本ライブラリが対象とする Minecraft Java版の DataVersion (26.2)。 |
| `utf16_to_string` | — | — | — | — | `utf16_to_string()` |  |
| `write` | `Write()` | `write()` | `write()` | `write()` | `write()` | タグを 1 行の SNBT へ変換する。 |
| `write_bytes` | `WriteBytes()` | `writeBytes()` | `writeBytes()` | `write_bytes()` | `write_bytes()` | NBT をバイト列へ書き出す。 |
| `write_file` | `WriteFile()` | `writeFile()` | `writeFile()` | `write_file()` | `write_file()` | NBT をファイルへ書き出す。 |
| `write_pretty` | `WritePretty()` | `writePretty()` | `writePretty()` | `write_pretty()` | `write_pretty()` | タグを整形した SNBT へ変換する。 |
| `write_stream` | `WriteStream()` | `writeStream()` | — | `write_stream()` | — | NBT をストリームへ書き出す。 |
| `write_writer` | — | — | — | — | `write_writer()` |  |

<!-- generated:end -->

この表は実装から生成している。手で直さず、
`python3 spec/tools/check_docs_sync.py --write` で更新すること。

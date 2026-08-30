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
| **TagType** | `TagType` | `TagType` | `TagType` | `TagType` | `TagType` | NBT のタグ型 |
| `as_string` | `AsString()` | `asString()` | `tagTypeAsString()` | `as_string()` | `as_str()` | 適合性テストで言語間比較に使う識別子を返す |
| `byte` | `Byte` | `BYTE` | `Byte` | `BYTE` | `Byte` | TAG_Byte (1) |
| `byte_array` | `ByteArray` | `BYTE_ARRAY` | `ByteArray` | `BYTE_ARRAY` | `ByteArray` | TAG_Byte_Array (7) |
| `compound` | `Compound` | `COMPOUND` | `Compound` | `COMPOUND` | `Compound` | TAG_Compound (10) |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `double` | `Double` | `DOUBLE` | `Double` | `DOUBLE` | `Double` | TAG_Double (6) |
| `end` | `End` | `END` | `End` | `END` | `End` |  |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `float` | `Float` | `FLOAT` | `Float` | `FLOAT` | `Float` | TAG_Float (5) |
| `from_id` | `FromId()` | `fromId()` | `tagTypeFromId()` | `from_id()` | `from_id()` | タグIDから TagType を得る |
| `id` | `Id` | `id()` | `id` | `id()` | `id()` |  |
| `int` | `Int` | `INT` | `Int` | `INT` | `Int` | TAG_Int (3) |
| `int_array` | `IntArray` | `INT_ARRAY` | `IntArray` | `INT_ARRAY` | `IntArray` | TAG_Int_Array (11) |
| `list` | `List` | `LIST` | `List` | `LIST` | `List` | TAG_List (9) |
| `long` | `Long` | `LONG` | `Long` | `LONG` | `Long` | TAG_Long (4) |
| `long_array` | `LongArray` | `LONG_ARRAY` | `LongArray` | `LONG_ARRAY` | `LongArray` | TAG_Long_Array (12) |
| `short` | `Short` | `SHORT` | `Short` | `SHORT` | `Short` | TAG_Short (2) |
| `string` | `String` | `STRING` | `String` | `STRING` | `String` | TAG_String (8) |
| **NbtTag** | `NbtTag` | `NbtTag` | — | `NbtTag` | `NbtTag` | NBT のタグ |
| `byte` | `Byte` | `BYTE` | `Byte` | `BYTE` | `Byte` |  |
| `byte_array` | `ByteArray` | `BYTE_ARRAY` | `ByteArray` | `BYTE_ARRAY` | `ByteArray` |  |
| `compound` | `Compound` | `COMPOUND` | `Compound` | `COMPOUND` | `Compound` |  |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` | このタグの深いコピーを作る |
| `double` | `Double` | `DOUBLE` | `Double` | `DOUBLE` | `Double` |  |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `float` | `Float` | `FLOAT` | `Float` | `FLOAT` | `Float` |  |
| `int` | `Int` | `INT` | `Int` | `INT` | `Int` |  |
| `int_array` | `IntArray` | `INT_ARRAY` | `IntArray` | `INT_ARRAY` | `IntArray` |  |
| `list` | `List` | `LIST` | `List` | `LIST` | `List` |  |
| `long` | `Long` | `LONG` | `Long` | `LONG` | `Long` |  |
| `long_array` | `LongArray` | `LONG_ARRAY` | `LongArray` | `LONG_ARRAY` | `LongArray` |  |
| `short` | `Short` | `SHORT` | `Short` | `SHORT` | `Short` |  |
| `string` | `String` | `STRING` | `String` | `STRING` | `String` |  |
| `type` | `Type` | `type()` | `type` | `type` | `tag_type()` | このタグの型 |
| **NbtByte** | `NbtByte` | `NbtByte` | `NbtByte` | `NbtByte` | — |  |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `to_string` | `ToString()` | `toString()` | `toString()` | `==` | `to_string()` |  |
| `type` | `Type` | `type()` | `type` | `type` | `tag_type()` |  |
| `value` | `Value` | `value()` | `value()` | `value` | — | 保持している値 |
| **NbtShort** | `NbtShort` | `NbtShort` | `NbtShort` | `NbtShort` | — |  |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `to_string` | `ToString()` | `toString()` | `toString()` | `==` | `to_string()` |  |
| `type` | `Type` | `type()` | `type` | `type` | `tag_type()` |  |
| `value` | `Value` | `value()` | `value()` | `value` | — | 保持している値 |
| **NbtInt** | `NbtInt` | `NbtInt` | `NbtInt` | `NbtInt` | — |  |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `to_string` | `ToString()` | `toString()` | `toString()` | `==` | `to_string()` |  |
| `type` | `Type` | `type()` | `type` | `type` | `tag_type()` |  |
| `value` | `Value` | `value()` | `value()` | `value` | — | 保持している値 |
| **NbtLong** | `NbtLong` | `NbtLong` | `NbtLong` | `NbtLong` | — |  |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `to_string` | `ToString()` | `toString()` | `toString()` | `==` | `to_string()` |  |
| `type` | `Type` | `type()` | `type` | `type` | `tag_type()` |  |
| `value` | `Value` | `value()` | `value()` | `value` | — | 保持している値 |
| **NbtFloat** | `NbtFloat` | `NbtFloat` | `NbtFloat` | `NbtFloat` | — |  |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `to_string` | `ToString()` | `toString()` | `toString()` | `==` | `to_string()` |  |
| `type` | `Type` | `type()` | `type` | `type` | `tag_type()` |  |
| `value` | `Value` | `value()` | `value()` | `value` | — | 保持している値 |
| **NbtDouble** | `NbtDouble` | `NbtDouble` | `NbtDouble` | `NbtDouble` | — |  |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `to_string` | `ToString()` | `toString()` | `toString()` | `==` | `to_string()` |  |
| `type` | `Type` | `type()` | `type` | `type` | `tag_type()` |  |
| `value` | `Value` | `value()` | `value` | `value` | — | 保持している値 |
| **NbtByteArray** | `NbtByteArray` | `NbtByteArray` | `NbtByteArray` | `NbtByteArray` | — |  |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `to_string` | `ToString()` | `toString()` | `toString()` | `==` | `to_string()` |  |
| `type` | `Type` | `type()` | `type` | `type` | `tag_type()` |  |
| `value` | `Value` | `value()` | `value` | `value` | — | 保持している配列 |
| **NbtIntArray** | `NbtIntArray` | `NbtIntArray` | `NbtIntArray` | `NbtIntArray` | — |  |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `to_string` | `ToString()` | `toString()` | `toString()` | `==` | `to_string()` |  |
| `type` | `Type` | `type()` | `type` | `type` | `tag_type()` |  |
| `value` | `Value` | `value()` | `value` | `value` | — | 保持している配列 |
| **NbtLongArray** | `NbtLongArray` | `NbtLongArray` | `NbtLongArray` | `NbtLongArray` | — |  |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `to_string` | `ToString()` | `toString()` | `toString()` | `==` | `to_string()` |  |
| `type` | `Type` | `type()` | `type` | `type` | `tag_type()` |  |
| `value` | `Value` | `value()` | `value` | `value` | — | 保持している配列 |
| **NbtString** | `NbtString` | `NbtString` | `NbtString` | `NbtString` | `NbtString` |  |
| `as_string` | `AsString()` | `asString()` | `chunkCompressionAsString()` | `as_string()` | `as_str()` |  |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `from_utf16` | — | — | — | — | `from_utf16()` |  |
| `mutf8_len` | — | — | — | — | `mutf8_len()` |  |
| `surrogates` | — | — | — | — | `Surrogates` |  |
| `text` | — | — | — | — | `Text` |  |
| `to_mutf8` | — | — | — | — | `to_mutf8()` |  |
| `to_string` | `ToString()` | `toString()` | `toString()` | `==` | `to_string()` |  |
| `to_utf16` | — | — | — | — | `to_utf16()` |  |
| `type` | `Type` | `type()` | `type` | `type` | `tag_type()` |  |
| `value` | `Value` | `value()` | `value()` | `value` | — | 保持している値 |
| **NbtList** | `NbtList` | `NbtList` | `NbtList` | `NbtList` | `NbtList` | TAG_List |
| `clear` | `Clear()` | `clear()` | `clear()` | `clear()` | `clear()` |  |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `element_type` | `ElementType` | `elementType()` | `elementType()` | `element_type` | `element_type()` |  |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `get` | `Get()` | `get()` | `get()` | `get()` | `get()` |  |
| `remove` | `Remove()` | `remove()` | `remove()` | `remove()` | `remove()` |  |
| `set` | `Set()` | `set()` | `set()` | `set()` | `set()` |  |
| `to_string` | `ToString()` | `toString()` | `toString()` | `==` | `to_string()` |  |
| `type` | `Type` | `type()` | `type` | `type` | `tag_type()` |  |
| `with_element_type` | — | — | — | — | `with_element_type()` |  |
| **NbtCompound** | `NbtCompound` | `NbtCompound` | `NbtCompound` | `NbtCompound` | `NbtCompound` | TAG_Compound |
| `clear` | `Clear()` | `clear()` | `clear()` | `clear()` | `clear()` | 全要素を削除する |
| `contains_key` | `ContainsKey()` | `containsKey()` | `containsKey()` | `contains_key()` | `contains_key()` | キーが存在するか |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `get` | `Get()` | `get()` | `get()` | `get()` | `get()` |  |
| `get_bool` | `GetBool()` | `getBool()` | `getBool()` | `get_bool()` | `get_bool()` |  |
| `get_byte` | `GetByte()` | `getByte()` | `getByte()` | `get_byte()` | `get_byte()` |  |
| `get_byte_array` | `GetByteArray()` | `getByteArray()` | `getByteArray()` | `get_byte_array()` | `get_byte_array()` |  |
| `get_compound` | `GetCompound()` | `getCompound()` | `getCompound()` | `get_compound()` | `get_compound()` |  |
| `get_double` | `GetDouble()` | `getDouble()` | `getDouble()` | `get_double()` | `get_double()` |  |
| `get_float` | `GetFloat()` | `getFloat()` | `getFloat()` | `get_float()` | `get_float()` |  |
| `get_int` | `GetInt()` | `getInt()` | `getInt()` | `get_int()` | `get_int()` |  |
| `get_int_array` | `GetIntArray()` | `getIntArray()` | `getIntArray()` | `get_int_array()` | `get_int_array()` |  |
| `get_list` | `GetList()` | `getList()` | `getList()` | `get_list()` | `get_list()` |  |
| `get_long` | `GetLong()` | `getLong()` | `getLong()` | `get_long()` | `get_long()` |  |
| `get_long_array` | `GetLongArray()` | `getLongArray()` | `getLongArray()` | `get_long_array()` | `get_long_array()` |  |
| `get_short` | `GetShort()` | `getShort()` | `getShort()` | `get_short()` | `get_short()` |  |
| `get_string` | `GetString()` | `getString()` | `getString()` | `get_string()` | `get_string()` |  |
| `get_string_tag` | — | — | — | — | `get_string_tag()` |  |
| `opt` | `Opt()` | `opt()` | `opt()` | `opt()` | `opt()` |  |
| `opt_bool` | `OptBool()` | `optBool()` | `optBool()` | `opt_bool()` | `opt_bool()` |  |
| `opt_byte` | `OptByte()` | `optByte()` | `optByte()` | `opt_byte()` | `opt_byte()` |  |
| `opt_byte_array` | `OptByteArray()` | `optByteArray()` | `optByteArray()` | `opt_byte_array()` | `opt_byte_array()` |  |
| `opt_compound` | `OptCompound()` | `optCompound()` | `optCompound()` | `opt_compound()` | `opt_compound()` |  |
| `opt_double` | `OptDouble()` | `optDouble()` | `optDouble()` | `opt_double()` | `opt_double()` |  |
| `opt_float` | `OptFloat()` | `optFloat()` | `optFloat()` | `opt_float()` | `opt_float()` |  |
| `opt_int` | `OptInt()` | `optInt()` | `optInt()` | `opt_int()` | `opt_int()` |  |
| `opt_int_array` | `OptIntArray()` | `optIntArray()` | `optIntArray()` | `opt_int_array()` | `opt_int_array()` |  |
| `opt_list` | `OptList()` | `optList()` | `optList()` | `opt_list()` | `opt_list()` |  |
| `opt_long` | `OptLong()` | `optLong()` | `optLong()` | `opt_long()` | `opt_long()` |  |
| `opt_long_array` | `OptLongArray()` | `optLongArray()` | `optLongArray()` | `opt_long_array()` | `opt_long_array()` |  |
| `opt_short` | `OptShort()` | `optShort()` | `optShort()` | `opt_short()` | `opt_short()` |  |
| `opt_string` | `OptString()` | `optString()` | `optString()` | `opt_string()` | `opt_string()` |  |
| `opt_string_tag` | — | — | — | — | `opt_string_tag()` |  |
| `remove` | `Remove()` | `remove()` | `remove()` | `remove()` | `remove()` |  |
| `set` | `Set()` | `set()` | `set()` | `set()` | `set()` | 値を設定する |
| `set_bool` | `SetBool()` | `setBool()` | `setBool()` | `set_bool()` | `set_bool()` | TAG_Byte として設定する |
| `set_byte` | `SetByte()` | `setByte()` | `setByte()` | `set_byte()` | `set_byte()` | TAG_Byte として設定する |
| `set_byte_array` | `SetByteArray()` | `setByteArray()` | `setByteArray()` | `set_byte_array()` | `set_byte_array()` | TAG_Byte_Array として設定する |
| `set_double` | `SetDouble()` | `setDouble()` | `setDouble()` | `set_double()` | `set_double()` | TAG_Double として設定する |
| `set_float` | `SetFloat()` | `setFloat()` | `setFloat()` | `set_float()` | `set_float()` | TAG_Float として設定する |
| `set_int` | `SetInt()` | `setInt()` | `setInt()` | `set_int()` | `set_int()` | TAG_Int として設定する |
| `set_int_array` | `SetIntArray()` | `setIntArray()` | `setIntArray()` | `set_int_array()` | `set_int_array()` | TAG_Int_Array として設定する |
| `set_long` | `SetLong()` | `setLong()` | `setLong()` | `set_long()` | `set_long()` | TAG_Long として設定する |
| `set_long_array` | `SetLongArray()` | `setLongArray()` | `setLongArray()` | `set_long_array()` | `set_long_array()` | TAG_Long_Array として設定する |
| `set_short` | `SetShort()` | `setShort()` | `setShort()` | `set_short()` | `set_short()` | TAG_Short として設定する |
| `set_string` | `SetString()` | `setString()` | `setString()` | `set_string()` | `set_string()` | TAG_String として設定する |
| `to_string` | `ToString()` | `toString()` | `toString()` | `==` | `to_string()` |  |
| `type` | `Type` | `type()` | `type` | `type` | `tag_type()` |  |
| **NamedTag** | `NamedTag` | `NamedTag` | `NamedTag` | `NamedTag` | `NamedTag` | ルート名とルートタグの組 |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `name` | `Name` | `name()` | `name` | `name` | `name` | ルート名 |
| `tag` | `Tag` | `tag()` | `tag` | `tag` | `tag` | ルートタグ |
| `to_string` | `ToString()` | `toString()` | `toString()` | `==` | `to_string()` |  |
| **Compression** | `Compression` | `Compression` | `Compression` | `Compression` | `Compression` | 圧縮方式 |
| `auto` | `Auto` | `AUTO` | `Auto` | `AUTO` | `Auto` | 先頭バイトから自動判定する |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `gzip` | `Gzip` | `GZIP` | `Gzip` | `GZIP` | `Gzip` | GZip (RFC 1952) |
| `none` | `None` | `NONE` | `None` | `NONE` | `None` | 無圧縮 |
| `zlib` | `Zlib` | `ZLIB` | `Zlib` | `ZLIB` | `Zlib` | Zlib (RFC 1950) |
| **NbtFormat** | `NbtFormat` | `NbtFormat` | `NbtFormat` | `NbtFormat` | `NbtFormat` | NBT のルートタグの並び方 |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `java` | `Java` | `JAVA` | `Java` | `JAVA` | `Java` | ファイル形式 |
| `network` | `Network` | `NETWORK` | `Network` | `NETWORK` | `Network` | ネットワーク形式 (1.20.2 以降) |
| **NbtReadOptions** | `NbtReadOptions` | `NbtReadOptions` | `NbtReadOptions` | `NbtReadOptions` | `NbtReadOptions` | NBT 読み込みのオプション |
| `compression` | `Compression` | `compression()` | `compression` | `compression` | `compression` |  |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `default_max_depth` | — | `DEFAULT_MAX_DEPTH` | — | — | — |  |
| `format` | `Format` | `format()` | `format` | `format` | `format` |  |
| `max_decompressed_size` | `MaxDecompressedSize` | `maxDecompressedSize()` | `maxDecompressedSize` | `max_decompressed_size` | `max_decompressed_size` |  |
| `max_depth` | `MaxDepth` | `maxDepth()` | `maxDepth` | `max_depth` | `max_depth` |  |
| **NbtReadResult** | `NbtReadResult` | `NbtReadResult` | `NbtReadResult` | `NbtReadResult` | `NbtReadResult` | 位置を指定した読み込みの結果 |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `end` | `End` | `end()` | `end` | `end` | `end` | 読み終わった直後の位置 |
| `equals` | `Equals()` | `equals()` | `equals()` | `==` | `==` |  |
| `tag` | `Tag` | `tag()` | `tag` | `tag` | `tag` | 読んだタグ |
| `to_string` | `ToString()` | `toString()` | `toString()` | `==` | `to_string()` |  |
| **NbtWriteOptions** | `NbtWriteOptions` | `NbtWriteOptions` | `NbtWriteOptions` | `NbtWriteOptions` | `NbtWriteOptions` | NBT 書き込みのオプション |
| `compression` | `Compression` | `compression()` | `compression` | `compression` | `compression` |  |
| `copy` | `Copy()` | `copy()` | `copy()` | `copy()` | `clone()` |  |
| `format` | `Format` | `format()` | `format` | `format` | `format` |  |
| `uncompressed` | `Uncompressed` | `uncompressed()` | — | `uncompressed()` | `uncompressed()` | 無圧縮で書き出すオプション |
| （モジュール関数） | — | — | — | — | — | 自由関数。C# / Java には自由関数が無いので静的クラスに置く |
| `biome_index` | `BiomeIndex()` | `biomeIndex()` | `biomeIndex()` | `biome_index()` | `biome_index()` |  |
| `biomes_per_section` | `BiomesPerSection` | `BIOMES_PER_SECTION` | `BIOMES_PER_SECTION` | `BIOMES_PER_SECTION` | `BIOMES_PER_SECTION` |  |
| `block_index` | `BlockIndex()` | `blockIndex()` | `blockIndex()` | `block_index()` | `block_index()` |  |
| `blocks_per_section` | `BlocksPerSection` | `BLOCKS_PER_SECTION` | `BLOCKS_PER_SECTION` | `BLOCKS_PER_SECTION` | `BLOCKS_PER_SECTION` |  |
| `byte_length` | `ByteLength()` | `byteLength()` | `byteLength()` | `byte_length()` | `byte_length()` | 文字列を MUTF-8 で符号化したときのバイト長を求める |
| `ceil_log2` | `CeilLog2()` | `ceilLog2()` | `ceilLog2()` | `ceil_log2()` | `ceil_log2()` |  |
| `decode` | `Decode()` | `decode()` | `decode()` | `decode()` | `decode()` | MUTF-8 バイト列を文字列へ復号する |
| `decode_to_utf16` | — | — | — | — | `decode_to_utf16()` |  |
| `decompress` | — | — | — | — | `decompress()` |  |
| `decompress_lz4` | — | — | `decompressLz4()` | `decompress_lz4()` | — |  |
| `default_max_cached_regions` | `DefaultMaxCachedRegions` | `DEFAULT_MAX_CACHED_REGIONS` | `DEFAULT_MAX_CACHED_REGIONS` | `DEFAULT_MAX_CACHED_REGIONS` | `DEFAULT_MAX_CACHED_REGIONS` |  |
| `detect_compression` | `DetectCompression()` | `detectCompression()` | `detectCompression()` | `detect_compression()` | `detect_compression()` | 先頭バイトから圧縮方式を判定する |
| `encode` | `Encode()` | `encode()` | `encode()` | `encode()` | `encode()` | 文字列を MUTF-8 バイト列へ符号化する |
| `encode_from_utf16` | — | — | — | — | `encode_from_utf16()` |  |
| `from_double` | — | — | `fromDouble()` | `from_double()` | — |  |
| `from_f32` | — | — | — | — | `from_f32()` |  |
| `from_f64` | — | — | — | — | `from_f64()` |  |
| `from_float` | — | — | `fromFloat()` | `from_float()` | — |  |
| `header_length` | — | — | — | `HEADER_LENGTH` | — |  |
| `is_bare_char` | — | — | — | `is_bare_char()` | — |  |
| `magic` | — | — | — | `MAGIC` | — |  |
| `max_byte_length` | `MaxByteLength` | `MAX_BYTE_LENGTH` | `MAX_BYTE_LENGTH` | `MAX_BYTE_LENGTH` | `MAX_BYTE_LENGTH` | MUTF-8 の文字列が取りうる最大バイト長（長さフィールドが u16 のため） |
| `method_compressed` | — | — | — | `METHOD_COMPRESSED` | — |  |
| `method_stored` | — | — | — | `METHOD_STORED` | — |  |
| `min_match` | — | — | — | `MIN_MATCH` | — |  |
| `parse` | `Parse()` | `parse()` | `parse()` | `parse()` | `parse()` | SNBT 文字列をタグへ変換する |
| `parse_compound` | `ParseCompound()` | `parseCompound()` | `parseCompound()` | `parse_compound()` | `parse_compound()` | SNBT 文字列を Compound へ変換する |
| `read_bytes` | `ReadBytes()` | `readBytes()` | `readBytes()` | `read_bytes()` | `read_bytes()` | バイト列から NBT を読む |
| `read_bytes_all` | `ReadBytesAll()` | `readBytesAll()` | `readBytesAll()` | `read_bytes_all()` | `read_bytes_all()` | バイト列に連なっている NBT をすべて読む |
| `read_bytes_at` | `ReadBytesAt()` | `readBytesAt()` | `readBytesAt()` | `read_bytes_at()` | `read_bytes_at()` | バイト列の指定した位置から NBT を 1 つ読む |
| `read_file` | `ReadFile()` | `readFile()` | `readFile()` | `read_file()` | `read_file()` | ファイルから NBT を読む |
| `read_stream` | `ReadStream()` | `readStream()` | — | `read_stream()` | `read_reader()` |  |
| `sector_size` | `SectorSize` | `SECTOR_SIZE` | `SECTOR_SIZE` | `SECTOR_SIZE` | `SECTOR_SIZE` |  |
| `target_data_version` | `TargetDataVersion` | `TARGET_DATA_VERSION` | `TARGET_DATA_VERSION` | `TARGET_DATA_VERSION` | `TARGET_DATA_VERSION` | 本ライブラリが対象とする Minecraft Java版の DataVersion (26.2) |
| `utf16_to_string` | — | — | — | — | `utf16_to_string()` |  |
| `write` | `Write()` | `write()` | `write()` | `write()` | `write()` | タグを 1 行の SNBT へ変換する |
| `write_bytes` | `WriteBytes()` | `writeBytes()` | `writeBytes()` | `write_bytes()` | `write_bytes()` | NBT をバイト列へ書き出す |
| `write_file` | `WriteFile()` | `writeFile()` | `writeFile()` | `write_file()` | `write_file()` | NBT をファイルへ書き出す |
| `write_pretty` | `WritePretty()` | `writePretty()` | `writePretty()` | `write_pretty()` | `write_pretty()` |  |
| `write_stream` | `WriteStream()` | `writeStream()` | — | `write_stream()` | `write_writer()` | NBT をストリームへ書き出す |

<!-- generated:end -->

この表は実装から生成している。手で直さず、
`python3 spec/tools/check_docs_sync.py --write` で更新すること。

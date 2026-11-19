using SpringNBTLibrary.Anvil;
using SpringNBTLibrary.Nbt;
using SpringNBTLibrary.World;

namespace SpringNBTLibrary.Tests;

/// <summary>
/// World / Blockレイヤ
/// </summary>
public class WorldTests
{
    /// <summary>共通テストベクタ（world/*.nbt）のパス</summary>
    private static string VectorPath(string name)
    {
        string current = AppContext.BaseDirectory;

        // ビルド出力からリポジトリ直下まで遡ってspec/testdataを探す
        while (current is not null)
        {
            string candidate = Path.Combine(current, "spec", "testdata", "world", name + ".nbt");

            if (File.Exists(candidate))
            {
                return candidate;
            }

            DirectoryInfo? parent = System.IO.Directory.GetParent(current);

            if (parent is null)
            {
                break;
            }

            current = parent.FullName;
        }

        throw new InvalidOperationException("テストベクタが見つからない: world/" + name + ".nbt");
    }

    /// <summary>テストベクタをチャンクとして読む</summary>
    private static Chunk LoadChunk(string name, ChunkReadOptions? options = null)
    {
        NamedTag named = NbtIo.ReadFile(VectorPath(name));
        return Chunk.FromNbt((NbtCompound)named.Tag, options);
    }

    /// <summary>異種リストの要素を包むCompoundを作る</summary>
    private static NbtCompound Wrapped(NbtTag tag)
    {
        NbtCompound wrapper = new NbtCompound();
        wrapper.Set("", tag);
        return wrapper;
    }

    /// <summary>26.2までの形式（Name / Properties）のパレット要素を作る</summary>
    private static NbtCompound NameProperties(string name, params (string Key, string Value)[] properties)
    {
        NbtCompound entry = new NbtCompound();
        entry.SetString("Name", name);

        // プロパティがあるときだけPropertiesを足す
        if (properties.Length > 0)
        {
            NbtCompound propertiesTag = new NbtCompound();

            // 渡された順に入れる
            foreach ((string key, string value) in properties)
            {
                propertiesTag.SetString(key, value);
            }

            entry.Set("Properties", propertiesTag);
        }

        return entry;
    }

    /// <summary>26.3からの形式（id / properties）のパレット要素を作る</summary>
    private static NbtCompound IdProperties(string name, params (string Key, string Value)[] properties)
    {
        NbtCompound entry = new NbtCompound();
        entry.SetString("id", name);
        NbtCompound propertiesTag = new NbtCompound();

        // 渡された順に入れる
        foreach ((string key, string value) in properties)
        {
            propertiesTag.SetString(key, value);
        }

        entry.Set("properties", propertiesTag);
        return entry;
    }

    /// <summary>
    /// 扱える形式の下限より古く、1.13より前でもあるDataVersion
    /// どの世代でも解釈しない
    /// </summary>
    private const int PreFlatteningDataVersion = 1400;

    /// <summary>1.13より前のようにLevelに本体を包み、ブロックを数値IDで持つチャンクを作る</summary>
    private static NbtCompound PreFlatteningChunk()
    {
        NbtCompound section = new NbtCompound();
        section.SetByte("Y", 0);
        section.SetByteArray("Blocks", Enumerable.Repeat((sbyte)1, 4096).ToArray());
        section.SetByteArray("Data", new sbyte[2048]);
        NbtList sections = new NbtList(TagType.Compound);
        sections.Add(section);

        NbtCompound level = new NbtCompound();
        level.SetInt("xPos", 3);
        level.SetInt("zPos", -2);
        level.Set("Sections", sections);

        NbtCompound root = new NbtCompound();
        root.SetInt("DataVersion", PreFlatteningDataVersion);
        root.Set("Level", level);
        return root;
    }

    /// <summary>1.17までのようにLevelに本体を包んだチャンクを作る</summary>
    private static NbtCompound LevelChunk(int dataVersion)
    {
        NbtCompound level = new NbtCompound();
        level.SetInt("xPos", 0);
        level.SetInt("zPos", 0);
        level.SetString("Status", "full");
        level.Set("Sections", new NbtList(TagType.Compound));

        NbtCompound root = new NbtCompound();
        root.SetInt("DataVersion", dataVersion);
        root.Set("Level", level);
        return root;
    }

    /// <summary>チャンクのNBTを無圧縮のバイト列にする</summary>
    private static byte[] ChunkBytes(NbtCompound tag)
    {
        return NbtIo.WriteBytes(new NamedTag("", tag), new NbtWriteOptions { Compression = Compression.None });
    }

    /// <summary>書き出したチャンクの最初のセクションのブロックのパレット</summary>
    private static NbtList FirstBlockPalette(NbtCompound written)
    {
        NbtCompound section = (NbtCompound)written.GetList("sections")[0];
        return section.GetCompound("block_states").GetList("palette");
    }

    // ------------------------------------------------------------------
    // BlockState
    // ------------------------------------------------------------------

    public class BlockStateTests
    {
        [Fact]
        public void 名前空間を省略すると_minecraft_が補われる()
        {
            BlockState state = BlockState.Parse("stone");
            Assert.Equal("minecraft:stone", state.Name);
            Assert.Empty(state.Properties);
            Assert.Equal("minecraft:stone", state.ToString());
        }

        [Fact]
        public void プロパティは名前の昇順に並ぶ()
        {
            BlockState state = BlockState.Parse("minecraft:oak_stairs[waterlogged=false,facing=north,half=top]");
            Assert.Equal("minecraft:oak_stairs[facing=north,half=top,waterlogged=false]", state.ToString());
        }

        [Fact]
        public void 並び順が違っても同じブロックとして等しい()
        {
            BlockState first = BlockState.Parse("minecraft:oak_stairs[facing=north,half=top]");
            BlockState second = BlockState.Parse("minecraft:oak_stairs[half=top,facing=north]");
            Assert.Equal(first, second);
        }

        [Fact]
        public void 名前が同じでもプロパティが違えば等しくない()
        {
            BlockState first = BlockState.Parse("minecraft:oak_stairs[facing=north]");
            BlockState second = BlockState.Parse("minecraft:oak_stairs[facing=south]");
            Assert.NotEqual(first, second);
        }

        [Fact]
        public void Withで作り直しても元は変わらない()
        {
            BlockState original = BlockState.Parse("minecraft:oak_stairs[facing=north]");
            BlockState changed = original.With("facing", "south");
            Assert.Equal("north", original.Property("facing"));
            Assert.Equal("south", changed.Property("facing"));
        }

        [Fact]
        public void 存在しないプロパティはnull()
        {
            Assert.Null(BlockState.Parse("minecraft:stone").Property("facing"));
        }

        [Fact]
        public void NBTとの相互変換でプロパティが保たれる()
        {
            BlockState state = BlockState.Parse("minecraft:oak_stairs[facing=north,half=top]");
            NbtCompound nbt = (NbtCompound)state.ToNbt();
            Assert.Equal(new[] { "id", "properties" }, nbt.Keys.ToArray());
            Assert.Equal("minecraft:oak_stairs", nbt.GetString("id"));
            Assert.Equal("north", nbt.GetCompound("properties").GetString("facing"));
            Assert.Equal(state, BlockState.FromNbt(nbt));
        }

        [Fact]
        public void プロパティ無しのブロックは文字列になる()
        {
            Assert.Equal(new NbtString("minecraft:air"), BlockState.Parse("minecraft:air").ToNbt());
        }

        [Fact]
        public void 文字列のパレット要素を読める()
        {
            BlockState state = BlockState.FromNbt(new NbtString("minecraft:stone"));
            Assert.Equal("minecraft:stone", state.Name);
            Assert.Empty(state.Properties);
        }

        [Fact]
        public void 包まれたパレット要素を読める()
        {
            BlockState state = BlockState.FromNbt(Wrapped(new NbtString("minecraft:stone")));
            Assert.Equal("minecraft:stone", state.ToString());
        }

        [Fact]
        public void propertiesの無いCompoundも読める()
        {
            NbtCompound entry = new NbtCompound();
            entry.Set("id", new NbtString("minecraft:stone"));
            Assert.Equal("minecraft:stone", BlockState.FromNbt(entry).ToString());
        }

        [Fact]
        public void パレット要素が26_2までの形式ならMALFORMED_DATA()
        {
            NbtCompound entry = new NbtCompound();
            entry.Set("Name", new NbtString("minecraft:stone"));
            SpringNbtException error = Assert.Throws<SpringNbtException>(() => BlockState.FromNbt(entry));
            Assert.Equal(ErrorCode.MalformedData, error.Code);
        }

        [Fact]
        public void 文字列でもCompoundでもない要素はUNEXPECTED_TAG_TYPE()
        {
            SpringNbtException error = Assert.Throws<SpringNbtException>(() => BlockState.FromNbt(new NbtInt(1)));
            Assert.Equal(ErrorCode.UnexpectedTagType, error.Code);
        }

        [Fact]
        public void DataVersion2844ではName_Propertiesを読む()
        {
            NbtCompound properties = new NbtCompound();
            properties.Set("facing", new NbtString("north"));
            NbtCompound entry = new NbtCompound();
            entry.Set("Name", new NbtString("minecraft:oak_stairs"));
            entry.Set("Properties", properties);

            BlockState state = BlockState.FromNbtForDataVersion(entry, 2844);
            Assert.Equal("minecraft:oak_stairs[facing=north]", state.ToString());
        }

        [Fact]
        public void DataVersion2844でidを持つ要素はMALFORMED_DATA()
        {
            NbtCompound entry = new NbtCompound();
            entry.Set("id", new NbtString("minecraft:stone"));
            SpringNbtException error = Assert.Throws<SpringNbtException>(
                () => BlockState.FromNbtForDataVersion(entry, 2844));
            Assert.Equal(ErrorCode.MalformedData, error.Code);
        }

        [Fact]
        public void DataVersion2844で文字列の要素はUNEXPECTED_TAG_TYPE()
        {
            SpringNbtException error = Assert.Throws<SpringNbtException>(
                () => BlockState.FromNbtForDataVersion(new NbtString("minecraft:stone"), 2844));
            Assert.Equal(ErrorCode.UnexpectedTagType, error.Code);
        }

        [Fact]
        public void DataVersion2844でPropertiesの値が文字列でなければUNEXPECTED_TAG_TYPE()
        {
            NbtCompound properties = new NbtCompound();
            properties.Set("facing", new NbtInt(1));
            NbtCompound entry = new NbtCompound();
            entry.Set("Name", new NbtString("minecraft:oak_stairs"));
            entry.Set("Properties", properties);
            SpringNbtException error = Assert.Throws<SpringNbtException>(
                () => BlockState.FromNbtForDataVersion(entry, 2844));
            Assert.Equal(ErrorCode.UnexpectedTagType, error.Code);
        }

        [Fact]
        public void DataVersion2844ではName_Propertiesで書く()
        {
            NbtCompound plain = (NbtCompound)BlockState.Parse("minecraft:stone").ToNbtForDataVersion(2844);
            NbtCompound expected = new NbtCompound();
            expected.Set("Name", new NbtString("minecraft:stone"));
            Assert.Equal(expected, plain);
            Assert.False(plain.ContainsKey("Properties"));

            BlockState stairs = BlockState.Parse("minecraft:oak_stairs[half=top,facing=north]");
            NbtCompound nbt = (NbtCompound)stairs.ToNbtForDataVersion(2844);
            Assert.Equal(new[] { "Name", "Properties" }, nbt.Keys.ToArray());
            Assert.Equal("minecraft:oak_stairs", nbt.GetString("Name"));
            Assert.Equal(new[] { "facing", "half" }, nbt.GetCompound("Properties").Keys.ToArray());
            Assert.Equal(stairs, BlockState.FromNbtForDataVersion(nbt, 2844));
        }

        [Theory]
        [InlineData(5006)]
        [InlineData(5023)]
        public void DataVersion5006以降はFromNbtとToNbtと同じ(int dataVersion)
        {
            BlockState stairs = BlockState.Parse("minecraft:oak_stairs[facing=north,half=top]");
            Assert.Equal(stairs.ToNbt(), stairs.ToNbtForDataVersion(dataVersion));

            BlockState plain = BlockState.Parse("minecraft:stone");
            Assert.Equal(new NbtString("minecraft:stone"), plain.ToNbtForDataVersion(dataVersion));

            Assert.Equal(plain, BlockState.FromNbtForDataVersion(new NbtString("minecraft:stone"), dataVersion));
            Assert.Equal(stairs, BlockState.FromNbtForDataVersion(stairs.ToNbt(), dataVersion));
            NbtCompound wrapper = Wrapped(new NbtString("minecraft:stone"));
            Assert.Equal(BlockState.FromNbt(wrapper), BlockState.FromNbtForDataVersion(wrapper, dataVersion));
        }

        [Fact]
        public void DataVersion1519で境界の形式を扱える()
        {
            BlockState state = BlockState.Parse("minecraft:oak_stairs[facing=north]");
            Assert.Equal(state, BlockState.FromNbtForDataVersion(state.ToNbtForDataVersion(1519), 1519));
        }

        [Fact]
        public void DataVersionが1519未満ならINVALID_ARGUMENT()
        {
            SpringNbtException readError = Assert.Throws<SpringNbtException>(
                () => BlockState.FromNbtForDataVersion(new NbtString("minecraft:stone"), 1518));
            Assert.Equal(ErrorCode.InvalidArgument, readError.Code);

            SpringNbtException writeError = Assert.Throws<SpringNbtException>(
                () => BlockState.Parse("minecraft:stone").ToNbtForDataVersion(1518));
            Assert.Equal(ErrorCode.InvalidArgument, writeError.Code);
        }

        [Theory]
        [InlineData("")]
        [InlineData("minecraft:oak_stairs[facing=north")]
        [InlineData("minecraft:oak_stairs[facing]")]
        [InlineData("minecraft:oak_stairs[facing=north,facing=south]")]
        [InlineData("minecraft:oak_stairs[]extra")]
        public void 壊れた文字列はINVALID_ARGUMENT(string text)
        {
            SpringNbtException error = Assert.Throws<SpringNbtException>(() => BlockState.Parse(text));
            Assert.Equal(ErrorCode.InvalidArgument, error.Code);
        }
    }

    // ------------------------------------------------------------------
    // BitStorage
    // ------------------------------------------------------------------

    public class BitStorageTests
    {
        [Theory]
        [InlineData(4, 4096, 256)]
        [InlineData(5, 4096, 342)]
        [InlineData(1, 64, 1)]
        [InlineData(6, 64, 7)]
        public void 必要なlong数は跨ぎなしで求まる(int bits, int entryCount, int expected)
        {
            Assert.Equal(expected, BitStorage.LongCount(bits, entryCount));
        }

        [Fact]
        public void 書いた値をそのまま読み出せる()
        {
            BitStorage storage = BitStorage.Create(5, 4096);

            // 全エントリに位置由来の値を書いて、取りこぼしが無いか確かめる
            for (int index = 0; index < 4096; index++)
            {
                storage.Set(index, index % 32);
            }

            for (int index = 0; index < 4096; index++)
            {
                Assert.Equal(index % 32, storage.Get(index));
            }
        }

        [Fact]
        public void long境界を跨がずに詰める()
        {
            BitStorage storage = BitStorage.Create(5, 4096);

            // bits=5なら1つのlongに12個
            // 添字12は次のlongの最下位から始まる
            storage.Set(11, 31);
            storage.Set(12, 1);
            long[] longs = storage.ToLongs();

            Assert.Equal(31L << 55, longs[0]);
            Assert.Equal(1L, longs[1]);
        }

        [Fact]
        public void ビット幅を広げても値が保たれる()
        {
            BitStorage storage = BitStorage.Create(4, 4096);

            for (int index = 0; index < 4096; index++)
            {
                storage.Set(index, index % 16);
            }

            BitStorage widened = storage.Resize(5);
            Assert.Equal(5, widened.BitsPerEntry);
            Assert.Equal(342, widened.ToLongs().Length);

            for (int index = 0; index < 4096; index++)
            {
                Assert.Equal(index % 16, widened.Get(index));
            }
        }

        [Fact]
        public void ビット幅に対して長さが合わない配列はMALFORMED_DATA()
        {
            SpringNbtException error = Assert.Throws<SpringNbtException>(
                () => BitStorage.FromLongs(new long[100], 4, 4096));
            Assert.Equal(ErrorCode.MalformedData, error.Code);
        }

        [Fact]
        public void 寛容モードなら長さからビット幅を逆算する()
        {
            // 4096エントリを342 longで表せるのはbits=5のときだけ
            BitStorage storage = BitStorage.FromLongs(new long[342], 4, 4096, lenient: true);
            Assert.Equal(5, storage.BitsPerEntry);
        }

        [Fact]
        public void ビット幅に収まらない値はINVALID_ARGUMENT()
        {
            BitStorage storage = BitStorage.Create(4, 64);
            SpringNbtException error = Assert.Throws<SpringNbtException>(() => storage.Set(0, 16));
            Assert.Equal(ErrorCode.InvalidArgument, error.Code);
        }

        [Fact]
        public void 範囲外の添字はINVALID_ARGUMENT()
        {
            BitStorage storage = BitStorage.Create(4, 64);
            SpringNbtException error = Assert.Throws<SpringNbtException>(() => storage.Get(64));
            Assert.Equal(ErrorCode.InvalidArgument, error.Code);
        }
    }

    // ------------------------------------------------------------------
    // PalettedContainer
    // ------------------------------------------------------------------

    public class PalettedContainerTests
    {
        /// <summary>プロパティの無いブロックのパレット要素を作る
        /// 26.3からはブロックIDだけの文字列で入る</summary>
        private static NbtString BlockEntry(string name)
        {
            return new NbtString(name);
        }

        [Theory]
        [InlineData(1, 0)]
        [InlineData(2, 1)]
        [InlineData(4, 2)]
        [InlineData(5, 3)]
        [InlineData(17, 5)]
        public void 必要ビット数はceil_log2(int count, int expected)
        {
            Assert.Equal(expected, PalettedContainer.CeilLog2(count));
        }

        [Fact]
        public void 単一値のコンテナはdataを持たない()
        {
            PalettedContainer container = PalettedContainer.Filled(BlockEntry("minecraft:air"), 4096, 4);
            Assert.Equal(0, container.BitsPerEntry);

            NbtCompound nbt = container.ToNbt();
            Assert.Null(nbt.OptLongArray("data"));
            Assert.Single(nbt.GetList("palette"));
        }

        [Fact]
        public void 値を足すとパレットとビット幅が広がる()
        {
            PalettedContainer container = PalettedContainer.Filled(BlockEntry("minecraft:air"), 4096, 4);

            // 17種のブロックを足してパレットを18要素にし、bits=4から5への拡張を起こす
            for (int index = 0; index < 17; index++)
            {
                container.Set(index, BlockEntry("minecraft:block_" + index));
            }

            Assert.Equal(18, container.Palette.Count);
            Assert.Equal(5, container.BitsPerEntry);
            Assert.Equal(342, container.ToNbt().GetLongArray("data").Length);
        }

        [Fact]
        public void 書き出しはdataが先でpaletteが後()
        {
            // 実データがこの順なので、無変更で書き戻したときにバイト単位で一致する
            PalettedContainer container = PalettedContainer.Filled(BlockEntry("minecraft:air"), 4096, 4);
            container.Set(0, BlockEntry("minecraft:stone"));

            Assert.Equal(new[] { "data", "palette" }, container.ToNbt().Keys.ToArray());
        }

        [Fact]
        public void compactで未使用のパレット要素が消える()
        {
            PalettedContainer container = PalettedContainer.Filled(BlockEntry("minecraft:air"), 4096, 4);
            container.Set(0, BlockEntry("minecraft:stone"));
            container.Set(0, BlockEntry("minecraft:dirt"));
            Assert.Equal(3, container.Palette.Count);

            container.Compact();

            // 残るのは実際に使われているairとdirtの2つ
            Assert.Equal(2, container.Palette.Count);
            Assert.Equal("minecraft:dirt", ((NbtString)container.Get(0)).Value);
        }

        [Fact]
        public void fillで単一値に戻る()
        {
            PalettedContainer container = PalettedContainer.Filled(BlockEntry("minecraft:air"), 4096, 4);
            container.Set(0, BlockEntry("minecraft:stone"));
            container.Fill(BlockEntry("minecraft:water"));

            Assert.Single(container.Palette);
            Assert.Equal(0, container.BitsPerEntry);
            Assert.Equal("minecraft:water", ((NbtString)container.Get(4095)).Value);
        }

        [Fact]
        public void 文字列だけのパレットは文字列のリストで書く()
        {
            PalettedContainer container = PalettedContainer.Filled(BlockEntry("minecraft:air"), 4096, 4);
            container.Set(0, BlockEntry("minecraft:stone"));

            NbtList palette = container.ToNbt().GetList("palette");
            Assert.Equal(TagType.String, palette.ElementType);
            Assert.Equal(new NbtString("minecraft:stone"), palette[1]);
        }

        [Fact]
        public void 型が混ざったパレットは文字列を包んでCompoundのリストで書く()
        {
            NbtTag stairs = BlockState.Parse("minecraft:oak_stairs[facing=north]").ToNbt();
            PalettedContainer container = PalettedContainer.Filled(BlockEntry("minecraft:air"), 4096, 4);
            container.Set(0, stairs);

            NbtList palette = container.ToNbt().GetList("palette");
            Assert.Equal(TagType.Compound, palette.ElementType);
            Assert.Equal(Wrapped(new NbtString("minecraft:air")), palette[0]);
            Assert.Equal(stairs, palette[1]);
        }

        [Fact]
        public void 包まれたパレットは包みを外して持ち元どおりに書き戻す()
        {
            NbtTag stairs = BlockState.Parse("minecraft:oak_stairs[facing=north]").ToNbt();
            NbtList palette = new NbtList(TagType.Compound);
            palette.Add(Wrapped(new NbtString("minecraft:air")));
            palette.Add(stairs);

            // パレット2要素ならbits=4で256 long
            NbtCompound nbt = new NbtCompound();
            nbt.Set("data", new NbtLongArray(new long[256]));
            nbt.Set("palette", palette);

            PalettedContainer container = PalettedContainer.FromNbt(nbt, 4096, 4);

            // 包みは外れ、要素は文字列とCompoundとして並ぶ
            Assert.Equal(new NbtString("minecraft:air"), container.Palette[0]);
            Assert.Equal(stairs, container.Palette[1]);

            // 書き戻すと、また包まれて元と同じになる
            Assert.Equal(nbt, container.ToNbt());
        }

        [Fact]
        public void compactでCompoundが消えると文字列のリストに戻る()
        {
            NbtTag stairs = BlockState.Parse("minecraft:oak_stairs[facing=north]").ToNbt();
            PalettedContainer container = PalettedContainer.Filled(BlockEntry("minecraft:air"), 4096, 4);
            container.Set(0, stairs);
            container.Set(0, BlockEntry("minecraft:stone"));

            container.Compact();

            NbtList palette = container.ToNbt().GetList("palette");
            Assert.Equal(TagType.String, palette.ElementType);
            Assert.Equal(2, palette.Count);
        }

        [Fact]
        public void 範囲外の添字はINVALID_ARGUMENT()
        {
            PalettedContainer container = PalettedContainer.Filled(BlockEntry("minecraft:air"), 4096, 4);
            SpringNbtException error = Assert.Throws<SpringNbtException>(() => container.Get(4096));
            Assert.Equal(ErrorCode.InvalidArgument, error.Code);
        }
    }

    // ------------------------------------------------------------------
    // Chunk
    // ------------------------------------------------------------------

    public class ChunkTests
    {
        [Fact]
        public void パレット1要素のチャンクを読める()
        {
            Chunk chunk = LoadChunk("palette_1");

            Assert.Equal(SpringNbt.TargetDataVersion, chunk.DataVersion);
            Assert.Equal(0, chunk.X);
            Assert.Equal(0, chunk.Z);
            Assert.Equal(-4, chunk.MinSectionY);
            Assert.True(chunk.IsFullyGenerated);
            Assert.Equal(new[] { -4 }, chunk.SectionYs.ToArray());
            Assert.Equal("minecraft:air", chunk.GetBlock(0, -64, 0)!.Name);
            Assert.Equal("minecraft:plains", chunk.GetBiome(0, -64, 0));
        }

        [Fact]
        public void ビット幅5のチャンクを端から端まで読める()
        {
            Chunk chunk = LoadChunk("palette_17");
            string[] expected = new[]
            {
                "minecraft:air",
                "minecraft:stone",
            };

            // ベクタの添字は (位置 * 11) % 17
            // パレットの先頭2つだけ名前が違う
            for (int position = 0; position < 4096; position++)
            {
                int paletteIndex = (position * 11) % 17;
                int x = position & 15;
                int z = (position >> 4) & 15;
                int y = -64 + (position >> 8);
                BlockState block = chunk.GetBlock(x, y, z)!;

                if (paletteIndex < 2)
                {
                    Assert.Equal(expected[paletteIndex], block.ToString());
                }
                else
                {
                    Assert.Equal("minecraft:stone[variant=v" + (paletteIndex - 2) + "]", block.ToString());
                }
            }
        }

        [Fact]
        public void セクションの無い高さはnull()
        {
            Chunk chunk = LoadChunk("palette_1");
            Assert.Null(chunk.GetBlock(0, 100, 0));
            Assert.Null(chunk.Section(0));
        }

        [Fact]
        public void 生成途中のチャンクはfullではない()
        {
            Chunk chunk = LoadChunk("proto_chunk");
            Assert.Equal("minecraft:structure_starts", chunk.Status);
            Assert.False(chunk.IsFullyGenerated);
        }

        [Fact]
        public void ブロックを置くとその場所だけ変わる()
        {
            Chunk chunk = LoadChunk("palette_1");
            chunk.SetBlock(3, -60, 7, BlockState.Parse("minecraft:oak_stairs[facing=north,half=top]"));

            Assert.Equal("minecraft:oak_stairs[facing=north,half=top]", chunk.GetBlock(3, -60, 7)!.ToString());
            Assert.Equal("minecraft:air", chunk.GetBlock(3, -60, 6)!.Name);
            Assert.Equal("minecraft:air", chunk.GetBlock(4, -60, 7)!.Name);
        }

        [Fact]
        public void ブロックを文字列でも置ける()
        {
            Chunk chunk = LoadChunk("palette_1");
            chunk.SetBlock(3, -60, 7, "minecraft:oak_stairs[facing=north,half=top]");

            Assert.Equal(
                "minecraft:oak_stairs[facing=north,half=top]",
                chunk.GetBlock(3, -60, 7)!.ToString());
        }

        [Fact]
        public void 変更したチャンクには印が付く()
        {
            Chunk chunk = LoadChunk("palette_1");
            Assert.False(chunk.IsModified);

            chunk.SetBlock(3, -60, 7, "minecraft:stone");
            Assert.True(chunk.IsModified);

            // 保存済みとして印を外せる
            chunk.IsModified = false;
            Assert.False(chunk.IsModified);

            // 同じ状態を置き直すだけなら何も起きないので印も付かない
            chunk.SetBlock(3, -60, 7, "minecraft:stone");
            Assert.False(chunk.IsModified);

            chunk.ClearHeightmaps();
            Assert.True(chunk.IsModified);
        }

        [Fact]
        public void バイオームは4ブロック単位で効く()
        {
            Chunk chunk = LoadChunk("palette_1");
            chunk.SetBiome(0, -64, 0, "minecraft:desert");

            // 同じ4×4×4の枠内はまとめて変わる
            Assert.Equal("minecraft:desert", chunk.GetBiome(3, -61, 3));
            Assert.Equal("minecraft:plains", chunk.GetBiome(4, -64, 0));
        }

        [Fact]
        public void compactで未使用のパレット要素が消える()
        {
            Chunk chunk = LoadChunk("palette_unused");
            NbtCompound before = chunk.Section(-4)!.ToNbt();
            Assert.Equal(4, before.GetCompound("block_states").GetList("palette").Count);

            chunk.Compact();

            NbtCompound after = chunk.Section(-4)!.ToNbt();
            Assert.Equal(2, after.GetCompound("block_states").GetList("palette").Count);
        }

        [Fact]
        public void 無変更で書き戻すと元と同じNBTになる()
        {
            NamedTag named = NbtIo.ReadFile(VectorPath("multi_section"));
            byte[] before = NbtIo.WriteBytes(named, new NbtWriteOptions { Compression = Compression.None });

            Chunk chunk = Chunk.FromNbt((NbtCompound)named.Tag);
            NamedTag rebuilt = new NamedTag(named.Name, chunk.ToNbt());
            byte[] after = NbtIo.WriteBytes(rebuilt, new NbtWriteOptions { Compression = Compression.None });

            Assert.Equal(before, after);
        }

        [Fact]
        public void ブロックを置き換えると同じ座標の付随データが消える()
        {
            Chunk chunk = LoadChunk("block_entities");
            NbtCompound before = chunk.Raw;
            Assert.Equal(3, before.GetList("block_entities").Count);
            Assert.Equal(2, before.GetList("block_ticks").Count);
            Assert.Single(before.GetList("fluid_ticks"));

            // (0,-64,0)にはchestとblock_tick、(1,-64,1)にはfurnaceとfluid_tickがある
            chunk.SetBlock(0, -64, 0, BlockState.Parse("minecraft:stone"));
            chunk.SetBlock(1, -64, 1, BlockState.Parse("minecraft:stone"));

            NbtCompound after = chunk.Raw;
            NbtList entities = after.GetList("block_entities");

            // 触っていない(15,-50,15)のbarrelだけが残る
            Assert.Single(entities);
            Assert.Equal("minecraft:barrel", ((NbtCompound)entities[0]).GetString("id"));

            // block_ticksも同様に、対象の座標のものだけ消える
            NbtList ticks = after.GetList("block_ticks");
            Assert.Single(ticks);
            Assert.Equal(15, ((NbtCompound)ticks[0]).GetInt("x"));

            Assert.Empty(after.GetList("fluid_ticks"));
        }

        [Fact]
        public void 同じブロックを置き直しても付随データは消えない()
        {
            Chunk chunk = LoadChunk("block_entities");
            BlockState current = chunk.GetBlock(0, -64, 0)!;

            // 変化が無いなら付随データを触る理由がない
            chunk.SetBlock(0, -64, 0, current);

            Assert.Equal(3, chunk.Raw.GetList("block_entities").Count);
            Assert.Equal(2, chunk.Raw.GetList("block_ticks").Count);
        }

        [Fact]
        public void 別のチャンクの同じ相対座標は消さない()
        {
            // 付随データは絶対座標で持つので、チャンク座標を間違えると無関係な要素を消してしまう
            NamedTag named = NbtIo.ReadFile(VectorPath("block_entities"));
            NbtCompound root = (NbtCompound)named.Tag;
            root.Set("xPos", new NbtInt(1));
            root.Set("zPos", new NbtInt(1));

            Chunk chunk = Chunk.FromNbt(root);
            chunk.SetBlock(0, -64, 0, BlockState.Parse("minecraft:stone"));

            // このチャンクの(0,-64,0)は絶対座標(16,-64,16)
            // どれとも一致しない
            Assert.Equal(3, chunk.Raw.GetList("block_entities").Count);
        }

        [Fact]
        public void 高さマップと光源を無効化できる()
        {
            Chunk chunk = LoadChunk("palette_1");
            chunk.ClearHeightmaps();
            chunk.InvalidateLighting();

            NbtCompound raw = chunk.ToNbt();
            Assert.Null(raw.OptCompound("Heightmaps"));
            Assert.False(raw.GetBool("isLightOn"));
        }

        [Fact]
        public void 添字が範囲外のチャンクはMALFORMED_DATA()
        {
            SpringNbtException error = Assert.Throws<SpringNbtException>(
                () => LoadChunk("palette_index_out_of_range"));
            Assert.Equal(ErrorCode.MalformedData, error.Code);
        }

        [Fact]
        public void data長が合わないチャンクはMALFORMED_DATA()
        {
            SpringNbtException error = Assert.Throws<SpringNbtException>(
                () => LoadChunk("bitstorage_wrong_length"));
            Assert.Equal(ErrorCode.MalformedData, error.Code);
        }

        [Fact]
        public void チャンク内の相対座標が範囲外ならINVALID_ARGUMENT()
        {
            Chunk chunk = LoadChunk("palette_1");
            SpringNbtException error = Assert.Throws<SpringNbtException>(() => chunk.GetBlock(16, -64, 0));
            Assert.Equal(ErrorCode.InvalidArgument, error.Code);
        }
    }

    // ------------------------------------------------------------------
    // DataVersionの扱い
    // ------------------------------------------------------------------

    public class DataVersionTests
    {
        /// <summary>DataVersionだけを、扱える形式の下限より古い値に差し替えたチャンクを作る</summary>
        private static NbtCompound ForeignChunk()
        {
            NamedTag named = NbtIo.ReadFile(VectorPath("palette_1"));
            NbtCompound root = (NbtCompound)named.Tag;
            root.Set("DataVersion", new NbtInt(PreFlatteningDataVersion));
            return root;
        }

        [Fact]
        public void 既定では警告として通す()
        {
            List<string> warnings = new List<string>();
            ChunkReadOptions options = new ChunkReadOptions
            {
                OnVersionMismatch = VersionMismatchAction.Warn,
                OnWarning = message => warnings.Add(message),
            };

            Chunk chunk = Chunk.FromNbt(ForeignChunk(), options);
            Assert.Equal(PreFlatteningDataVersion, chunk.DataVersion);
            Assert.Single(warnings);
        }

        [Fact]
        public void DataVersionが26_2のチャンクは警告を出さずに読める()
        {
            List<string> warnings = new List<string>();
            ChunkReadOptions options = new ChunkReadOptions
            {
                OnVersionMismatch = VersionMismatchAction.Warn,
                OnWarning = message => warnings.Add(message),
            };

            // 26.2の形式も扱う形式に含まれる
            LoadChunk("palette_old_format", options);
            Assert.Empty(warnings);
        }

        [Fact]
        public void 扱える形式の下限は1_18()
        {
            Assert.Equal(2844, SpringNbt.MinSupportedDataVersion);
        }

        [Fact]
        public void Errorを指定すると読み込みで弾く()
        {
            ChunkReadOptions options = new ChunkReadOptions
            {
                OnVersionMismatch = VersionMismatchAction.Error,
            };

            SpringNbtException error = Assert.Throws<SpringNbtException>(
                () => Chunk.FromNbt(ForeignChunk(), options));
            Assert.Equal(ErrorCode.UnsupportedDataVersion, error.Code);
        }

        [Fact]
        public void Ignoreなら何も起きない()
        {
            List<string> warnings = new List<string>();
            ChunkReadOptions options = new ChunkReadOptions
            {
                OnVersionMismatch = VersionMismatchAction.Ignore,
                OnWarning = message => warnings.Add(message),
            };

            Chunk.FromNbt(ForeignChunk(), options);
            Assert.Empty(warnings);
        }

        [Fact]
        public void 別バージョン由来のチャンクは既定で書き戻せない()
        {
            ChunkReadOptions read = new ChunkReadOptions { OnVersionMismatch = VersionMismatchAction.Ignore };
            Chunk chunk = Chunk.FromNbt(ForeignChunk(), read);

            SpringNbtException error = Assert.Throws<SpringNbtException>(() => chunk.ToNbt());
            Assert.Equal(ErrorCode.UnsupportedDataVersion, error.Code);
        }

        [Fact]
        public void 許可すれば古いチャンクも元のバージョンのまま書き戻せる()
        {
            ChunkReadOptions read = new ChunkReadOptions { OnVersionMismatch = VersionMismatchAction.Ignore };
            Chunk chunk = Chunk.FromNbt(ForeignChunk(), read);
            ChunkWriteOptions write = new ChunkWriteOptions { AllowForeignDataVersion = true };

            // DataVersionは読んだ値のまま残す
            Assert.Equal(PreFlatteningDataVersion, chunk.ToNbt(write).GetInt("DataVersion"));
        }

        /// <summary>対象より新しいDataVersionを持つチャンクを作る</summary>
        private static NbtCompound NewerChunk()
        {
            NamedTag named = NbtIo.ReadFile(VectorPath("palette_1"));
            NbtCompound root = (NbtCompound)named.Tag;
            root.SetInt("DataVersion", 5100);
            return root;
        }

        [Fact]
        public void 新しいバージョンのチャンクは警告を出さない()
        {
            List<string> warnings = new List<string>();
            ChunkReadOptions options = new ChunkReadOptions
            {
                OnVersionMismatch = VersionMismatchAction.Warn,
                OnWarning = warnings.Add,
            };

            // 形式が同じであれば、新しいバージョンでも警告を出さずに読める
            Chunk chunk = Chunk.FromNbt(NewerChunk(), options);
            Assert.Equal(5100, chunk.DataVersion);
            Assert.Empty(warnings);
        }

        [Fact]
        public void 新しいバージョンのチャンクはエラー設定でも通る()
        {
            ChunkReadOptions options = new ChunkReadOptions
            {
                OnVersionMismatch = VersionMismatchAction.Error,
            };

            Assert.Equal(5100, Chunk.FromNbt(NewerChunk(), options).DataVersion);
        }

        [Fact]
        public void 新しいバージョンのチャンクはそのまま書き戻せる()
        {
            Chunk chunk = Chunk.FromNbt(NewerChunk());

            // 許可を出さなくても書き戻せて、DataVersionも変わらない
            Assert.Equal(5100, chunk.ToNbt().GetInt("DataVersion"));
        }

        [Fact]
        public void 対象バージョンのチャンクはそのまま書き戻せる()
        {
            Chunk chunk = LoadChunk("palette_1");
            Assert.Equal(SpringNbt.TargetDataVersion, chunk.ToNbt().GetInt("DataVersion"));
        }
    }

    // ------------------------------------------------------------------
    // チャンクの形式の世代
    // ------------------------------------------------------------------

    public class ChunkFormatTests
    {
        [Fact]
        public void DataVersion4903のチャンクを読み無変更で書き戻すと元と同じになる()
        {
            NbtCompound tag = (NbtCompound)NbtIo.ReadFile(VectorPath("v4903_edit")).Tag;
            byte[] before = ChunkBytes(tag);
            Chunk chunk = Chunk.FromNbt(tag);

            // ベクタの添字は (位置 * 7) % 5
            Assert.Equal(4903, chunk.DataVersion);
            Assert.Equal("minecraft:air", chunk.GetBlock(0, -64, 0)!.ToString());
            Assert.Equal("minecraft:dirt", chunk.GetBlock(1, -64, 0)!.ToString());
            Assert.Equal("minecraft:oak_stairs[facing=west,half=top]", chunk.GetBlock(2, -64, 0)!.ToString());
            Assert.Equal("minecraft:stone", chunk.GetBlock(3, -64, 0)!.ToString());
            Assert.Equal("minecraft:oak_stairs[facing=east,half=bottom]", chunk.GetBlock(4, -64, 0)!.ToString());
            Assert.Equal("minecraft:plains", chunk.GetBiome(0, -64, 0));

            Assert.Equal(before, ChunkBytes(chunk.ToNbt()));
        }

        [Fact]
        public void DataVersion4903のチャンクに置いたブロックはName_Propertiesで入る()
        {
            Chunk chunk = LoadChunk("v4903_edit");
            chunk.SetBlock(5, -64, 5, BlockState.Parse("minecraft:oak_stairs[facing=north]"));
            NbtCompound written = chunk.ToNbt();

            // パレットの末尾に26.2の形式で足される
            NbtList palette = FirstBlockPalette(written);
            Assert.Equal(NameProperties("minecraft:oak_stairs", ("facing", "north")), palette[palette.Count - 1]);

            // DataVersionは読んだ値のまま
            Assert.Equal(4903, written.GetInt("DataVersion"));

            // 読み直しても同じ状態が返る
            Chunk reread = Chunk.FromNbt(written);
            Assert.Equal("minecraft:oak_stairs[facing=north]", reread.GetBlock(5, -64, 5)!.ToString());
        }

        [Fact]
        public void 形式の違うチャンクはそれぞれ読んだ形式で書き出す()
        {
            Chunk older = LoadChunk("v4903_edit");
            Chunk newer = LoadChunk("palette_5");

            // 2つのチャンクに同じ手順で同じブロックを置く
            foreach (Chunk chunk in new[] { older, newer })
            {
                chunk.SetBlock(5, -64, 5, BlockState.Parse("minecraft:oak_stairs[facing=north]"));
                chunk.SetBlock(6, -64, 6, BlockState.Parse("minecraft:edited_plain"));
            }

            NbtCompound olderWritten = older.ToNbt();
            NbtList olderPalette = FirstBlockPalette(olderWritten);
            Assert.Equal(
                NameProperties("minecraft:oak_stairs", ("facing", "north")), olderPalette[olderPalette.Count - 2]);
            Assert.Equal(NameProperties("minecraft:edited_plain"), olderPalette[olderPalette.Count - 1]);
            Assert.Equal(4903, olderWritten.GetInt("DataVersion"));

            NbtCompound newerWritten = newer.ToNbt();
            NbtList newerPalette = FirstBlockPalette(newerWritten);

            // 型の混ざったパレットはCompoundのリストになり、文字列の要素だけが包まれる
            Assert.Equal(
                IdProperties("minecraft:oak_stairs", ("facing", "north")), newerPalette[newerPalette.Count - 2]);
            Assert.Equal(
                Wrapped(new NbtString("minecraft:edited_plain")), newerPalette[newerPalette.Count - 1]);
            Assert.Equal(SpringNbt.TargetDataVersion, newerWritten.GetInt("DataVersion"));
        }

        [Fact]
        public void 指定した世代とLevelの有無が食い違えばMALFORMED_DATA()
        {
            ChunkReadOptions options = new ChunkReadOptions
            {
                OnVersionMismatch = VersionMismatchAction.Ignore,
                FormatDataVersion = 5023,
            };

            // Levelを持つチャンクを、Levelの無い世代で読ませる
            SpringNbtException error = Assert.Throws<SpringNbtException>(
                () => Chunk.FromNbt(LevelChunk(2586), options));
            Assert.Equal(ErrorCode.MalformedData, error.Code);
        }

        [Fact]
        public void 世代を指定しても下限より古いチャンクは書き戻せない()
        {
            ChunkReadOptions options = new ChunkReadOptions
            {
                OnVersionMismatch = VersionMismatchAction.Ignore,
                FormatDataVersion = 5023,
            };
            Chunk chunk = Chunk.FromNbt(PreFlatteningChunk(), options);

            SpringNbtException error = Assert.Throws<SpringNbtException>(() => chunk.ToNbt());
            Assert.Equal(ErrorCode.UnsupportedDataVersion, error.Code);
        }

        [Fact]
        public void 世代に1519未満を指定するとINVALID_ARGUMENT()
        {
            ChunkReadOptions options = new ChunkReadOptions { FormatDataVersion = 1518 };

            SpringNbtException error = Assert.Throws<SpringNbtException>(
                () => LoadChunk("palette_1", options));
            Assert.Equal(ErrorCode.InvalidArgument, error.Code);
        }

        [Fact]
        public void DataVersionが1519未満のチャンクは元のNBTだけを持つ()
        {
            NbtCompound root = PreFlatteningChunk();
            byte[] before = ChunkBytes(root);
            ChunkReadOptions options = new ChunkReadOptions { OnVersionMismatch = VersionMismatchAction.Ignore };
            Chunk chunk = Chunk.FromNbt(root, options);

            // 座標はLevelの中から読み、セクションは解釈しない
            Assert.Equal(3, chunk.X);
            Assert.Equal(-2, chunk.Z);
            Assert.Empty(chunk.SectionYs);

            // ブロック・バイオーム・高さマップ・光源の操作はどれも受け付けない
            Action[] operations =
            {
                () => chunk.GetBlock(0, 0, 0),
                () => chunk.SetBlock(0, 0, 0, "minecraft:stone"),
                () => chunk.GetBiome(0, 0, 0),
                () => chunk.SetBiome(0, 0, 0, "minecraft:plains"),
                () => chunk.ClearHeightmaps(),
                () => chunk.InvalidateLighting(),
            };

            // 操作ごとにUnsupportedDataVersionになることを確かめる
            foreach (Action operation in operations)
            {
                SpringNbtException error = Assert.Throws<SpringNbtException>(operation);
                Assert.Equal(ErrorCode.UnsupportedDataVersion, error.Code);
            }

            // 許可すれば、読んだNBTがそのまま返る
            ChunkWriteOptions write = new ChunkWriteOptions { AllowForeignDataVersion = true };
            Assert.Equal(before, ChunkBytes(chunk.ToNbt(write)));
        }

        [Fact]
        public void 世代を選んだDataVersionを返す()
        {
            NbtCompound tag = (NbtCompound)NbtIo.ReadFile(VectorPath("v4903_edit")).Tag;
            Assert.Equal(4903, Chunk.FromNbt(tag).FormatDataVersion);

            // 指定すれば、チャンク自身のDataVersionではなくその値になる
            Chunk chunk = Chunk.FromNbt(tag, new ChunkReadOptions { FormatDataVersion = 5023 });
            Assert.Equal(5023, chunk.FormatDataVersion);
            Assert.Equal(4903, chunk.DataVersion);
        }
    }

    // ------------------------------------------------------------------
    // MinecraftWorld
    // ------------------------------------------------------------------

    public class MinecraftWorldTests
    {
        [Fact]
        public void 存在しないディレクトリはIO()
        {
            string missing = Path.Combine(Path.GetTempPath(), "springnbt-missing-" + Guid.NewGuid().ToString("N"));
            SpringNbtException error = Assert.Throws<SpringNbtException>(() => MinecraftWorld.Open(missing));
            Assert.Equal(ErrorCode.Io, error.Code);
        }

        [Fact]
        public void levelDatが無いディレクトリはIO()
        {
            string empty = Path.Combine(Path.GetTempPath(), "springnbt-empty-" + Guid.NewGuid().ToString("N"));
            System.IO.Directory.CreateDirectory(empty);

            try
            {
                SpringNbtException error = Assert.Throws<SpringNbtException>(() => MinecraftWorld.Open(empty));
                Assert.Equal(ErrorCode.Io, error.Code);
            }
            finally
            {
                System.IO.Directory.Delete(empty, recursive: true);
            }
        }

        [Fact]
        public void 次元経由で読んだチャンクの警告も通知先へ届く()
        {
            string root = Path.Combine(Path.GetTempPath(), "springnbt-warn-" + Guid.NewGuid().ToString("N"));
            string region = Path.Combine(root, "dimensions", "minecraft", "overworld", "region");
            System.IO.Directory.CreateDirectory(region);

            try
            {
                // DataVersionが扱える形式より古いチャンクを1つだけ持つワールドを作る
                NbtCompound level = new NbtCompound();
                level.Set("Data", new NbtCompound());
                NbtIo.WriteFile(Path.Combine(root, "level.dat"), new NamedTag("", level));

                NbtCompound chunk = (NbtCompound)NbtIo.ReadFile(VectorPath("palette_1")).Tag;
                chunk.Set("DataVersion", new NbtInt(PreFlatteningDataVersion));

                using (RegionFile file = RegionFile.Open(Path.Combine(region, "r.0.0.mca"), RegionFileMode.ReadWrite))
                {
                    file.WriteChunk(0, 0, chunk);
                }

                List<string> warnings = new List<string>();
                WorldOpenOptions options = new WorldOpenOptions
                {
                    ChunkRead = new ChunkReadOptions { OnWarning = message => warnings.Add(message) },
                };

                using (MinecraftWorld world = MinecraftWorld.Open(root, options))
                {
                    Assert.NotNull(world.Dimension(Dimension.Overworld)!.Chunk(0, 0));
                }

                // ワールドを開くときに渡した通知先が、次元経由の読み込みでも呼ばれる
                Assert.Single(warnings);
            }
            finally
            {
                System.IO.Directory.Delete(root, recursive: true);
            }
        }
    }
}

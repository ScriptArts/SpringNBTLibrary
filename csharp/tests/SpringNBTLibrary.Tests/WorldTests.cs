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
        public void またぐ詰め方で長さが合う()
        {
            Assert.Equal(320, BitStorage.LongCount(5, 4096, true));
            Assert.Equal(256, BitStorage.LongCount(4, 4096, true));
        }

        [Fact]
        public void またぐ詰め方では値が64bitの境目をまたいで並ぶ()
        {
            BitStorage storage = BitStorage.Create(5, 4096, true);

            // 添字12はビット60から64までなので、data[0]の上位4bitとdata[1]の最下位bitに分かれる
            storage.Set(12, 0b10111);
            long[] longs = storage.ToLongs();

            Assert.Equal(0b0111L, (long)((ulong)longs[0] >> 60) & 0b1111L);
            Assert.Equal(1L, longs[1] & 1L);
            Assert.Equal(0b10111, storage.Get(12));
        }

        [Fact]
        public void またぐ詰め方で境目の値を上書きしても隣が壊れない()
        {
            BitStorage storage = BitStorage.Create(5, 4096, true);
            storage.Set(11, 0b11111);
            storage.Set(13, 0b11111);

            // 添字12は境目をまたぐので、書き込みのたびに両隣が保たれるか確かめる
            foreach (int value in new[] { 0b11111, 0b00000, 0b10101 })
            {
                storage.Set(12, value);
                Assert.Equal(value, storage.Get(12));
                Assert.Equal(0b11111, storage.Get(11));
                Assert.Equal(0b11111, storage.Get(13));
            }
        }

        [Fact]
        public void またぐ詰め方で最後のlongの末尾まで読み書きできる()
        {
            BitStorage storage = BitStorage.Create(5, 4096, true);
            storage.Set(4094, 0b10101);
            storage.Set(4095, 0b11011);

            // 添字4095はビット20475から20479で、最後のlongのビット59から63に収まる
            Assert.Equal(0b10101, storage.Get(4094));
            Assert.Equal(0b11011, storage.Get(4095));
            Assert.Equal(0b11011UL, (ulong)storage.ToLongs()[319] >> 59);
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
        public void またぐ詰め方のコンテナは17種類目でビット幅が5になる()
        {
            List<NbtTag> palette = new List<NbtTag>();

            for (int index = 0; index < 16; index++)
            {
                palette.Add(BlockEntry("minecraft:block_" + index));
            }

            PalettedContainer container = PalettedContainer.FromParts(
                palette, new long[256], 4096, 4, true, false, false);
            Assert.Equal(4, container.BitsPerEntry);

            // 全エントリに位置由来の値を書いてから、17種類目を1つ足す
            for (int index = 0; index < 4096; index++)
            {
                container.Set(index, BlockEntry("minecraft:block_" + (index % 16)));
            }

            container.Set(7, BlockEntry("minecraft:block_16"));
            Assert.Equal(5, container.BitsPerEntry);
            Assert.Equal(320, container.ToParts().Data!.Length);

            for (int index = 0; index < 4096; index++)
            {
                string expected = "minecraft:block_" + (index % 16);

                if (index == 7)
                {
                    expected = "minecraft:block_16";
                }

                Assert.Equal(new NbtString(expected), container.Get(index));
            }
        }

        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public void dataが必ず書かれる形式なら1要素のパレットでもビット幅4のdataを返す(bool spanning)
        {
            PalettedContainer container = PalettedContainer.FromParts(
                new List<NbtTag> { BlockEntry("minecraft:air") }, new long[256], 4096, 4, spanning, true, false);

            (List<NbtTag> palette, long[]? data) = container.ToParts();
            Assert.Single(palette);
            Assert.NotNull(data);
            Assert.Equal(new long[256], data);
        }

        [Theory]
        [InlineData(false)]
        [InlineData(true)]
        public void dataが必ず書かれる形式でdataが無ければMALFORMED_DATA(bool spanning)
        {
            SpringNbtException error = Assert.Throws<SpringNbtException>(
                () => PalettedContainer.FromParts(
                    new List<NbtTag> { BlockEntry("minecraft:air") }, null, 4096, 4, spanning, true, false));
            Assert.Equal(ErrorCode.MalformedData, error.Code);
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
        public void 扱える形式の下限は1_13()
        {
            Assert.Equal(1519, SpringNbt.MinSupportedDataVersion);

            List<string> warnings = new List<string>();
            ChunkReadOptions options = new ChunkReadOptions
            {
                OnVersionMismatch = VersionMismatchAction.Warn,
                OnWarning = message => warnings.Add(message),
            };

            // 1.13の正式版より1つ古いチャンクは、読み込みで警告になる
            NbtCompound root = PreFlatteningChunk();
            root.SetInt("DataVersion", 1518);
            Chunk.FromNbt(root, options);
            Assert.Single(warnings);

            // 1.13の正式版のチャンクは警告を出さない
            Chunk.FromNbt(LevelChunk(1519), options);
            Assert.Single(warnings);
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
                () => chunk.GetBiomeId(0, 0, 0),
                () => chunk.SetBiomeId(0, 0, 0, 1),
                () => chunk.ClearHeightmaps(),
                () => chunk.InvalidateLighting(),
                () => _ = chunk.MinSectionY,
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

        [Fact]
        public void C5の世代で26_2のチャンクを読むとブロックの取得でMALFORMED_DATA()
        {
            Chunk chunk = LoadChunk("v4903_edit", new ChunkReadOptions { FormatDataVersion = 5023 });

            // パレットの要素がName / Propertiesなので、26.3の形式としては読めない
            SpringNbtException error = Assert.Throws<SpringNbtException>(() => chunk.GetBlock(0, -64, 0));
            Assert.Equal(ErrorCode.MalformedData, error.Code);
        }

        [Fact]
        public void ルートの直下にsectionsがあるチャンクを1_16の世代で読むとMALFORMED_DATA()
        {
            ChunkReadOptions options = new ChunkReadOptions { FormatDataVersion = 2586 };

            // Levelの無いチャンクを、Levelに本体を包む世代で読ませる
            SpringNbtException error = Assert.Throws<SpringNbtException>(() => LoadChunk("palette_1", options));
            Assert.Equal(ErrorCode.MalformedData, error.Code);
        }

        [Fact]
        public void 名前空間の無いfullも生成済みとみなす()
        {
            NbtCompound root = (NbtCompound)NbtIo.ReadFile(VectorPath("v4903_edit")).Tag;
            root.SetString("Status", "full");
            Chunk chunk = Chunk.FromNbt(root);

            Assert.Equal("full", chunk.Status);
            Assert.True(chunk.IsFullyGenerated);
        }
    }

    /// <summary>1.16.5の形式のテストベクタのLevel.Biomesの値</summary>
    private static int LevelBiome(int index) => ((index * 3) % 11) + 1;

    /// <summary>1.16.5の形式のテストベクタをNBTのまま読む</summary>
    private static NbtCompound LevelVector() => (NbtCompound)NbtIo.ReadFile(VectorPath("v2586_level")).Tag;

    /// <summary>Level.SectionsからY位置の合うセクションを探す</summary>
    private static NbtCompound LevelSection(NbtCompound root, int sectionY)
    {
        // Yが一致する要素を返す
        foreach (NbtTag entry in root.GetCompound("Level").GetList("Sections"))
        {
            NbtCompound section = (NbtCompound)entry;

            // Yの合うセクションだけを対象にする
            if (section.GetByte("Y") == sectionY)
            {
                return section;
            }
        }

        throw new InvalidOperationException("Y=" + sectionY + " のセクションが無い");
    }

    /// <summary>付随データの要素の座標を並べる</summary>
    private static List<(int X, int Y, int Z)> Positions(NbtList values)
    {
        List<(int X, int Y, int Z)> result = new List<(int X, int Y, int Z)>();

        // 要素ごとに絶対座標を取り出す
        foreach (NbtTag entry in values)
        {
            NbtCompound compound = (NbtCompound)entry;
            result.Add((compound.GetInt("x"), compound.GetInt("y"), compound.GetInt("z")));
        }

        return result;
    }

    // ------------------------------------------------------------------
    // 1.16〜1.17の形式（本体がLevelの中）のチャンク
    // ------------------------------------------------------------------

    public class LevelChunkTests
    {
        [Fact]
        public void DataVersion2586のチャンクを読み無変更で書き戻すと元と同じになる()
        {
            NbtCompound root = LevelVector();
            byte[] before = ChunkBytes(root);
            Chunk chunk = Chunk.FromNbt(root);

            Assert.Equal(2586, chunk.DataVersion);
            Assert.Equal(2, chunk.X);
            Assert.Equal(-1, chunk.Z);
            Assert.Equal(0, chunk.MinSectionY);
            Assert.Equal("full", chunk.Status);
            Assert.True(chunk.IsFullyGenerated);
            Assert.Equal(new[] { -1, 0, 1 }, chunk.SectionYs);

            // ベクタの添字は (位置 * 7) % 5
            Assert.Equal("minecraft:air", chunk.GetBlock(0, 0, 0)!.ToString());
            Assert.Equal("minecraft:dirt", chunk.GetBlock(1, 0, 0)!.ToString());
            Assert.Equal("minecraft:oak_stairs[facing=west,half=top]", chunk.GetBlock(2, 0, 0)!.ToString());
            Assert.Equal("minecraft:stone", chunk.GetBlock(3, 0, 0)!.ToString());
            Assert.Equal("minecraft:oak_stairs[facing=east,half=bottom]", chunk.GetBlock(4, 0, 0)!.ToString());
            Assert.Equal("minecraft:air", chunk.GetBlock(15, 31, 15)!.ToString());

            // Paletteの無いセクションと、セクションの無い高さはブロックを持たない
            Assert.False(chunk.Section(-1)!.HasBlockStates);
            Assert.Null(chunk.GetBlock(0, -1, 0));
            Assert.Null(chunk.GetBlock(0, 32, 0));

            Assert.Equal(before, ChunkBytes(chunk.ToNbt()));
        }

        [Fact]
        public void DataVersion2586のチャンクでブロックを置くとLevelの付随データが消える()
        {
            Chunk chunk = Chunk.FromNbt(LevelVector());

            // 絶対座標はx = 32 + 相対x、z = -16 + 相対z
            chunk.SetBlock(0, 0, 0, "minecraft:stone");
            chunk.SetBlock(1, 0, 1, "minecraft:stone");
            chunk.SetBlock(2, 2, 2, "minecraft:oak_stairs[facing=north]");
            NbtCompound written = chunk.ToNbt();
            NbtCompound level = written.GetCompound("Level");

            Assert.Equal(new[] { (47, 20, -1) }, Positions(level.GetList("TileEntities")));
            Assert.Empty(level.GetList("TileTicks"));
            Assert.Equal(new[] { (40, 5, -10) }, Positions(level.GetList("LiquidTicks")));

            // ルートには付随データのキーを作らない
            Assert.False(written.ContainsKey("block_entities"));
            Assert.False(written.ContainsKey("TileEntities"));

            // パレットの末尾にName / Propertiesの形式で足され、BlockStatesも書き直される
            NbtCompound section = LevelSection(written, 0);
            NbtList palette = section.GetList("Palette");
            Assert.Equal(NameProperties("minecraft:oak_stairs", ("facing", "north")), palette[palette.Count - 1]);
            Assert.Equal(256, section.GetLongArray("BlockStates").Length);
            Assert.Equal(2586, written.GetInt("DataVersion"));

            // 読み直しても同じ状態が返る
            Chunk reread = Chunk.FromNbt(written);
            Assert.Equal("minecraft:oak_stairs[facing=north]", reread.GetBlock(2, 2, 2)!.ToString());
            Assert.Equal("minecraft:stone", reread.GetBlock(0, 0, 0)!.ToString());
        }

        [Fact]
        public void DataVersion2586のチャンクのバイオームIDを読み書きできる()
        {
            Chunk chunk = Chunk.FromNbt(LevelVector());

            Assert.Equal(LevelBiome(0), chunk.GetBiomeId(0, 0, 0));
            Assert.Equal(LevelBiome((17 * 16) + (2 * 4) + 1), chunk.GetBiomeId(5, 70, 9));
            Assert.Equal(LevelBiome(1023), chunk.GetBiomeId(15, 255, 15));

            // 高さ0..255の外は値を持たない
            Assert.Null(chunk.GetBiomeId(0, -1, 0));
            Assert.Null(chunk.GetBiomeId(0, 256, 0));

            chunk.SetBiomeId(5, 70, 9, 42);
            Assert.True(chunk.IsModified);
            Assert.Equal(42, chunk.GetBiomeId(4, 68, 8));

            NbtCompound written = chunk.ToNbt();
            Assert.Equal(42, written.GetCompound("Level").GetIntArray("Biomes")[(17 * 16) + (2 * 4) + 1]);
        }

        [Theory]
        [InlineData(-1)]
        [InlineData(256)]
        public void 高さ0から255の外へバイオームIDを書くとINVALID_ARGUMENT(int y)
        {
            Chunk chunk = Chunk.FromNbt(LevelVector());

            SpringNbtException error = Assert.Throws<SpringNbtException>(() => chunk.SetBiomeId(0, y, 0, 1));
            Assert.Equal(ErrorCode.InvalidArgument, error.Code);
        }

        [Theory]
        [InlineData("absent")]
        [InlineData("int0")]
        [InlineData("int256")]
        [InlineData("byte256")]
        public void Biomesを読めないチャンクのバイオームIDはnullで書き込めない(string kind)
        {
            NbtCompound root = LevelVector();
            NbtCompound level = root.GetCompound("Level");
            level.Remove("Biomes");

            // 種類ごとに、読めない形のBiomesを置く
            if (kind == "int0")
            {
                level.Set("Biomes", new NbtIntArray(new int[0]));
            }
            else if (kind == "int256")
            {
                level.Set("Biomes", new NbtIntArray(Enumerable.Repeat(1, 256).ToArray()));
            }
            else if (kind == "byte256")
            {
                level.Set("Biomes", new NbtByteArray(Enumerable.Repeat((sbyte)1, 256).ToArray()));
            }

            byte[] before = ChunkBytes(root);
            Chunk chunk = Chunk.FromNbt(root);
            Assert.Null(chunk.GetBiomeId(0, 0, 0));

            SpringNbtException error = Assert.Throws<SpringNbtException>(() => chunk.SetBiomeId(0, 0, 0, 1));
            Assert.Equal(ErrorCode.InvalidArgument, error.Code);

            // 元のNBTはそのまま残る
            Assert.Equal(before, ChunkBytes(chunk.ToNbt()));
        }

        [Fact]
        public void DataVersion2586のチャンクではバイオーム名のAPIはUNSUPPORTED_FEATURE()
        {
            Chunk chunk = Chunk.FromNbt(LevelVector());

            // セクションの無い高さでも、形式で決まるので同じエラーになる
            Action[] operations =
            {
                () => chunk.GetBiome(0, 0, 0),
                () => chunk.GetBiome(0, 200, 0),
                () => chunk.SetBiome(0, 0, 0, "minecraft:plains"),
            };

            // 操作ごとにUnsupportedFeatureになることを確かめる
            foreach (Action operation in operations)
            {
                SpringNbtException error = Assert.Throws<SpringNbtException>(operation);
                Assert.Equal(ErrorCode.UnsupportedFeature, error.Code);
            }
        }

        [Theory]
        [InlineData("palette_1")]
        [InlineData("v4903_edit")]
        public void バイオームIDのAPIは1_18以降のチャンクではUNSUPPORTED_FEATURE(string name)
        {
            Chunk chunk = LoadChunk(name);

            SpringNbtException error = Assert.Throws<SpringNbtException>(() => chunk.GetBiomeId(0, 0, 0));
            Assert.Equal(ErrorCode.UnsupportedFeature, error.Code);

            error = Assert.Throws<SpringNbtException>(() => chunk.SetBiomeId(0, 0, 0, 1));
            Assert.Equal(ErrorCode.UnsupportedFeature, error.Code);
        }

        [Fact]
        public void DataVersion2586のチャンクの高さマップと光源を無効化できる()
        {
            Chunk chunk = Chunk.FromNbt(LevelVector());
            chunk.ClearHeightmaps();
            chunk.InvalidateLighting();
            NbtCompound written = chunk.ToNbt();
            NbtCompound level = written.GetCompound("Level");

            Assert.Null(level.OptCompound("Heightmaps"));
            Assert.Equal(0, level.GetByte("isLightOn"));

            // ルートには作らない
            Assert.False(written.ContainsKey("isLightOn"));
        }

        [Fact]
        public void isLightOnの無いDataVersion2586のチャンクは光源を無効化できない()
        {
            NbtCompound root = LevelVector();
            root.GetCompound("Level").Remove("isLightOn");
            byte[] before = ChunkBytes(root);
            Chunk chunk = Chunk.FromNbt(root);

            SpringNbtException error = Assert.Throws<SpringNbtException>(() => chunk.InvalidateLighting());
            Assert.Equal(ErrorCode.UnsupportedFeature, error.Code);
            Assert.Equal(before, ChunkBytes(chunk.ToNbt()));
        }

        [Fact]
        public void 生成途中のDataVersion2586のチャンクは生成済みではない()
        {
            NbtCompound root = LevelVector();
            root.GetCompound("Level").SetString("Status", "structure_starts");

            Assert.False(Chunk.FromNbt(root).IsFullyGenerated);
        }

        [Theory]
        [InlineData("BlockStates")]
        [InlineData("Palette")]
        public void PaletteとBlockStatesの片方しか無いセクションはブロックを持たない(string key)
        {
            NbtCompound root = LevelVector();
            LevelSection(root, 1).Remove(key);
            byte[] before = ChunkBytes(root);
            Chunk chunk = Chunk.FromNbt(root);

            // Minecraftも両方がそろったセクションだけを読むので、ブロックの無いセクションとして扱う
            Assert.False(chunk.Section(1)!.HasBlockStates);
            Assert.Null(chunk.GetBlock(0, 16, 0));

            SpringNbtException error = Assert.Throws<SpringNbtException>(
                () => chunk.SetBlock(0, 16, 0, "minecraft:stone"));
            Assert.Equal(ErrorCode.InvalidArgument, error.Code);

            // 元のNBTはそのまま残る
            Assert.Equal(before, ChunkBytes(chunk.ToNbt()));
        }

        [Fact]
        public void Properties_Nameの並びの要素と同じ状態を置いてもパレットは増えない()
        {
            NbtCompound root = LevelVector();
            List<NbtTag> paletteBefore = LevelSection(root, 0).GetList("Palette").Select(entry => entry.Copy()).ToList();
            Chunk chunk = Chunk.FromNbt(root);

            // 実データと同じくProperties -> Nameの並びで入っている状態を、プロパティの並びを変えて置く
            chunk.SetBlock(0, 0, 0, "minecraft:oak_stairs[half=bottom,facing=east]");
            NbtCompound written = chunk.ToNbt();

            // 同じ状態の要素を使い回すので、パレットは元のまま
            Assert.Equal(paletteBefore, LevelSection(written, 0).GetList("Palette").ToList());
            Chunk reread = Chunk.FromNbt(written);
            Assert.Equal("minecraft:oak_stairs[facing=east,half=bottom]", reread.GetBlock(0, 0, 0)!.ToString());
        }

        [Fact]
        public void Paletteの要素がCompoundでなければUNEXPECTED_TAG_TYPE()
        {
            NbtCompound root = LevelVector();
            NbtList palette = new NbtList(TagType.String);
            palette.Add(new NbtString("minecraft:air"));
            LevelSection(root, 1).Set("Palette", palette);

            SpringNbtException error = Assert.Throws<SpringNbtException>(() => Chunk.FromNbt(root));
            Assert.Equal(ErrorCode.UnexpectedTagType, error.Code);
        }
    }

    /// <summary>1.15.2の形式のテストベクタの0段目のパレットを、ブロック状態の文字列表現で並べたもの</summary>
    private static List<string> SpanningStates()
    {
        List<string> states = new List<string> { "minecraft:air", "minecraft:stone" };

        // 階段は下半分の4方向、上半分の4方向の順に並ぶ
        foreach (string half in new[] { "bottom", "top" })
        {
            // 向きは名前の順に並ぶ
            foreach (string facing in new[] { "east", "north", "south", "west" })
            {
                states.Add($"minecraft:oak_stairs[facing={facing},half={half}]");
            }
        }

        // プロパティの無いブロックを後ろに並べる
        foreach (string name in new[] { "dirt", "gravel", "sand", "bedrock", "cobblestone", "oak_planks", "glass" })
        {
            states.Add("minecraft:" + name);
        }

        return states;
    }

    /// <summary>1.15.2の形式のテストベクタのLevel.Biomesの値</summary>
    private static int SpanningBiome(int index) => ((index * 5) % 13) + 1;

    /// <summary>1.14.4の形式のテストベクタのLevel.Biomesの値</summary>
    private static int Biome2D(int index) => ((index * 7) % 61) + 1;

    /// <summary>1.16.5と1.14.4の形式のテストベクタの0段目のパレットを、ブロック状態の文字列表現で並べたもの</summary>
    private static readonly string[] LevelStates =
    {
        "minecraft:air",
        "minecraft:stone",
        "minecraft:dirt",
        "minecraft:oak_stairs[facing=east,half=bottom]",
        "minecraft:oak_stairs[facing=west,half=top]",
    };

    /// <summary>1.15.2の形式のテストベクタをNBTのまま読む</summary>
    private static NbtCompound SpanningVector() => (NbtCompound)NbtIo.ReadFile(VectorPath("v2230_spanning")).Tag;

    /// <summary>1.14.4の形式のテストベクタをNBTのまま読む</summary>
    private static NbtCompound Biomes2DVector() => (NbtCompound)NbtIo.ReadFile(VectorPath("v1976_biomes_2d")).Tag;

    /// <summary>DataVersionを持たないチャンクを作る</summary>
    private static NbtCompound ChunkWithoutDataVersion()
    {
        NbtCompound root = PreFlatteningChunk();
        root.Remove("DataVersion");
        return root;
    }

    // ------------------------------------------------------------------
    // 1.13〜1.15の形式（ビット詰めが64bitの境目をまたぐ）のチャンク
    // ------------------------------------------------------------------

    public class LegacyChunkTests
    {
        [Fact]
        public void DataVersion2230のまたぐ詰め方のチャンクを読み無変更で書き戻すと元と同じになる()
        {
            NbtCompound root = SpanningVector();
            byte[] before = ChunkBytes(root);
            Chunk chunk = Chunk.FromNbt(root);
            List<string> states = SpanningStates();

            Assert.Equal(2230, chunk.DataVersion);
            Assert.Equal(-3, chunk.X);
            Assert.Equal(5, chunk.Z);
            Assert.Equal(0, chunk.MinSectionY);
            Assert.True(chunk.IsFullyGenerated);
            Assert.Equal(new[] { -1, 0, 1 }, chunk.SectionYs);
            Assert.Equal(17, chunk.Section(0)!.BlockStates!.Palette.Count);
            Assert.Equal(5, chunk.Section(0)!.BlockStates!.BitsPerEntry);

            // ベクタの添字は (位置 * 7) % 17
            // ビット幅5なので、位置12や25の値は64bitの境目をまたぐ
            Assert.Equal(states[(12 * 7) % 17], chunk.GetBlock(12, 0, 0)!.ToString());
            Assert.Equal(states[(25 * 7) % 17], chunk.GetBlock(9, 0, 1)!.ToString());

            // 全ブロックが元の添字どおりに読める
            for (int position = 0; position < 4096; position++)
            {
                BlockState? block = chunk.GetBlock(position & 15, position >> 8, (position >> 4) & 15);
                Assert.Equal(states[(position * 7) % 17], block!.ToString());
            }

            Assert.Equal("minecraft:air", chunk.GetBlock(15, 31, 15)!.ToString());
            Assert.Null(chunk.GetBlock(0, -1, 0));

            Assert.Equal(before, ChunkBytes(chunk.ToNbt()));
        }

        [Fact]
        public void DataVersion2230のチャンクでパレットが育ってもまたぐ詰め方で書き戻す()
        {
            Chunk chunk = Chunk.FromNbt(SpanningVector());
            List<string> states = SpanningStates();

            // 20種類を足してパレットを37要素にし、ビット幅を5から6へ広げる
            for (int index = 0; index < 20; index++)
            {
                chunk.SetBlock(index % 16, index / 16, 0, $"minecraft:edited_{index}");
            }

            NbtCompound written = chunk.ToNbt();
            NbtCompound section = LevelSection(written, 0);

            // またぐ詰め方なので、長さは ceil(4096 * 6 / 64) = 384
            Assert.Equal(37, section.GetList("Palette").Count);
            Assert.Equal(384, section.GetLongArray("BlockStates").Length);
            Assert.Equal(2230, written.GetInt("DataVersion"));

            Chunk reread = Chunk.FromNbt(written);

            // 置いたブロックと、触っていないブロックの両方が読み直せる
            for (int position = 0; position < 4096; position++)
            {
                int x = position & 15;
                int y = position >> 8;
                int z = (position >> 4) & 15;
                int index = (y * 16) + x;
                string block = reread.GetBlock(x, y, z)!.ToString();

                // 置いた位置だけ新しい状態になる
                if (z == 0 && index < 20)
                {
                    Assert.Equal($"minecraft:edited_{index}", block);
                }
                else
                {
                    Assert.Equal(states[(position * 7) % 17], block);
                }
            }
        }

        [Fact]
        public void DataVersion2230のチャンクのバイオームIDは4ブロック単位で読める()
        {
            Chunk chunk = Chunk.FromNbt(SpanningVector());

            Assert.Equal(SpanningBiome((17 * 16) + (2 * 4) + 1), chunk.GetBiomeId(5, 70, 9));
            Assert.Null(chunk.GetBiomeId(0, 256, 0));
        }

        [Fact]
        public void DataVersion1976のチャンクを読み無変更で書き戻すと元と同じになる()
        {
            NbtCompound root = Biomes2DVector();
            byte[] before = ChunkBytes(root);
            Chunk chunk = Chunk.FromNbt(root);

            Assert.Equal(1976, chunk.DataVersion);
            Assert.Equal(4, chunk.X);
            Assert.Equal(-2, chunk.Z);
            Assert.Equal(0, chunk.MinSectionY);
            Assert.Equal(new[] { 0, 1 }, chunk.SectionYs);

            // ベクタの添字は (位置 * 7) % 5
            Assert.Equal("minecraft:air", chunk.GetBlock(0, 0, 0)!.ToString());
            Assert.Equal("minecraft:dirt", chunk.GetBlock(1, 0, 0)!.ToString());
            Assert.Equal("minecraft:oak_stairs[facing=west,half=top]", chunk.GetBlock(2, 0, 0)!.ToString());
            Assert.Equal("minecraft:stone", chunk.GetBlock(3, 0, 0)!.ToString());
            Assert.Equal("minecraft:oak_stairs[facing=east,half=bottom]", chunk.GetBlock(4, 0, 0)!.ToString());
            Assert.Equal("minecraft:air", chunk.GetBlock(15, 31, 15)!.ToString());

            Assert.Equal(before, ChunkBytes(chunk.ToNbt()));
        }

        [Fact]
        public void DataVersion1976のチャンクでパレットが育ってもまたぐ詰め方で書き戻す()
        {
            Chunk chunk = Chunk.FromNbt(Biomes2DVector());

            // 12種類を足してパレットを17要素にし、ビット幅を4から5へ広げる
            for (int index = 0; index < 12; index++)
            {
                chunk.SetBlock(index, 0, 0, $"minecraft:edited_{index}");
            }

            NbtCompound written = chunk.ToNbt();
            NbtCompound section = LevelSection(written, 0);

            // またぐ詰め方なので、長さは ceil(4096 * 5 / 64) = 320（またがない詰め方なら342）
            Assert.Equal(17, section.GetList("Palette").Count);
            Assert.Equal(320, section.GetLongArray("BlockStates").Length);

            Chunk reread = Chunk.FromNbt(written);

            // 置いたブロックと、触っていないブロックの両方が読み直せる
            for (int position = 0; position < 4096; position++)
            {
                string block = reread.GetBlock(position & 15, position >> 8, (position >> 4) & 15)!.ToString();

                // 置いた位置だけ新しい状態になる
                if (position < 12)
                {
                    Assert.Equal($"minecraft:edited_{position}", block);
                }
                else
                {
                    Assert.Equal(LevelStates[(position * 7) % 5], block);
                }
            }
        }

        [Fact]
        public void DataVersion1976のバイオームIDは高さに関係なく列ごとに読み書きできる()
        {
            Chunk chunk = Chunk.FromNbt(Biomes2DVector());

            // 添字は z * 16 + x で、yは見ない
            Assert.Equal(Biome2D((7 * 16) + 3), chunk.GetBiomeId(3, 0, 7));
            Assert.Equal(Biome2D((7 * 16) + 3), chunk.GetBiomeId(3, 200, 7));
            Assert.Equal(Biome2D((7 * 16) + 3), chunk.GetBiomeId(3, -10, 7));
            Assert.Equal(Biome2D((7 * 16) + 3), chunk.GetBiomeId(3, 300, 7));
            Assert.Equal(Biome2D((3 * 16) + 7), chunk.GetBiomeId(7, 0, 3));

            chunk.SetBiomeId(3, 1000, 7, 42);
            Assert.True(chunk.IsModified);
            Assert.Equal(42, chunk.GetBiomeId(3, 0, 7));

            // 同じ列の値だけが変わる
            int[] biomes = chunk.ToNbt().GetCompound("Level").GetIntArray("Biomes");
            Assert.Equal(42, biomes[(7 * 16) + 3]);
            Assert.Equal(Biome2D((3 * 16) + 7), biomes[(3 * 16) + 7]);
        }

        [Theory]
        [InlineData("absent")]
        [InlineData("int0")]
        [InlineData("int1024")]
        [InlineData("byte256")]
        public void DataVersion1976のBiomesを読めないチャンクのバイオームIDはnullで書き込めない(string kind)
        {
            NbtCompound root = Biomes2DVector();
            NbtCompound level = root.GetCompound("Level");
            level.Remove("Biomes");

            // 種類ごとに、読めない形のBiomesを置く
            if (kind == "int0")
            {
                level.Set("Biomes", new NbtIntArray(new int[0]));
            }
            else if (kind == "int1024")
            {
                level.Set("Biomes", new NbtIntArray(Enumerable.Repeat(1, 1024).ToArray()));
            }
            else if (kind == "byte256")
            {
                level.Set("Biomes", new NbtByteArray(Enumerable.Repeat((sbyte)1, 256).ToArray()));
            }

            byte[] before = ChunkBytes(root);
            Chunk chunk = Chunk.FromNbt(root);
            Assert.Null(chunk.GetBiomeId(0, 0, 0));

            SpringNbtException error = Assert.Throws<SpringNbtException>(() => chunk.SetBiomeId(0, 0, 0, 1));
            Assert.Equal(ErrorCode.InvalidArgument, error.Code);

            // 元のNBTはそのまま残る
            Assert.Equal(before, ChunkBytes(chunk.ToNbt()));
        }

        [Fact]
        public void DataVersion1976のチャンクではバイオーム名のAPIはUNSUPPORTED_FEATURE()
        {
            Chunk chunk = Chunk.FromNbt(Biomes2DVector());

            SpringNbtException error = Assert.Throws<SpringNbtException>(() => chunk.GetBiome(0, 0, 0));
            Assert.Equal(ErrorCode.UnsupportedFeature, error.Code);
        }

        [Fact]
        public void isLightOnの無い1_13の形式のチャンクは光源を無効化できない()
        {
            NbtCompound root = Biomes2DVector();
            root.SetInt("DataVersion", 1519);
            root.GetCompound("Level").Remove("isLightOn");
            byte[] before = ChunkBytes(root);
            Chunk chunk = Chunk.FromNbt(root);

            SpringNbtException error = Assert.Throws<SpringNbtException>(() => chunk.InvalidateLighting());
            Assert.Equal(ErrorCode.UnsupportedFeature, error.Code);
            Assert.Equal(before, ChunkBytes(chunk.ToNbt()));
        }

        [Theory]
        [InlineData("full", true)]
        [InlineData("postprocessed", true)]
        [InlineData("fullchunk", true)]
        [InlineData("mobs_spawned", false)]
        [InlineData("decorated", false)]
        public void 形式が1_14までならpostprocessedとfullchunkも生成済みとみなす(string status, bool expected)
        {
            NbtCompound root = Biomes2DVector();
            root.GetCompound("Level").SetString("Status", status);

            Assert.Equal(expected, Chunk.FromNbt(root).IsFullyGenerated);
        }

        [Fact]
        public void 形式が1_15ならpostprocessedを生成済みとみなさない()
        {
            NbtCompound root = SpanningVector();
            root.GetCompound("Level").SetString("Status", "postprocessed");

            Assert.False(Chunk.FromNbt(root).IsFullyGenerated);
        }

        [Fact]
        public void Statusの無いチャンクは生成済みとみなさない()
        {
            ChunkReadOptions options = new ChunkReadOptions { OnVersionMismatch = VersionMismatchAction.Ignore };
            NbtCompound legacy = Biomes2DVector();
            legacy.GetCompound("Level").Remove("Status");

            // 1.13より前のチャンクはStatusを持たない
            Assert.False(Chunk.FromNbt(PreFlatteningChunk(), options).IsFullyGenerated);
            Assert.False(Chunk.FromNbt(legacy).IsFullyGenerated);
        }

        [Fact]
        public void Statusが文字列でないチャンクは生成済みとみなさない()
        {
            NbtCompound root = Biomes2DVector();
            root.GetCompound("Level").SetInt("Status", 1);
            Chunk chunk = Chunk.FromNbt(root);

            // 生成段階の取得子は、いまと同じく型の違いをエラーにする
            SpringNbtException error = Assert.Throws<SpringNbtException>(() => chunk.Status);
            Assert.Equal(ErrorCode.UnexpectedTagType, error.Code);
            Assert.False(chunk.IsFullyGenerated);
        }

        [Fact]
        public void DataVersionの無いチャンクは元のNBTだけを持つ()
        {
            NbtCompound root = ChunkWithoutDataVersion();
            byte[] before = ChunkBytes(root);
            List<string> warnings = new List<string>();
            ChunkReadOptions options = new ChunkReadOptions
            {
                OnVersionMismatch = VersionMismatchAction.Warn,
                OnWarning = message => warnings.Add(message),
            };
            Chunk chunk = Chunk.FromNbt(root, options);

            // 1.13より前と同じく、読み込みで警告になる
            Assert.Single(warnings);

            // 座標はLevelの中から読み、セクションは解釈しない
            Assert.Equal(3, chunk.X);
            Assert.Equal(-2, chunk.Z);
            Assert.Empty(chunk.SectionYs);
            Assert.Equal(-1, chunk.FormatDataVersion);

            // DataVersionの取得子は、いまと同じく無ければエラー
            Assert.Throws<SpringNbtException>(() => chunk.DataVersion);

            // ブロック・バイオーム・高さマップ・光源の操作はどれも受け付けない
            Action[] operations =
            {
                () => chunk.GetBlock(0, 0, 0),
                () => chunk.SetBlock(0, 0, 0, "minecraft:stone"),
                () => chunk.GetBiome(0, 0, 0),
                () => chunk.SetBiome(0, 0, 0, "minecraft:plains"),
                () => chunk.GetBiomeId(0, 0, 0),
                () => chunk.SetBiomeId(0, 0, 0, 1),
                () => chunk.ClearHeightmaps(),
                () => chunk.InvalidateLighting(),
                () => _ = chunk.MinSectionY,
                () => chunk.ToNbt(),
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
        public void DataVersionの無いチャンクはErrorなら読み込みで弾く()
        {
            ChunkReadOptions options = new ChunkReadOptions { OnVersionMismatch = VersionMismatchAction.Error };

            SpringNbtException error = Assert.Throws<SpringNbtException>(
                () => Chunk.FromNbt(ChunkWithoutDataVersion(), options));
            Assert.Equal(ErrorCode.UnsupportedDataVersion, error.Code);
        }

        [Fact]
        public void DataVersionの無いチャンクも世代を指定すればその値を返す()
        {
            ChunkReadOptions options = new ChunkReadOptions
            {
                OnVersionMismatch = VersionMismatchAction.Ignore,
                FormatDataVersion = 2230,
            };
            Chunk chunk = Chunk.FromNbt(ChunkWithoutDataVersion(), options);

            // 指定しても世代は選ばず、元のNBTだけを持つ
            Assert.Equal(2230, chunk.FormatDataVersion);

            SpringNbtException error = Assert.Throws<SpringNbtException>(() => chunk.GetBlock(0, 0, 0));
            Assert.Equal(ErrorCode.UnsupportedDataVersion, error.Code);
        }
    }

    /// <summary><c>Data</c>に指定の項目だけを持つlevel.datを書く</summary>
    private static void WriteLevel(string directory, Dictionary<string, NbtTag> entries)
    {
        NbtCompound data = new NbtCompound();

        foreach (KeyValuePair<string, NbtTag> entry in entries)
        {
            data.Set(entry.Key, entry.Value);
        }

        NbtCompound root = new NbtCompound();
        root.Set("Data", data);
        NbtIo.WriteFile(Path.Combine(directory, "level.dat"), new NamedTag("", root));
    }

    /// <summary>指定の項目を持つ.datを、フォルダごと作って書く</summary>
    private static void WriteDat(string path, Dictionary<string, NbtTag> entries)
    {
        System.IO.Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        NbtCompound root = new NbtCompound();

        foreach (KeyValuePair<string, NbtTag> entry in entries)
        {
            root.Set(entry.Key, entry.Value);
        }

        NbtIo.WriteFile(path, new NamedTag("", root));
    }

    /// <summary>一時フォルダを作って渡し、終わったら消す</summary>
    private static void WithTempWorld(Action<string> body)
    {
        string root = Path.Combine(Path.GetTempPath(), "springnbt-layout-" + Guid.NewGuid().ToString("N"));
        System.IO.Directory.CreateDirectory(root);

        try
        {
            body(root);
        }
        finally
        {
            System.IO.Directory.Delete(root, recursive: true);
        }
    }

    /// <summary>L1の合成ワールドを作る</summary>
    private static void MakeL1World(string root)
    {
        WriteLevel(root, new Dictionary<string, NbtTag> { ["DataVersion"] = new NbtInt(3953) });

        foreach (string folder in new[] { "region", "DIM-1/region", "DIM1/region", "dimensions/mymap/arena/region" })
        {
            System.IO.Directory.CreateDirectory(Path.Combine(root, folder));
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
                WriteLevel(root, new Dictionary<string, NbtTag> { ["DataVersion"] = new NbtInt(5023) });

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

    // ------------------------------------------------------------------
    // ワールドの構成の世代（L1とL2）
    // ------------------------------------------------------------------

    public class WorldLayoutTests
    {
        [Fact]
        public void World_l1_dimensions()
        {
            WithTempWorld(root =>
            {
                MakeL1World(root);

                using MinecraftWorld world = MinecraftWorld.Open(root);
                Assert.Equal(
                    new[] { "minecraft:overworld", "minecraft:the_nether", "minecraft:the_end", "mymap:arena" },
                    world.DimensionIds().ToArray());
                Assert.Equal(root, world.Dimension("minecraft:overworld")!.Directory);
                Assert.Equal(Path.Combine(root, "DIM-1"), world.Dimension("minecraft:the_nether")!.Directory);
                Assert.Equal(Path.Combine(root, "DIM1"), world.Dimension("minecraft:the_end")!.Directory);
                Assert.Equal(
                    Path.Combine(root, "dimensions", "mymap", "arena"), world.Dimension("mymap:arena")!.Directory);

                // 次元が無ければnull
                Assert.Null(world.Dimension("mymap:missing"));
            });
        }

        [Fact]
        public void L1で存在しない標準の次元は並ばない()
        {
            WithTempWorld(root =>
            {
                WriteLevel(root, new Dictionary<string, NbtTag> { ["DataVersion"] = new NbtInt(3953) });
                System.IO.Directory.CreateDirectory(Path.Combine(root, "region"));

                using MinecraftWorld world = MinecraftWorld.Open(root);
                Assert.Equal(new[] { "minecraft:overworld" }, world.DimensionIds().ToArray());
                Assert.Null(world.Dimension("minecraft:the_nether"));
            });
        }

        [Fact]
        public void L1ではdimensionsの下の標準の次元は並ばない()
        {
            WithTempWorld(root =>
            {
                WriteLevel(root, new Dictionary<string, NbtTag> { ["DataVersion"] = new NbtInt(3953) });
                System.IO.Directory.CreateDirectory(Path.Combine(root, "dimensions", "minecraft", "the_nether", "region"));

                using MinecraftWorld world = MinecraftWorld.Open(root);
                Assert.DoesNotContain("minecraft:the_nether", world.DimensionIds());
                Assert.Null(world.Dimension("minecraft:the_nether"));
            });
        }

        [Fact]
        public void World_l1_players()
        {
            WithTempWorld(root =>
            {
                MakeL1World(root);
                WriteDat(Path.Combine(root, "playerdata", "b-uuid.dat"), new Dictionary<string, NbtTag> { ["Health"] = new NbtInt(20) });
                WriteDat(Path.Combine(root, "playerdata", "a-uuid.dat"), new Dictionary<string, NbtTag> { ["Health"] = new NbtInt(7) });

                using MinecraftWorld world = MinecraftWorld.Open(root);
                Assert.Equal(new[] { "a-uuid", "b-uuid" }, world.PlayerIds().ToArray());
                Assert.Equal(7, world.Player("a-uuid")!.GetInt("Health"));
                Assert.Null(world.Player("missing"));
            });
        }

        [Fact]
        public void World_l1_data_file()
        {
            WithTempWorld(root =>
            {
                MakeL1World(root);
                WriteDat(Path.Combine(root, "data", "scoreboard.dat"), new Dictionary<string, NbtTag> { ["Value"] = new NbtInt(1) });
                WriteDat(Path.Combine(root, "DIM-1", "data", "raids_nether.dat"), new Dictionary<string, NbtTag> { ["Value"] = new NbtInt(2) });

                using MinecraftWorld world = MinecraftWorld.Open(root);
                Assert.Equal(1, world.DataFile("scoreboard")!.GetInt("Value"));
                Assert.Null(world.DataFile("missing"));
                Assert.Equal(2, world.Dimension("minecraft:the_nether")!.DataFile("raids_nether")!.GetInt("Value"));

                // オーバーワールドの次元は、ワールドと同じdata/を読む
                Assert.Equal(1, world.Dimension("minecraft:overworld")!.DataFile("scoreboard")!.GetInt("Value"));
            });
        }

        [Fact]
        public void Level_data_l1_getters()
        {
            WithTempWorld(root =>
            {
                WriteLevel(root, new Dictionary<string, NbtTag>
                {
                    ["DataVersion"] = new NbtInt(3953),
                    ["SpawnX"] = new NbtInt(10),
                    ["SpawnY"] = new NbtInt(64),
                    ["SpawnZ"] = new NbtInt(-5),
                    ["Difficulty"] = new NbtByte(2),
                    ["hardcore"] = new NbtByte(1),
                });

                using MinecraftWorld world = MinecraftWorld.Open(root);
                Assert.Equal(new[] { 10, 64, -5 }, world.Level.SpawnPos);
                Assert.Equal("normal", world.Level.Difficulty);
                Assert.True(world.Level.IsHardcore);

                SpringNbtException error = Assert.Throws<SpringNbtException>(() => world.Level.SpawnDimension);
                Assert.Equal(ErrorCode.UnsupportedFeature, error.Code);
            });
        }

        [Theory]
        [InlineData(0, "peaceful")]
        [InlineData(1, "easy")]
        [InlineData(2, "normal")]
        [InlineData(3, "hard")]
        public void L1の難易度は数値を名前に直す(int number, string name)
        {
            WithTempWorld(root =>
            {
                WriteLevel(root, new Dictionary<string, NbtTag>
                {
                    ["DataVersion"] = new NbtInt(3953),
                    ["Difficulty"] = new NbtByte((sbyte)number),
                });

                using MinecraftWorld world = MinecraftWorld.Open(root);
                Assert.Equal(name, world.Level.Difficulty);
            });
        }

        [Theory]
        [InlineData(-1)]
        [InlineData(4)]
        public void L1の難易度が範囲外ならMALFORMED_DATA(int number)
        {
            WithTempWorld(root =>
            {
                WriteLevel(root, new Dictionary<string, NbtTag>
                {
                    ["DataVersion"] = new NbtInt(3953),
                    ["Difficulty"] = new NbtByte((sbyte)number),
                });

                using MinecraftWorld world = MinecraftWorld.Open(root);
                SpringNbtException error = Assert.Throws<SpringNbtException>(() => world.Level.Difficulty);
                Assert.Equal(ErrorCode.MalformedData, error.Code);
            });
        }

        [Fact]
        public void World_l2_unchanged()
        {
            WithTempWorld(root =>
            {
                NbtCompound spawn = new NbtCompound();
                spawn.Set("pos", new NbtIntArray(new[] { 1, 2, 3 }));
                spawn.Set("dimension", new NbtString("minecraft:overworld"));
                NbtCompound settings = new NbtCompound();
                settings.Set("difficulty", new NbtString("hard"));
                settings.Set("hardcore", new NbtByte(1));
                WriteLevel(root, new Dictionary<string, NbtTag>
                {
                    ["DataVersion"] = new NbtInt(5023),
                    ["spawn"] = spawn,
                    ["difficulty_settings"] = settings,
                });

                System.IO.Directory.CreateDirectory(Path.Combine(root, "dimensions", "minecraft", "overworld"));
                System.IO.Directory.CreateDirectory(Path.Combine(root, "dimensions", "minecraft", "the_end"));
                WriteDat(Path.Combine(root, "players", "data", "u.dat"), new Dictionary<string, NbtTag> { ["Health"] = new NbtInt(3) });
                WriteDat(Path.Combine(root, "data", "minecraft", "weather.dat"), new Dictionary<string, NbtTag> { ["Value"] = new NbtInt(4) });
                WriteDat(
                    Path.Combine(root, "dimensions", "minecraft", "the_end", "data", "minecraft", "raids.dat"),
                    new Dictionary<string, NbtTag> { ["Value"] = new NbtInt(5) });

                using MinecraftWorld world = MinecraftWorld.Open(root);
                Assert.Equal(new[] { 1, 2, 3 }, world.Level.SpawnPos);
                Assert.Equal("minecraft:overworld", world.Level.SpawnDimension);
                Assert.Equal("hard", world.Level.Difficulty);
                Assert.True(world.Level.IsHardcore);
                Assert.Equal(new[] { "minecraft:overworld", "minecraft:the_end" }, world.DimensionIds().ToArray());
                Assert.Equal(new[] { "u" }, world.PlayerIds().ToArray());
                Assert.Equal(4, world.DataFile("weather")!.GetInt("Value"));
                Assert.Equal(5, world.Dimension("the_end")!.DataFile("raids")!.GetInt("Value"));
            });
        }

        [Fact]
        public void DataVersionが無いlevelDatはL1として読む()
        {
            WithTempWorld(root =>
            {
                WriteLevel(root, new Dictionary<string, NbtTag>());
                System.IO.Directory.CreateDirectory(Path.Combine(root, "DIM1"));

                using MinecraftWorld world = MinecraftWorld.Open(root);
                Assert.Equal(new[] { "minecraft:the_end" }, world.DimensionIds().ToArray());
            });
        }

        [Fact]
        public void World_override_layout()
        {
            WithTempWorld(root =>
            {
                // level.datは26.3を名乗るが、構成はL1
                WriteLevel(root, new Dictionary<string, NbtTag>
                {
                    ["DataVersion"] = new NbtInt(5023),
                    ["SpawnX"] = new NbtInt(1),
                    ["SpawnY"] = new NbtInt(2),
                    ["SpawnZ"] = new NbtInt(3),
                });
                System.IO.Directory.CreateDirectory(Path.Combine(root, "region"));

                using (MinecraftWorld plain = MinecraftWorld.Open(root))
                {
                    Assert.Empty(plain.DimensionIds());
                }

                using (MinecraftWorld world = MinecraftWorld.Open(root, new WorldOpenOptions { FormatDataVersion = 3953 }))
                {
                    Assert.Equal(new[] { "minecraft:overworld" }, world.DimensionIds().ToArray());
                    Assert.Equal(new[] { 1, 2, 3 }, world.Level.SpawnPos);
                }

                SpringNbtException error = Assert.Throws<SpringNbtException>(
                    () => MinecraftWorld.Open(root, new WorldOpenOptions { FormatDataVersion = 1518 }));
                Assert.Equal(ErrorCode.InvalidArgument, error.Code);
            });
        }

        [Fact]
        public void ワールドの指定は読むチャンクの世代にも効く()
        {
            WithTempWorld(root =>
            {
                WriteLevel(root, new Dictionary<string, NbtTag> { ["DataVersion"] = new NbtInt(5023) });
                string region = Path.Combine(root, "dimensions", "minecraft", "overworld", "region");
                System.IO.Directory.CreateDirectory(region);
                NbtCompound chunk = (NbtCompound)NbtIo.ReadFile(VectorPath("palette_1")).Tag;

                using (RegionFile file = RegionFile.Open(Path.Combine(region, "r.0.0.mca"), RegionFileMode.ReadWrite))
                {
                    file.WriteChunk(0, 0, chunk);
                }

                // ワールドの指定がChunkReadの指定より優先される
                ChunkReadOptions readOptions = new ChunkReadOptions { FormatDataVersion = 5023 };
                WorldOpenOptions options = new WorldOpenOptions { ChunkRead = readOptions, FormatDataVersion = 5006 };

                using (MinecraftWorld world = MinecraftWorld.Open(root, options))
                {
                    Chunk loaded = world.Dimension("minecraft:overworld")!.Chunk(0, 0)!;
                    Assert.Equal(5006, loaded.FormatDataVersion);
                }

                // 渡したオプションは書き換えない
                Assert.Equal(5023, readOptions.FormatDataVersion);
            });
        }
    }
}

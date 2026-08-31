using SpringNBTLibrary.Nbt;
using SpringNBTLibrary.World;

namespace SpringNBTLibrary.Tests;

/// <summary>
/// World / Block レイヤ。仕様: docs/spec/30-chunk-format.md / 31-paletted-container.md / 40-world-layout.md
/// </summary>
public class WorldTests
{
    /// <summary>共通テストベクタ（world/*.nbt）のパス。</summary>
    private static string VectorPath(string name)
    {
        string current = AppContext.BaseDirectory;

        // ビルド出力からリポジトリ直下まで遡って spec/testdata を探す
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

    /// <summary>テストベクタをチャンクとして読む。</summary>
    private static Chunk LoadChunk(string name, ChunkReadOptions? options = null)
    {
        NamedTag named = NbtIo.ReadFile(VectorPath(name));
        return Chunk.FromNbt((NbtCompound)named.Tag, options);
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
            NbtCompound nbt = state.ToNbt();
            Assert.Equal("minecraft:oak_stairs", nbt.GetString("Name"));
            Assert.Equal("north", nbt.GetCompound("Properties").GetString("facing"));
            Assert.Equal(state, BlockState.FromNbt(nbt));
        }

        [Fact]
        public void プロパティ無しのNBTにはPropertiesを書かない()
        {
            NbtCompound nbt = BlockState.Parse("minecraft:air").ToNbt();
            Assert.Null(nbt.OptCompound("Properties"));
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

            // bits=5 なら 1 つの long に 12 個。12 個目は次の long の最下位から始まる
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
            // 4096 エントリを 342 long で表せるのは bits=5 のときだけ
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
        private static NbtCompound BlockEntry(string name)
        {
            NbtCompound entry = new NbtCompound();
            entry.Set("Name", new NbtString(name));
            return entry;
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

            // パレットを 17 要素まで増やして bits=4 から 5 への拡張を起こす
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

            // 残るのは実際に使われている air と dirt の 2 つ
            Assert.Equal(2, container.Palette.Count);
            Assert.Equal("minecraft:dirt", ((NbtCompound)container.Get(0)).GetString("Name"));
        }

        [Fact]
        public void fillで単一値に戻る()
        {
            PalettedContainer container = PalettedContainer.Filled(BlockEntry("minecraft:air"), 4096, 4);
            container.Set(0, BlockEntry("minecraft:stone"));
            container.Fill(BlockEntry("minecraft:water"));

            Assert.Single(container.Palette);
            Assert.Equal(0, container.BitsPerEntry);
            Assert.Equal("minecraft:water", ((NbtCompound)container.Get(4095)).GetString("Name"));
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

            // ベクタの添字は (位置 * 11) % 17。パレット先頭 2 つだけ名前が違う
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

            // 保存済みとして印を下ろせる
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

            // 同じ 4×4×4 の枠内はまとめて変わる
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

            // (0,-64,0) には chest と block_tick、(1,-64,1) には furnace と fluid_tick がある
            chunk.SetBlock(0, -64, 0, BlockState.Parse("minecraft:stone"));
            chunk.SetBlock(1, -64, 1, BlockState.Parse("minecraft:stone"));

            NbtCompound after = chunk.Raw;
            NbtList entities = after.GetList("block_entities");

            // 触っていない (15,-50,15) の barrel だけが残る
            Assert.Single(entities);
            Assert.Equal("minecraft:barrel", ((NbtCompound)entities[0]).GetString("id"));

            // block_ticks も同様に、対象の座標のものだけ消える
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
            // 付随データは絶対座標で持つので、チャンク座標を取り違えると
            // 無関係な要素を消してしまう
            NamedTag named = NbtIo.ReadFile(VectorPath("block_entities"));
            NbtCompound root = (NbtCompound)named.Tag;
            root.Set("xPos", new NbtInt(1));
            root.Set("zPos", new NbtInt(1));

            Chunk chunk = Chunk.FromNbt(root);
            chunk.SetBlock(0, -64, 0, BlockState.Parse("minecraft:stone"));

            // このチャンクの (0,-64,0) は絶対座標 (16,-64,16)。どれとも一致しない
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
    // DataVersion の扱い
    // ------------------------------------------------------------------

    public class DataVersionTests
    {
        /// <summary>DataVersion だけを差し替えたチャンクを作る。</summary>
        private static NbtCompound ForeignChunk()
        {
            NamedTag named = NbtIo.ReadFile(VectorPath("palette_1"));
            NbtCompound root = (NbtCompound)named.Tag;
            root.Set("DataVersion", new NbtInt(3953));
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
            Assert.Equal(3953, chunk.DataVersion);
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

            // DataVersion は読んだ値のまま残す
            Assert.Equal(3953, chunk.ToNbt(write).GetInt("DataVersion"));
        }

        /// <summary>対象より新しい DataVersion を持つチャンクを作る。</summary>
        private static NbtCompound NewerChunk()
        {
            NamedTag named = NbtIo.ReadFile(VectorPath("palette_1"));
            NbtCompound root = (NbtCompound)named.Tag;
            root.SetInt("DataVersion", 5015);
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

            // 形式が同じであれば、新しいバージョンでも黙って読める
            Chunk chunk = Chunk.FromNbt(NewerChunk(), options);
            Assert.Equal(5015, chunk.DataVersion);
            Assert.Empty(warnings);
        }

        [Fact]
        public void 新しいバージョンのチャンクはエラー設定でも通る()
        {
            ChunkReadOptions options = new ChunkReadOptions
            {
                OnVersionMismatch = VersionMismatchAction.Error,
            };

            Assert.Equal(5015, Chunk.FromNbt(NewerChunk(), options).DataVersion);
        }

        [Fact]
        public void 新しいバージョンのチャンクはそのまま書き戻せる()
        {
            Chunk chunk = Chunk.FromNbt(NewerChunk());

            // 許可を出さなくても書き戻せて、DataVersion も変わらない
            Assert.Equal(5015, chunk.ToNbt().GetInt("DataVersion"));
        }

        [Fact]
        public void 対象バージョンのチャンクはそのまま書き戻せる()
        {
            Chunk chunk = LoadChunk("palette_1");
            Assert.Equal(SpringNbt.TargetDataVersion, chunk.ToNbt().GetInt("DataVersion"));
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
    }
}

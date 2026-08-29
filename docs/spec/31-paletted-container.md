# 31. パレット付きコンテナと BitStorage

セクション内のブロック状態・バイオームを格納する形式。
本ライブラリで最も間違いやすい箇所なので、ビット演算を厳密に定める。

前提: [30 チャンク形式](30-chunk-format.md)

---

## 1. 構造

```
block_states: {
    palette: [ {Name: "minecraft:stone"}, {Name:"minecraft:oak_stairs", Properties:{facing:"north"}} ],
    data: [L; ...]        // パレットが 1 要素のときは存在しない
}
```

`data` はパレットへの添字を 64bit 整数の配列へ詰めたもの。

| 用途 | 要素数 | 添字の並び順 | ビット幅 | パレット上限 |
|---|---:|---|---|---:|
| `block_states` | 4096 | `y*256 + z*16 + x` | `max(4, ceil_log2(len))` | 4096 |
| `biomes` | 64 | `y*16 + z*4 + x` | `max(1, ceil_log2(len))` | 64 |

`x` `y` `z` はセクション内の相対座標。ブロックは 0..15、バイオームは 0..3（1エントリが 4×4×4 ブロック）。

`ceil_log2(n)` は「`n` 個の値を表すのに必要な最小ビット数」で、`n = 1` のとき **0** を返す。

```
ceil_log2(1) = 0
ceil_log2(2) = 1
ceil_log2(3) = 2
ceil_log2(4) = 2
ceil_log2(5) = 3
...
ceil_log2(4096) = 12
```

したがってブロックのビット幅は 4..12、バイオームのビット幅は 1..6 になる。

**パレットが 1 要素のとき `data` は存在しない**（全エントリがその 1 種類）。
逆に `data` があるのにパレットが 1 要素の場合は、`data` を無視せず読み、全要素が 0 であることを確認する。

---

## 2. ビット詰め（跨ぎなし）

1.16 以降、添字は **64bit 境界を跨がない**。
1つの `i64` に入りきらない分は、その `i64` の残りビットを未使用のまま捨て、次の `i64` の最下位ビットから始める。

```
values_per_long = 64 / bits             (整数除算。切り捨て)
long_count      = ceil(entry_count / values_per_long)

entry i の位置:
    long_index = i / values_per_long    (整数除算)
    bit_offset = (i % values_per_long) * bits

読み出し:
    value = (data[long_index] >>> bit_offset) & ((1 << bits) - 1)

書き込み:
    mask = ((1 << bits) - 1) << bit_offset
    data[long_index] = (data[long_index] & ~mask) | ((value << bit_offset) & mask)
```

`>>>` は**論理右シフト**であること。`i64` は符号付きなので、算術シフトを使うと
最上位ビット付近の値が壊れる。

| 言語 | 論理右シフトの書き方 |
|---|---|
| Rust | `(v as u64) >> n` （`u64` へキャストしてからシフト） |
| C# | `(long)((ulong)v >> n)` |
| Java | `v >>> n` |
| Python | `(v & 0xFFFFFFFFFFFFFFFF) >> n` |

Python は整数が無限精度なので、`i64` として扱う箇所では
**読み込み時に符号付き 64bit へ、書き込み時に符号なし 64bit へ**明示的に変換する。

### 2.1 実データで確認した組み合わせ

Java版 26.2 の実ワールド（83,544 セクション = 167,088 個のコンテナ）を走査した結果、
上式で求めた `long_count` は**すべて実際の `data` 長と一致した**。

| コンテナ | パレット長 | bits | `data` の長さ | 出現数 |
|---|---:|---:|---|---:|
| `biomes` | 1 | — | **無し** | 73,345 |
| `block_states` | 1 | — | **無し** | 67,532 |
| `block_states` | 2〜16 | 4 | 256 long | 13,635 |
| `biomes` | 2 | 1 | 1 long | 9,464 |
| `block_states` | 17〜32 | 5 | 342 long | 2,016 |
| `biomes` | 3〜4 | 2 | 2 long | 735 |
| `block_states` | 33〜64 | 6 | 410 long | 361 |

`spec/tools/scan_world.py` がこの検証を行う。仕様を変えたら必ず実ワールドで再確認すること。

### 2.2 具体例

ブロック（4096 エントリ）でパレットが 5 要素の場合:

```
bits            = max(4, ceil_log2(5)) = max(4, 3) = 4
values_per_long = 64 / 4 = 16
long_count      = ceil(4096 / 16) = 256      -- 端数なし。全ビット使用
```

パレットが 17 要素の場合:

```
bits            = max(4, ceil_log2(17)) = 5
values_per_long = 64 / 5 = 12                -- 60 ビット使用、上位 4 ビットは未使用
long_count      = ceil(4096 / 12) = 342
```

最後の `i64` には `4096 - 341*12 = 4` 個しか入らないため、
残り 8 スロット分のビットは**ゼロで埋める**。

---

## 3. 読み込み時の検証

1. `palette` が空 → `MALFORMED_DATA`
2. `data` の長さが上式の `long_count` と一致しない → `MALFORMED_DATA`
   - ただし `ReadOptions.lenient_bit_storage = true` のときは、
     `data` の長さから `bits` を逆算して読む（第三者ツールが書いたデータの救済用）
3. 取り出した添字が `palette` の範囲外 → `MALFORMED_DATA`

いずれも黙って 0 番目のパレット要素で代替してはならない。壊れたデータを
そうと分からない形で書き戻してしまうため。

---

## 4. 書き込み時のビット幅再計算

`set` でパレットに新しい要素を追加した結果ビット幅が変わる場合は、
`data` 配列全体を新しいビット幅で詰め直す。

```
新しい bits を求める
  -> 変わらなければ該当エントリだけ書き換える
  -> 変わったら long_count を求め直し、全 entry_count 個を読み直して新配列へ詰める
```

**未使用パレットの掃除** (`compact()`): どのエントリからも参照されていない
パレット要素を取り除き、添字を振り直す。ビット幅が縮む場合は詰め直す。
これは明示的に呼んだときだけ行い、`set` のたびに自動実行はしない
（大量の `set` を行う用途で著しく遅くなるため）。

### 4.1 キーの並び順

compound へ書き出すときは **`data` を先、`palette` を後**に置く。

Minecraft 26.2 が実際に書き出したデータを走査したところ、
`block_states` / `biomes` のどちらも例外なくこの順だった。

| コンテナ | キーの並び | 出現数 |
|---|---|---|
| `block_states` | `palette` のみ（`data` 無し） | 67,532 |
| `block_states` | `data`, `palette` | 16,012 |
| `biomes` | `palette` のみ（`data` 無し） | 73,345 |
| `biomes` | `data`, `palette` | 10,199 |

NBT の compound は挿入順を保持するため、この並びを揃えないと
**内容が同じでもバイト列が変わる**。触っていないチャンクを書き戻しても
元と一致させるために、並び順まで仕様として固定する。

---

## 5. 論理API

```
PalettedContainer<T>
    entry_count() -> i32                 -- 4096 または 64
    palette() -> List<T>                 -- 読み取り専用ビュー
    bits_per_entry() -> i32
    get(index) -> T
    set(index, value)
    fill(value)
    compact()                            -- 未使用パレット要素を除去して詰め直す
    to_nbt() -> NbtCompound
    from_nbt(nbt, entry_count, min_bits) -> PalettedContainer<T>
```

`min_bits` は `block_states` なら 4、`biomes` なら 1。
座標から `index` への変換はセクション側（[30](30-chunk-format.md)）の責務とする。

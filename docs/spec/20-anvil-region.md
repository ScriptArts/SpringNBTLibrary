# 20. Anvil リージョン形式

チャンクをまとめて格納する `.mca` ファイルの仕様。

前提: [00 共通規約](00-conventions.md) / [10 NBT バイナリ形式](10-nbt-binary.md)

---

## 1. ファイル名と担当範囲

`r.<X>.<Z>.mca` の `X` / `Z` は**リージョン座標**で、1リージョンは 32×32 チャンクを担当する。

```
regionX = chunkX >> 5        (算術シフト。負値も正しく動く)
regionZ = chunkZ >> 5
localX  = chunkX & 31        (リージョン内のチャンク位置 0..31)
localZ  = chunkZ & 31
index   = localX + localZ * 32     (0..1023)
```

`>>` は**算術右シフト**であること。C# の `int` / Java の `int` / Rust の `i32` / Python の `int`
はいずれも算術シフトになるが、実装時に論理シフトへ取り違えないこと。

---

## 2. ファイル構造

ファイル全体は **4096 バイト（1セクタ）の倍数**でなければならない。

| セクタ番号 | 内容 |
|---:|---|
| 0 | ロケーションテーブル（4096 バイト） |
| 1 | タイムスタンプテーブル（4096 バイト） |
| 2 以降 | チャンクデータ |

### 2.1 ロケーションテーブル

1024 エントリ × 4 バイト。エントリ `index` はチャンク `(localX, localZ)` に対応する。

```
バイト 0..2 : オフセット (u24, ビッグエンディアン) — チャンクデータの開始セクタ番号
バイト 3    : 長さ (u8) — チャンクデータが占めるセクタ数
```

**オフセットと長さが両方 0 のエントリは「チャンクが存在しない」**を意味する。
オフセットが 2 未満（ヘッダ領域を指す）で 0 でない場合は `MALFORMED_DATA`。

長さは `u8` なので最大 255 セクタ = 1,044,480 バイト。
これを超えるチャンクは外部ファイルへ退避する（→ 4章）。

### 2.2 タイムスタンプテーブル

1024 エントリ × 4 バイト。`i32` ビッグエンディアンの **Unix 秒**（最終更新時刻）。
チャンクが存在しない場合は 0。本ライブラリは書き込み時に現在時刻を設定する
（`WriteOptions.preserve_timestamp` で元の値を保つこともできる）。

---

## 3. チャンクデータのペイロード

ロケーションが指すセクタの先頭から次の並びで始まる。

```
i32  length          -- 後続バイト数（圧縮方式の 1 バイトを含む）
u8   compression     -- 圧縮方式
...  data            -- length - 1 バイト
```

`length` は**必ず 1 以上**。0 以下は `MALFORMED_DATA`。
`4 + length` が `セクタ数 × 4096` を超える場合も `MALFORMED_DATA`。
セクタ内の余りはゼロ埋めする。

### 3.1 圧縮方式ID

| ID | 方式 | 本ライブラリの扱い |
|---:|---|---|
| 1 | GZip (RFC 1952) | 読み書き対応 |
| 2 | Zlib (RFC 1950) | 読み書き対応。**書き込みの既定** |
| 3 | 無圧縮 | 読み書き対応 |
| 4 | LZ4 (ブロック形式、フレーム無し) | 任意依存。無効時は `UNSUPPORTED_FEATURE` |
| 127 | サードパーティ製サーバのカスタム方式 | 読み込み時 `UNSUPPORTED_FEATURE`。生バイト API でのみ取得可 |

上記以外のIDは `MALFORMED_DATA`。

### 3.2 外部ファイルへの退避 (`.mcc`)

圧縮方式IDの**最上位ビット (0x80) が立っている**場合、
チャンクの実データはリージョンファイル内ではなく次のファイルに格納される。

```
<リージョンと同じディレクトリ>/c.<chunkX>.<chunkZ>.mcc
```

- `.mcc` の中身は**圧縮済みデータそのもの**。`length` も `compression` バイトも持たない
- 実際の圧縮方式は `compression & 0x7F` で得る
- このときリージョン内には 1 セクタだけが確保され、`length` は 1（`compression` バイトのみ）となる

`chunkX` / `chunkZ` は**絶対チャンク座標**であってリージョン内相対ではない。

**書き込み時の自動退避**: 圧縮後のデータが `255 * 4096 - 5` バイトを超える場合、
本ライブラリは自動的に `.mcc` へ退避し、フラグを立てる。
逆に `.mcc` にあったチャンクが縮んだ場合はリージョン内へ戻し、`.mcc` を削除する。

---

## 4. セクタ確保

書き込み時のセクタ管理規則。破損しやすい箇所なので厳密に定める。

1. 起動時にロケーションテーブルを走査し、**使用中セクタの集合**を作る
   - セクタ 0・1 は常に使用中（ヘッダ）
   - 同じセクタを 2 つのチャンクが指していたら `MALFORMED_DATA`
2. チャンクを書くとき、必要セクタ数 `n = ceil((4 + length) / 4096)` を求める
3. 既存の割り当てが `n` セクタ**ちょうど**なら、その場に上書きする
4. そうでなければ、**先頭から探して `n` 連続で空いている領域**へ書く
   - 見つからなければファイル末尾へ追記する
   - 元の割り当ては解放する
5. 書き終えたらロケーション／タイムスタンプの両テーブルを更新する
6. ファイル長を 4096 の倍数へ切り上げる（不足分はゼロ埋め）

削除は、ロケーションエントリとタイムスタンプエントリを 0 にし、セクタを解放する。
**ファイルの縮小は行わない**（次の書き込みで再利用される）。

`optimize()` は全チャンクを読み出して新しいファイルへ隙間なく詰め直す。
断片化した `.mca` のサイズを縮めたいときに使う。

---

## 5. 論理API

```
RegionFile
    open(path, mode)                  -> RegionFile     -- mode: ReadOnly | ReadWrite
    region_x() -> i32
    region_z() -> i32
    has_chunk(chunk_x, chunk_z)       -> bool
    read_chunk(chunk_x, chunk_z)      -> Option<NbtCompound>
    read_chunk_raw(chunk_x, chunk_z)  -> Option<RawChunk>
    write_chunk(chunk_x, chunk_z, nbt)
    write_chunk_raw(chunk_x, chunk_z, raw)
    delete_chunk(chunk_x, chunk_z)    -> bool
    timestamp(chunk_x, chunk_z)       -> i32
    set_timestamp(chunk_x, chunk_z, value)
    chunk_positions()                 -> Iterator<ChunkPos>
    optimize()
    flush()
    close()

RawChunk { compression: Compression, external: bool, data: bytes }
```

チャンク座標は**絶対座標**で受け取り、内部でリージョン内位置へ変換する。
このリージョンの担当外の座標が渡されたら `INVALID_ARGUMENT`。

```
RegionFolder
    open(dir)                            -> RegionFolder
    region_positions()                   -> Iterator<RegionPos>
    region(region_x, region_z)           -> Option<RegionFile>
    read_chunk(chunk_x, chunk_z)         -> Option<NbtCompound>
    write_chunk(chunk_x, chunk_z, nbt)
```

`RegionFolder` は `region/` `entities/` `poi/` のいずれか1つのディレクトリを表す。
開いたリージョンファイルはキャッシュし、`close()` でまとめて閉じる。

---

## 6. 関連

- チャンクの中身 → [30 チャンク形式](30-chunk-format.md)
- ディレクトリ構成 → [40 ワールドのディレクトリ構成](40-world-layout.md)

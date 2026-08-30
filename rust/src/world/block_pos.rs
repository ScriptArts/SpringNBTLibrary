//! ブロックの絶対座標と、その範囲
//!
//! 仕様: `docs/spec/30-chunk-format.md` 5章

use std::fmt;

use crate::anvil::ChunkPos;

/// ブロックの絶対座標
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct BlockPos {
    /// X座標
    pub x: i32,
    /// Y座標
    pub y: i32,
    /// Z座標
    pub z: i32,
}

impl BlockPos {
    /// 座標を指定して作る
    pub fn new(x: i32, y: i32, z: i32) -> BlockPos {
        BlockPos { x, y, z }
    }

    /// この座標を含むチャンクの座標
    /// 算術右シフトなので負の座標でも正しく求まる
    pub fn chunk_pos(&self) -> ChunkPos {
        ChunkPos::new(self.x >> 4, self.z >> 4)
    }

    /// チャンク内でのX位置 (0..15)
    pub fn local_x(&self) -> i32 {
        self.x & 15
    }

    /// チャンク内でのZ位置 (0..15)
    pub fn local_z(&self) -> i32 {
        self.z & 15
    }

    /// 各軸へずらした座標を返す
    pub fn offset(&self, dx: i32, dy: i32, dz: i32) -> BlockPos {
        BlockPos::new(self.x + dx, self.y + dy, self.z + dz)
    }
}

impl fmt::Display for BlockPos {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "({}, {}, {})", self.x, self.y, self.z)
    }
}

/// ブロック座標の直方体な範囲
///
/// 両端を含む
/// `Cuboid::of(0, 0, 0, 0, 0, 0)` は 1 ブロック
///
/// 範囲内のブロックを順に処理したいときに使う
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Cuboid {
    /// X の最小値
    pub min_x: i32,
    /// Y の最小値
    pub min_y: i32,
    /// Z の最小値
    pub min_z: i32,
    /// X の最大値（含む）
    pub max_x: i32,
    /// Y の最大値（含む）
    pub max_y: i32,
    /// Z の最大値（含む）
    pub max_z: i32,
}

impl Cuboid {
    /// 両端の座標から作る
    /// 大小の順序は問わない
    /// 内部で小さいほうを最小に揃える
    pub fn new(first: BlockPos, second: BlockPos) -> Cuboid {
        Cuboid {
            min_x: first.x.min(second.x),
            min_y: first.y.min(second.y),
            min_z: first.z.min(second.z),
            max_x: first.x.max(second.x),
            max_y: first.y.max(second.y),
            max_z: first.z.max(second.z),
        }
    }

    /// 両端の座標から作る
    pub fn of(x1: i32, y1: i32, z1: i32, x2: i32, y2: i32, z2: i32) -> Cuboid {
        Cuboid::new(BlockPos::new(x1, y1, z1), BlockPos::new(x2, y2, z2))
    }

    /// X 方向の長さ
    pub fn size_x(&self) -> i32 {
        self.max_x - self.min_x + 1
    }

    /// Y 方向の長さ
    pub fn size_y(&self) -> i32 {
        self.max_y - self.min_y + 1
    }

    /// Z 方向の長さ
    pub fn size_z(&self) -> i32 {
        self.max_z - self.min_z + 1
    }

    /// 含まれるブロックの個数
    pub fn volume(&self) -> i64 {
        self.size_x() as i64 * self.size_y() as i64 * self.size_z() as i64
    }

    /// その座標が範囲に含まれるか
    pub fn contains(&self, x: i32, y: i32, z: i32) -> bool {
        x >= self.min_x
            && x <= self.max_x
            && y >= self.min_y
            && y <= self.max_y
            && z >= self.min_z
            && z <= self.max_z
    }

    /// 範囲内の座標を順に返す
    /// 並びは Y、Z、X の順で、X がいちばん内側で動く
    pub fn positions(&self) -> impl Iterator<Item = BlockPos> + '_ {
        // 内側から X が動くので、同じチャンクの並びを続けて触れる
        (self.min_y..=self.max_y).flat_map(move |y| {
            (self.min_z..=self.max_z)
                .flat_map(move |z| (self.min_x..=self.max_x).map(move |x| BlockPos::new(x, y, z)))
        })
    }
}

impl fmt::Display for Cuboid {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "({}, {}, {})-({}, {}, {})",
            self.min_x, self.min_y, self.min_z, self.max_x, self.max_y, self.max_z
        )
    }
}

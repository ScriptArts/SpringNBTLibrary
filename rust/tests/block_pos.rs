//! ブロック座標と範囲の統合テスト。
//!
//! 仕様: `docs/spec/30-chunk-format.md` 5章

use spring_nbt_library::anvil::ChunkPos;
use spring_nbt_library::world::{BlockPos, Cuboid};

#[test]
fn resolves_chunk_and_local_coordinates() {
    let pos = BlockPos::new(100, 64, -200);

    // 算術右シフトなので負の座標でも正しく求まる
    assert_eq!(pos.chunk_pos(), ChunkPos::new(6, -13));
    assert_eq!(pos.local_x(), 4);
    assert_eq!(pos.local_z(), 8);
}

#[test]
fn offsets_each_axis() {
    let moved = BlockPos::new(1, 2, 3).offset(10, -20, 30);

    assert_eq!(moved, BlockPos::new(11, -18, 33));
    assert_ne!(moved, BlockPos::new(11, -18, 34));
}

#[test]
fn normalizes_the_order_of_the_two_corners() {
    let box_ = Cuboid::of(10, 20, 30, 0, 5, 15);

    assert_eq!(box_.min_x, 0);
    assert_eq!(box_.max_x, 10);
    assert_eq!(box_.size_x(), 11);
    assert_eq!(box_.size_y(), 16);
    assert_eq!(box_.size_z(), 16);
}

#[test]
fn contains_only_the_positions_inside() {
    let box_ = Cuboid::of(0, 0, 0, 1, 1, 1);

    assert!(box_.contains(0, 0, 0));
    assert!(box_.contains(1, 1, 1));
    assert!(!box_.contains(2, 0, 0));
    assert!(!box_.contains(0, -1, 0));
}

#[test]
fn walks_every_position_inside() {
    let box_ = Cuboid::of(0, 0, 0, 1, 2, 3);
    let positions: Vec<BlockPos> = box_.positions().collect();

    assert_eq!(positions.len() as i64, box_.volume());
    assert_eq!(positions.len(), 2 * 3 * 4);

    // 並びは Y、Z、X の順で、X がいちばん内側で動く
    assert_eq!(positions[0], BlockPos::new(0, 0, 0));
    assert_eq!(positions[1], BlockPos::new(1, 0, 0));
    assert_eq!(positions[2], BlockPos::new(0, 0, 1));
    assert_eq!(positions[positions.len() - 1], BlockPos::new(1, 2, 3));
}

#[test]
fn one_block_box_has_volume_one() {
    let box_ = Cuboid::of(5, 5, 5, 5, 5, 5);

    assert_eq!(box_.volume(), 1);
    assert_eq!(box_.positions().count(), 1);
}

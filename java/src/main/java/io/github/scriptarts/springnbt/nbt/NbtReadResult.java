package io.github.scriptarts.springnbt.nbt;

/**
 * 位置を指定した読み込みの結果
 *
 * <p>読んだタグと、その直後の位置を持つ
 *
 * <p>続けて読むときは {@code end} を次の開始位置として渡す
 *
 * <p>仕様: {@code docs/spec/10-nbt-binary.md} 3.1章
 *
 * @param tag 読んだタグ
 * @param end 読み終わった直後の位置
 */
public record NbtReadResult(NamedTag tag, int end) {
}

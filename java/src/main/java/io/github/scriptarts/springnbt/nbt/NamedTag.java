package io.github.scriptarts.springnbt.nbt;

import java.util.Objects;

/**
 * ルート名とルートタグの組。
 *
 * <p>{@link NbtFormat#JAVA} ではルート名は通常空文字列だが、
 * 読んだ値をそのまま保持し、書き出しでも同じ値を出力する。
 *
 * @param name ルート名
 * @param tag  ルートタグ
 */
public record NamedTag(String name, NbtCompound tag) {

    /**
     * ルート名とルートタグを指定して作る。
     *
     * @param name ルート名
     * @param tag  ルートタグ
     */
    public NamedTag {
        Objects.requireNonNull(name, "name");
        Objects.requireNonNull(tag, "tag");
    }
}

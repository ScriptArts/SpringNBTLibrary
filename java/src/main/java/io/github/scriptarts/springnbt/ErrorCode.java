package io.github.scriptarts.springnbt;

/**
 * エラーの分類。4言語すべてで同一の集合を持つ。
 *
 * <p>仕様: {@code docs/spec/00-conventions.md} 4章
 */
public enum ErrorCode {

    /** 下位の入出力失敗。 */
    IO,

    /** バイト列が仕様に反する。 */
    MALFORMED_DATA,

    /** 期待した型と違うタグを取り出した。 */
    UNEXPECTED_TAG_TYPE,

    /** 仕様上は妥当だが、このビルドでは扱えない。 */
    UNSUPPORTED_FEATURE,

    /** 安全上限を超えた。 */
    LIMIT_EXCEEDED,

    /** 呼び出し側の引数が不正。 */
    INVALID_ARGUMENT,

    /** 対象バージョン外のデータ。 */
    UNSUPPORTED_DATA_VERSION;

    /**
     * 適合性テストで言語間比較に使う識別子を返す。
     *
     * @return 識別子
     */
    public String asString() {
        return name();
    }
}

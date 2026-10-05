package io.github.scriptarts.springnbt;

/**
 * エラーの分類
 * 全言語で同一の集合を持つ
 */
public enum ErrorCode {

    /** 下位の入出力失敗 */
    IO,

    /** バイト列が仕様に反する */
    MALFORMED_DATA,

    /** 期待した型と違うタグを取り出した */
    UNEXPECTED_TAG_TYPE,

    /** 仕様上は妥当だが、このライブラリでは扱えない */
    UNSUPPORTED_FEATURE,

    /** 安全上限を超えた */
    LIMIT_EXCEEDED,

    /** 呼び出し側の引数が不正 */
    INVALID_ARGUMENT,

    /** 扱える形式より古いデータ */
    UNSUPPORTED_DATA_VERSION;

    /**
     * 適合性テストで言語間比較に使う識別子を返す
     *
     * @return 識別子
     */
    public String asString() {
        return name();
    }
}

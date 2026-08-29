package io.github.scriptarts.springnbt;

/**
 * 本ライブラリが送出する例外。分類は {@link #code()} で判別する。
 *
 * <p>検査例外にしていないのは、4言語でメソッドのシグネチャを揃えるため。
 * 入出力エラーも {@link ErrorCode#IO} でラップして送出する。
 *
 * <p>仕様: {@code docs/spec/00-conventions.md} 4章 / {@code docs/adr/0005-unified-error-model.md}
 */
public final class SpringNbtException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    private final ErrorCode code;

    /**
     * 分類とメッセージから例外を作る。
     *
     * @param code    エラーの分類
     * @param message 説明
     */
    public SpringNbtException(ErrorCode code, String message) {
        super(message);
        this.code = code;
    }

    /**
     * 原因となった下位の例外を保持して例外を作る。
     *
     * @param code    エラーの分類
     * @param message 説明
     * @param cause   原因
     */
    public SpringNbtException(ErrorCode code, String message, Throwable cause) {
        super(message, cause);
        this.code = code;
    }

    /**
     * エラーの分類。
     *
     * @return 分類
     */
    public ErrorCode code() {
        return code;
    }

    @Override
    public String toString() {
        return "[" + code.asString() + "] " + getMessage();
    }

    /**
     * {@link ErrorCode#MALFORMED_DATA} の例外を作る。
     *
     * @param message 説明
     * @return 例外
     */
    public static SpringNbtException malformed(String message) {
        return new SpringNbtException(ErrorCode.MALFORMED_DATA, message);
    }

    /**
     * {@link ErrorCode#INVALID_ARGUMENT} の例外を作る。
     *
     * @param message 説明
     * @return 例外
     */
    public static SpringNbtException invalidArgument(String message) {
        return new SpringNbtException(ErrorCode.INVALID_ARGUMENT, message);
    }

    /**
     * {@link ErrorCode#UNEXPECTED_TAG_TYPE} の例外を作る。
     *
     * @param message 説明
     * @return 例外
     */
    public static SpringNbtException unexpectedTagType(String message) {
        return new SpringNbtException(ErrorCode.UNEXPECTED_TAG_TYPE, message);
    }

    /**
     * {@link ErrorCode#LIMIT_EXCEEDED} の例外を作る。
     *
     * @param message 説明
     * @return 例外
     */
    public static SpringNbtException limitExceeded(String message) {
        return new SpringNbtException(ErrorCode.LIMIT_EXCEEDED, message);
    }

    /**
     * {@link ErrorCode#UNSUPPORTED_FEATURE} の例外を作る。
     *
     * @param message 説明
     * @return 例外
     */
    public static SpringNbtException unsupportedFeature(String message) {
        return new SpringNbtException(ErrorCode.UNSUPPORTED_FEATURE, message);
    }
}

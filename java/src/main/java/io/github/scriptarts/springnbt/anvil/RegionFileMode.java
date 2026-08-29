package io.github.scriptarts.springnbt.anvil;

/** リージョンファイルを開くときの動作。 */
public enum RegionFileMode {

    /** 読み取り専用。書き込み系の操作はエラーになる。 */
    READ_ONLY,

    /** 読み書き。ファイルが無ければ空のリージョンとして扱う。 */
    READ_WRITE
}

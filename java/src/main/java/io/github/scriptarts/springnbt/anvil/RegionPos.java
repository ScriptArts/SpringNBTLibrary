package io.github.scriptarts.springnbt.anvil;

/**
 * リージョンの座標
 * 1リージョンは 32×32 チャンクを担当する
 *
 * @param x リージョンX座標
 * @param z リージョンZ座標
 */
public record RegionPos(int x, int z) {

    /**
     * このリージョンのファイル名（{@code r.X.Z.mca}）
     *
     * @return ファイル名
     */
    public String fileName() {
        return "r." + x + "." + z + ".mca";
    }

    /**
     * {@code r.X.Z.mca} 形式のファイル名から座標を得る
     *
     * @param fileName ファイル名
     * @return 座標
     * 解釈できなければ null
     */
    public static RegionPos fromFileName(String fileName) {
        String[] parts = fileName.split("\\.");

        // "r" "<x>" "<z>" "mca" の 4 つに分かれるはず
        if (parts.length != 4 || !parts[0].equals("r") || !parts[3].equals("mca")) {
            return null;
        }

        try {
            return new RegionPos(Integer.parseInt(parts[1]), Integer.parseInt(parts[2]));
        } catch (NumberFormatException error) {
            return null;
        }
    }
}

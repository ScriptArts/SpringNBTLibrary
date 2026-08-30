Minecraft **Java版 26.2**（DataVersion `4903`）のワールドデータ・NBTファイルを
読み書きするライブラリです。

下の成果物をダウンロードして、自分のプロジェクトへ組み込んでください。

## 成果物

| 言語 | ファイル | 組み込み方 |
|---|---|---|
| C# | `SpringNBTLibrary.*.nupkg` | 置き場所を `nuget.config` で教えて `dotnet add package` |
| C# | `SpringNBTLibrary-*-dotnet8.zip` | 展開して `.dll` を参照に追加（`.xml` を隣に置くと補完が効く） |
| Java | `spring-nbt-library-*.jar` | クラスパスへ追加、またはローカルリポジトリへ install |
| TypeScript | `spring-nbt-library-*.tgz` | `npm install ./spring-nbt-library-*.tgz` |
| Python | `spring_nbt_library-*.whl` | `pip install spring_nbt_library-*.whl` |
| Rust | `spring-nbt-library-*.crate` | 展開してパス参照。git 参照でも使えます |

言語ごとの詳しい手順は [はじめに](https://github.com/ScriptArts/SpringNBTLibrary/tree/main/docs/getting-started) を参照してください。

## 確認

`SHA256SUMS.txt` で、落としたファイルが壊れていないか確かめられます。

```bash
sha256sum -c SHA256SUMS.txt
```

## ライセンス

MIT License — Copyright (c) 2026 ScriptArts

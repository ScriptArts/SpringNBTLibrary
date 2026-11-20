Minecraft **Java版1.13以降**のワールドデータ・NBTファイルを読み書きするライブラリです。

C#・TypeScript・Pythonは、それぞれのパッケージレジストリから入れられます。

```bash
dotnet add package SpringNBTLibrary   # C#（NuGet）
npm install spring-nbt-library        # TypeScript（npm）
pip install spring-nbt-library        # Python（PyPI）
```

JavaとRustは、下の成果物を落として組み込んでください。Rustはgitで参照することもできます。C#・TypeScript・Pythonの成果物も同じものを置いています。

## 成果物

| 言語 | ファイル | 組み込み方 |
|---|---|---|
| C# | `SpringNBTLibrary.*.nupkg` | 置き場所を`nuget.config`で教えて`dotnet add package` |
| C# | `SpringNBTLibrary-*-dotnet8.zip` | 展開して`.dll`を参照に追加（`.xml`を隣に置くと補完が効く） |
| Java | `spring-nbt-library-*.jar` | クラスパスへ追加、またはローカルリポジトリへinstall |
| TypeScript | `spring-nbt-library-*.tgz` | `npm install ./spring-nbt-library-*.tgz` |
| Python | `spring_nbt_library-*.whl` | `pip install spring_nbt_library-*.whl` |
| Rust | `spring-nbt-library-*.crate` | 展開してパス参照。git参照でも使えます |

言語ごとの詳しい手順は[はじめに](https://github.com/ScriptArts/SpringNBTLibrary/tree/main/docs/getting-started)を参照してください。

## 確認

`SHA256SUMS.txt`で、落としたファイルが破損していないか確かめられます。

```bash
sha256sum -c SHA256SUMS.txt
```

## ライセンス

MIT License — Copyright (c) 2026 ScriptArts

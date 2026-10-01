# はじめに

このガイドでは、まず文献探索を実行して候補を確認し、その後 MR 解析を続けます。

## 必要環境

- Python 3.11 / 3.12 を推奨し、CI で確認しています。事前チェックは Python 3.9〜3.12（3.9.7 を除く）を受け入れます。3.9 / 3.10 は CI 対象外、3.13 以降は現在ブロックされます。
- R 4.3.4 以降と [`../../references/environment.md`](../../references/environment.md) に記載の R パッケージ。
- 上流 `mragent` パッケージと対応する LLM バックエンド。
- OpenGWAS JWT を `MRAGENT_GWAS_TOKEN` または `OPENGWAS_JWT` 環境変数に設定します。

インストーラーはスキルファイルを配置するだけで、Python、R、MRAgent の依存関係はインストールしません。

## インストール

```bash
python install.py --target all
```

`--target claude`、`workbuddy`、`codebuddy`、`codex`、`deepseek` で対象を選べます。Codex の既定先は `~/.codex/skills/mr-agent`、DeepSeek Harness は `~/.dsh/skills/mr-agent` です。`CODEX_HOME` / `DSH_HOME` でルートを変更できます。`python install.py --list` はインストールせずメタデータと保存先を確認します。

## 環境を準備

Python 3.11 または 3.12 の環境を作成し、`mragent==0.2.5` と必要な R パッケージを用意して、認証情報を環境変数に設定してください。OS ごとの手順は [`../../references/environment.md`](../../references/environment.md) を参照してください。認証情報をコマンド、ソースコード、公開 issue に貼り付けないでください。

LLM や API の利用枠を消費する前に、事前チェックを実行します。

```bash
python scripts/preflight.py --no-network
```

不足項目は報告されますが、認証情報そのものは表示されません。

## 文献探索と候補確認

モードとパラメーターを確認します。

```bash
python scripts/run_mr.py --mode O --outcome "back pain" --steps 1,2 --dry-run
```

文献探索を実行します。

```bash
python scripts/run_mr.py --mode O --outcome "back pain" --steps 1,2
```

実行ディレクトリの `Exposure_and_Outcome.csv` を確認し、必要に応じて曝露・アウトカムの組を編集してから後続ステップを実行してください。

```bash
python scripts/run_mr.py --mode O --outcome "back pain" --steps 3,4,5,6,7,8,9
python scripts/summarize_output.py ./mragent-runs/back_pain_O_*/output
python tools/export_results.py ./mragent-runs/back_pain_O_*/output
```

実解析では毎回新しい作業ディレクトリを作成します。`--dry-run` はディレクトリを作らず設定だけを表示します。成功判定では終了コードだけでなく `mr_run.csv` の生成を確認します。

## モード

| モード | 必須入力 | 目的 |
| --- | --- | --- |
| `O` | `--outcome` | アウトカムから候補曝露を探索 |
| `E` | `--exposure` | 曝露から候補アウトカムを探索 |
| `OE` | `--exposure` と `--outcome` | 指定したペアを検証 |

## 同義語拡張

UMLS 同義語拡張はデフォルトでオフです。上流 MRAgent API は UMLS key を内部に持ち、現在このランナーから置き換えられません。`--synonyms` を明示すると上流の動作が有効になります。単独の `tools/mr_synonyms.py` はユーザー自身の `UMLS_API_KEY` を必要とします。

## 結果を慎重に解釈する

MR 推定値は操作変数、研究デザイン、サンプル重複、データの利用可能性に依存します。専門家がデータセットや診断結果も確認してください。結果は研究上の根拠であり、臨床助言や因果関係の証明ではありません。

## 関連ドキュメント

- [`references/api.md`](../../references/api.md) — コンストラクターとステップ
- [`references/pitfalls.md`](../../references/pitfalls.md) — 上流の既知の問題
- [`references/environment.md`](../../references/environment.md) — 環境設定
- [`SECURITY.md`](../../SECURITY.md) — 認証情報とリスク

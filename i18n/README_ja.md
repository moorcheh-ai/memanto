<p align="center"><a href="https://www.memanto.ai/"><img alt="MEMANTO ロゴ" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/memanto-logo.svg" width="500"></a></p>

<div align="center"><h1>AI エージェントが愛するメモリ</h1></div>
<h2 align="center"><em>Memanto は、他のエージェントのメモリを管理するためのコンパニオン・メモリエージェントです。残すべき情報を整理し、セッションをまたいで統合し、エージェントが開始した瞬間に要点を伝えます。学習した内容の所有権は、常にあなたにあります。</em></h2>

<p align="center">Claude Code、Cursor、Codex など 20 以上のエージェントで自動的に動作します。セマンティックバックエンドと Open Knowledge Format（LLM Wiki スタイルの *.md ファイル）を完全に相互変換できるため、メモリ資産は確認、エクスポート、どこへでも移行できます。<code>memanto migrate</code> を実行すれば、メモリも一緒に移動します。</p>
<p align="center"><code>pip install memanto</code></p>

<p align="center"><a href="https://memanto.ai/discord"><img src="https://img.shields.io/badge/Join-Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord に参加"></a> <a href="https://www.reddit.com/r/Memanto/"><img src="https://img.shields.io/badge/Join-Reddit-FF4500?style=for-the-badge&logo=reddit&logoColor=white" alt="Reddit に参加"></a> <a href="https://docs.memanto.ai"><img src="https://img.shields.io/badge/Docs-memanto.ai-000000?style=for-the-badge&logo=readthedocs&logoColor=white" alt="ドキュメント"></a></p>

---
## MEMANTO とは？

**MEMANTO はメモリエージェントです。記憶、検索、回答を行い、エージェントが長期目標を達成し混乱を避けられるようにします。**

今日の多くのメモリツールは受動的なインフラです。エージェント自身が問い合わせ、結果を解析し、次の行動を判断する必要があります。MEMANTO は異なります。エージェント自身がメモリについて語った不足点から設計された能動的なメモリエージェントです。`remember`、`recall`、`answer` の 3 操作で、セッションをまたぐ永続的なコンテキストを提供します。最先端の検索性能と、取り込み時の待ち時間ゼロを備えています。

<div align="center"><h1>Memanto の動作</h1><h2>Memanto なし</h2><img src="https://github.com/moorcheh-ai/memanto/raw/main/assets/Before.gif" alt="導入前" width="1100" style="border-radius: 8px;"><h2>Memanto 接続後</h2><img src="https://github.com/moorcheh-ai/memanto/raw/main/assets/After.gif" alt="導入後" width="1100" style="border-radius: 8px;"></div>

## 2 分で始める
macOS、Linux、Windows に対応しています。

**オプション A: 完全ローカル（アカウント・API キー不要）:**
```bash
pip install memanto
memanto           # "On-Prem" を選択。Docker + Ollama のセットアップを案内します
```
Docker が必要です。すべてあなたのマシンで実行・保存されます。

**オプション B: 無料クラウド（カード不要、約 60 秒）:**
```bash
pip install memanto
memanto           # "Cloud" を選択し、無料の Moorcheh API キーを貼り付けます
```
無料 API は https://console.moorcheh.ai/api-keys で取得できます。

`memanto config backend` でいつでもローカルとクラウドを切り替えられます。

---
## 得られるもの
- **コンテキストリセットのたびにコードベースを説明し直す必要がありません。** Memanto がセッション間で保持し、エージェントは中断地点から再開できます。
- **繰り返しのコンテキストで消費するトークンを削減。** 関連する場合にだけメモリを取得します。
- **保存直後からメモリを検索可能。** インデックス待ちや書き込み時の LLM 抽出コストはありません。
- **`pip install` 一つ。** 構築するベクトル DB、スキーマ、リランカー、保守するバックエンドサービスは不要です。
- **柔軟なデプロイ。** 完全ローカル、クラウド SaaS、独自 VPC のいずれも選べ、いつでも切り替えられます。

---
## 統合
Claude Code、Cursor、Codex、Windsurf、Cline、Continue、Goose、GitHub Copilot などで利用できます。[完全な一覧 →](https://docs.memanto.ai/integrations/overview)
```bash
memanto connect <integration-tool-id> # 1 コマンドで統合
#例: memanto connect claude-code
```

---
## 6 つの不足点
| # | 不足点 | MEMANTO の対応 |
| --- | --- | --- |
| 1 | **静的な注入**: メモリが塊で入り、関連性で検索できない | 注入ではなく検索可能 |
| 2 | **時間的減衰なし**: 6 か月前の設定と昨日の期限が同じ重み | バージョン、鮮度シグナル、時間検索 |
| 3 | **来歴なし**: 明示的な事実、推論したパターン、古い情報を区別できない | 各メモリに信頼度と来歴メタデータ |
| 4 | **フラットなメモリ**: エピソード、意味、手続きが 1 層に混在 | 13 種類を内蔵した型付き・階層型メモリ |
| 5 | **書き戻しなし**: 矛盾が黙って共存する | 競合検出、明示的バージョニング、暗黙の上書きなし |
| 6 | **インデックス遅延**: LLM 抽出とグラフ構築が必須 | オーバーヘッドなしで取り込み、書き込み時から利用可能 |

> *「私のメモリはコンテキストに注入される静的なスナップショットで、有用だが根本的には受動的だ。」* このモデルの言葉が Memanto の設計指針になりました。

---
## ベンチマーク
- **LongMemEval で 89.8%**、**LoCoMo で 87.1%**。Mem0、Zep、Letta を上回ります。[公開データセット →](https://huggingface.co/moorcheh)
- **2 つではなく 3 つのプリミティブ**: `remember`、`recall`、`answer`。追加 API キーなしで、メモリに基づく LLM 回答を提供します。
- **単一クエリ検索。** 多段パイプライン、グラフスキーマ、リランカーは不要です。
- **型付きセマンティックメモリ。** `instruction`、`fact`、`decision`、`goal`、`preference`、`relationship` など 13 カテゴリ。

---
## アーキテクチャ
Memanto の検索は情報理論的セマンティックエンジン [Moorcheh](https://moorcheh.ai) を使用します。無料・アカウント不要のローカル Docker コンテナ、または 10 万回無料操作を含むクラウドサービスとして動作し、`memanto` CLI が管理します。
<p align="center"><img alt="MEMANTO アーキテクチャ" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/Architecture-diagram.png" width="1000"></p>
### オンプレミス
<p align="center"><img alt="MEMANTO オンプレミスアーキテクチャ" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/On-prem-architecture-diagram.png" width="1000"></p>

---
## なぜ Moorcheh？
Moorcheh は Memanto の検索を支えるセマンティックエンジンです。近似検索とインデックスパイプラインに依存するベクトルデータベースとは異なり、情報理論的手法により、インデックス遅延なく正確な結果を返します。メモリを書き込めば、すぐに検索できます。

そのため Memanto には個別のベクトル DB、埋め込みパイプライン、再ランキング段階が必要ありません。Moorcheh はオンプレミス向けのローカル Docker コンテナ、または無料枠を持つマネージドクラウドとして動作します。どちらも `memanto` CLI が処理します。

---
## セットアップとデモ
<p align="center"><a href="https://www.youtube.com/watch?v=vEtOaoweIG4"><img src="https://github.com/moorcheh-ai/memanto/raw/main/assets/video-demo.png" alt="セットアップ動画"></a></p>
## 最適な体験のためのローカルダッシュボード
<p align="center"><a href="https://www.youtube.com/watch?v=5n976CmzohE"><img src="https://github.com/moorcheh-ai/memanto/raw/main/assets/video-uidashboard.png" alt="ローカルダッシュボードのデモ"></a></p>

---
## CLI リファレンス
| 機能 | コマンド | 内容 |
|---|---|---|
| システム状態ダッシュボード | `memanto status` | 環境、設定、サーバーヘルス、アクティブセッション、登録済みエージェントを表示。 |
| ローカル REST API と Web UI | `memanto serve`, `memanto ui` | MEMANTO REST API をローカル実行し、対話的なブラウザ UI を開く。CLI のみの利用では任意。 |
| エージェントのライフサイクル | `memanto agent ...` | エージェントの作成、一覧、削除、セッションの有効化・無効化、`agent bootstrap` を実行。 |
| メモリの記録 | `memanto remember` | 個別に保存、JSON から一括取り込み、`--from-conversation` でチャットログから事実を抽出。 |
| 編集と削除 | `memanto edit`, `memanto forget` | 既存メモリを更新、または誤った・古いメモリを完全に削除。 |
| ファイルアップロード | `memanto upload` | .pdf、.docx、.xlsx、.json、.txt、.csv、.md をエージェントの名前空間に保存し、`recall` で即時検索。 |
| 高度な検索 | `memanto recall` | フィルタ付き標準検索と時間クエリ（`--as-of`、`--changed-since`）を実行。 |
| メモリに基づく QA | `memanto answer` | 取得したメモリコンテキストで RAG 回答を生成。 |
| 日次インテリジェンス | `memanto daily-summary`, `memanto conflicts` | 要約生成、矛盾検出、対話的な解決。 |
| セッションと自動化 | `memanto session ...`, `memanto schedule ...` | セッションを確認し、日次要約をスケジュール。 |
| メモリファイル | `memanto memory export`, `memanto memory sync` | 構造化 Markdown をエクスポートし、`MEMORY.md` を同期。`--okf` で [Open Knowledge Format](https://docs.memanto.ai/integrations/okf) バンドルに対応。 |
| インポートと移行 | `memanto migrate` | Mem0、Letta、Supermemory、または [OKF](https://docs.memanto.ai/integrations/okf) バンドルからインポート。 |
| 設定確認 | `memanto config show` | API キー、アクティブなエージェントとセッション、サーバー設定、スケジュール時刻を確認。 |
| マルチエージェント統合 | `memanto connect ...` | Claude Code、Codex、Cursor、Windsurf、Antigravity、Gemini CLI、Cline、Continue、OpenCode、Goose、Roo、GitHub Copilot、Augment の統合を接続・削除・一覧表示。 |

完全なコマンドリファレンスは [CLI ユーザーガイド](https://docs.memanto.ai/cli) を参照してください。

### 対応するメモリタイプ
`instruction`, `fact`, `decision`, `goal`, `commitment`, `preference`, `relationship`, `context`, `event`, `learning`, `observation`, `artifact`, `error`
- 型を指定して保存: `memanto remember "ユーザーは簡潔な回答を好む" --type preference`
- 型でフィルタ: `memanto recall "ユーザーのコミュニケーションスタイル" --type preference`

---
## SDK
- **TypeScript / Node.js**: [`@moorcheh-ai/memanto`](../sdks/typescript) は `uvx` でローカル Memanto サーバーを起動し、使いやすい `Memanto` クライアント（`remember` / `recall` / `answer`）を公開します。

---
## REST API
Memanto はセッションベースの REST API を提供します。ローカルサーバーを起動します:
```bash
memanto serve
```
完全なエンドポイントリファレンスは [docs.memanto.ai/api](https://docs.memanto.ai/api) と、実行中の `http://localhost:8000/docs` で確認できます。

---
## 研究
[Memanto: Typed Semantic Memory with Information-Theoretic Retrieval for Long-Horizon Agents](https://huggingface.co/papers/2604.22085)
```bibtex
@misc{abtahi2026memantotypedsemanticmemory,
      title={Memanto: Typed Semantic Memory with Information-Theoretic Retrieval for Long-Horizon Agents},
      author={Seyed Moein Abtahi and Rasa Rahnema and Hetkumar Patel and Neel Patel and Majid Fekri and Tara Khani},
      year={2026}, eprint={2604.22085}, archivePrefix={arXiv}, primaryClass={cs.AI},
      url={https://arxiv.org/abs/2604.22085},
}
```

---
## サポート
- **ドキュメント**: [https://docs.memanto.ai](https://docs.memanto.ai)
- **Discord**: [Discord サーバーに参加](https://memanto.ai/discord)
- **Reddit**: [Reddit コミュニティに参加](https://www.reddit.com/r/Memanto/)
- **メール**: support@moorcheh.ai
- **X / Twitter**: [@moorcheh_ai](https://x.com/moorcheh_ai)

---
**MIT ライセンス**

<br>
<p align="center">
  <a href="../README.md">English</a> | <a href="README_es.md">Español</a> | <a href="README_zh-CN.md">简体中文</a> | <a href="README_ja.md">日本語</a>
</p>
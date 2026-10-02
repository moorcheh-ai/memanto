<p align="center">
  <a href="https://www.memanto.ai/">
    <img alt="Memanto" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/memanto-logo.svg" width="440">
  </a>
</p>

<h3 align="center">AI エージェントが愛するメモリ！</h3>

<p align="center">Memanto は<strong>メモリエージェント</strong>です。他のエージェントの記憶について、<br>残すもの、矛盾するもの、期限切れになるもの、知らせるべき相手を管理します。</p>

<p align="center">
  <a href="https://github.com/moorcheh-ai/memanto"><img alt="GitHub stars" src="https://img.shields.io/github/stars/moorcheh-ai/memanto?style=social"></a>
  <a href="https://pepy.tech/projects/memanto"><img alt="Downloads" src="https://static.pepy.tech/personalized-badge/memanto?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=downloads"></a>
  <a href="https://arxiv.org/abs/2604.22085"><img alt="arXiv" src="https://img.shields.io/badge/arXiv-2604.22085-b31b1b.svg"></a>
  <a href="https://pypi.org/project/memanto/"><img alt="PyPI" src="https://img.shields.io/pypi/v/memanto.svg?color=%2334D058"></a>
  <a href="https://opensource.org/licenses/MIT"><img alt="MIT License" src="https://img.shields.io/badge/license-MIT-yellow.svg"></a>
</p>

```bash
pip install memanto
```
<!-- ============================================================
     デモ GIF — 最も重要な未追加アセット。assets/demo.gif
     VHS テープは別途提供。15 秒未満、3 MB 未満。
     ============================================================ -->
<p align="center">
  <img alt="15 秒でわかる Memanto" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/demo.gif" width="900">
</p>

---
> **すべてのプラットフォームはエージェントの記憶を保存します。管理はしません。** プラットフォーム横断で管理することは彼らの利益に反します。それがメモリエージェントの仕事です。

永続化はすでに解決されています。Claude、Bedrock、Cursor、あらゆるベクトルストアはエージェントの書いた内容を保存しますが、認証サービスについて二つのエージェントが正反対のことを信じていること、古い設定が新しい判断を上書きしていること、別のエージェントが完了して戻した作業をやり直そうとしていることは教えてくれません。

ストレージは書類棚です。Memanto は参謀役として、入れるものを決め、アクセスを見守り、矛盾を解消し、古いものを捨て、エージェントが動く前に要点を伝えます。

---
## API ではなくエージェント

Memanto は呼び出すライブラリではありません。あなたのフリートと並行して動き、自ら判断して六つの仕事をする第二のエージェントです。どれもコマンドで裏付けられた実際の動作で、ロードマップ項目ではありません。
| | Memanto の仕事 | 実行 |
|---|---|---|
| **観察と抽出** | 一時的な対話から、決定、好み、事実、失敗という永続的知識を抽出します。 | `memanto remember --from-conversation` |
| **統合** | 重複を畳み、断片を結び、繰り返しの観察で信頼度を高め、一つの正規資産へ統合します。 | `memanto schedule enable` |
| **照合** | 新しい知識が古い知識と矛盾するとき、追記でなく置換し、いつ何を信じたかを残します。 | `memanto conflicts` |
| **忘却** | 減衰、期限切れ、意図的な削除をポリシーとして実行します。 | `memanto forget` |
| **ブリーフィング** | 行動前に最小限の関連部分を渡します。エージェントは自分で問い合わせません。 | `memanto agent bootstrap` |
| **知識の移動** | Open Knowledge Format により、フレームワークやベンダーをまたいで一つの記憶を共有します。 | `memanto memory export --okf` |

**寝ている間にも動きます。** `memanto schedule enable` は毎日、新しい記憶を整理し、重複を統合し、矛盾をレビュー用に表示します。

---
## 60 秒で管理されたフリートへ

```bash
pip install memanto
memanto                            # "On-Prem"（Docker、アカウント不要）または "Cloud"（無料キー）
memanto connect claude-code        # cursor, codex, windsurf, cline, goose, copilot… も対応
```
コード変更も wrapper もエージェントループの書き換えも不要で、エージェントは管理された一つの資産を共有します。

```bash
# backend-agent が月曜に学習
memanto remember "Auth migrated to JWT — session cookies deprecated" --type decision
# review-agent はそのセッションを見ていなくても金曜に知っている
memanto recall "how does auth work"
memanto answer  "why did we drop session cookies?"     # 根拠付き、追加 API キー不要
# 先週火曜にフリートは何を信じたか？リリース後に何が変わったか？
memanto recall "deployment policy" --as-of 2026-08-05
memanto recall "deployment policy" --changed-since v2.1
```
macOS、Linux、Windows に対応。`memanto ui` は資産全体を閲覧、検索、監査できるローカルダッシュボードを開きます。

---
## エージェントの記憶を所有する
**資産はファイルです。** `memanto memory export --okf` は[Open Knowledge Format](https://docs.memanto.ai/integrations/okf)を提供します。これは可読、diff、commit、grep が可能なプレーン Markdown で、名目だけの専有エクスポートではなく実際の作業形式です。

**移動します。** `memanto migrate` は Mem0、Letta、Supermemory、任意の OKF バンドルからインポートし、逆方向にも動作します。OKF は競合他社を含む誰もが実装できるオープンな交換形式です。

**自分のマシンで動きます。** ローカル Docker + Ollama ならアカウントも API キーも不要で、インフラ外へ出ません。無料クラウドや自前ホストも選べ、`memanto config backend` で切り替え、資産を持ち運べます。

**MIT。** open-core の壁、機能フラグ、席数制限、突然の撤回はありません。ロックするものがないためロックインもありません。

---
## セキュリティと主権
<!-- ============================================================
     TODO — Majid: ハードニング作業に基づき記入。構造は正しい。
     ⟨…⟩ の項目には入力が必要。裏付けられないものは弱めず削除。
     ============================================================ -->
**オンプレミスでは何もマシン外へ出ません。** Docker + Ollama、アカウントなし、外向き呼び出しなしで、抽出、統合、照合、ブリーフィングの全ループがローカル実行されます。

**既定でスコープ分離。** 各エージェントには名前空間があり、知るべき内容だけを割り当てます。

**すべての信念は追跡可能。** 信頼度、ソース、来歴、タイムスタンプから、いつどこでフリートに入ったかを辿れます。

**忘却は副作用ではなくあなたの判断です。** メモリは `active` または `expired` のみ。書いたポリシーによってだけ期限切れになり、日付とルール名を持ちます。期限切れでも明示的に表示され、`memanto memory restore` で戻せます。削除は別の明示的操作です。

---
## 自分の条件で期限切れにするメモリ
各メモリはポリシーが退役させるまで**有効**です。期限切れは記録、監査、復元可能で、内容は `[EXPIRED]` と理由付きで検索に残ります。

```bash
memanto policy list-preset          # conservative / balanced / aggressive
memanto policy apply-preset balanced  # 全体を表示して確認
memanto policy apply --dry-run      # ルールごとに期限切れになるもの
memanto policy apply                # ポリシーと一致項目を表示して確認
```
ポリシーは `~/.memanto/policies/<agent>.yaml` にあり、型別保持表と名前付きルールで構成されます。最初に一致したルールが勝つため、期限切れになるメモリを*固定*できます。

```yaml
retention:
  context: 7d
  event: 30d
  preference: never          # 永続的なユーザーの真実は古びない
rules:
  - name: pinned
    match: {tags: [pinned]}
    expire_after: never      # 明示的な固定が表より優先
  - name: low-confidence-guesses
    match: {provenance: [inferred], confidence_below: 0.5}
    expire_after: 14d
purge_expired_after: never   # 任意の完全削除。既定では無効
```
両状態は並べて表示され、`--active`、`--expired` で絞れます。`--as-of` は後に期限切れになったメモリも含め当時を再構築します。

```bash
memanto memory expire mem-123       # 一つを手動で退役
memanto memory restore mem-123      # 戻す
```
夜間ジョブ（`memanto schedule enable`）が掃除を実行し、ポリシーのないエージェントは何も期限切れにしません。

---
## メモリストレージとの違い
| | メモリストレージ | **Memanto** |
|---|---|---|
| 正体 | SDK 付きデータベース：書く、埋め込む、取得する | フリートの記憶を判断するエージェント |
| 中核動作 | 保存 | 選別、照合、統合、忘却、ブリーフィング |
| 保持を決める者 | アプリケーションコードのあなた | 一度設定するポリシーに従う Memanto |
| 意見の不一致 | 最後の書き込みが黙って勝つ | 両方を版管理しレビューへ提示 |
| 忘却 | 覚えて実行する `DELETE` | スケジュールで動く第一級のポリシー |
| 範囲 | 一つのアプリ、一つのスタック、一社の壁 | スタックとベンダーをまたぐフリート |
| データ | 理論上はエクスポート可能 | 作業形式*そのもの*が可搬 Markdown |

ベクトルストア、ファイルシステム、プラットフォーム固有メモリはすべて Memanto *の下* にあり、管理対象のバックエンドです。

---
<p align="center">
  <strong>⭐ Memanto がフリートの記憶を管理しているならリポジトリにスターを</strong><br>
  <sub>MIT の下で何も隠さずオープンに作り続けるための合図です。</sub></p>

---
## 開発者体験
**`pip install` 一つ。** ベクトルストア、embedding パイプライン、reranker、スキーマ移行、見守るバックエンドは不要で、検索エンジンも同梱です。

**今使っているものと動きます。** `memanto connect claude-code`、Cursor、Codex、Windsurf、Cline、Continue、Goose、Copilot なども各一コマンドです。

**書いた瞬間に検索可能。** 書き込み時の抽出、再構築するグラフ、インデックス待ち行列はありません。`remember` が戻れば全エージェントが検索できます。

**スープではなく型付き。** `instruction`、`fact`、`decision`、`goal`、`preference`、`relationship` など 13 カテゴリで、検索を絞れます。

**ログファイルではなくダッシュボード。** `memanto ui` は全資産、`memanto daily-summary` は変更の要約、`memanto status` はエージェント、セッション、健全性を表示します。

---
<details><summary><strong>完全な CLI リファレンス</strong></summary>
<br>

| 機能 | コマンド | 内容 |
|---|---|---|
| システム状態 | `memanto status` | 環境、設定、サーバーヘルス、アクティブセッション、登録済みエージェント。 |
| ローカル REST API + Web UI | `memanto serve`, `memanto ui` | REST API をローカル実行し対話的 UI を開く。 |
| エージェントライフサイクル | `memanto agent ...` | 作成、一覧、削除、セッション有効化、`agent bootstrap`。 |
| 大規模メモリ取得 | `memanto remember` | 単一、バッチ JSON、`--from-conversation`。 |
| 編集と削除 | `memanto edit`, `memanto forget` | メモリ更新または完全削除。 |
| ファイル取り込み | `memanto upload` | .pdf、.docx、.xlsx、.json、.txt、.csv、.md を名前空間へ。 |
| 高度な検索 | `memanto recall` | フィルター付きの通常・時点検索（`--as-of`、`--changed-since`）。 |
| 根拠付き回答 | `memanto answer` | 取得メモリから回答を生成。 |
| 日次インテリジェンス | `memanto daily-summary`, `memanto conflicts` | 要約、矛盾検出、対話的解決。 |
| セッションと自動化 | `memanto session ...`, `memanto schedule ...` | セッション確認、日次実行を有効化。 |
| 資産のエクスポートと同期 | `memanto memory export`, `memanto memory sync` | 構造化 Markdown を出力し `MEMORY.md` を同期。`--okf` は可搬 [OKF](https://docs.memanto.ai/integrations/okf) バンドル。 |
| インポートと移行 | `memanto migrate` | Mem0、Letta、Supermemory、OKF からインポート。 |
| 設定 | `memanto config show` | API キー、アクティブなエージェント/セッション、サーバー、予定時刻。 |
| フリート統合 | `memanto connect ...` | Claude Code、Codex、Cursor、Windsurf、Antigravity、Gemini CLI、Cline、Continue、OpenCode、Goose、Roo、GitHub Copilot、Augment。 |

**メモリタイプ：** `instruction`, `fact`, `decision`, `goal`, `commitment`, `preference`, `relationship`, `context`, `event`, `learning`, `observation`, `artifact`, `error`

```bash
memanto remember "User prefers concise answers" --type preference
memanto recall "user communication style" --type preference
```
完全な参照：[CLI User Guide](https://docs.memanto.ai/cli)
</details>

<details><summary><strong>インストールオプション：完全ローカルと無料クラウド</strong></summary>
<br>
**完全ローカル。アカウント、API キー不要。何もマシン外へ出ません：**

```bash
pip install memanto
memanto           # "On-Prem" を選択。Docker + Ollama セットアップを案内
```
Docker が必要です。

**無料クラウド。カード不要、約 60 秒：**

```bash
pip install memanto
memanto           # "Cloud" を選択。無料 API キーを貼り付け
```
無料キーは [console.moorcheh.ai/api-keys](https://console.moorcheh.ai/api-keys) から。100K 回の無料操作。

いつでも切り替え：`memanto config backend`
</details>

<details><summary><strong>アーキテクチャ</strong></summary>
<br>
検索は同梱の情報理論的セマンティックエンジンで動作し、ローカル Docker コンテナまたは無料クラウドサービスとして提供されます。`memanto` CLI がどちらも管理します。下位のストレージはプラグイン可能で、Memanto はその上のエージェントです。
<p align="center">
  <img alt="アーキテクチャ" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/Architecture-diagram.png" width="900">
</p>
**オンプレミス：**
<p align="center">
  <img alt="オンプレミスアーキテクチャ" src="https://github.com/moorcheh-ai/memanto/raw/main/assets/On-prem-architecture-diagram.png" width="900">
</p>
</details>

<details><summary><strong>SDK と REST API</strong></summary>
<br>
**TypeScript / Node.js** — [`@moorcheh-ai/memanto`](../sdks/typescript) は `uvx` でローカル Memanto サーバーを起動し、使いやすいクライアント（`remember` / `recall` / `answer`）を公開します。

**REST API** — `memanto serve` で開始。エンドポイントは [docs.memanto.ai/api](https://docs.memanto.ai/api) と、実行中の `http://localhost:8000/docs` にあります。
</details>

---
## 動作を見る
| | |
|---|---|
| [**Recall は検索以上のもの**](https://youtu.be/zoKP4b_rUhY) — 6:20 | [**セットアップとデモ**](https://www.youtube.com/watch?v=vEtOaoweIG4) |
| [**ローカルダッシュボードツアー**](https://www.youtube.com/watch?v=5n976CmzohE) | [**ドキュメント →**](https://docs.memanto.ai) |

---
## 研究
**[Memanto: Typed Semantic Memory with Information-Theoretic Retrieval for Long-Horizon Agents](https://arxiv.org/abs/2604.22085)**

公開 recall ベンチマークでは LongMemEval 89.8%、LoCoMo 87.1% を報告しています。<!-- TODO: reader model、judge model、subset をここに記載。条件を分かりやすく示す。 --> データセットとハーネスは [huggingface.co/moorcheh](https://huggingface.co/moorcheh) で公開されています。

率直な注意点：これらのベンチマークのプロジェクト間スコアは比較できません。reader model、judge model、judge prompt、検索予算のいずれも数ポイント結果を動かし、公開実行に同じ設定はありません。私たちの数字を含め、方向性として扱ってください。メモリエージェントが最終的に測るべきものは recall ではなく、時間に伴う資産品質、矛盾率、古さ、6 か月時点の精度です。

```bibtex
@misc{abtahi2026memantotypedsemanticmemory,
      title={Memanto: Typed Semantic Memory with Information-Theoretic Retrieval for Long-Horizon Agents},
      author={Seyed Moein Abtahi and Rasa Rahnema and Hetkumar Patel and Neel Patel and Majid Fekri and Tara Khani},
      year={2026},
      eprint={2604.22085},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2604.22085},
}
```

---

## コミュニティ
<p align="center">
  <a href="https://memanto.ai/discord"><img src="https://img.shields.io/badge/Join-Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord"></a>
  <a href="https://www.reddit.com/r/Memanto/"><img src="https://img.shields.io/badge/Join-Reddit-FF4500?style=for-the-badge&logo=reddit&logoColor=white" alt="Reddit"></a>
  <a href="https://docs.memanto.ai"><img src="https://img.shields.io/badge/Docs-memanto.ai-000000?style=for-the-badge&logo=readthedocs&logoColor=white" alt="Docs"></a>
</p>

<p align="center">
  <a href="https://trendshift.io/repositories/27378"><img src="https://trendshift.io/api/badge/repositories/27378" alt="Trendshift" width="220"></a>
  <!-- <a href="https://mcptoplist.com/server/glama%2Fmoorcheh-ai%2Fmemanto"><img src="https://mcptoplist.com/badge/glama%2Fmoorcheh-ai%2Fmemanto.svg" alt="MCP Top List" width="220"></a> -->
  <a href="https://deepwiki.com/moorcheh-ai/memanto"><img alt="DeepWiki" src="https://deepwiki.com/badge.svg"></a>
</p>

質問：[support@moorcheh.ai](mailto:support@moorcheh.ai) · [@moorcheh_ai](https://x.com/moorcheh_ai)

---
<p align="center">
  <strong>MIT License</strong><br>
  <sub><a href="../README.md">English</a> · <a href="README_es.md">Español</a> · <a href="README_zh-CN.md">简体中文</a> · <a href="README_ja.md">日本語</a></sub>
</p>

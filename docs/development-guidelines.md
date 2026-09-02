# 開発ガイドライン — ユーチューブ要約

本書は `docs/architecture.md`（技術スタック）・`docs/repository-structure.md`（フォルダ構成）を前提に、
本リポジトリのコーディング規約を定義する。レビュー時に機械的に判定できる具体性を持たせることを目的とする。

## 命名規則

### ファイル名
- フロントの JS は小文字1語または camelCase + `.js`: `app.js`
- スタイルは `style.css`
- Python スクリプトは snake_case + `.py`: `update.py`、`resolve_channels.py`
- データファイルは小文字 + `.json`: `channels.json`、`summaries.json`

### 変数・関数名
- JavaScript: 変数・関数は camelCase（`loadData`、`formatWhen`）、モジュール定数は UPPER_SNAKE_CASE。
- Python: 変数・関数は snake_case、モジュール定数は UPPER_SNAKE_CASE（`MAX_PER_RUN`、`LOOKBACK_DAYS`、`MODEL`）。
- 真偽を返すものは `is` / `has` で始める（JS: `isFresh()` / Python: `is_fresh()`）。

### JSON のフィールド名
- すべて snake_case（`video_id`、`published_at`、`channel_id`、`summarized_at`）。
- フロント（`app.js`）とスクリプト（`update.py`）で同じ名前を使う。正は `docs/functional-design.md` のデータモデル表。

### CSS クラス名
- ケバブケース。コンポーネント名を接頭辞にして衝突を避ける: `.card`、`.card__title`、`.card__meta`、`.filter-bar`。
- 色・余白・フォントサイズは `style.css` 先頭の CSS カスタムプロパティ（`--color-*`、`--space-*`）を使い、数値を直書きしない。

### 日本語・英語の使い分け
- コード上の識別子（変数・関数・ファイル・CSSクラス・JSONキー）はすべて英語。
- 画面に表示する文言・`aria-label`・要約プロンプトは日本語。
- 表示文言は `app.js` 先頭の定数、または `index.html` にまとめ、散らばらせない。
- ドメイン用語の英日対応は `docs/glossary.md` を正とする。

## コーディング規約（フロント: index.html / assets）
- モジュールは ESM（`<script type="module">`）。外部CDN・npm パッケージは使わない。
- セミコロンなし、シングルクォート、インデント2スペース。
- 非同期は `async` / `await`。`.then()` チェーンは使わない。
- `fetch` するのは自リポジトリ内の `data/summaries.json` のみ。外部APIをブラウザから呼ばない。
- 日時の表示整形は必ず `formatWhen()` を通す（表記のばらつき防止）。
- DOM 生成は `textContent` を使い、要約や外部由来の文字列を `innerHTML` に入れない（XSS防止）。
- マジックナンバーを埋め込まず意味のある定数名を付ける。
- 1関数1責務。`app.js` は「読み込み → 絞り込み → 描画」の流れが追える構成にする。

## コーディング規約（バッチ: scripts/*.py）
- Python 3.12。標準ライブラリを優先し、依存は `google-genai` のみに留める（増やす場合は `architecture.md` を更新）。
- 調整用の設定値はファイル冒頭の定数に集約（`MODEL` / `MAX_PER_RUN` / `LOOKBACK_DAYS` / `KEEP_ITEMS`）。
- `GEMINI_API_KEY` は `os.environ` から読む。コードに書かない・ログに出さない・例外メッセージに含めない。
- 外部アクセス（RSS取得・Gemini 呼び出し）は必ず try/except で囲み、1件の失敗で全体を止めない。
- 失敗した動画は `status: "failed"` で記録し、次回実行で再試行する。リトライ上限（`MAX_RETRY`）を超えたら諦める。
- `summaries.json` は「読み込む → マージする → 全体を書き出す」。既存データを壊さない。
  書き出しは `ensure_ascii=False`、`indent=2`、末尾改行あり。
- 標準出力に進捗（対象チャンネル数・新着件数・要約成功/失敗数）を出す。Actions のログで追えるようにする。

## UI・アクセシビリティ
- 操作要素は適切な要素を使う（リンクは `<a>`、選択は `<select>`）。`div` のクリックで代用しない。
- 絞り込み `<select>` には `<label>` を関連付ける。
- サムネイル `<img>` には `alt`（動画タイトル）と `loading="lazy"` を付ける。
- レイアウトはモバイルファースト。スマホ幅で横スクロールを発生させない。
- ライト／ダーク両対応（`prefers-color-scheme`）。本文コントラストは WCAG AA（4.5:1）目安。
- 外部リンク（YouTube）は `rel="noopener"` を付け、新しいタブで開く。

## データ・秘密情報の扱い
- `data/summaries.json` は Actions が自動更新する。人間が手編集しない。
- `data/channels.json` は手編集可。編集後 `resolve_channels.py` で `channel_id` を補完・検証する。
- `GEMINI_API_KEY` は GitHub Actions Secrets のみ。`.env` を作る場合は必ず `.gitignore` に含める。
- 個人情報・YouTube アカウント情報は一切保存しない。

## Git規約
- コミットメッセージは Conventional Commits のプレフィックスを付ける:
  `feat:` / `fix:` / `docs:` / `chore:` / `style:` / `refactor:`（プレフィックスは英語、本文は日本語可）。
  - 例: `feat: チャンネル絞り込みプルダウンを追加`
- ブランチ名は `feature/<概要>` ・ `fix/<概要>` のケバブケース英語（例: `feature/summary-list`）。
- 1コミットは1つの論理的な変更に留める。
- `main` へは基本ブランチ → マージ。ただし Actions による `data/summaries.json` の自動コミットは
  `github-actions[bot]` が直接 `main` に push する（データ更新のみ）。
- `node_modules/` ・ ローカル生成物 ・ `.env` はコミットしない（`.gitignore`）。
- ドキュメントを伴う変更は `docs/` を先に更新してから実装する（CLAUDE.md のワークフロー）。

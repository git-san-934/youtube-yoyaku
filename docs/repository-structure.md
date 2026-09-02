# リポジトリ構造定義書 — ユーチューブ要約

本書は `docs/architecture.md` で確定した技術スタック（静的 HTML/CSS/JS ＋ GitHub Actions(Python) ＋ Gemini API）を前提に、
本リポジトリのフォルダ・ファイル構成を定義する。コード実装開始前時点のスナップショットである。

## 全体構成（リポジトリルート）

アプリ本体（`index.html` と `assets/`）はリポジトリ直下に置き、GitHub Pages（main / root）への配信を単純化する。

```
youtube-yoyaku/                    # GitHub リポジトリ名（ローカルの作業フォルダ名も同じ）
├── docs/                          # 恒久的ドキュメント（本書もここに含まれる）
│   ├── product-requirements.md
│   ├── functional-design.md
│   ├── architecture.md
│   ├── repository-structure.md
│   ├── development-guidelines.md
│   └── glossary.md
├── .steering/                     # 作業単位のステアリングファイル
│   └── [YYYYMMDD]-[開発タイトル]/
│       ├── requirements.md
│       ├── design.md
│       └── tasklist.md
├── .github/
│   └── workflows/
│       └── update.yml             # 6時間おき＋手動実行。update.py を回して summaries.json を更新・push
├── data/
│   ├── channels.json              # フォロー中チャンネル一覧（handle / channel_id / name）。手動編集
│   └── summaries.json             # 自動生成。要約済み動画の一覧（新しい順・最大200件）
├── scripts/
│   ├── requirements.txt           # google-genai など Python 依存
│   ├── resolve_channels.py        # @名 → channel_id を解決して channels.json を整える（随時・手動）
│   └── update.py                  # 新着検知 → Gemini 要約 → summaries.json 書き出し（Actions が実行）
├── assets/
│   ├── style.css                  # レスポンシブ、ライト/ダーク、テーマ用 CSS 変数
│   └── app.js                     # summaries.json を読み込み、絞り込み・カード描画
├── index.html                    # 単一画面。ヘッダー・絞り込み・カード一覧の器
├── .nojekyll                     # GitHub Pages の Jekyll 処理を無効化
├── .gitignore                    # ローカル生成物・.env など
├── LICENSE
└── README.md                     # 使い方・公開手順・Gemini キー設定・チャンネル追加手順
```

## ディレクトリ・主要ファイルの役割

| パス | 役割 | 対応する `functional-design.md` の要素 |
|---|---|---|
| `index.html` | 画面の器（ヘッダー・注意書き・絞り込み・一覧コンテナ） | 要約一覧画面 |
| `assets/app.js` | `data/summaries.json` の読み込み、チャンネル絞り込み、カード描画、日時整形 | `loadData` / `renderFilter` / `render` / `formatWhen` / `setupControls` |
| `assets/style.css` | 画面スタイル（レスポンシブ・ダークモード・カードレイアウト） | 要約一覧画面 |
| `data/channels.json` | 監視対象チャンネルの定義。追加・削除はこのファイルを直接編集 | channels.json データモデル |
| `data/summaries.json` | 要約データ。`update.py` が生成し、フロントが読む唯一のデータ源 | summaries.json データモデル |
| `scripts/update.py` | RSS取得 → 未要約動画抽出 → Gemini 要約 → `summaries.json` 更新 | 定期バッチ |
| `scripts/resolve_channels.py` | @名からチャンネルIDを取得して `channels.json` を補完・検証 | 新着検知のしくみ（前準備） |
| `scripts/requirements.txt` | `google-genai`（Gemini SDK）。RSS/HTTP は標準ライブラリで足りる想定 | 定期バッチ |
| `.github/workflows/update.yml` | 定期・手動で `update.py` を実行し、変更を commit / push | システム構成（cron） |

**注**: 利用者ごとのデータは扱わない。ブラウザに保存されるのは「絞り込みの選択」（localStorage・任意）のみで、リポジトリには含まれない。
`GEMINI_API_KEY` はリポジトリに置かず、GitHub Actions Secrets に保管する。

## ファイル配置ルール

- **チャンネルを追加・削除する場合**: `data/channels.json` を編集する。新規は `handle` だけ書いて
  `scripts/resolve_channels.py` を実行すれば `channel_id` と `name` が補完される。他のファイルは変更しない。
- **要約の指示（プロンプト）を変える場合**: `scripts/update.py` 内のプロンプト定数のみを編集する。
- **1実行あたりの件数・対象日数・モデルを変える場合**: `scripts/update.py` 冒頭の設定値
  （`MAX_PER_RUN` / `LOOKBACK_DAYS` / `MODEL`）を変更する。フロントは変更不要。
- **画面の見た目を変える場合**: `assets/style.css` を編集する。表示ロジックは `assets/app.js`。
  `index.html` は構造の骨組みのみとし、テキスト整形は `app.js` 側で行う。
- **実行頻度を変える場合**: `.github/workflows/update.yml` の `cron` を編集する。
- **ドキュメント**: 設計判断・仕様の記録は `docs/` に置く。`README.md` には手順（公開設定・キー登録・
  チャンネル追加・ローカル確認）のみを記載する。
- **データファイル**: `data/summaries.json` は Actions が自動更新する。人間が手で編集しない
  （手編集すると次回実行時の差分・重複判定と競合しうる）。

# tasklist.md — 初回実装タスク

## 1. リポジトリの土台
- [x] `.gitignore`（`__pycache__/`、`.env`、`*.pyc`、`.DS_Store`）
- [x] `.nojekyll`（空ファイル）
- [x] `LICENSE`（配置済み）
- [x] `CLAUDE.md`（配置済み）

## 2. チャンネルデータ
- [x] `data/channels.json` に初期20チャンネルを `handle` のみで作成
- [x] `scripts/resolve_channels.py`
  - [x] `channel_id` 空の行について `youtube.com/<handle>` を取得（非ASCIIは URL エンコード、UA 明示、1秒スリープ）
  - [x] canonical / `"channelId"` / `itemprop=identifier` の順で `UC...` を抽出
  - [x] `og:title` から `name` を取得
  - [x] 解決分を `channels.json` に上書き保存、未解決 `handle` を標準エラーに一覧表示
- [x] ローカルで `resolve_channels.py` を実行し、`channels.json` を完成させてコミット

## 3. 要約バッチ
- [x] `scripts/requirements.txt`（`google-genai`）
- [x] `scripts/update.py`
  - [x] 設定定数（`MODEL` / `MAX_PER_RUN=6` / `LOOKBACK_DAYS=5` / `MAX_NEW_PER_CHANNEL=4` / `KEEP_ITEMS=200` / `MAX_RETRY=3`）
  - [x] `channels.json` / `summaries.json` 読み込み、`video_id` インデックス化
  - [x] RSS取得・解析（標準ライブラリ、名前空間対応、チャンネル単位で失敗を握りつぶす）
  - [x] 候補抽出（failed再試行分 ＋ 未要約かつ5日以内・1チャンネル最大4本）→ 公開昇順 → 最大6件
  - [x] Gemini 呼び出し（動画URL＋`PROMPT`、`max_output_tokens=500`、低解像度）
  - [x] 成功/失敗を項目へ反映、クォータ超過で `break`
  - [x] `GEMINI_API_KEY` 未設定時は要約スキップ（一覧化のみ）
  - [x] マージ → `published_at` 降順 → 200件に切り詰め → 変更あれば書き出し（`ensure_ascii=False`, `indent=2`）
  - [x] 集計を標準出力へ
- [x] `data/summaries.json` の初期ファイル（`{"updated_at": null, "items": []}`）を作成
- [ ] ローカルで `GEMINI_API_KEY` を設定して `update.py` を1回実行し、要約が入ることを確認

## 4. フロントエンド
- [x] `index.html`（ヘッダー・注意書き・チャンネル `<select>`＋`<label>`・一覧コンテナ・空メッセージ）
- [x] `assets/style.css`（CSS変数、モバイルファースト、ライト/ダーク、カードレイアウト、横スクロール防止）
- [x] `assets/app.js`
  - [x] `loadData()`（キャッシュ回避クエリ、失敗時メッセージ）
  - [x] `renderFilter()`（重複なしチャンネル一覧、localStorage 復元）
  - [x] `render()` / `card()`（降順、`textContent` で要約挿入、`failed` は「要約準備中」）
  - [x] `formatWhen()`（24時間以内は相対、以降は M/D、JST）
  - [x] `setupControls()`（選択を localStorage 保存）
  - [x] ヘッダーの「最終更新」表示
- [x] ローカル（`python -m http.server`）で表示確認：一覧・絞り込み・スマホ幅・ダークモード

## 5. 自動更新
- [x] `.github/workflows/update.yml`（6時間おき＋手動、`contents: write`、`GEMINI_API_KEY` を env に、差分commit）

## 6. 公開まわり
- [x] `README.md`
  - [x] これは何か／公開URL
  - [x] GitHub Pages 設定手順（Settings → Pages → Deploy from a branch → main / root）
  - [x] Gemini API キーの取得（Google AI Studio）と Secrets 登録（`GEMINI_API_KEY`）手順
  - [x] チャンネルの追加・削除手順（`channels.json` 編集 →  `resolve_channels.py`）
  - [x] ローカル確認方法
  - [x] 調整用定数の説明（`update.py` 冒頭）
- [x] ローカルコミット（`main` ブランチ）
- [x] ポータル `portal/index.html` に「ユーチューブ要約」カードを追加（ローカルコミット）

## 7. ユーザー作業（引き渡し後・手順は私が案内）
- [ ] GitHub に `youtube-yoyaku` リポジトリを作成して push
- [ ] Google AI Studio で API キーを発行
- [ ] リポジトリ Settings → Secrets and variables → Actions に `GEMINI_API_KEY` を登録
- [ ] Settings → Pages で main / root を配信に設定
- [ ] Actions タブで「要約データ更新」を手動実行して動作確認
- [ ] `portal` リポジトリを push

## 完了条件
- `https://git-san-934.github.io/youtube-yoyaku/` で要約カードが新しい順に表示される
- チャンネル絞り込みが動く。スマホ幅で横スクロールなし。ダークモードで崩れない
- 6時間おきに `summaries.json` が自動更新される
- 要約に失敗した動画は「要約準備中」と表示され、次回実行で再試行される
- ポータルからリンクで開ける

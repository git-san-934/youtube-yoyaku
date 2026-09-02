# ユーチューブ要約

フォロー中の YouTube チャンネルの新着動画を自動でチェックし、Google Gemini が内容を
日本語で要約して新しい順に一覧表示する Web ページです。サーバーは持たず、
GitHub Pages ＋ GitHub Actions の無料枠だけで動きます。

公開URL: https://git-san-934.github.io/youtube-yoyaku/

## 仕組み

```
GitHub Actions（6時間おき ＋ 手動実行）
  └ scripts/update.py
       ├ data/channels.json の各チャンネルの公開RSSを取得（ログイン不要）
       ├ 未要約かつ公開5日以内の新着を抽出（1チャンネル最大4本／回）
       ├ 前回失敗分も加え、古い順に最大6件を Gemini で日本語要約
       └ data/summaries.json を更新して commit / push
GitHub Pages（main ブランチをそのまま配信）
  └ index.html + assets/ が summaries.json を読んでカード一覧を描画
```

| ファイル | 役割 |
|---|---|
| `index.html`, `assets/` | 画面（HTML / CSS / JavaScript） |
| `data/channels.json` | フォロー中チャンネル（`handle` / `channel_id` / `name`）。**ここを編集して追加・削除** |
| `data/summaries.json` | 要約データ（Actions が自動更新。手で編集しない） |
| `scripts/resolve_channels.py` | `@名` からチャンネルIDを調べて `channels.json` を補完 |
| `scripts/update.py` | 新着検知 → Gemini 要約 → `summaries.json` 更新 |
| `.github/workflows/update.yml` | 定期実行の設定 |

## 公開手順（最初の1回だけ）

### 1. Gemini API キーを取得する
1. https://aistudio.google.com/apikey を開き、Google アカウントでログイン。
2. 「Create API key」でキーを作成し、文字列をコピーする（無料枠で利用可）。

### 2. GitHub リポジトリを作って push する
1. GitHub で空のリポジトリ `youtube-yoyaku` を作成する。
2. 自分のターミナルから push する:
   ```
   cd "C:\Users\a\Desktop\youtube-yoyaku"
   git remote add origin git@github.com:git-san-934/youtube-yoyaku.git
   git push -u origin main
   ```

### 3. API キーを Secrets に登録する
リポジトリの **Settings → Secrets and variables → Actions → New repository secret** で
- Name: `GEMINI_API_KEY`
- Secret: 手順1でコピーしたキー

を登録する。

### 4. GitHub Pages を有効にする
**Settings → Pages → Source** で「Deploy from a branch」を選び、
ブランチ `main` / フォルダ `/ (root)` を指定して保存する。

### 5. 初回実行
**Actions** タブ →「要約データ更新」→「Run workflow」を1回手動実行する。
数分後、公開URLに要約カードが並びます。以降は6時間おきに自動更新されます。

## チャンネルを追加・削除する

1. `data/channels.json` を編集する。
   - 追加: `{ "handle": "@あたらしいチャンネル" }` を1行足すだけ。
   - 削除: その行を消すだけ（過去の要約は残ります）。
2. チャンネルIDを補完する:
   ```
   python scripts/resolve_channels.py
   ```
3. 変更を commit して push する。

`@名` はチャンネルページのURL `https://www.youtube.com/@xxxx` の `@xxxx` の部分です。

## ローカルで確認する

```
# 要約データを更新（キーを一時的に環境変数で渡す）
GEMINI_API_KEY=あなたのキー python scripts/update.py

# 画面を確認
python -m http.server 8000    # http://localhost:8000 を開く
```

`GEMINI_API_KEY` を渡さずに実行すると、要約はせず新着の一覧化だけ行います
（カードは「要約準備中」と表示されます）。

## 調整用の設定

`scripts/update.py` の冒頭にまとめてあります。

| 定数 | 既定値 | 意味 |
|---|---|---|
| `MODEL` | `gemini-2.5-flash` | 要約に使う Gemini モデル。無料枠が厳しければ `gemini-2.5-flash-lite` に |
| `MAX_PER_RUN` | `6` | 1回の実行で要約する最大件数 |
| `LOOKBACK_DAYS` | `5` | 「新着」とみなす公開からの日数 |
| `MAX_NEW_PER_CHANNEL` | `4` | 1チャンネルあたり1回で拾う新着の最大本数 |
| `KEEP_ITEMS` | `200` | 一覧に残す最大件数 |
| `MAX_RETRY` | `3` | 要約失敗時に再挑戦する上限回数 |

実行頻度は `.github/workflows/update.yml` の `cron` で変更できます。

## 注意

要約は AI（Google Gemini）が自動生成したもので、内容の正確性は保証しません。
正確な内容は各動画をご覧ください。メンバー限定・地域制限などで AI が解釈できない動画は
「要約準備中」のまま残ることがあります。個人情報や YouTube アカウントは一切扱いません。

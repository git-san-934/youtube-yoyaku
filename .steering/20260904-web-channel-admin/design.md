# design.md — チャンネルを Web から追加・削除する（管理ページ）

## 全体像
```
admin.html (GitHub Pages)
  └─ assets/admin.js
       ├─ GET  contents/data/channels.json   ← 一覧取得（blob SHA も取得）
       └─ PUT  contents/data/channels.json   ← 追加・削除を保存（要 token + SHA）
                     │ push
                     ▼
  .github/workflows/resolve-channels.yml
       └─ python scripts/resolve_channels.py  → channel_id / name を補完して自動コミット
                     │ push
                     ▼
  .github/workflows/update.yml (既存・6hおき)  → 新チャンネルの新着を要約
```

## 追加・変更するファイル
| ファイル | 内容 |
| --- | --- |
| `admin.html` | 新規。管理ページ本体。`noindex`。style.css と admin.css を読み込む |
| `assets/admin.js` | 新規。トークン管理・GitHub API・一覧描画・追加/削除 |
| `assets/admin.css` | 新規。管理ページ専用の見た目（:root 変数は style.css を流用） |
| `.github/workflows/resolve-channels.yml` | 新規。channels.json 変更時に ID を解決して自動コミット |
| `index.html` | フッターに「チャンネルを管理」リンクを1つ追加 |

`scripts/`（update.py / resolve_channels.py）、`data/*.json` は変更しない。

## GitHub API の使い方（トークン方式）
- ベース: `https://api.github.com/repos/git-san-934/youtube-yoyaku/contents/data/channels.json`
- ヘッダ: `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`,
  `X-GitHub-Api-Version: 2022-11-28`
- 取得(GET): レスポンスの `content`(base64) をデコードして JSON パース、`sha` を保持。
- 保存(PUT): body =
  ```json
  { "message": "...", "content": "<base64>", "sha": "<取得したsha>", "branch": "main" }
  ```
  - `409`（sha が古い＝その間に Actions がコミットした）→ GET し直して 1 回だけ自動リトライ。
  - `401` → トークン無効。`403` → 権限不足。それぞれ日本語メッセージ。
- 文字コード: UTF-8。base64 は
  `btoa(String.fromCharCode(...new TextEncoder().encode(text)))` / デコードは
  `new TextDecoder().decode(Uint8Array.from(atob(b64), c => c.charCodeAt(0)))`。

## channels.json の書き込み形式（既存と揃える）
`resolve_channels.py` と同じ: `JSON.stringify(list, null, 2) + "\n"`。
- 2スペースインデント、日本語はそのまま（`ensure_ascii=False` 相当＝JS 既定）。
- 差分が最小になるよう、配列の順序は「既存＋末尾に追加」。削除は該当要素を除くだけ。

## assets/admin.js の構成

### 定数・状態
```
const REPO = 'git-san-934/youtube-yoyaku'
const FILE = 'data/channels.json'
const TOKEN_KEY = 'yy-gh-token'
const state = { token: '', list: [], sha: '' }
```

### トークン
- `loadToken()` / `saveToken(v)` / `clearToken()` … `localStorage`、try/catch。
- 画面: トークン未設定なら `#setup` を表示、設定済みなら `#manager` を表示。
- `#setup` の内容（静的 HTML）:
  1. 「GitHub のトークン発行ページを開く」リンク →
     `https://github.com/settings/personal-access-tokens/new`
  2. 選ぶ項目の説明（日本語・箇条書き）:
     - Token name: 任意（例「youtube-yoyaku 管理」）
     - Expiration: 任意（切れたら再発行）
     - Repository access: **Only select repositories** → `git-san-934/youtube-yoyaku`
     - Permissions → Repository permissions → **Contents** を **Read and write**
  3. 発行された `github_pat_...` を貼る入力欄 ＋「保存」ボタン
- 保存時に軽く検証: `GET /repos/{REPO}`（200 なら OK）。失敗ならメッセージ。

### 一覧の取得・描画
- `fetchList()` … GET contents → `state.list`, `state.sha` をセット。
- `renderList()` …
  - 各要素: 表示名（`name` があればそれ、無ければ `handle`）、`handle`、
    `channel_id` が空なら「変換待ち」バッジ。
  - 「削除」ボタン → 「削除しますか？ 削除／やめる」インライン確認
    （video 側の実装と同じ作法）。確定で `removeAt(i)`。
- 空なら「登録チャンネルがありません」。

### 追加
- `parseInput(raw)` → `{ handle }` または `{ channel_id }` または `null`。
  - 前後空白除去、先頭 `http(s)://`、`www.` 除去。
  - `youtube.com/channel/UC{22}` → `{ channel_id: 'UC…' }`
  - `youtube.com/@name` / `@name` / `name` → `{ handle: '@name' }`
    （name 部分はスラッシュ・クエリ以降を捨てる。`@` が無ければ付ける）
  - それ以外 → `null`（「URL か @名を入れてください」）
- `addChannel()`:
  - 重複チェック（handle 完全一致 / channel_id 一致、大文字小文字は handle のみ無視）。
  - `state.list.push(parsed)` → `save('add: ' + 表示)`。

### 削除
- `removeAt(i)` … `state.list.splice(i,1)` → `save('remove: ' + 表示)`。

### 保存
- `save(msgSuffix)`:
  1. PUT contents（content=base64(JSON), sha=state.sha, message=`chore: チャンネル変更 (${msgSuffix})`）。
  2. 成功 → レスポンスの新しい `sha` を `state.sha` に。成功メッセージ表示。`renderList()`。
  3. 409 → `fetchList()` してマージし直し（実質: サーバの最新に対して同じ操作をもう一度）。
     - 簡単化: 409 のときは「他の更新と重なりました。もう一度お試しください」を出し、
       `fetchList()` で最新に更新して自動リトライは1回だけ。
  4. ネットワークエラー → 「保存できませんでした。通信を確認してください」。
- 保存中はボタンを無効化（二重送信防止）。

### 初期化
```
state.token = loadToken()
if (!state.token) showSetup()
else { showManager(); await fetchList(); renderList() }
```

## .github/workflows/resolve-channels.yml
```yaml
name: チャンネルID解決
on:
  push:
    paths: [ data/channels.json ]
  workflow_dispatch: {}
permissions:
  contents: write
concurrency:
  group: resolve-channels
  cancel-in-progress: false
jobs:
  resolve:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - name: ID と名前を解決
        run: python scripts/resolve_channels.py || echo "一部は変換できませんでした（変換待ちのまま）"
      - name: 変更があればコミット
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          if git diff --quiet -- data/channels.json; then
            echo "変更なし"
          else
            git add data/channels.json
            git commit -m "chore: チャンネルIDを解決 ($(date -u +%Y-%m-%dT%H:%MZ))"
            git push
          fi
```
- ループしない: 2回目の実行では解決対象が無く diff 0 → コミットしない → 追加の push なし。
- `resolve_channels.py` が exit 1（未解決あり）でもワークフローを失敗させない（`|| echo`）。

## index.html の変更
フッターの `<p>` の後に:
```html
<p class="admin-link"><a href="admin.html">チャンネルを管理</a></p>
```
`.admin-link` は小さく控えめ（既存 footer の文字色）。

## admin.html の骨組み
```html
<!doctype html><html lang="ja"><head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex">
  <title>チャンネル管理 — ユーチューブ要約</title>
  <link rel="stylesheet" href="assets/style.css">
  <link rel="stylesheet" href="assets/admin.css">
</head><body>
  <header> … 見出し ＋ index.html へ戻るリンク … </header>
  <main>
    <section id="setup" hidden> … 手順 ＋ トークン入力 … </section>
    <section id="manager" hidden>
      <form id="add-form"> URL/@名 入力 ＋「追加」 </form>
      <div id="channel-list"></div>
      <p id="msg" role="status"></p>
      <button id="forget">トークンを削除</button>
    </section>
  </main>
  <script type="module" src="assets/admin.js"></script>
</body></html>
```

## セキュリティ / 運用メモ
- トークンはこの端末の `localStorage` のみ。漏れた場合の影響範囲は
  「このリポジトリのファイル編集」に限定（細粒度・Contents のみ）。GitHub 設定でいつでも失効可。
- `admin.html` は誰でも開けるが、トークンが無いと一覧取得も保存も 401 で不可。
- Actions の自動コミット（summaries.json / channels.json）と PUT が競合しても、
  409 → 取り直し で回復する。最悪でも次の操作で解消。

## 手動テスト観点
1. トークン未設定 → 手順が出る。デタラメなトークン → 「使えません」。
2. 正しいトークン → 一覧が出る。
3. `@name` / フル URL / `channel/UC...` URL / `name`（@なし）を各々追加 → channels.json に反映。
4. 重複追加 → 弾かれる。
5. 削除 → 確認 → channels.json から消える。
6. 追加後 resolve-channels ワークフローが走り、`channel_id` と `name` が埋まる。
   デタラメな @名は「変換待ち」のまま。
7. スマホ幅・ダークで崩れない。横スクロールなし。
8. `localStorage` 無効 → クラッシュせずメッセージ。
9. index.html フッターの「チャンネルを管理」から開ける。

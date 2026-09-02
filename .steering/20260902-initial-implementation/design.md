# design.md — 初回実装の設計

## 全体構成（サーバーなし）

```
[GitHub Actions（自動の取り込み役）]
   6時間おき（＋手動実行）に起動
   └ scripts/update.py を実行
        ├ data/channels.json の各チャンネルの公開RSSを取得
        ├ 未要約 かつ 公開5日以内 の動画を新着として抽出（1チャンネル最大4本／回）
        ├ 前回失敗（status:"failed"）の動画も再試行対象に加える
        ├ 公開が古い順に最大4件、Gemini に「動画URL＋指示」を渡して日本語要約
        └ data/summaries.json を書き出して git commit / push
                    │
                    ▼
[GitHub Pages（公開ページ）]  ← main ブランチをそのまま配信
   index.html + assets/（app.js, style.css）
        └ data/summaries.json（Actionsが更新）を読み込んでカード一覧を描画
```

## ファイル構成
| パス | 役割 |
|---|---|
| `index.html` | ページ本体（ヘッダー・注意書き・絞り込み・一覧コンテナ） |
| `assets/style.css` | 配色・レイアウト（ライト/ダーク対応、カード） |
| `assets/app.js` | `summaries.json` 読み込み → 絞り込み → カード描画 → 日時整形 |
| `data/channels.json` | 監視対象チャンネル（`handle` / `channel_id` / `name`）。手動編集 |
| `data/summaries.json` | 要約データ（自動生成） |
| `scripts/resolve_channels.py` | `@名` → `channel_id` / `name` を解決して `channels.json` を補完 |
| `scripts/update.py` | 新着検知 → Gemini 要約 → `summaries.json` 更新 |
| `scripts/requirements.txt` | `google-genai` |
| `.github/workflows/update.yml` | 6時間おき＋手動の定期実行 |
| `.nojekyll` / `.gitignore` / `README.md` / `LICENSE` | 公開・運用まわり |

## data/channels.json の形
```json
[
  { "handle": "@senxotimes", "channel_id": "UCxxxxxxxxxxxxxxxxxxxxxx", "name": "せんちょうタイムズ" },
  { "handle": "@CNBC",       "channel_id": "UCrp_UI8XtuYfpiqluWLD7Lw", "name": "CNBC" }
]
```
- 追加時は `{ "handle": "@newone" }` だけ書けばよい。`resolve_channels.py` が残りを埋める。

## data/summaries.json の形
```json
{
  "updated_at": "2026-09-02T18:20:00+09:00",
  "items": [
    {
      "video_id": "abc123XYZ",
      "url": "https://www.youtube.com/watch?v=abc123XYZ",
      "title": "日経平均、次の焦点は？",
      "channel": "せんちょうタイムズ",
      "channel_id": "UCxxxx",
      "published_at": "2026-09-02T09:00:00+00:00",
      "thumbnail": "https://i.ytimg.com/vi/abc123XYZ/hqdefault.jpg",
      "summary": "結論：…\n・要点1 …\n・要点2 …",
      "status": "ok",
      "summarized_at": "2026-09-02T18:19:40+09:00",
      "retry_count": 0
    }
  ]
}
```
- `items` は `published_at` の新しい順。最大 `KEEP_ITEMS`（200）件。
- `status: "failed"` の項目は `summary` を空文字にし、`retry_count` を持つ。

## 新着RSSの解析（標準ライブラリ）
- URL: `https://www.youtube.com/feeds/videos.xml?channel_id=<channel_id>`
- `urllib.request`（User-Agent 明示）で取得し、`xml.etree.ElementTree` で解析。
- 名前空間: atom=`http://www.w3.org/2005/Atom`, yt=`http://www.youtube.com/xml/schemas/2015`,
  media=`http://search.yahoo.com/mrss/`
- 1エントリから取り出す値:
  | 取得先 | 値 |
  |---|---|
  | `atom:entry/yt:videoId` | `video_id` |
  | `atom:entry/atom:title` | `title` |
  | `atom:entry/atom:published` | `published_at` |
  | `atom:entry/atom:author/atom:name` | `channel`（channels.json の `name` を優先、無ければこれ） |
  | `media:group/media:thumbnail/@url` | `thumbnail` |
- RSSは最新15件程度。取得失敗（HTTPエラー・パース失敗）はそのチャンネルをスキップして継続。

## チャンネルID解決（resolve_channels.py）
- `channel_id` が空の行について、`https://www.youtube.com/<handle>` を User-Agent 付きで取得。
  - `handle` が非ASCII（例 `@マーケットマスターズ-v1r`）の場合は URL エンコードする。
- HTML から以下の順で `channel_id` を探す:
  1. `<link rel="canonical" href="https://www.youtube.com/channel/UC...">`
  2. `"channelId":"(UC[0-9A-Za-z_-]+)"`
  3. `<meta itemprop="identifier" content="UC...">`
- `name` は `<meta property="og:title" content="...">` から取得。
- 解決できた行は `channels.json` を上書き保存。できなかった `handle` は最後にまとめて標準エラーに出す（処理は継続）。
- ネットワーク負荷を避けるため、リクエスト間に1秒スリープを入れる。

## Gemini 要約（update.py）
- SDK: `google-genai`。`genai.Client(api_key=os.environ["GEMINI_API_KEY"])`。
- 入力: `Part(file_data=FileData(file_uri=<動画URL>))` ＋ 指示テキスト（YouTube URL は mime_type 不要）。
- 生成設定: `max_output_tokens=900`、`temperature=0.3`、`media_resolution` 低め、`VideoMetadata.fps=0.3`。
- `thinking_config(thinking_budget=0)` で思考を無効化する。Gemini 3系は既定で思考に出力枠を使い、
  本文が数十文字で打ち切られるため。短すぎる応答（`MIN_SUMMARY_CHARS` 未満）は失敗扱いで再試行。
- モデルは `MODELS`（`gemini-flash-lite-latest` → `gemini-3.6-flash` → `gemini-flash-latest`）を
  先頭から試し、「モデルが無い」エラーなら次へ。`gemini-2.5-flash` は新規ユーザー提供終了。
- 無料枠には「1日あたりのリクエスト数」上限もある（`gemini-3.6-flash` は20/日）。日次上限を検知したら
  待たずにその実行を打ち切る。要約は「今回の新着（新しい順）→ 未要約の積み残し」の優先順で行う。
- 指示テキスト（`PROMPT` 定数）: 「動画を最後まで視聴し日本語で短く。1行目に結論を1文。
  そのあと要点を箇条書き3〜4項目（各行「・」開始・全体5行程度・重要な数字や固有名詞は残す・
  専門用語に補足）。述べられていないことは書かない。前置き/挨拶は不要」。
  `max_output_tokens` は `MAX_OUTPUT_TOKENS`（2000）。長すぎる旧要約（`MAX_SUMMARY_CHARS` 超）は作り直す。
- 応答が空、または例外時は失敗扱い。
- 動画1本ごとに `SLEEP_BETWEEN_SEC`（既定45秒）待つ。無料枠には「1分あたりの入力トークン上限」があり、
  動画は1本で大量のトークンを使うため、間隔を空けないと数本で上限に当たる。
- クォータ超過（`RESOURCE_EXHAUSTED` / HTTP 429）を検知したら、エラー中の `retryDelay` 秒だけ待って
  同じ動画を1回だけ再試行する。それでも超過が続く場合はその実行を打ち切り、既存分を書き出して
  正常終了する（残りは次回に持ち越し）。

## update.py の処理フロー
```
設定定数: MODEL=gemini-3.6-flash, MAX_PER_RUN=4, LOOKBACK_DAYS=5, MAX_NEW_PER_CHANNEL=4,
          SLEEP_BETWEEN_SEC=45, KEEP_ITEMS=200, MAX_RETRY=3

1. channels.json を読む（channel_id が無い行は警告して除外）
2. summaries.json を読む → video_id をキーに既存インデックス化
3. 候補リストを作る:
   a) 既存で status=="failed" かつ retry_count < MAX_RETRY のもの
   b) 各チャンネルのRSSを取得し、公開が新しい順に、
      「インデックスに無い」かつ「published が今から LOOKBACK_DAYS 以内」の動画を
      1チャンネルあたり最大 MAX_NEW_PER_CHANNEL 本まで拾う
      （拾った時点で status="failed", retry_count=0 でインデックスに追加＝一覧には出る）
4. 候補を published の昇順（古い順）に並べ、先頭から MAX_PER_RUN 件に絞る
   （a の再試行分を優先して詰める）
5. 各候補を Gemini で要約（1本ごとに SLEEP_BETWEEN_SEC 待つ）:
   - 成功 → status="ok", summary=本文, summarized_at=now, retry_count 据え置き
   - 失敗 → status="failed", summary="", retry_count += 1
   - クォータ超過 → retryDelay 秒待って1回だけ再試行。なお続くなら break
6. 既存項目は更新、新規項目は追加してマージ
7. published_at の降順にソートし、先頭 KEEP_ITEMS 件に切り詰め
8. GEMINI_API_KEY 未設定時は 5 をスキップ（候補は status="failed", retry_count=0 で一覧化のみ）
9. 中身が前回と変わっていれば summaries.json を書き出す（updated_at を更新）
10. 標準出力に集計（対象チャンネル数 / 新着 / 成功 / 失敗 / 打ち切り有無）
```

## フロント（assets/app.js）
| 関数 | 役割 |
|---|---|
| `loadData()` | `data/summaries.json?ts=<現在時刻>` を fetch（キャッシュ回避）。失敗時はエラーメッセージ表示 |
| `renderFilter(items)` | `items` の `channel` から重複なしリストを作り `<select>` に option を生成。前回選択を localStorage から復元 |
| `render()` | 選択チャンネルで絞り込み → `published_at` 降順 → カードDOMを生成して差し替え。0件なら空メッセージ |
| `card(item)` | 1件のカードDOM。`img`(alt=title, loading=lazy) / `a`(title, target=_blank, rel=noopener) / meta / 要約 or「要約準備中」。要約は `textContent` で挿入 |
| `formatWhen(iso)` | 24時間以内は「◯時間前 / ◯分前」、それ以外は「M/D」。JST基準 |
| `setupControls()` | `<select>` の change で選択を localStorage 保存 → `render()`。`prefers-color-scheme` 変更は CSS 側で対応 |

- ヘッダーの「最終更新」は `summaries.json` の `updated_at` を `formatWhen` せず `YYYY/M/D HH:mm` で表示。

## .github/workflows/update.yml（骨子）
```yaml
name: 要約データ更新
on:
  schedule:
    - cron: "0 */6 * * *"   # 6時間おき（UTC）
  workflow_dispatch: {}
permissions:
  contents: write
concurrency:
  group: update-summaries
  cancel-in-progress: false
jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12", cache: pip }
      - run: pip install -r scripts/requirements.txt
      - run: python scripts/update.py
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
      - name: 変更があればコミット
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          if git diff --quiet -- data/summaries.json; then
            echo "変更なし"
          else
            git add data/summaries.json
            git commit -m "chore: 要約データ更新 ($(date -u +%Y-%m-%dT%H:%MZ))"
            git push
          fi
```

## 影響範囲
- 新規リポジトリのため既存アプリへの影響なし。
- ポータルの `index.html`（別リポジトリ `portal`）にカードを1枚追加（別途 push が必要）。

## やらないこと（今回のスコープ外）
- 通知（メール・プッシュ）、画面からのチャンネル編集、検索・既読管理。
- 要約の言語・長さ切り替え。
- 動画の全文文字起こしの保存・表示。

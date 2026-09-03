# design.md — 読んだ要約をその場で消す

## 実装アプローチ
静的サイトのままなので、非表示状態は各端末の `localStorage` に持つ。
描画時に「非表示リストに載っている動画IDのカード」を除外するだけ。

## 変更するファイル
| ファイル | 変更内容 |
| --- | --- |
| `assets/app.js` | 非表示リストの読み書き、カードへの「消す」ボタン、確認UI、描画時の除外、空表示の文言 |
| `assets/style.css` | 「消す」ボタンと確認バーの見た目、カードのフェード |
| `index.html` | 空メッセージ（`#empty`）の文言を「未読の要約はありません。…」に更新 |

`data/summaries.json` / `scripts/` / `.github/workflows/` は変更しない。

## データ構造（localStorage）
- 既存キー: `yy-channel-filter`（チャンネル絞り込み）… そのまま
- 追加キー: `yy-hidden` … 非表示にした動画IDの配列を JSON 文字列で保存
  例: `["abc123","def456"]`

読み込み時の掃除:
1. `yy-hidden` を配列として読む（壊れていれば空配列）。
2. `summaries.json` の `items` に存在する `video_id` の集合を作る。
3. 積集合を取り、存在しないIDを捨てて `yy-hidden` に書き戻す。
   → 200件上限で流れ落ちた古い動画のIDが溜まり続けない。

すべての localStorage アクセスは既存の `safeGet` / `safeSet` と同じく try/catch で包む
（Safari プライベートモードなどで例外が出ても描画は継続）。

## app.js の変更詳細

### 状態
```
const HIDDEN_KEY = 'yy-hidden'
state.hidden = new Set()   // 非表示の video_id
```

### 関数
- `loadHidden()` … `yy-hidden` を読んで `Set` にして返す。パース失敗時は空 `Set`。
- `saveHidden()` … `state.hidden` を配列化して JSON で保存（try/catch）。
- `pruneHidden(validIds)` … `state.hidden` を `validIds` との積集合に絞り、`saveHidden()`。
- `hideItem(videoId)` … `state.hidden.add(videoId)` → `saveHidden()` → `render()`。

### 描画（render）
先頭で非表示を除外してから、これまでのチャンネル絞り込み・並べ替えを行う:
```
const visible = state.items.filter((it) => !state.hidden.has(it.video_id))
```
以降は `visible` を使う。`els.empty.hidden = sorted.length > 0` は従来通り。

### カード（card）
`card__body` の右上に「消す」ボタンを追加。
- 通常時: `<button class="card__del">消す</button>`
- クリックで、そのカード内のボタン領域を確認表示に差し替える:
  `この要約を消しますか？ [消す] [やめる]`
  - `[消す]` → カードに `.is-removing`（フェード）を付け、200ms 後に `hideItem(video_id)`
  - `[やめる]` → 確認表示を元のボタンに戻す
- 確認は「そのカードのボタン内」だけで完結（他カードやページ全体を触らない）。
- 実装は card 内のローカル state（差し替え用の DOM を組み替え）で行い、
  イベントリスナは各カード生成時に付与。

### 初期化（main）
```
state.hidden = loadHidden()
...
state.items = Array.isArray(data.items) ? data.items : []
pruneHidden(new Set(state.items.map((it) => it.video_id)))
```

## style.css の変更詳細
- `.card__body` を `position: relative`。
- `.card__del`（「消す」ボタン）:
  - 右上に配置（`position: absolute; top: 0; right: 0`）。
  - 小さめ・控えめ（`font-size: .75rem`、`color: var(--text-sub)`、枠線 `var(--border)`、角丸）。
  - タップ領域を確保（最低 `min-height: 32px`、パディング）。
- `.card__confirm`（確認バー）:
  - 「消す」= アクセント色、「やめる」= 通常色の小ボタン2つ＋短い文言。
  - カード幅に収まり、スマホでも折り返さない大きさ。
- `.card.is-removing { opacity: 0; transition: opacity .2s ease; }`
- タイトルと「消す」ボタンが重ならないよう、`.card__title` に右パディング（例 `padding-right: 3.5rem`）。

## index.html の変更詳細
`#empty` のテキストを差し替え:
```
<p id="empty" class="empty" hidden>未読の要約はありません。新しい動画が公開されると自動で追加されます。</p>
```

## 影響範囲
- 既存のチャンネル絞り込み・並べ替え・相対時刻表示には手を入れない（描画対象の配列を1段フィルタするだけ）。
- 非表示リストが空なら、見た目・挙動は現状と「消す」ボタンが増える以外は同じ。
- `data/summaries.json` を読むだけ・書かないので、自動更新ワークフローと干渉しない。

## テスト観点（手動）
1. 「消す」→「やめる」で元に戻る。
2. 「消す」→「消す」でカードが消え、再読み込み後も消えたまま。
3. チャンネル絞り込み中でも「消す」が効く。絞り込み解除後もそのカードは非表示。
4. 全部消すと空メッセージが出る。
5. `yy-hidden` に存在しない動画IDを仕込んで読み込む → 自動で消えている（掃除）。
6. スマホ幅・ダークモードで確認バーが崩れない。横スクロールが出ない。
7. localStorage を無効化しても、エラーにならずカードは表示される（消しても再読み込みで復活するだけ）。

# tasklist.md — 読んだ要約をその場で消す

## 実装タスク
- [x] `assets/app.js`: `HIDDEN_KEY` 定数と `state.hidden`（Set）を追加
- [x] `assets/app.js`: `loadHidden()` / `saveHidden()` / `pruneHidden()` / `hideItem()` を実装
- [x] `assets/app.js`: `main()` で `state.hidden` を読み込み、データ取得後に `pruneHidden()`
- [x] `assets/app.js`: `render()` で非表示IDを除外してから絞り込み・並べ替え
- [x] `assets/app.js`: `card()` に「消す」ボタンと「消す／やめる」確認UIを追加
- [x] `index.html`: `#empty` の文言を差し替え
- [x] `assets/style.css`: `.card__del` / `.card__confirm` / `.card.is-removing` と `.card__title` 余白

## 完了条件
- [x] 「消す」→「やめる」で元に戻る（headless DOMテストで確認）
- [x] 「消す」→「消す」でカードが消え、再読み込み後も非表示（localStorage 保存を確認）
- [x] チャンネル絞り込み中でも「消す」が効く（除外→絞り込みの順で実装）
- [x] 全件消すと新しい空メッセージが出る（テストで確認）
- [x] 存在しないIDを仕込むと読み込み時に掃除される（テストで確認）
- [ ] スマホ幅・ダークモードで崩れない／横スクロールなし（ブラウザ目視 ※環境にブラウザなし、ユーザー確認）
- [x] localStorage 無効でもエラーなく表示される（try/catch で実装）
- [ ] ローカルで確認（`http://127.0.0.1:8765/` 起動中）
- [ ] コミット（`data/summaries.json` は含めない）＋ push

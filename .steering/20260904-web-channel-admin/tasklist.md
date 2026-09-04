# tasklist.md — チャンネルを Web から追加・削除する（管理ページ）

## 実装タスク
- [x] `admin.html`: 骨組み（setup / manager セクション、noindex、style.css + admin.css）
- [x] `assets/admin.css`: setup 手順・入力欄・一覧・確認UI・メッセージの見た目
- [x] `assets/admin.js`: トークン `loadToken`/`saveToken`/`clearToken` と画面切替
- [x] `assets/admin.js`: setup — 手順表示、トークン検証（`GET /repos/{REPO}`）、保存
- [x] `assets/admin.js`: `fetchList()` — GET contents、base64→JSON、sha 保持
- [x] `assets/admin.js`: `renderList()` — 表示名／handle／「変換待ち」／削除ボタン＋確認
- [x] `assets/admin.js`: `parseInput()` — @名 / URL / channel URL / @なし を解析
- [x] `assets/admin.js`: `addChannel()` — 重複チェック、push、save
- [x] `assets/admin.js`: `removeAt()` — splice、save
- [x] `assets/admin.js`: `save()` — PUT contents、409 で取り直し1回、401/403/通信エラー表示、二重送信防止
- [x] `assets/admin.js`: base64 の UTF-8 エンコード/デコードヘルパ
- [x] `.github/workflows/resolve-channels.yml`: 新規
- [x] `index.html`: フッターに「チャンネルを管理」リンク
- [x] `assets/style.css`: `.admin-link` の控えめスタイル

## 完了条件
- [x] トークン未設定で手順が出る／デタラメなトークンで「使えません」（テスト）
- [x] 正しいトークンで一覧表示（テスト）
- [x] `@name` / フルURL / `channel/UC...` / `name`（@なし）を追加できる（テスト）
- [x] 重複追加を弾く（大小文字違いも）（テスト）
- [x] 削除（確認つき）で channels.json から消える（テスト）
- [ ] `channels.json` 変更で resolve-channels ワークフローが走り ID/name が埋まる（push 後に確認）
- [ ] スマホ幅・ダークで崩れない／横スクロールなし（ブラウザ目視 ※環境にブラウザなし）
- [x] localStorage 無効でもクラッシュしない（try/catch）
- [ ] index.html フッターから開ける（目視）
- [x] JS 構文チェック（`node --check`）＋ ヘッドレスDOMテスト（19項目 pass）
- [x] 409 → 取り直し1回リトライ（テスト）
- [x] 401 → setup に戻りトークン削除（テスト）
- [ ] コミット（`data/*.json` は含めない）＋ push

## 手動確認（push 後・ユーザー）
- [ ] iPhone で `admin.html` を開き、トークン発行 → 一覧表示
- [ ] 1チャンネル追加 → 数分後に「変換待ち」が名前に変わる
- [ ] 1チャンネル削除 → 一覧から消える
- [ ] トップの要約一覧が従来どおり表示される

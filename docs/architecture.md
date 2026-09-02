# 技術仕様書 — ユーチューブ要約

## テクノロジースタック

| 層 | 技術 | 備考 |
|---|---|---|
| ホスティング | GitHub Pages（main / root を配信） | 静的のみ。ビルド工程なし |
| フロントエンド | 素の HTML / CSS / JavaScript（ES2020） | フレームワーク不使用・CDN不使用 |
| 定期バッチ | GitHub Actions + Python 3.12 | `.github/workflows/update.yml` |
| 新着取得 | YouTube 公開RSS（`videos.xml`） | Python標準ライブラリ（`urllib`＋`xml.etree`）で取得・解析。APIキー不要 |
| 要約 | Google Gemini API（`google-genai` SDK） | モデルは `MODELS` の先頭から試行（flash-lite→3.6-flash→flash-latest）。動画URLを直接入力 |
| チャンネルID解決 | `scripts/resolve_channels.py`（一度だけ実行） | @名のチャンネルページから `channelId` を抽出して `channels.json` に保存 |
| 秘密情報 | GitHub Actions Secrets: `GEMINI_API_KEY` | ソース・フロントには一切書かない |

## 開発ツールと手法
- ドキュメント先行（`docs/` と `.steering/`）。CLAUDE.md のワークフローに従う。
- ビルド／バンドラなし。ファイルをそのまま配置。
- ローカル確認: フロントは `python -m http.server`。バッチは `GEMINI_API_KEY=... python scripts/update.py`。

## Gemini API の使い方
- エンドポイント: `google-genai` SDK 経由（内部的に `generativelanguage.googleapis.com`）。
- 入力: テキストのプロンプト ＋ `Part(file_data=FileData(file_uri="https://www.youtube.com/watch?v=..."))`。
- 要約は「結論2〜3文 ＋ 箇条書き15〜20項目」の詳しめ。max_output_tokens は 3000。
- 動画のトークン消費を抑えるため `media_resolution` を低め（LOW）に、`VideoMetadata.fps` を 0.3 に設定する。
- 無料枠（Google AI Studio のキー）を前提とする。制約と対策:
  - 「1分あたりの入力トークン上限（約25万）」があり、動画は1本で10万トークン規模を消費する。
  - 対策: fps を下げて1本のトークンを削減、動画1本ごとに `SLEEP_BETWEEN_SEC` 待つ、
    1実行あたり最大4件・1チャンネル最大4本、実行は6時間おき。
  - 超過エラー時は `retryDelay` 秒待って1回再試行。なお続けばその実行を打ち切り次回へ。
  - それでも足りない場合は、モデルを `gemini-3.6-flash-lite` に変更、または対象日数・件数を減らす。

## 技術的制約
- サーバーサイドの常時実行環境を持てない（GitHub Pages は静的配信のみ）。
  → 要約データは Actions が生成した `data/summaries.json` を介してのみ供給する。
- Actions のスケジュール実行は数分〜十数分遅延しうる。分単位の即時性は保証しない。
- YouTube RSS は最新15件程度しか返さない。公開頻度が非常に高いチャンネルで、
  実行間隔中に16件以上更新された場合は取りこぼしうる（実用上は問題にならない想定）。
- Gemini が動画を解釈できない場合（メンバー限定・地域制限・極端に長い等）は
  その動画を `failed` として記録し、一定回数リトライ後はあきらめる。
- ブラウザから外部API（YouTube / Gemini）を直接叩かない（CORS・レート制限・鍵管理を避ける）。

## パフォーマンス要件
- 初回表示: `summaries.json`（最大200件・要約込みで ~300KB 想定）1ファイルのみ。1〜2秒以内の描画。
- 一覧描画・絞り込み: 200件程度の DOM 構築。体感遅延なし。
- 画像（サムネイル）は YouTube の `i.ytimg.com` を直接参照（遅延読み込み `loading="lazy"`）。

## セキュリティ / プライバシー
- 個人情報・認証情報を一切扱わない。Cookie は未使用。
- localStorage は「選択中のチャンネル絞り込み」の記憶のみ（任意・なくても動作）。
- Actions は `contents: write` 権限のみ。`GITHUB_TOKEN` で自リポジトリへ push。
- `GEMINI_API_KEY` は Secrets のみ。ログに出力しない。
- 生成した要約は元動画の「要約」であり、字幕や説明文の全文転載はしない。

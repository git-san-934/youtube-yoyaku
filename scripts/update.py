"""フォロー中チャンネルの新着動画を検知し、Gemini で日本語要約して data/summaries.json を更新する。

使い方:
    GEMINI_API_KEY=xxxx python scripts/update.py

- data/channels.json の各チャンネルの公開RSSを取得
- 「未要約かつ公開 LOOKBACK_DAYS 日以内」の動画 ＋ 前回失敗分を候補にする
- 公開が古い順に最大 MAX_PER_RUN 件を Gemini で要約
- 1件の失敗で全体を止めない。クォータ超過なら安全に打ち切り
- GEMINI_API_KEY 未設定なら要約はスキップし、新着の一覧化のみ行う
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --- 調整用の設定値 ---------------------------------------------------------
# 要約に使う Gemini モデル。先頭から順に試し、「モデルが無い」エラーなら次にフォールバックする。
# flash-lite は無料枠の1日リクエスト数が多い。gemini-3.6-flash は無料枠だと1日20回まで。
MODELS = [
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-flash-latest",
    "gemini-3.6-flash",
]
MAX_PER_RUN = 4                 # 1回の実行で要約する最大件数（残りは次回へ）
LOOKBACK_DAYS = 5             # 「新着」とみなす公開からの日数
MAX_NEW_PER_CHANNEL = 4       # 1チャンネルあたり新着として拾う最大本数（1回の実行）
SLEEP_BETWEEN_SEC = 45       # 動画1本ごとの待ち時間（Gemini無料枠の「分あたり入力量」上限対策）
QUOTA_WAIT_MAX_SEC = 120     # クォータ超過時に待つ最大秒数
VIDEO_FPS = 0.3             # 動画のフレーム抽出頻度（低いほどトークン節約。話し中心なら0.2〜0.5で十分）
MIN_SUMMARY_CHARS = 50      # これ未満の要約は「打ち切り」とみなして失敗扱い・次回再試行
MAX_SUMMARY_CHARS = 500     # これを大きく超える既存要約は「長すぎ」として作り直し対象にする
MAX_OUTPUT_TOKENS = 2000    # 要約本文の最大トークン（5行程度＋思考分の余裕）
KEEP_ITEMS = 200              # summaries.json に残す最大件数
MAX_RETRY = 3                 # 同じ動画の要約をリトライする上限回数
# 無料枠の目安: 上記だと 1日4回実行 × 4件 = 最大16件/日。
# 初回はバックログをこの速度で消化する。超過・不足があればここを調整する。
# -------------------------------------------------------------------------

try:  # Windows のコンソール等で絵文字混じりタイトルを print してもクラッシュさせない
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parent.parent
CHANNELS_PATH = ROOT / "data" / "channels.json"
SUMMARIES_PATH = ROOT / "data" / "summaries.json"

JST = timezone(timedelta(hours=9))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
ATOM_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}

PROMPT = (
    "次のYouTube動画を最後まで視聴し、内容を日本語で短く要約してください。\n"
    "・全体で5行程度。1行目に結論・主題を1文で書く\n"
    "・2行目以降は要点を箇条書きで3〜4項目、各行を「・」で始める\n"
    "・重要な数字・固有名詞は残す。専門用語には短い補足を付ける\n"
    "・動画内で述べられていない情報は書かない。推測で補わない\n"
    "・前置き（「この動画は」等）や締めの挨拶は不要。すぐ本題から書く"
)


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def parse_rss(xml_bytes: bytes, fallback_name: str) -> list[dict]:
    """RSS(atom) から動画エントリの一覧を取り出す。"""
    root = ET.fromstring(xml_bytes)
    entries = []
    for e in root.findall("atom:entry", ATOM_NS):
        vid_el = e.find("yt:videoId", ATOM_NS)
        title_el = e.find("atom:title", ATOM_NS)
        pub_el = e.find("atom:published", ATOM_NS)
        if vid_el is None or title_el is None or pub_el is None:
            continue
        vid = (vid_el.text or "").strip()
        if not vid:
            continue
        name_el = e.find("atom:author/atom:name", ATOM_NS)
        thumb_el = e.find("media:group/media:thumbnail", ATOM_NS)
        thumbnail = thumb_el.get("url") if thumb_el is not None else None
        entries.append(
            {
                "video_id": vid,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "title": (title_el.text or "").strip(),
                "channel": fallback_name or (name_el.text.strip() if name_el is not None and name_el.text else ""),
                "published_at": (pub_el.text or "").strip(),
                "thumbnail": thumbnail or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            }
        )
    return entries


def parse_dt(iso: str) -> datetime | None:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def within_lookback(iso: str, now: datetime) -> bool:
    dt = parse_dt(iso)
    return dt is not None and (now - dt) <= timedelta(days=LOOKBACK_DAYS)


def make_client(api_key: str):
    from google import genai

    return genai.Client(api_key=api_key)


_active_model = None   # 一度成功したモデルを覚えて以降はそれを使う
_active_config = None  # 一度成功した設定パターンの番号


def _video_part(types, url: str):
    # YouTube URL の場合、mime_type は指定しない（指定すると弾かれる版がある）
    # fps を下げて動画のトークン消費を減らす（話し中心の動画は音声で内容が取れる）
    try:
        return types.Part(
            file_data=types.FileData(file_uri=url),
            video_metadata=types.VideoMetadata(fps=VIDEO_FPS),
        )
    except (AttributeError, TypeError):
        return types.Part(file_data=types.FileData(file_uri=url))


def _configs(types):
    """試す設定パターン。多機能→単純の順。1つ弾かれたら次を試す。"""
    base = {"max_output_tokens": MAX_OUTPUT_TOKENS, "temperature": 0.3}
    low_res = dict(base)
    try:
        low_res["media_resolution"] = types.MediaResolution.MEDIA_RESOLUTION_LOW
    except AttributeError:
        pass
    return [types.GenerateContentConfig(**low_res), types.GenerateContentConfig(**base)]


def is_overloaded_error(exc: Exception) -> bool:
    s = f"{exc}".upper()
    return "503" in s or "UNAVAILABLE" in s or "OVERLOADED" in s or "HIGH DEMAND" in s


def clean_summary(text: str) -> str:
    """モデル出力の整形。文字列の "\\n" を本物の改行に、余分な空行を圧縮。"""
    text = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def summarize(client, url: str) -> str:
    """動画URLを渡して要約テキストを返す。失敗時は例外を送出。"""
    from google.genai import types

    global _active_model, _active_config
    contents = types.Content(parts=[_video_part(types, url), types.Part(text=PROMPT)])
    configs = _configs(types)

    models = [_active_model] if _active_model else list(MODELS)
    cfg_order = [_active_config] if _active_config is not None else list(range(len(configs)))
    last_exc = None

    for model in models:
        for ci in cfg_order:
            for attempt in range(3):  # 503（混雑）は少し待って再試行
                try:
                    resp = client.models.generate_content(
                        model=model, contents=contents, config=configs[ci]
                    )
                except Exception as exc:
                    last_exc = exc
                    if is_quota_error(exc):
                        raise
                    if is_overloaded_error(exc) and attempt < 2:
                        print(f"  {model} 混雑中。15秒待って再試行…", file=sys.stderr)
                        time.sleep(15)
                        continue
                    # INVALID_ARGUMENT / NOT_FOUND など → 次の設定・次のモデルへ
                    print(f"  {model} / 設定{ci} で失敗（{exc}）。次を試します", file=sys.stderr)
                    break
                _active_model, _active_config = model, ci
                text = clean_summary(resp.text or "")
                if not text:
                    raise RuntimeError("空の応答")
                if len(text) < MIN_SUMMARY_CHARS:
                    raise RuntimeError(f"要約が短すぎる（{len(text)}字・打ち切りの可能性）")
                return text
    raise last_exc or RuntimeError("要約できるモデル/設定がありませんでした")


def is_quota_error(exc: Exception) -> bool:
    s = f"{type(exc).__name__} {exc}".upper()
    return "RESOURCE_EXHAUSTED" in s or "429" in s or "QUOTA" in s or "RATE LIMIT" in s


def print_available_models(client) -> None:
    """このAPIキーで generateContent に使えるモデル一覧を出す（診断用・生成クォータは消費しない）。"""
    try:
        names = []
        for m in client.models.list():
            actions = getattr(m, "supported_actions", None) or getattr(m, "supported_generation_methods", None) or []
            if not actions or "generateContent" in actions:
                names.append(getattr(m, "name", str(m)))
        print("  利用可能モデル: " + ", ".join(sorted(names)), file=sys.stderr)
    except Exception as exc:
        print(f"  モデル一覧の取得に失敗: {exc}", file=sys.stderr)


def is_daily_quota_error(exc: Exception) -> bool:
    """1日あたりの上限（分あたりではなく日次）かどうか。日次なら待っても無駄。"""
    s = f"{exc}".upper()
    return "PERDAY" in s or "PER DAY" in s or "REQUESTSPERDAY" in s or "FREE_TIER_REQUESTS" in s


def parse_retry_delay(exc: Exception) -> int:
    """クォータ超過エラーから「何秒後に再試行」を読み取る。読めなければ 45 秒。"""
    s = str(exc)
    m = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", s)
    if not m:
        m = re.search(r"retry in (\d+(?:\.\d+)?)\s*s", s)
    if m:
        return min(int(float(m.group(1))) + 5, QUOTA_WAIT_MAX_SEC)
    return SLEEP_BETWEEN_SEC


def main() -> int:
    now = datetime.now(timezone.utc)
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    channels = load_json(CHANNELS_PATH, [])
    data = load_json(SUMMARIES_PATH, {"updated_at": None, "items": []})
    old_items = data.get("items", [])
    index: dict[str, dict] = {it["video_id"]: dict(it) for it in old_items if it.get("video_id")}

    # 既存要約の整形（文字列の "\n" を本物の改行に直す等）を一度かける
    for it in index.values():
        if it.get("summary"):
            it["summary"] = clean_summary(it["summary"])

    # --- 各チャンネルのRSSを取得して新着候補を集める ---
    new_ids: list[str] = []
    ok_channels = 0
    for ch in channels:
        cid = (ch.get("channel_id") or "").strip()
        if not cid:
            print(f"  channel_id 未設定のためスキップ: {ch.get('handle')}", file=sys.stderr)
            continue
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
        try:
            entries = parse_rss(fetch(rss_url), ch.get("name", ""))
        except Exception as exc:
            print(f"  RSS取得失敗 {ch.get('handle')}: {exc}", file=sys.stderr)
            continue
        ok_channels += 1
        entries.sort(key=lambda e: e.get("published_at") or "", reverse=True)
        # 公開が新しいものから MAX_NEW_PER_CHANNEL 件まで拾う
        picked = 0
        for ent in entries:
            vid = ent["video_id"]
            if vid in index:
                continue
            if not within_lookback(ent["published_at"], now):
                continue
            if picked >= MAX_NEW_PER_CHANNEL:
                break
            picked += 1
            ent.update({
                "channel_id": cid,
                "summary": "",
                "status": "failed",
                "summarized_at": None,
                "retry_count": 0,
            })
            index[vid] = ent
            new_ids.append(vid)

    # --- 要約する候補を並べる ---
    # 優先順位: ①今回の新着（新しい順）② 未要約の積み残し（新しい順）
    # 無料枠が限られるので、まず「今日の新しい動画」を確実に要約する。古い積み残しは余った回数で消化。
    # 未要約(failed) / 短すぎ / 長すぎ(旧仕様の詳細版) を作り直し対象にする
    retry_items = [
        it for it in index.values()
        if it["video_id"] not in new_ids
        and it.get("retry_count", 0) < MAX_RETRY
        and (
            it.get("status") == "failed"
            or len(it.get("summary", "")) < MIN_SUMMARY_CHARS
            or len(it.get("summary", "")) > MAX_SUMMARY_CHARS
        )
    ]
    new_items = [index[v] for v in new_ids]
    new_items.sort(key=lambda it: it.get("published_at") or "", reverse=True)
    retry_items.sort(key=lambda it: it.get("published_at") or "", reverse=True)
    todo = (new_items + retry_items)[:MAX_PER_RUN]

    # --- 要約 ---
    done_ok = done_ng = 0
    stopped = False
    listed_models = False
    if api_key and todo:
        client = make_client(api_key)
        for idx, it in enumerate(todo):
            for attempt in (1, 2):
                try:
                    summary = summarize(client, it["url"])
                    it["summary"] = summary
                    it["status"] = "ok"
                    it["summarized_at"] = datetime.now(JST).isoformat(timespec="seconds")
                    done_ok += 1
                    print(f"  OK  {it['channel']} / {it['title'][:40]}")
                    break
                except Exception as exc:
                    if is_quota_error(exc):
                        if is_daily_quota_error(exc):
                            print("  1日あたりの上限に到達。今回は打ち切り（明日以降に持ち越し）", file=sys.stderr)
                            stopped = True
                            break
                        if attempt == 1:
                            wait = parse_retry_delay(exc)
                            print(f"  分あたり上限。{wait}秒待って再試行します…", file=sys.stderr)
                            time.sleep(wait)
                            continue
                        # 2回目も超過 = レート制限が続いている。この動画の試行回数だけ進めて打ち切り
                        it["status"] = "failed"
                        it["retry_count"] = it.get("retry_count", 0) + 1
                        print("  上限が続くため今回はここで打ち切り（残りは次回へ）", file=sys.stderr)
                        stopped = True
                        break
                    it["status"] = "failed"
                    it["retry_count"] = it.get("retry_count", 0) + 1
                    done_ng += 1
                    print(f"  NG  {it['channel']} / {it['title'][:40]} : {exc}", file=sys.stderr)
                    if not listed_models:
                        listed_models = True
                        print_available_models(client)
                    break
            if stopped:
                break
            if idx < len(todo) - 1:
                time.sleep(SLEEP_BETWEEN_SEC)
    elif not api_key:
        print("  GEMINI_API_KEY 未設定のため要約はスキップ（新着の一覧化のみ）", file=sys.stderr)

    # --- 並べ替え・切り詰め ---
    final_items = sorted(
        index.values(), key=lambda it: it.get("published_at") or "", reverse=True
    )[:KEEP_ITEMS]

    new_data = {"updated_at": data.get("updated_at"), "items": final_items}
    changed = json.dumps(final_items, ensure_ascii=False, sort_keys=True) != json.dumps(
        old_items, ensure_ascii=False, sort_keys=True
    )
    if changed:
        new_data["updated_at"] = datetime.now(JST).isoformat(timespec="seconds")
        SUMMARIES_PATH.write_text(
            json.dumps(new_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\n{SUMMARIES_PATH.name} を更新しました。")
    else:
        print("\n変更なし。")

    print(
        f"チャンネル成功 {ok_channels}/{len(channels)} ／ 新着 {len(new_ids)} ／ "
        f"要約成功 {done_ok} ／ 要約失敗 {done_ng}"
        + (f" ／ モデル {_active_model}" if _active_model else "")
        + ("／ クォータで打ち切り" if stopped else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

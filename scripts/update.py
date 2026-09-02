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
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --- 調整用の設定値 ---------------------------------------------------------
MODEL = "gemini-3.6-flash"     # 要約に使う Gemini モデル（無料枠が厳しければ "gemini-3.6-flash-lite"）
MAX_PER_RUN = 6                 # 1回の実行で要約する最大件数（残りは次回へ）
LOOKBACK_DAYS = 5             # 「新着」とみなす公開からの日数
MAX_NEW_PER_CHANNEL = 4       # 1チャンネルあたり新着として拾う最大本数（1回の実行）
KEEP_ITEMS = 200              # summaries.json に残す最大件数
MAX_RETRY = 3                 # 同じ動画の要約をリトライする上限回数
# 無料枠の目安: 上記だと 1日4回実行 × 6件 = 最大24件/日。
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
    "次のYouTube動画を視聴し、内容を日本語で要約してください。\n"
    "・最初の1文で結論・主題を述べる\n"
    "・続けて要点を箇条書きで3〜6個（各行「・」で始める）\n"
    "・専門用語には10〜20字程度の簡単な補足を付ける\n"
    "・全体で400字以内\n"
    "・動画内で述べられていない情報は書かない\n"
    "・前置き（「この動画は」等）や締めの挨拶は不要"
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


def summarize(client, url: str) -> str:
    """動画URLを渡して要約テキストを返す。失敗時は例外を送出。"""
    from google.genai import types

    # YouTube URL の場合、mime_type は指定しない（指定すると弾かれる版がある）
    part_video = types.Part(file_data=types.FileData(file_uri=url))
    part_text = types.Part(text=PROMPT)
    contents = types.Content(parts=[part_video, part_text])

    config_kwargs = {"max_output_tokens": 500, "temperature": 0.3}
    try:
        config_kwargs["media_resolution"] = types.MediaResolution.MEDIA_RESOLUTION_LOW
    except AttributeError:
        pass

    resp = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(**config_kwargs),
    )
    text = (resp.text or "").strip()
    if not text:
        raise RuntimeError("空の応答")
    return text


def is_quota_error(exc: Exception) -> bool:
    s = f"{type(exc).__name__} {exc}".upper()
    return "RESOURCE_EXHAUSTED" in s or "429" in s or "QUOTA" in s or "RATE LIMIT" in s


def main() -> int:
    now = datetime.now(timezone.utc)
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    channels = load_json(CHANNELS_PATH, [])
    data = load_json(SUMMARIES_PATH, {"updated_at": None, "items": []})
    old_items = data.get("items", [])
    index: dict[str, dict] = {it["video_id"]: dict(it) for it in old_items if it.get("video_id")}

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

    # --- 要約する候補を並べる（前回失敗の再試行 → 新着、いずれも公開が古い順）---
    retry_items = [
        it for it in index.values()
        if it.get("status") == "failed"
        and it["video_id"] not in new_ids
        and it.get("retry_count", 0) < MAX_RETRY
    ]
    new_items = [index[v] for v in new_ids]
    retry_items.sort(key=lambda it: it.get("published_at") or "")
    new_items.sort(key=lambda it: it.get("published_at") or "")
    todo = (retry_items + new_items)[:MAX_PER_RUN]

    # --- 要約 ---
    done_ok = done_ng = 0
    stopped = False
    if api_key and todo:
        client = make_client(api_key)
        for it in todo:
            try:
                summary = summarize(client, it["url"])
                it["summary"] = summary
                it["status"] = "ok"
                it["summarized_at"] = datetime.now(JST).isoformat(timespec="seconds")
                done_ok += 1
                print(f"  OK  {it['channel']} / {it['title'][:40]}")
            except Exception as exc:
                if is_quota_error(exc):
                    print(f"  クォータ超過を検知。今回はここで打ち切り: {exc}", file=sys.stderr)
                    stopped = True
                    break
                it["status"] = "failed"
                it["retry_count"] = it.get("retry_count", 0) + 1
                done_ng += 1
                print(f"  NG  {it['channel']} / {it['title'][:40]} : {exc}", file=sys.stderr)
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
        + ("／ クォータで打ち切り" if stopped else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

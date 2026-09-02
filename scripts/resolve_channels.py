"""@名から YouTube チャンネルID(UC...)と表示名を解決して data/channels.json を補完する。

使い方:
    python scripts/resolve_channels.py

channels.json の各要素は最低限 {"handle": "@name"} があればよい。
channel_id が空の行だけを対象に YouTube のチャンネルページを取得し、
canonical URL などから UC... を抜き出して書き戻す。
解決できなかった handle は最後にまとめて表示する（処理は止めない）。
標準ライブラリのみ。ネットワークが必要。
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

CHANNELS_PATH = Path(__file__).resolve().parent.parent / "data" / "channels.json"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
REQUEST_INTERVAL_SEC = 1.0

CANONICAL_RE = re.compile(r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[0-9A-Za-z_-]{20,})"')
CHANNELID_RE = re.compile(r'"channelId":"(UC[0-9A-Za-z_-]{20,})"')
IDENTIFIER_RE = re.compile(r'<meta itemprop="identifier" content="(UC[0-9A-Za-z_-]{20,})"')
OG_TITLE_RE = re.compile(r'<meta property="og:title" content="([^"]*)"')


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "ja,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def resolve_one(handle: str) -> tuple[str | None, str | None]:
    """handle からチャンネルページを取得し (channel_id, name) を返す。失敗時は (None, None)。"""
    # @名は非ASCIIを含みうる（例 @マーケットマスターズ-v1r）のでパス部分をエンコードする
    quoted = urllib.parse.quote(handle, safe="@")
    url = f"https://www.youtube.com/{quoted}"
    try:
        html = fetch(url)
    except Exception as exc:  # ネットワーク・HTTPエラー
        print(f"  取得失敗 {handle}: {exc}", file=sys.stderr)
        return None, None

    channel_id = None
    for pattern in (CANONICAL_RE, CHANNELID_RE, IDENTIFIER_RE):
        m = pattern.search(html)
        if m:
            channel_id = m.group(1)
            break

    name = None
    m = OG_TITLE_RE.search(html)
    if m:
        name = m.group(1).strip() or None

    return channel_id, name


def main() -> int:
    channels = json.loads(CHANNELS_PATH.read_text(encoding="utf-8"))
    unresolved: list[str] = []
    changed = False

    for entry in channels:
        handle = entry.get("handle", "").strip()
        if not handle:
            continue
        if entry.get("channel_id"):
            continue

        print(f"解決中: {handle}")
        channel_id, name = resolve_one(handle)
        time.sleep(REQUEST_INTERVAL_SEC)

        if not channel_id:
            unresolved.append(handle)
            continue

        entry["channel_id"] = channel_id
        if name and not entry.get("name"):
            entry["name"] = name
        elif not entry.get("name"):
            entry["name"] = handle.lstrip("@")
        changed = True
        print(f"  -> {channel_id} / {entry['name']}")

    if changed:
        CHANNELS_PATH.write_text(
            json.dumps(channels, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\n{CHANNELS_PATH} を更新しました。")
    else:
        print("\n更新はありませんでした。")

    if unresolved:
        print("\n--- 解決できなかった handle（手動で channel_id を調べて channels.json に追記してください）---", file=sys.stderr)
        for h in unresolved:
            print(f"  {h}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

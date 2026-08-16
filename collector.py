#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VAIO VJPJ21 中古品 価格トラッカー

楽天市場商品検索API (IchibaItem/Search) を叩いて、
「VJPJ21」を含む商品を検索 -> 商品名/説明文からランクとスペックを推定
-> docs/data/price_history.csv に1日分のスナップショットを追記する。

必要な環境変数:
    RAKUTEN_APPLICATION_ID  楽天ウェブサービスで発行したアプリID
    RAKUTEN_ACCESS_KEY      同アクセスキー (2026-07-01版APIから必須)
    RAKUTEN_AFFILIATE_ID    (任意) アフィリエイトID
"""

import csv
import os
import re
import sys
import time
import datetime as dt
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import json

API_ENDPOINT = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"
KEYWORD = "VJPJ21"
# 楽天ウェブサービスの管理画面 (https://webservice.rakuten.co.jp/app/list) で
# 対象アプリの「許可されたWebサイト」に登録した値と完全に一致させること。
# 一致していないと 403 REQUEST_CONTEXT_BODY_HTTP_REFERRER_MISSING になる。
ALLOWED_SITE = os.environ.get("RAKUTEN_ALLOWED_SITE", "https://github.com/")
OUTPUT_CSV = Path(__file__).parent / "docs" / "data" / "price_history.csv"
FIELDS = [
    "collected_at", "itemCode", "itemName", "shopName",
    "price", "rank", "memory_gb", "ssd_gb", "availability", "itemUrl",
]

# ランク判定パターン（上から順に評価。先にマッチしたものを採用）
RANK_PATTERNS = [
    ("新品/未開封", re.compile(r"新品|未開封|未使用品")),
    ("S(極美品)", re.compile(r"極美品|未使用に近い|Sランク")),
    ("A(美品)", re.compile(r"美品|Aランク")),
    ("B(傷や汚れあり)", re.compile(r"傷や汚れ|やや傷|使用感あり|Bランク")),
    ("C(ジャンク/訳あり)", re.compile(r"ジャンク|訳あり|動作未確認|Cランク|ワケあり")),
]

MEMORY_RE = re.compile(r"(?:メモリ|RAM)[^\d]{0,6}(\d{1,3})\s*GB", re.IGNORECASE)
SSD_RE = re.compile(r"SSD[^\d]{0,6}(\d{1,4})\s*(GB|TB)", re.IGNORECASE)


def classify_rank(text: str) -> str:
    for label, pattern in RANK_PATTERNS:
        if pattern.search(text):
            return label
    return "不明"


def extract_specs(text: str):
    memory_gb = None
    ssd_gb = None

    m = MEMORY_RE.search(text)
    if m:
        memory_gb = int(m.group(1))

    s = SSD_RE.search(text)
    if s:
        value = int(s.group(1))
        unit = s.group(2).upper()
        ssd_gb = value * 1024 if unit == "TB" else value

    return memory_gb, ssd_gb


def fetch_items():
    app_id = os.environ.get("RAKUTEN_APPLICATION_ID")
    access_key = os.environ.get("RAKUTEN_ACCESS_KEY")
    affiliate_id = os.environ.get("RAKUTEN_AFFILIATE_ID", "")

    if not app_id or not access_key:
        print("ERROR: RAKUTEN_APPLICATION_ID / RAKUTEN_ACCESS_KEY が未設定です", file=sys.stderr)
        sys.exit(1)

    items = []
    page = 1
    while True:
        params = {
            "applicationId": app_id,
            "accessKey": access_key,
            "keyword": KEYWORD,
            "availability": 0,  # 在庫なしも含めて全件監視（在庫復活の検知のため）
            "hits": 30,
            "page": page,
            "sort": "+itemPrice",
            "formatVersion": 2,
        }
        if affiliate_id:
            params["affiliateId"] = affiliate_id

        url = f"{API_ENDPOINT}?{urlencode(params)}"
        req = Request(
            url,
            headers={
                # 新基盤のBot対策。Referer/Origin両方が必須で、値は楽天側アプリ設定の
                # 「許可されたWebサイト」と完全一致している必要がある。
                "User-Agent": "Mozilla/5.0 (compatible; vaio-price-tracker/1.0; +https://github.com/)",
                "Referer": ALLOWED_SITE,
                "Origin": ALLOWED_SITE.rstrip("/"),
            },
        )
        try:
            with urlopen(req, timeout=15) as resp:
                data = json.load(resp)
        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            print(f"ERROR: HTTP {e.code} from Rakuten API", file=sys.stderr)
            print(f"Response body: {body}", file=sys.stderr)
            print(f"Request URL (secrets redacted): {url.split('?')[0]}?keyword={KEYWORD}&page={page}", file=sys.stderr)
            sys.exit(1)

        page_items = data.get("Items", data.get("items", []))
        if not page_items:
            break

        items.extend(page_items)

        page_count = data.get("pageCount", 1)
        if page >= page_count:
            break
        page += 1
        time.sleep(1)  # レート制限対策

    return items


def build_rows(items):
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d")
    rows = []
    for item in items:
        text = " ".join([
            item.get("itemName", ""),
            item.get("catchcopy", ""),
            item.get("itemCaption", ""),
        ])
        memory_gb, ssd_gb = extract_specs(text)
        rows.append({
            "collected_at": now,
            "itemCode": item.get("itemCode", ""),
            "itemName": item.get("itemName", ""),
            "shopName": item.get("shopName", ""),
            "price": item.get("itemPrice", ""),
            "rank": classify_rank(text),
            "memory_gb": memory_gb if memory_gb is not None else "",
            "ssd_gb": ssd_gb if ssd_gb is not None else "",
            "availability": item.get("availability", ""),
            "itemUrl": item.get("itemUrl", ""),
        })
    return rows


def append_csv(rows):
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    file_exists = OUTPUT_CSV.exists()
    with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


def main():
    items = fetch_items()
    rows = build_rows(items)
    append_csv(rows)
    print(f"{len(rows)} 件を {OUTPUT_CSV} に追記しました")


if __name__ == "__main__":
    main()

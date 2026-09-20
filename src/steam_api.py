from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

USER_AGENT = (
    "FURB-PLN-Projeto-Etapa1/1.0 "
    "(uso academico; contato: 00jonathan.ribeiro@gmail.com)"
)

HEADERS = {"User-Agent": USER_AGENT}
TIMEOUT = 20
REQUEST_DELAY_SECONDS = 1.2

REVIEWS_URL_TEMPLATE = "https://store.steampowered.com/appreviews/{appid}"
APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_REVIEWS_DIR = PROJECT_ROOT / "data" / "raw" / "reviews"
RAW_APPDETAILS_DIR = PROJECT_ROOT / "data" / "raw" / "appdetails"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request_with_backoff(session: requests.Session, url: str, params: dict) -> requests.Response:
    backoff = 5
    for attempt in range(5):
        response = session.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        if response.status_code in (429, 503):
            time.sleep(backoff)
            backoff *= 2
            continue
        response.raise_for_status()
        return response
    response.raise_for_status()
    return response


def fetch_reviews_page(
    session: requests.Session,
    appid: int,
    cursor: str = "*",
    language: str = "all",
    filter_: str = "recent",
    review_type: str = "all",
    purchase_type: str = "all",
    num_per_page: int = 100,
) -> dict:
    params = {
        "json": 1,
        "filter": filter_,
        "language": language,
        "cursor": cursor,
        "review_type": review_type,
        "purchase_type": purchase_type,
        "num_per_page": num_per_page,
    }
    url = REVIEWS_URL_TEMPLATE.format(appid=appid)
    response = _request_with_backoff(session, url, params)
    return response.json()


def collect_reviews(
    appid: int,
    max_reviews: int = 400,
    language: str = "all",
    filter_: str = "recent",
    save_raw: bool = True,
) -> list[dict]:
    session = requests.Session()
    out_dir = RAW_REVIEWS_DIR / str(appid)
    if save_raw:
        out_dir.mkdir(parents=True, exist_ok=True)

    collected: list[dict] = []
    cursor = "*"
    page = 0

    while len(collected) < max_reviews:
        payload = fetch_reviews_page(
            session, appid, cursor=cursor, language=language, filter_=filter_
        )

        if save_raw:
            record = {
                "collected_at": _now_iso(),
                "url": REVIEWS_URL_TEMPLATE.format(appid=appid),
                "params": {
                    "json": 1,
                    "filter": filter_,
                    "language": language,
                    "cursor": cursor,
                    "review_type": "all",
                    "purchase_type": "all",
                    "num_per_page": 100,
                },
                "response": payload,
            }
            page_path = out_dir / f"page_{page:03d}.json"
            page_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

        reviews = payload.get("reviews", [])
        if not reviews:
            break

        for review in reviews:
            review["appid"] = appid
            collected.append(review)

        next_cursor = payload.get("cursor")
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
        page += 1

        time.sleep(REQUEST_DELAY_SECONDS)

    return collected[:max_reviews]


def fetch_appdetails(appid: int, save_raw: bool = True) -> dict | None:
    session = requests.Session()
    params = {"appids": appid, "l": "portuguese"}
    response = _request_with_backoff(session, APPDETAILS_URL, params)
    payload = response.json()

    if save_raw:
        RAW_APPDETAILS_DIR.mkdir(parents=True, exist_ok=True)
        record = {
            "collected_at": _now_iso(),
            "url": APPDETAILS_URL,
            "params": params,
            "response": payload,
        }
        out_path = RAW_APPDETAILS_DIR / f"{appid}.json"
        out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    entry = payload.get(str(appid), {})
    if not entry.get("success"):
        return None
    return entry.get("data")


def hash_steam_id(steamid: str) -> str:
    return hashlib.sha256(steamid.encode("utf-8")).hexdigest()[:16]

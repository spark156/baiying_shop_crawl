import hashlib
import json
import re
import threading
from datetime import date, datetime
from pathlib import Path


STORE_PATH = Path("outputs/baiying_history.json")
LEGACY_JSON_PATH = Path("outputs/baiying_scene_products.json")
_LOCK = threading.RLock()


def _empty_store():
    return {"version": 1, "sessions": {}, "records": {}}


def _load():
    if not STORE_PATH.exists():
        return _empty_store()
    try:
        data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_store()
    if not isinstance(data, dict):
        return _empty_store()
    data.setdefault("sessions", {})
    data.setdefault("records", {})
    return data


def _save(data):
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def init_store():
    with _LOCK:
        if not STORE_PATH.exists():
            _save(_empty_store())


def parse_live_date(value):
    match = re.search(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", str(value or ""))
    if not match:
        return ""
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()
    except ValueError:
        return ""


def make_live_key(shop_name, live_row):
    identity = str(live_row.get("直播ID") or live_row.get("直播时间") or "").strip()
    raw = "{}|{}".format(str(shop_name or "").strip(), identity)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _make_record_key(live_key, row, index):
    identity = str(
        row.get("商品ID")
        or row.get("商品链接")
        or "{}|{}".format(row.get("商品名称", ""), index)
    ).strip()
    return hashlib.sha256("{}|{}".format(live_key, identity).encode("utf-8")).hexdigest()


def is_historical(live_date):
    return bool(live_date and live_date < date.today().isoformat())


def is_session_complete(shop_name, live_row):
    live_key = make_live_key(shop_name, live_row)
    with _LOCK:
        return live_key in _load()["sessions"]


def save_session(shop_name, shop_url, live_row, product_rows):
    live_key = make_live_key(shop_name, live_row)
    live_time = str(live_row.get("直播时间", ""))
    live_date = parse_live_date(live_time)
    now = datetime.now().isoformat(timespec="seconds")
    with _LOCK:
        data = _load()
        data["sessions"][live_key] = {
            "shop_name": shop_name,
            "shop_url": shop_url or "",
            "live_id": str(live_row.get("直播ID", "")),
            "live_time": live_time,
            "live_date": live_date,
            "live_duration": str(live_row.get("直播时长", "")),
            "product_count": int(live_row.get("带货商品数") or 0),
            "settled_count": len(product_rows),
            "completed_at": now,
        }
        stale_keys = [
            key for key, record in data["records"].items()
            if record.get("live_key") == live_key
        ]
        for key in stale_keys:
            del data["records"][key]
        for index, source_row in enumerate(product_rows, 1):
            row = dict(source_row)
            row["店铺名称"] = shop_name
            row["店铺网址"] = shop_url or row.get("店铺网址", "")
            row["直播日期"] = live_date
            record_key = _make_record_key(live_key, row, index)
            data["records"][record_key] = {
                "live_key": live_key,
                "shop_name": shop_name,
                "live_date": live_date,
                "live_time": live_time,
                "row": row,
                "updated_at": now,
            }
        _save(data)
    return live_key


def _matches(item, start_date, end_date, shop_names):
    live_date = item.get("live_date", "")
    if start_date and live_date and live_date < start_date:
        return False
    if end_date and live_date and live_date > end_date:
        return False
    if shop_names and item.get("shop_name", "") not in shop_names:
        return False
    return True


def query_records(start_date="", end_date="", shop_names=None, limit=None):
    with _LOCK:
        records = [
            item for item in _load()["records"].values()
            if _matches(item, start_date, end_date, shop_names)
        ]
    records.sort(
        key=lambda item: (
            item.get("live_time", ""),
            item.get("shop_name", ""),
            item.get("row", {}).get("商品名称", ""),
        ),
        reverse=True,
    )
    if limit:
        records = records[: int(limit)]
    return [item["row"] for item in records]


def get_summary(start_date="", end_date="", shop_names=None):
    with _LOCK:
        data = _load()
        records = [
            item for item in data["records"].values()
            if _matches(item, start_date, end_date, shop_names)
        ]
        sessions = [
            item for item in data["sessions"].values()
            if _matches(item, start_date, end_date, shop_names)
        ]
    dates = [item.get("live_date", "") for item in records if item.get("live_date")]
    shops = {item.get("shop_name", "") for item in records if item.get("shop_name")}
    return {
        "product_count": len(records),
        "shop_count": len(shops),
        "session_count": len(sessions),
        "first_date": min(dates) if dates else "",
        "last_date": max(dates) if dates else "",
    }


def import_legacy_json_if_needed():
    init_store()
    if not LEGACY_JSON_PATH.exists():
        return 0
    with _LOCK:
        if _load()["sessions"]:
            return 0
    rows = json.loads(LEGACY_JSON_PATH.read_text(encoding="utf-8"))
    groups = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        key = (
            str(row.get("店铺名称", "")),
            str(row.get("直播ID") or row.get("直播时间") or ""),
        )
        groups.setdefault(key, []).append(row)
    imported = 0
    for (shop_name, _), product_rows in groups.items():
        first = product_rows[0]
        live_row = {
            "直播ID": first.get("直播ID", ""),
            "直播时间": first.get("直播时间", ""),
            "直播时长": first.get("直播时长", ""),
            "带货商品数": len(product_rows),
        }
        save_session(shop_name, first.get("店铺网址", ""), live_row, product_rows)
        imported += len(product_rows)
    return imported

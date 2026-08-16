#!/usr/bin/env python3
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

OUT = Path("dongguan_out")
RAW = OUT / "raw"
OUT.mkdir(exist_ok=True)
RAW.mkdir(exist_ok=True)
PAGE_TITLE = "东莞市人民政府关于公布我市第三次全国文物普查不可移动文物名录的通知"
MIRROR_URL = "https://zh.wikisource.org/zh/" + quote(PAGE_TITLE)
API_URL = "https://zh.wikisource.org/w/api.php"
OFFICIAL_URL = "https://www.dg.gov.cn/zwgk/zfgb/zfgb/2012n/dbq/content/post_4408321.html"
TARGET = {"古建筑", "近现代重要史迹及代表性建筑"}
KNOWN = ["古遗址", "古墓葬", "古建筑", "石窟寺及石刻", "近现代重要史迹及代表性建筑", "其他"]
HEADERS = [
    "source_record_id", "census_name", "census_reference_date", "province_cn", "prefecture_cn",
    "county_district_cn", "local_sequence", "source_local_code", "relic_name", "era_raw", "category_raw",
    "category_standard", "address_raw", "protection_level_raw", "protection_level_standard",
    "longitude_wgs84", "latitude_wgs84", "coordinate_status", "source_id", "source_authority",
    "source_page_title", "source_page_date", "source_page_url", "source_attachment_url", "source_file",
    "source_locator", "source_grade", "verification_status", "notes"
]


def clean(value):
    s = "" if value is None else str(value)
    s = s.replace("\u3000", " ").replace("\xa0", " ")
    s = re.sub(r"[\r\n\t]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize_category(value):
    s = re.sub(r"\s+", "", clean(value))
    if "近现代" in s:
        return "近现代重要史迹及代表性建筑"
    if "古建筑" in s:
        return "古建筑"
    if "古遗址" in s or s == "遗址":
        return "古遗址"
    if "古墓葬" in s or s == "墓葬":
        return "古墓葬"
    if "石窟" in s or "石刻" in s:
        return "石窟寺及石刻"
    if "其他" in s:
        return "其他"
    return clean(value)


def normalize_level(raw, note):
    text = clean(raw) + " " + clean(note)
    if any(k in text for k in ["全国重点文物保护单位", "国保"]):
        return "国家级"
    if any(k in text for k in ["广东省文物保护单位", "省级文物保护单位", "省保"]):
        return "省级"
    if any(k in text for k in ["东莞市文物保护单位", "市级文物保护单位", "市保"]):
        return "市级"
    if "市、县级文物保护单位" in text or "市/县级" in text:
        return "市/县级未区分"
    if any(k in text for k in ["县级文物保护单位", "区级文物保护单位"]):
        return "县区级"
    if any(k in text for k in ["尚未核定", "未核定", "未定级"]):
        return "未核定为保护单位"
    return "未注明"


def make(seq, name, era, raw_level, address, note, category, locator):
    norm_level = normalize_level(raw_level, note)
    identity = "|".join([str(seq), name, category, address])
    return {
        "source_record_id": "SRC-DG-20120813-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16],
        "census_name": "第三次全国文物普查", "census_reference_date": "2007-09-30",
        "province_cn": "广东省", "prefecture_cn": "东莞市", "county_district_cn": "",
        "local_sequence": str(seq), "source_local_code": "", "relic_name": name, "era_raw": era,
        "category_raw": category, "category_standard": category, "address_raw": address,
        "protection_level_raw": clean(raw_level), "protection_level_standard": norm_level,
        "longitude_wgs84": "", "latitude_wgs84": "", "coordinate_status": "待地理编码",
        "source_id": "SRC-DG-20120813", "source_authority": "东莞市人民政府",
        "source_page_title": "关于公布我市第三次全国文物普查不可移动文物名录的通知",
        "source_page_date": "2012-08-13", "source_page_url": OFFICIAL_URL,
        "source_attachment_url": MIRROR_URL, "source_file": "dongguan_wikisource_api.html",
        "source_locator": locator, "source_grade": "B+-政府公报文本镜像，官方页面总量交叉核验",
        "verification_status": "镜像逐条文本；官方页面确认名录总量459条",
        "notes": clean(note)
    }


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADERS, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": "historical-building-research/1.0", "Accept-Language": "zh-CN,zh;q=0.9"})
    r = session.get(API_URL, params={"action":"parse", "page":PAGE_TITLE, "prop":"text", "format":"json", "formatversion":"2"}, timeout=120)
    r.raise_for_status()
    payload = r.json()
    html = payload["parse"]["text"]
    (RAW / "dongguan_wikisource_api.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    (RAW / "dongguan_wikisource_api.html").write_text(html, encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")
    rows = []
    current = ""
    table_no = 0
    for table_no, table in enumerate(soup.find_all("table"), start=1):
        for row_no, tr in enumerate(table.find_all("tr"), start=1):
            cells = [clean(c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])]
            if len(cells) == 1 and cells[0]:
                maybe = normalize_category(cells[0])
                if maybe in KNOWN:
                    current = maybe
                continue
            # Expected: sequence, name, era, protection level, address, note.
            if len(cells) >= 6 and re.fullmatch(r"\d+", cells[0]):
                seq, name, era, raw_level, address = cells[:5]
                note = clean(" ".join(cells[5:]))
                if current not in KNOWN:
                    continue
                rows.append(make(seq, name, era, raw_level, address, note, current, f"table:{table_no};row:{row_no}"))
    # Deduplicate by section sequence/name/address.
    best = {}
    for rec in rows:
        key = (rec["category_standard"], rec["local_sequence"], rec["relic_name"], rec["address_raw"])
        best[key] = rec
    rows = list(best.values())
    rows.sort(key=lambda x: (KNOWN.index(x["category_standard"]), int(x["local_sequence"]), x["relic_name"]))
    target = [r for r in rows if r["category_standard"] in TARGET]
    write_csv(OUT / "dongguan_all_records.csv", rows)
    write_csv(OUT / "dongguan_target_records.csv", target)
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "official_page_url": OFFICIAL_URL,
        "mirror_url": MIRROR_URL, "all_record_count": len(rows), "target_record_count": len(target),
        "category_counts": dict(Counter(r["category_standard"] for r in rows)),
        "target_category_counts": dict(Counter(r["category_standard"] for r in target)),
        "protection_level_counts_all": dict(Counter(r["protection_level_standard"] for r in rows)),
        "protection_level_counts_target": dict(Counter(r["protection_level_standard"] for r in target)),
        "expected_official_total": 459,
        "reconciliation_status": "complete" if len(rows) == 459 else "mismatch"
    }
    (OUT / "dongguan_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    with open(OUT / "SHA256SUMS.txt", "w", encoding="utf-8") as f:
        for p in sorted(OUT.rglob("*")):
            if p.is_file() and p.name != "SHA256SUMS.txt":
                f.write(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(OUT)}\n")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import csv
import hashlib
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
OUT = Path("supplemental_out")
RAW = OUT / "raw"
OUT.mkdir(exist_ok=True)
RAW.mkdir(exist_ok=True)
TARGET = {"古建筑", "近现代重要史迹及代表性建筑"}
KNOWN = ["古遗址", "古墓葬", "古建筑", "石窟寺及石刻", "近现代重要史迹及代表性建筑", "其他"]
HEADERS = [
    "source_record_id", "census_name", "census_reference_date", "province_cn", "prefecture_cn",
    "county_district_cn", "local_sequence", "source_local_code", "relic_name", "era_raw", "category_raw",
    "category_standard", "address_raw", "protection_level_raw", "protection_level_standard",
    "longitude_wgs84", "latitude_wgs84", "coordinate_status", "source_id", "source_authority",
    "source_page_title", "source_page_date", "source_page_url", "source_file", "source_locator",
    "source_grade", "verification_status", "notes"
]

SOURCES = {
    "DG": {
        "source_id": "SRC-DG-20120813", "province_cn": "广东省", "prefecture_cn": "东莞市", "county_district_cn": "",
        "authority": "东莞市人民政府", "title": "关于公布我市第三次全国文物普查不可移动文物名录的通知",
        "date": "2012-08-13", "page_url": "https://www.dg.gov.cn/zwgk/zfgb/zfgb/2012n/dbq/content/post_4408321.html",
        "file_url": "https://www.dg.gov.cn/attachment/cmsfile/cndg/zfwj/201208/daofile/307doc126540.xls",
        "expected": 459, "grade": "A-地方人民政府"
    },
    "ND": {
        "source_id": "SRC-ND-20250924", "province_cn": "西藏自治区", "prefecture_cn": "山南市", "county_district_cn": "乃东区",
        "authority": "乃东区人民政府办公室", "title": "关于公布乃东区第三次全国文物普查文物名录的通知",
        "date": "2025-09-24", "page_url": "https://www.naidong.gov.cn/xwzx/tggs/202509/t20250924_155749.html",
        "expected": 72, "grade": "A-地方人民政府"
    }
}

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 historical-building-research/1.0", "Accept-Language": "zh-CN,zh;q=0.9"})


def clean(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).replace("\u3000", " ").replace("\xa0", " ")
    s = re.sub(r"[\r\n\t]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def category(v):
    s = re.sub(r"\s+", "", clean(v))
    aliases = {
        "遗址": "古遗址", "墓葬": "古墓葬", "石刻": "石窟寺及石刻", "石窟寺": "石窟寺及石刻",
        "近现代重要史迹": "近现代重要史迹及代表性建筑", "近现代重要史迹及代表性建筑": "近现代重要史迹及代表性建筑",
        "古建筑": "古建筑", "古遗址": "古遗址", "古墓葬": "古墓葬", "石窟寺及石刻": "石窟寺及石刻", "其他": "其他"
    }
    if s in aliases:
        return aliases[s]
    for k in ["近现代重要史迹及代表性建筑", "古建筑", "古遗址", "古墓葬", "石窟寺及石刻"]:
        if k in s:
            return k
    if "近现代" in s:
        return "近现代重要史迹及代表性建筑"
    if "石刻" in s or "石窟" in s:
        return "石窟寺及石刻"
    if "墓" in s:
        return "古墓葬"
    if "遗址" in s:
        return "古遗址"
    return clean(v)


def make(source, seq, code, name, era, cat_raw, address, source_file, locator):
    cat = category(cat_raw)
    raw = "|".join([source["source_id"], clean(code), clean(name), clean(era), cat, clean(address)])
    return {
        "source_record_id": f"{source['source_id']}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}",
        "census_name": "第三次全国文物普查", "census_reference_date": "2007-09-30",
        "province_cn": source["province_cn"], "prefecture_cn": source["prefecture_cn"],
        "county_district_cn": source["county_district_cn"], "local_sequence": clean(seq),
        "source_local_code": clean(code), "relic_name": clean(name), "era_raw": clean(era),
        "category_raw": clean(cat_raw), "category_standard": cat, "address_raw": clean(address),
        "protection_level_raw": "", "protection_level_standard": "未注明", "longitude_wgs84": "",
        "latitude_wgs84": "", "coordinate_status": "待地理编码", "source_id": source["source_id"],
        "source_authority": source["authority"], "source_page_title": source["title"],
        "source_page_date": source["date"], "source_page_url": source["page_url"], "source_file": source_file,
        "source_locator": locator, "source_grade": source["grade"], "verification_status": "已核验官方来源",
        "notes": "地方不可移动文物名录不等同于市级文物保护单位；未见明确保护级别时标记为未注明。"
    }


def write_csv(path, rows, headers=HEADERS):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)


def fetch(url, verify=True, attempts=3):
    last = None
    for n in range(1, attempts + 1):
        try:
            r = SESSION.get(url, timeout=120, allow_redirects=True, verify=verify)
            r.raise_for_status()
            return r
        except Exception as exc:
            last = exc; time.sleep(n * 2)
    raise last


def parse_dongguan():
    s = SOURCES["DG"]
    r = fetch(s["file_url"])
    path = RAW / "dongguan_459.xls"; path.write_bytes(r.content)
    sheets = pd.read_excel(path, sheet_name=None, header=None, dtype=object)
    records = []
    diagnostics = []
    for sheet_name, df in sheets.items():
        matrix = [[clean(v) for v in row] for row in df.astype(object).values.tolist()]
        diagnostics.append({"sheet": str(sheet_name), "rows": len(matrix), "cols": max((len(x) for x in matrix), default=0), "sample": matrix[:8]})
        # Locate a header row containing both 名称 and 类别/类型.
        hrow = None; mapping = {}
        for i, row in enumerate(matrix[:80]):
            compact = [re.sub(r"\s+", "", x) for x in row]
            joined = "|".join(compact)
            if "名称" not in joined or not any(k in joined for k in ["类别", "类型"]):
                continue
            for j, h in enumerate(compact):
                if "序号" in h: mapping.setdefault("seq", j)
                if any(k in h for k in ["编号", "编码", "代码"]): mapping.setdefault("code", j)
                if "名称" in h: mapping.setdefault("name", j)
                if any(k in h for k in ["年代", "时代"]): mapping.setdefault("era", j)
                if any(k in h for k in ["类别", "类型"]): mapping.setdefault("cat", j)
                if any(k in h for k in ["地址", "地点", "位置"]): mapping.setdefault("address", j)
            if "name" in mapping and "cat" in mapping:
                hrow = i; break
        if hrow is None:
            continue
        for idx, row in enumerate(matrix[hrow + 1:], start=hrow + 2):
            def get(k):
                j = mapping.get(k); return row[j] if j is not None and j < len(row) else ""
            name = clean(get("name")); cat_raw = clean(get("cat")); cat = category(cat_raw)
            if not name or cat not in KNOWN:
                continue
            seq = re.sub(r"\.0$", "", clean(get("seq")))
            code = re.sub(r"\.0$", "", clean(get("code")))
            records.append(make(s, seq, code, name, get("era"), cat_raw, get("address"), path.name, f"sheet:{sheet_name};row:{idx}"))
    (OUT / "dongguan_diagnostics.json").write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
    return records, path


def parse_naidong():
    s = SOURCES["ND"]
    r = fetch(s["page_url"], verify=False)
    path = RAW / "naidong_72.html"; path.write_bytes(r.content)
    if not r.encoding or r.encoding.lower() == "iso-8859-1": r.encoding = r.apparent_encoding or "utf-8"
    soup = BeautifulSoup(r.text, "lxml")
    records = []
    for tno, table in enumerate(soup.find_all("table"), start=1):
        for ridx, tr in enumerate(table.find_all("tr"), start=1):
            cells = [clean(c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])]
            if len(cells) < 5 or not re.fullmatch(r"\d+", cells[0]):
                continue
            seq, name, cat_raw, era = cells[:4]
            address = clean(" ".join(cells[4:]))
            cat = category(cat_raw)
            if name and cat in KNOWN:
                records.append(make(s, seq, "", name, era, cat_raw, address, path.name, f"table:{tno};row:{ridx}"))
    # Fallback: parse crawled text-like rows from page body if table markup is flattened.
    if len(records) < 10:
        text = soup.get_text("\n", strip=True)
        lines = [clean(x) for x in text.splitlines() if clean(x)]
        for i in range(len(lines) - 4):
            if not re.fullmatch(r"\d+", lines[i]):
                continue
            cat = category(lines[i+2])
            if cat in KNOWN:
                records.append(make(s, lines[i], "", lines[i+1], lines[i+3], lines[i+2], lines[i+4], path.name, f"text-line:{i+1}"))
    best = {}
    for rec in records:
        key = (rec["local_sequence"], rec["relic_name"], rec["category_standard"], rec["address_raw"])
        best[key] = rec
    return list(best.values()), path


def main():
    all_rows = []; status = []
    for key, parser in [("DG", parse_dongguan), ("ND", parse_naidong)]:
        src = SOURCES[key]
        try:
            rows, raw_path = parser()
            all_rows.extend(rows)
            status.append({"source_id": src["source_id"], "expected": src["expected"], "parsed": len(rows),
                           "target": sum(r["category_standard"] in TARGET for r in rows),
                           "status": "complete" if len(rows) == src["expected"] else ("partial" if rows else "failed"),
                           "raw_file": raw_path.name, "error": ""})
        except Exception as exc:
            status.append({"source_id": src["source_id"], "expected": src["expected"], "parsed": 0, "target": 0,
                           "status": "failed", "raw_file": "", "error": repr(exc)})
    all_rows.sort(key=lambda r: (r["source_id"], str(r["local_sequence"]).zfill(8), r["relic_name"]))
    target = [r for r in all_rows if r["category_standard"] in TARGET]
    write_csv(OUT / "supplemental_all_records.csv", all_rows)
    write_csv(OUT / "supplemental_target_records.csv", target)
    write_csv(OUT / "supplemental_source_status.csv", status, list(status[0].keys()))
    meta = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "all_record_count": len(all_rows),
        "target_record_count": len(target), "category_counts": dict(Counter(r["category_standard"] for r in all_rows)),
        "target_category_counts": dict(Counter(r["category_standard"] for r in target)), "sources": status
    }
    (OUT / "supplemental_metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    with open(OUT / "SHA256SUMS.txt", "w", encoding="utf-8") as f:
        for p in sorted(OUT.rglob("*")):
            if p.is_file() and p.name != "SHA256SUMS.txt":
                f.write(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(OUT)}\n")
    print(json.dumps(meta, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import csv
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

OUT = Path("local_out")
RAW = OUT / "raw"
ATT = OUT / "attachments"
OUT.mkdir(exist_ok=True)
RAW.mkdir(exist_ok=True)
ATT.mkdir(exist_ok=True)

TARGET = {"古建筑", "近现代重要史迹及代表性建筑"}
KNOWN_CATEGORIES = [
    "古遗址", "古墓葬", "古建筑", "石窟寺及石刻", "近现代重要史迹及代表性建筑", "其他"
]

SOURCES = [
    {
        "source_id": "SRC-BN-20250606",
        "jurisdiction": "重庆市巴南区",
        "province_cn": "重庆市",
        "prefecture_cn": "重庆市",
        "county_district_cn": "巴南区",
        "authority": "重庆市巴南区文物局",
        "title": "关于公布巴南区第三次全国文物普查不可移动文物名录的通知",
        "page_date": "2025-06-06",
        "url": "https://www.cqbn.gov.cn/bmjz/bm/whlyw/zwgk_88881/fdzdgknr_88883/lzyj_88884/zcwj/qtwj/202506/t20250606_14693125.html",
        "expected_records": 1485,
        "source_grade": "A-地方文物主管部门",
    },
    {
        "source_id": "SRC-KYZQ-20240222",
        "jurisdiction": "内蒙古自治区科尔沁右翼中旗",
        "province_cn": "内蒙古自治区",
        "prefecture_cn": "兴安盟",
        "county_district_cn": "科尔沁右翼中旗",
        "authority": "科尔沁右翼中旗人民政府",
        "title": "关于公布《科尔沁右翼中旗第三次全国不可移动文物普查名录》的通知",
        "page_date": "2024-02-22",
        "url": "https://kyzq.gov.cn/kyzq/2024-02/22/article_2024041409493378878.html",
        "expected_records": 186,
        "source_grade": "A-地方人民政府",
    },
    {
        "source_id": "SRC-TP-20250325",
        "jurisdiction": "辽宁省阜新市太平区",
        "province_cn": "辽宁省",
        "prefecture_cn": "阜新市",
        "county_district_cn": "太平区",
        "authority": "太平区人民政府办公室",
        "title": "关于公布第三次全国文物普查不可移动文物名录的通知",
        "page_date": "2025-03-25",
        "url": "https://www.fxtp.gov.cn/content/2025/981554.html",
        "expected_records": 15,
        "source_grade": "A-地方人民政府",
    },
    {
        "source_id": "SRC-ND-20250924",
        "jurisdiction": "西藏自治区山南市乃东区",
        "province_cn": "西藏自治区",
        "prefecture_cn": "山南市",
        "county_district_cn": "乃东区",
        "authority": "乃东区人民政府办公室",
        "title": "关于公布乃东区第三次全国文物普查文物名录的通知",
        "page_date": "2025-09-24",
        "url": "https://www.naidong.gov.cn/xwzx/tggs/202509/t20250924_155749.html",
        "expected_records": 72,
        "source_grade": "A-地方人民政府",
    },
    {
        "source_id": "SRC-YL-20240417",
        "jurisdiction": "陕西省咸阳市杨陵区",
        "province_cn": "陕西省",
        "prefecture_cn": "咸阳市",
        "county_district_cn": "杨陵区",
        "authority": "杨陵区人民政府",
        "title": "关于公布杨陵区第三次全国文物普查不可移动文物名录的通知",
        "page_date": "2024-04-17",
        "url": "https://www.ylq.gov.cn/zfxxgk/fdzdgknr/gkwj/qzfwj/1907002425423228930.html",
        "expected_records": 53,
        "source_grade": "A-地方人民政府",
    },
    {
        "source_id": "SRC-ZS-20120110",
        "jurisdiction": "广东省中山市",
        "province_cn": "广东省",
        "prefecture_cn": "中山市",
        "county_district_cn": "",
        "authority": "中山市人民政府",
        "title": "关于公布中山市第三次全国文物普查不可移动文物名录的通知",
        "page_date": "2012-01-10",
        "url": "https://www.zs.gov.cn/zwgk/fggw/szfwj/content/post_256288.html",
        "expected_records": 558,
        "source_grade": "A-地方人民政府",
    },
    {
        "source_id": "SRC-DG-20101001",
        "jurisdiction": "广东省东莞市",
        "province_cn": "广东省",
        "prefecture_cn": "东莞市",
        "county_district_cn": "",
        "authority": "东莞市人民政府",
        "title": "关于公布东莞市第三次全国文物普查不可移动文物名录的通知",
        "page_date": "2010-10-01",
        "url": "https://www.dg.gov.cn/zwgk/zfgb/szfwj/content/post_340920.html",
        "expected_records": 459,
        "source_grade": "A-地方人民政府",
    },
    {
        "source_id": "SRC-ZH-XZ-20111117",
        "jurisdiction": "广东省珠海市香洲区",
        "province_cn": "广东省",
        "prefecture_cn": "珠海市",
        "county_district_cn": "香洲区",
        "authority": "香洲区人民政府公报文本镜像",
        "title": "关于公布珠海市香洲区第三次全国文物普查不可移动文物名录的通知",
        "page_date": "2011-11-17",
        "url": "https://zh.wikisource.org/wiki/关于公布珠海市香洲区第三次全国文物普查不可移动文物名录的通知",
        "expected_records": 81,
        "source_grade": "B-政府公报镜像待回溯",
    },
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36 historical-building-research/1.0",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
})


def clean_text(value):
    if value is None:
        return ""
    s = str(value).replace("\u3000", " ").replace("\xa0", " ")
    s = re.sub(r"[\r\n\t]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def category_normalize(value):
    s = clean_text(value)
    compact = re.sub(r"\s+", "", s)
    compact = compact.replace("近现代重要史迹及代表性建 筑", "近现代重要史迹及代表性建筑")
    compact = compact.replace("石窟寺及石 刻", "石窟寺及石刻")
    for cat in KNOWN_CATEGORIES:
        if compact == cat or cat in compact:
            return cat
    return s


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def fetch_url(url, max_attempts=3):
    last = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = SESSION.get(url, timeout=90, allow_redirects=True)
            response.raise_for_status()
            if not response.encoding or response.encoding.lower() == "iso-8859-1":
                response.encoding = response.apparent_encoding or "utf-8"
            return response
        except Exception as exc:
            last = exc
            time.sleep(attempt * 2)
    raise last


def normalize_header(value):
    return re.sub(r"\s+", "", clean_text(value)).lower()


def parse_html_tables(html, source, source_file):
    soup = BeautifulSoup(html, "lxml")
    records = []
    seen = set()
    for table_no, table in enumerate(soup.find_all("table"), start=1):
        for row_no, tr in enumerate(table.find_all("tr"), start=1):
            cells = [clean_text(c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])]
            cells = [c for c in cells if c != ""]
            if len(cells) < 4:
                continue
            code_idx = None
            for idx, cell in enumerate(cells):
                compact = re.sub(r"\s+", "", cell)
                if re.fullmatch(r"(?:\d{6}-\d{4}|\d{15,20}|\d{6,}-?\d{1,6})", compact):
                    code_idx = idx
                    break
            if code_idx is None:
                continue
            cat_idx = None
            cat = ""
            for idx, cell in enumerate(cells):
                c = category_normalize(cell)
                if c in KNOWN_CATEGORIES:
                    cat_idx = idx
                    cat = c
                    break
            if cat_idx is None or cat_idx <= code_idx:
                continue
            code = re.sub(r"\s+", "", cells[code_idx])
            # Most official tables use [sequence, code, name, era, category, address].
            name = clean_text(cells[code_idx + 1]) if code_idx + 1 < len(cells) else ""
            era = clean_text(" ".join(cells[code_idx + 2:cat_idx]))
            address = clean_text(" ".join(cells[cat_idx + 1:]))
            seq = clean_text(cells[code_idx - 1]) if code_idx > 0 and re.fullmatch(r"\d+", cells[code_idx - 1]) else ""
            if not name or name in {"名称", "文物名称"}:
                continue
            key = (source["source_id"], code, name, cat, address)
            if key in seen:
                continue
            seen.add(key)
            records.append(make_record(source, seq, code, name, era, cat, address, source_file, f"HTML-table-{table_no}-row-{row_no}"))
    return records, soup


def find_header_mapping(matrix):
    for r_idx, row in enumerate(matrix[:60]):
        headers = [normalize_header(x) for x in row]
        joined = "|".join(headers)
        if "名称" not in joined or "类别" not in joined:
            continue
        mapping = {}
        for c_idx, h in enumerate(headers):
            if any(k in h for k in ["编号", "代码", "文物编码", "普查编号"]): mapping.setdefault("code", c_idx)
            if "序号" in h: mapping.setdefault("sequence", c_idx)
            if "名称" in h: mapping.setdefault("name", c_idx)
            if "年代" in h or "时代" in h: mapping.setdefault("era", c_idx)
            if "类别" in h or "类型" in h: mapping.setdefault("category", c_idx)
            if "地址" in h or "地点" in h or "位置" in h: mapping.setdefault("address", c_idx)
            if "保护级别" in h or "保护等级" in h: mapping.setdefault("protection", c_idx)
        if "name" in mapping and "category" in mapping:
            return r_idx, mapping
    return None, None


def dataframe_to_records(df, source, source_file, sheet_name):
    matrix = [[clean_text(v) if not pd.isna(v) else "" for v in row] for row in df.astype(object).values.tolist()]
    header_row, mapping = find_header_mapping(matrix)
    if mapping is None:
        return []
    records = []
    for idx, row in enumerate(matrix[header_row + 1:], start=header_row + 2):
        def get(k):
            pos = mapping.get(k)
            return clean_text(row[pos]) if pos is not None and pos < len(row) else ""
        name = get("name")
        cat = category_normalize(get("category"))
        if not name or cat not in KNOWN_CATEGORIES:
            continue
        code = re.sub(r"\.0$", "", get("code"))
        seq = re.sub(r"\.0$", "", get("sequence"))
        rec = make_record(source, seq, code, name, get("era"), cat, get("address"), source_file, f"sheet:{sheet_name};row:{idx}")
        rec["protection_level_raw"] = get("protection")
        records.append(rec)
    return records


def parse_spreadsheet(path, source):
    records = []
    try:
        sheets = pd.read_excel(path, sheet_name=None, header=None, dtype=object)
    except Exception as exc:
        return [], f"read_excel failed: {exc}"
    for sheet_name, df in sheets.items():
        records.extend(dataframe_to_records(df, source, path.name, str(sheet_name)))
    return records, ""


def make_record(source, sequence, code, name, era, category, address, source_file, locator):
    raw = "|".join([source["source_id"], code, name, era, category, address])
    return {
        "source_record_id": f"{source['source_id']}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}",
        "census_name": "第三次全国文物普查",
        "census_reference_date": "2007-09-30",
        "province_cn": source["province_cn"],
        "prefecture_cn": source["prefecture_cn"],
        "county_district_cn": source["county_district_cn"],
        "local_sequence": sequence,
        "source_local_code": code,
        "relic_name": clean_text(name),
        "era_raw": clean_text(era),
        "category_raw": clean_text(category),
        "category_standard": category_normalize(category),
        "address_raw": clean_text(address),
        "protection_level_raw": "",
        "protection_level_standard": "未注明",
        "longitude_wgs84": "",
        "latitude_wgs84": "",
        "coordinate_status": "待地理编码",
        "source_id": source["source_id"],
        "source_authority": source["authority"],
        "source_page_title": source["title"],
        "source_page_date": source["page_date"],
        "source_page_url": source["url"],
        "source_file": source_file,
        "source_locator": locator,
        "source_grade": source["source_grade"],
        "verification_status": "已核验官方来源" if source["source_grade"].startswith("A-") else "待回溯官方原件",
        "notes": "",
    }


def extract_attachments(soup, base_url, source):
    found = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a.get("href"))
        text = clean_text(a.get_text(" ", strip=True))
        path = urlparse(href).path.lower()
        if any(path.endswith(ext) for ext in [".xls", ".xlsx", ".csv", ".zip", ".doc", ".docx", ".pdf"]) or any(k in text for k in ["附件", "下载", "名录"]):
            found.append((href, text))
    # Preserve order, remove duplicates.
    out = []
    seen = set()
    for item in found:
        if item[0] not in seen:
            seen.add(item[0])
            out.append(item)
    return out


def safe_filename(source_id, url, content_type=""):
    name = Path(urlparse(url).path).name
    if not name or "." not in name:
        ext = ""
        ct = (content_type or "").lower()
        for k, v in [("excel", ".xlsx"), ("spreadsheet", ".xls"), ("zip", ".zip"), ("pdf", ".pdf"), ("word", ".docx")]:
            if k in ct:
                ext = v
                break
        name = "attachment" + ext
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return f"{source_id}__{name}"


def write_csv(path, rows, headers):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    all_records = []
    status_rows = []
    attachment_rows = []
    errors = []
    for source in SOURCES:
        status = {
            "source_id": source["source_id"],
            "jurisdiction": source["jurisdiction"],
            "url": source["url"],
            "expected_records": source["expected_records"],
            "http_status": "",
            "html_bytes": 0,
            "html_table_records": 0,
            "attachment_records": 0,
            "all_parsed_records": 0,
            "target_records": 0,
            "target_ancient_buildings": 0,
            "target_modern_sites": 0,
            "status": "",
            "error": "",
        }
        try:
            response = fetch_url(source["url"])
            status["http_status"] = response.status_code
            content = response.content
            status["html_bytes"] = len(content)
            raw_path = RAW / f"{source['source_id']}.html"
            raw_path.write_bytes(content)
            html = response.text
            html_records, soup = parse_html_tables(html, source, raw_path.name)
            status["html_table_records"] = len(html_records)
            source_records = list(html_records)
            for att_url, link_text in extract_attachments(soup, response.url, source):
                att_row = {
                    "source_id": source["source_id"], "url": att_url, "link_text": link_text,
                    "status": "", "file_name": "", "bytes": 0, "sha256": "", "parsed_records": 0, "error": ""
                }
                try:
                    r = fetch_url(att_url, max_attempts=2)
                    fname = safe_filename(source["source_id"], r.url, r.headers.get("content-type", ""))
                    fpath = ATT / fname
                    fpath.write_bytes(r.content)
                    att_row.update({"status": "downloaded", "file_name": fname, "bytes": len(r.content), "sha256": sha256_bytes(r.content)})
                    if fpath.suffix.lower() in {".xls", ".xlsx"}:
                        recs, err = parse_spreadsheet(fpath, source)
                        if err:
                            att_row["error"] = err
                        else:
                            att_row["parsed_records"] = len(recs)
                            source_records.extend(recs)
                except Exception as exc:
                    att_row["status"] = "failed"
                    att_row["error"] = repr(exc)
                attachment_rows.append(att_row)
            # Source-level de-duplication: prefer records with more complete fields.
            best = {}
            for rec in source_records:
                key = (rec["source_local_code"], rec["relic_name"], rec["category_standard"], rec["address_raw"])
                score = sum(bool(rec.get(k)) for k in ["source_local_code", "relic_name", "era_raw", "category_standard", "address_raw"])
                if key not in best or score > best[key][0]:
                    best[key] = (score, rec)
            source_records = [x[1] for x in best.values()]
            all_records.extend(source_records)
            status["attachment_records"] = sum(r["parsed_records"] for r in attachment_rows if r["source_id"] == source["source_id"])
            status["all_parsed_records"] = len(source_records)
            status["target_records"] = sum(r["category_standard"] in TARGET for r in source_records)
            status["target_ancient_buildings"] = sum(r["category_standard"] == "古建筑" for r in source_records)
            status["target_modern_sites"] = sum(r["category_standard"] == "近现代重要史迹及代表性建筑" for r in source_records)
            expected = source["expected_records"]
            if len(source_records) == expected:
                status["status"] = "complete"
            elif len(source_records) > 0:
                status["status"] = "partial"
            else:
                status["status"] = "no_records"
        except Exception as exc:
            status["status"] = "failed"
            status["error"] = repr(exc)
            errors.append({"source_id": source["source_id"], "url": source["url"], "error": repr(exc)})
        status_rows.append(status)
        print(json.dumps(status, ensure_ascii=False), flush=True)

    headers = list(make_record(SOURCES[0], "", "", "", "", "", "", "", "").keys())
    all_records.sort(key=lambda r: (r["source_id"], r["local_sequence"].zfill(8), r["source_local_code"], r["relic_name"]))
    target_records = [r for r in all_records if r["category_standard"] in TARGET]
    write_csv(OUT / "local_all_records.csv", all_records, headers)
    write_csv(OUT / "local_target_records.csv", target_records, headers)
    write_csv(OUT / "local_source_status.csv", status_rows, list(status_rows[0].keys()))
    if attachment_rows:
        write_csv(OUT / "attachment_manifest.csv", attachment_rows, list(attachment_rows[0].keys()))
    else:
        write_csv(OUT / "attachment_manifest.csv", [], ["source_id", "url", "link_text", "status", "file_name", "bytes", "sha256", "parsed_records", "error"])

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_count": len(SOURCES),
        "all_record_count": len(all_records),
        "target_record_count": len(target_records),
        "category_counts": dict(Counter(r["category_standard"] for r in all_records)),
        "target_category_counts": dict(Counter(r["category_standard"] for r in target_records)),
        "source_record_counts": dict(Counter(r["source_id"] for r in all_records)),
        "source_target_counts": dict(Counter(r["source_id"] for r in target_records)),
        "complete_sources": [r["source_id"] for r in status_rows if r["status"] == "complete"],
        "partial_sources": [r["source_id"] for r in status_rows if r["status"] == "partial"],
        "failed_sources": [r["source_id"] for r in status_rows if r["status"] == "failed"],
        "errors": errors,
    }
    (OUT / "local_harvest_metadata.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    with open(OUT / "SHA256SUMS.txt", "w", encoding="utf-8") as f:
        for p in sorted(OUT.rglob("*")):
            if p.is_file() and p.name != "SHA256SUMS.txt":
                f.write(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(OUT)}\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

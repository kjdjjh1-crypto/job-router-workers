#!/usr/bin/env python3
# H15 GHA 갈래 압축기 — 원천(data.binance.vision) 월·일 zip → 15분 특성 저장소 칸.
# 형식·규칙은 config/h15.json store와 src/h15_store.mjs와 같다(같은 15분 규칙, 같은 칸 정의).
# -2026- 이 든 원천 URL은 만들지 않는다(코드로 막고 시험한다). .CHECKSUM이 있으면 대조한다.
# 출력: jr-artifacts/ 에 칸마다 <cell>.f32 + <cell>.meta.json, 레인마다 manifest.json
import array, hashlib, io, json, os, sys, urllib.error, urllib.request, zipfile
from datetime import datetime, timezone

BIN_MS = 900000
SPAN_START = int(datetime(2017, 7, 1, tzinfo=timezone.utc).timestamp() * 1000) // BIN_MS * BIN_MS
SPAN_END = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
BASE = "https://data.binance.vision/"

TABLES = {
    "klines": ["o", "h", "l", "c", "quote_volume", "count", "taker_buy_quote"],
    "of": ["buy_quote", "sell_quote", "n_agg", "max_agg_quote",
           "buy_n_ge_10k", "buy_quote_ge_10k", "sell_n_ge_10k", "sell_quote_ge_10k",
           "buy_n_ge_100k", "buy_quote_ge_100k", "sell_n_ge_100k", "sell_quote_ge_100k",
           "buy_n_ge_1m", "buy_quote_ge_1m", "sell_n_ge_1m", "sell_quote_ge_1m"],
    "tf": ["n_trades", "n_buy", "buy_quote", "sell_quote", "max_trade_quote", "id_gaps"],
    "mark": ["c"], "index": ["c"], "premium": ["c", "h", "l"],
    "metrics": ["sum_open_interest", "sum_open_interest_value", "ratio_toptrader_account",
                "ratio_toptrader_position", "ratio_global_account", "ratio_global_position", "ratio_taker"],
    "funding": ["rate", "interval_hours"],
    "bd": ["b1", "a1", "b2", "a2", "b5", "a5", "imb1", "imb2", "imb5"],
    "bv": ["c"],
}


def to_ms(v):
    v = int(float(v))
    return v // 1000 if v >= 10**14 else v


def num(s):
    try:
        return float(s)
    except Exception:
        return float("nan")


class Cells:
    def __init__(self, kind):
        self.kind = kind
        self.ncols = len(TABLES[kind])
        self.bins = {}

    def cell(self, t):
        if t != t:
            return None
        b = t // BIN_MS * BIN_MS
        if b < SPAN_START or b >= SPAN_END:
            return None
        c = self.bins.get(b)
        if c is None:
            c = {"n": 0, "sum": [0.0] * self.ncols, "min": [float("inf")] * self.ncols,
                 "max": [float("-inf")] * self.ncols, "last": [float("nan")] * self.ncols,
                 "first": [float("nan")] * self.ncols, "snap": {}, "snapTs": -1}
            self.bins[b] = c
        return c

    def add(self, t, r):
        c = self.cell(t)
        if c is None:
            return
        k = self.kind
        if k == "klines":
            o, h, l, cl, q, n, tbq = r
            if c["first"][0] != c["first"][0]:
                c["first"][0] = o
            if h == h:
                c["max"][1] = max(c["max"][1], h)
            if l == l:
                c["min"][2] = min(c["min"][2], l)
            c["last"][3] = cl
            for j, v in ((4, q), (5, n), (6, tbq)):
                if v == v:
                    c["sum"][j] += v
        elif k in ("of", "tf"):
            for j, v in enumerate(r):
                if v != v:
                    continue
                if (k == "of" and j == 3) or (k == "tf" and j == 4):
                    c["max"][j] = max(c["max"][j], v)
                else:
                    c["sum"][j] += v
        elif k in ("mark", "index", "bv"):
            c["last"][0] = r[0]
        elif k == "premium":
            c["last"][0] = r[0]
            if r[1] == r[1]:
                c["max"][1] = max(c["max"][1], r[1])
            if r[2] == r[2]:
                c["min"][2] = min(c["min"][2], r[2])
        elif k == "metrics":
            for j, v in enumerate(r):
                c["last"][j] = v
        elif k == "funding":
            c["last"][0] = r[0]
            c["last"][1] = r[1]
        elif k == "bd":
            ts, pct, depth, notional = r
            band = abs(round(pct, 4))
            if band in (1.0, 2.0, 5.0):
                side = "b" if pct < 0 else "a"
                if ts >= c["snapTs"]:
                    if ts > c["snapTs"]:
                        c["snap"] = {}
                        c["snapTs"] = ts
                    c["snap"][side + str(int(band))] = notional

    def out(self):
        if not self.bins:
            return None
        ks = sorted(self.bins)
        bin0, bin_end = ks[0], ks[-1] + BIN_MS
        n = (bin_end - bin0) // BIN_MS
        data = [float("nan")] * (n * self.ncols)
        for b, c in self.bins.items():
            row = [float("nan")] * self.ncols
            k = (b - bin0) // BIN_MS
            if self.kind == "klines":
                row[0] = c["first"][0]
                row[1] = c["max"][1] if c["max"][1] != float("-inf") else float("nan")
                row[2] = c["min"][2] if c["min"][2] != float("inf") else float("nan")
                row[3] = c["last"][3]
                row[4], row[5], row[6] = c["sum"][4], c["sum"][5], c["sum"][6]
            elif self.kind in ("of", "tf"):
                for j in range(self.ncols):
                    row[j] = c["max"][j] if ((self.kind == "of" and j == 3) or (self.kind == "tf" and j == 4)) else c["sum"][j]
            elif self.kind == "premium":
                row[0] = c["last"][0]
                row[1] = c["max"][1] if c["max"][1] != float("-inf") else float("nan")
                row[2] = c["min"][2] if c["min"][2] != float("inf") else float("nan")
            elif self.kind == "bd":
                s = c["snap"]
                g = lambda kk: s.get(kk, float("nan"))
                row[0], row[1], row[2], row[3], row[4], row[5] = g("b1"), g("a1"), g("b2"), g("a2"), g("b5"), g("a5")
                for i, (bk, ak) in enumerate((("b1", "a1"), ("b2", "a2"), ("b5", "a5"))):
                    bv, av = g(bk), g(ak)
                    row[6 + i] = (bv - av) / (bv + av) if (bv == bv and av == av and bv + av != 0) else float("nan")
            else:
                for j in range(self.ncols):
                    row[j] = c["last"][j]
            data[k * self.ncols:(k + 1) * self.ncols] = row
        return {"bin0": bin0, "nrows": n, "ncols": self.ncols, "data": data}


def fetch(url, retries=3):
    for i in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return r.read()
        except Exception:
            if i == retries - 1:
                raise
    raise RuntimeError("unreachable")


def parse_zip(buf, kind, cells):
    z = zipfile.ZipFile(io.BytesIO(buf))
    name = z.namelist()[0]
    text = z.read(name).decode("utf-8", "replace")
    parse_csv(text, kind, cells)


def parse_csv(text, kind, cells):
    idx = None
    first = True
    for line in text.split("\n"):
        if not line:
            continue
        c = line.split(",")
        if first:
            first = False
            try:
                float(c[0])
            except Exception:
                idx = {h.strip(): i for i, h in enumerate(c)}
                continue
        if kind == "klines":
            t = to_ms(c[0])
            cells.add(t, (num(c[1]), num(c[2]), num(c[3]), num(c[4]), num(c[7]), num(c[8]), num(c[10])))
        elif kind in ("mark", "index", "premium"):
            t = to_ms(c[0])
            cells.add(t, (num(c[4]), num(c[2]), num(c[3])))
        elif kind == "metrics":
            g = lambda name_: num(c[idx[name_]]) if idx and name_ in idx else float("nan")
            t = int(datetime.strptime(c[idx["create_time"]].strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)
            ga = g("count_long_short_ratio")
            if ga != ga:
                ga = g("sum_global_long_short_ratio")
            cells.add(t, (g("sum_open_interest"), g("sum_open_interest_value"),
                          g("count_toptrader_long_short_ratio"), g("sum_toptrader_long_short_ratio"),
                          ga, g("count_global_long_short_ratio"), g("sum_taker_long_short_vol_ratio")))
        elif kind == "funding":
            t = to_ms(c[idx["calc_time"]])
            cells.add(t, (num(c[idx["last_funding_rate"]]), num(c[idx["funding_interval_hours"]])))
        elif kind == "bd":
            t = int(datetime.strptime(c[idx["timestamp"]].strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)
            cells.add(t, (t, num(c[idx["percentage"]]), num(c[idx["depth"]]), num(c[idx["notional"]])))
        elif kind == "bv":
            t = to_ms(c[0])
            cells.add(t, (num(c[idx["close"]]) if idx and "close" in idx else num(c[4]),))
        else:
            raise SystemExit("unknown kind " + kind)


def listing_names(dir_url):
    raw = fetch(dir_url).decode("utf-8", "replace")
    import re
    return sorted(set(re.findall(r'([A-Za-z0-9_.\-]+\.zip(?:\.CHECKSUM)?)', raw)))


def run_cell(cell, dirs, out_dir):
    kind = cell["table"]
    cells = Cells(kind)
    urls, checksum_ok, checksum_missing = [], 0, 0
    skipped_2026 = 0
    # 파일 목록은 칸이 거래소 공개 목록에서 만든다 (지시서 §2). -2026- URL은 만들지 않는다.
    dir_tpl = dirs.get(cell["market"] + "|" + cell["dataset"])
    if not dir_tpl:
        raise SystemExit("no dir template for " + cell["market"] + "|" + cell["dataset"])
    dir_url = BASE + dir_tpl.replace("{sym}", cell["sym"])
    names = listing_names(dir_url)
    skipped_2026 = sum(1 for n in names if "-2026-" in n)
    month = "-" + cell["month"]
    zips = [n for n in names if n.endswith(".zip") and month in n and "-2026-" not in n]
    if not zips:
        return {"cell": cell["id"], "empty": True, "urls": 0, "skipped_2026": skipped_2026}
    have_cs = set(names)

    def pull(name):
        buf = fetch(dir_url + name)
        cs_ok = None
        if name + ".CHECKSUM" in have_cs:
            cs = fetch(dir_url + name + ".CHECKSUM").decode().split()[0]
            cs_ok = hashlib.sha256(buf).hexdigest() == cs
        return buf, cs_ok

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(pull, zips))
    for name, (buf, cs_ok) in zip(zips, results):
        urls.append(dir_url + name)
        if cs_ok is False:
            raise SystemExit("CHECKSUM mismatch " + name)
        if cs_ok is True:
            checksum_ok += 1
        else:
            checksum_missing += 1
        parse_zip(buf, kind, cells)
    out = cells.out()
    if out is None:
        return {"cell": cell["id"], "empty": True, "urls": len(urls), "skipped_2026": skipped_2026}
    cell_id = cell["id"].replace("|", ".")
    arr = array.array("f", out["data"])
    if sys.byteorder != "little":
        arr.byteswap()
    f32 = arr.tobytes()
    with open(os.path.join(out_dir, cell_id + ".f32"), "wb") as f:
        f.write(f32)
    meta = {
        "cell_id": cell["id"], "market": cell["market"], "table": kind, "sym": cell["sym"], "month": cell["month"],
        "bin0_ms": out["bin0"], "nrows": out["nrows"], "ncols": out["ncols"], "cols": TABLES[kind],
        "sha256": hashlib.sha256(f32).hexdigest(), "bytes": len(f32),
        "urls": urls, "checksum_ok": checksum_ok, "checksum_missing": checksum_missing,
        "skipped_2026": skipped_2026,
    }
    with open(os.path.join(out_dir, cell_id + ".meta.json"), "w") as f:
        json.dump(meta, f)
    return meta


def main():
    plan_path, out_dir = sys.argv[1], sys.argv[2]
    shard = int(os.environ.get("JR_SHARD_INDEX", "0"))
    nshard = int(os.environ.get("JR_SHARD_COUNT", "1"))
    os.makedirs(out_dir, exist_ok=True)
    with open(plan_path) as f:
        plan = json.load(f)
    dirs = plan.get("dirs", {})
    mine = [c for i, c in enumerate(plan["cells"]) if i % nshard == shard]
    manifest = {"wave": plan.get("wave"), "shard": shard, "of": nshard, "cells": [], "failed": []}
    for cell in mine:
        try:
            manifest["cells"].append(run_cell(cell, dirs, out_dir))
        except Exception as e:
            manifest["failed"].append({"cell": cell["id"], "error": str(e)[:300]})
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f)
    print(json.dumps({"wave": plan.get("wave"), "shard": shard, "ok": len(manifest["cells"]), "failed": len(manifest["failed"])}))


if __name__ == "__main__":
    main()

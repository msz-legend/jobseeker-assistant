#!/usr/bin/env python3
"""Parse Chinese salary bands and compare them against the candidate's floor.

Why this parses instead of looking up
-------------------------------------
Chinese postings carry the salary *inside the JD text* in free-form conventions
rather than as a standardized index entry, so the computation is parsing, not
lookup:

    20-35K×15        2.5-4万×14        40,000/月        63w/年        8000-12000元/月

`/apply` Step 1 runs this tool with the raw string from the posting and the
candidate's floor read from 01-candidate-profile.md
([SALARY_FLOOR_MONTHLY]). The verdict is deterministic and testable - the agent
never "reasons" its way around your minimum.

Interpretation conventions (documented, not magic):
* explicit period wins:      月薪/万/月/K/元 → monthly;  年薪/w/年/总包 → annual
* multiplier (×15 / ·15薪 / 15薪) present → values are monthly salaries, paid over N months
* bare K (20K) → monthly
* bare 万 with max < 10  → monthly ("2.5-4万" convention)
* bare 万 with max >= 10 → annual  ("20-40万" convention) unless a multiplier says monthly
* bare >= 4-digit number ("8000-12000") → monthly CNY
* anything else → "ambiguous": true and verdict "needs_review" (never silently guessed)

Usage:
  python tools/salary_band.py "2.5-4万×14" --floor "42000/月"
  python tools/salary_band.py "20-35K·15"  --floor-annual 630000
  echo "薪资：2.5-4万×14，14薪" | python tools/salary_band.py --stdin

Output: JSON verdict on stdout. Exit codes: 0 parsed (any verdict), 1 usage error,
2 completely unparseable.
"""

import argparse
import json
import re
import sys


def _force_utf8_stdout() -> None:
    """Windows consoles default to a legacy codepage (GBK); JSON with Chinese
    must leave the process as UTF-8 whether piped or redirected."""
    try:
        if not sys.stdout.encoding or sys.stdout.encoding.lower().replace("-", "") != "utf8":
            sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass


SPACE_RE = re.compile(r"[\s\u3000]+")

NUM = r"(\d[\d,，]*(?:\.\d+)?)"
SEP = r"-|–|~|至|到"
UNIT = r"万|[wW]|[kK千]"

PERIOD_MONTHLY = re.compile(r"月薪|/月|·月|每月")
PERIOD_ANNUAL = re.compile(r"年薪|/年|·年|每年|年包|总包|总薪|按年")

RANGE_RE = re.compile(NUM + r"(?:" + UNIT + r")?" + r"(?:" + SEP + r")" + NUM + r"(?:" + UNIT + r")?")
SINGLE_RE = re.compile(NUM + r"(?:" + UNIT + r")?")

SALARY_CONTEXT = re.compile(r"薪资|薪水|月薪|年薪|元|package|pay", re.IGNORECASE)


def _norm(raw: str) -> str:
    text = SPACE_RE.sub("", raw or "")
    text = text.replace("－", "-").replace("—", "-").replace("～", "~").replace("～", "~")
    text = text.replace("・", "·")
    return text


def _money(value: str) -> float:
    return float(value.replace("，", "").replace(",", ""))


def _unit_after(text: str, start: int, end: int) -> str:
    """Unit char for the numbers in [start:end): prefer the char right after the span,
    else a unit char inside the span (e.g. the trailing 万 in "2.5-4万")."""
    ch = ""
    if end < len(text) and text[end] in "万wWkK千":
        ch = text[end]
    else:
        seg = re.sub(r"[\d,.，\-–~至到]", "", text[start:end])
        stripped = seg.strip()
        if stripped and stripped[-1] in "万wWkK千":
            ch = stripped[-1]
    if ch in ("w", "W", "万"):
        return "wan"
    if ch.lower() == "k" or ch == "千":
        return "k"
    return "none"


def _parse_multiplier(text: str):
    """Months like ×15 / ·15薪 / 15薪 / (15薪). None when absent."""
    m = re.search(r"[×xX*·]\s*(\d{1,2})(?:\s*薪)?(?![万kK千\d])", text)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d{1,2})\s*薪", text)
    if m:
        return int(m.group(1))
    return None


def _first_money(text: str):
    """Return (low, high, unit) picking the most salary-looking number span."""
    matches = list(RANGE_RE.finditer(text))
    singles = list(SINGLE_RE.finditer(text))
    candidates = matches or singles
    if not candidates:
        return None
    best, best_score = None, -1.0
    for m in candidates:
        low = _money(m.group(1))
        high = _money(m.group(2) if m.lastindex and m.lastindex >= 2 and m.group(2) else m.group(1))
        unit = _unit_after(text, m.start(), m.end())
        score = 0.0
        # 单位出现的候选优先
        if unit != "none":
            score += 2.0
        # 后文紧跟 薪/月/年/元 的优先
        tail = text[m.end():m.end() + 4]
        head = text[max(0, m.start() - 4):m.start()]
        if re.search(r"薪|月|年|元|K|万", tail + head):
            score += 2.0
        if SALARY_CONTEXT.search(text):
            score += 0.5
        # 薪资区间常见幅宽（同一数量级），跨两个数量级的候选（如电话号段）降权
        if high > 0 and 0.05 <= low / high <= 1.0:
            score += 1.0
        if score > best_score:
            best, best_score = m, score
    m = best
    low = _money(m.group(1))
    if m.lastindex and m.lastindex >= 2 and m.group(2):
        high = _money(m.group(2))
    else:
        high = low
    return low, high, _unit_after(text, m.start(), m.end())


def parse_band(raw: str) -> dict:
    """Turn a raw salary string into normalized monthly/annual numbers."""
    text = _norm(raw or "")
    first = _first_money(text)
    if first is None:
        return {
            "raw": raw,
            "parsed": False,
            "ambiguous": True,
            "reasons": ["没有解析出任何薪资数字"],
        }
    low, high, unit = first

    reasons: list[str] = []
    ambiguous = False
    period = None

    if PERIOD_ANNUAL.search(text):
        period = "annual"
        reasons.append("出现年薪/总包表述 → annual")
    elif PERIOD_MONTHLY.search(text):
        period = "monthly"
        reasons.append("出现月薪表述 → monthly")

    mult = _parse_multiplier(text)
    if mult is not None:
        period = "monthly"
        reasons.append(f"含 {mult} 薪表述 → 按 {mult} 个月计")

    monthly_scale = 1.0
    if unit == "k":
        monthly_scale = 1000.0
        if period is None:
            period = "monthly"
            reasons.append("K 计量 → 月薪（K 通常指月薪）")
    elif unit == "wan":
        monthly_scale = 10000.0
        if period is None:
            if high < 10:
                period = "monthly"
                reasons.append("万单位且值 < 10 → 月薪（2.5-4万 惯例）")
            elif high < 100:
                period = "annual"
                reasons.append("万单位且 10 <= 值 < 100 → 年薪（20-40万 惯例）")
            else:
                ambiguous = True
                period = "annual"
                reasons.append("万单位数值 >= 100 → 大概率年薪，请人工复核")
        elif period == "annual" and mult is not None and high < 100:
            period = "monthly"
            reasons.append("总包字样但有薪数，推翻为月薪×N 口径，请复核")
            ambiguous = True
    else:
        if period is None:
            if high >= 1000:
                period = "monthly"
                reasons.append("4 位以上纯数字 → 元/月薪")
            else:
                period = "monthly"
                ambiguous = True
                reasons.append("无单位小数字，默认按千/元月薪处理，请人工确认")
        if high >= 100000:
            ambiguous = True
            reasons.append("纯数字 >= 10 万：口头口径争议大（月薪 vs 年薪），请人工确认")

    if period is None:
        period = "monthly"
        ambiguous = True
        reasons.append("识别不到周期，默认月薪")

    low_m = low * monthly_scale
    high_m = high * monthly_scale
    months = mult if mult is not None else 12
    if period == "monthly":
        min_monthly, max_monthly = low_m, high_m
        min_annual, max_annual = low_m * months, high_m * months
    else:
        min_annual, max_annual = low_m, high_m
        min_monthly, max_monthly = low_m / 12.0, high_m / 12.0
        months = 12

    if period == "monthly" and max_monthly > 80000 and not ambiguous:
        ambiguous = True
        reasons.append("月薪上限 > 8 万，异常高额，请人工确认口径")

    return {
        "raw": raw,
        "parsed": not ambiguous,
        "period": period,
        "unit": {"wan": "万", "k": "K", "none": "元"}.get(unit, unit),
        "months": months,
        "min_monthly": round(min_monthly),
        "max_monthly": round(max_monthly),
        "min_annual": round(min_annual),
        "max_annual": round(max_annual),
        "ambiguous": ambiguous,
        "reasons": reasons,
    }


def parse_floor(text: str) -> dict:
    """Parse a floor spec like "42000/月", "42K", "4.2万", "63w/年", "630000"."""
    band = parse_band(text)
    if band.get("ambiguous") and band.get("min_monthly") is None:
        raise ValueError(f"无法解析底线: {text!r}（{band.get('reasons')}）")
    return band


def verdict(band: dict, floor: dict) -> dict:
    """Compare band max-monthly against the candidate's floor monthly."""
    floor_monthly = floor["min_monthly"]
    out = dict(band)
    if band["ambiguous"]:
        out["verdict"] = "needs_review"
        out["floor_monthly"] = round(floor_monthly)
        out["note"] = "band 口径不明确，人工确认后再判定"
        return out
    max_monthly = band["max_monthly"]
    gap_pct = round((floor_monthly - max_monthly) / floor_monthly * 100, 1) if floor_monthly else 0.0
    headroom_pct = (
        round((max_monthly - floor_monthly) / floor_monthly * 100, 1) if floor_monthly else None
    )
    out["verdict"] = "pass" if max_monthly >= floor_monthly else "fail"
    out["floor_monthly"] = round(floor_monthly)
    out["gap_pct"] = gap_pct if gap_pct > 0 else 0.0
    out["headroom_pct"] = headroom_pct if (headroom_pct or 0) > 0 else 0.0
    return out


def main() -> int:
    _force_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("raw", nargs="?", help='薪资原文，如 "20-35K×15"')
    ap.add_argument("--floor", help='候选人底线月薪，如 "42000/月" 或 "42K"')
    ap.add_argument("--floor-annual", type=float, dest="floor_annual", help="候选人底线年薪（元）")
    ap.add_argument("--months", type=int, help="覆盖薪数（例如 15），否则按 ×N/N薪 解析，默认 12")
    ap.add_argument("--stdin", action="store_true", help="从 stdin 读取文本并尝试提取薪资段")
    args = ap.parse_args()

    if args.stdin and not args.raw:
        args.raw = sys.stdin.read()

    if not args.raw or not args.raw.strip():
        ap.print_help()
        return 1

    band = parse_band(args.raw)
    if args.months and band.get("period") == "monthly":
        band["months"] = args.months
        band["min_annual"] = round(band["min_monthly"] * args.months)
        band["max_annual"] = round(band["max_monthly"] * args.months)

    if not band.get("parsed") and band.get("ambiguous") and band.get("min_monthly") is None:
        print(json.dumps(band, ensure_ascii=False, indent=2))
        return 2

    if args.floor:
        try:
            floor = parse_floor(args.floor)
        except ValueError as exc:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
            return 1
        result = verdict(band, floor)
    elif args.floor_annual:
        result = verdict(band, {"min_monthly": args.floor_annual / 12.0})
    else:
        result = band

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

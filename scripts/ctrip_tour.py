#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
携程「拼小团跟团」产品检索工具
数据范围：目的地 日本 / 韩国 / 新加坡 / 马来西亚 / 澳大利亚 / 新西兰

子命令：
  search   <自然语言查询>   例：search "澳大利亚5天"、search "日本 6天 拼小团 不含机票"
  list     --dest --days     结构化检索
  index                      生成并打印「按行程天数」分类索引 data/index.json
  stats                      数据集概览（合格/自营核验/排除/缺失）
  validate                   校验数据集字段与逻辑自洽

口径：
  · 出发地参团 = 含机票；当地参团 = 不含机票
  · 默认只返回 brand_status=verified_self_operated（自营已核验）；
    加 --include-unverified 可把「列表页未披露供应商」的产品一并列出（标注未核验）
仅依赖 Python 标准库。
"""

import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data", "products.json")
INDEX = os.path.join(BASE, "data", "index.json")

# ---------------------------------------------------------------- 目的地词表
DEST_ALIASES = {
    "日本": ["日本", "日韩", "东京", "大阪", "京都", "奈良", "富士山", "北海道", "冲绳",
             "福冈", "熊本", "由布院", "九州", "名古屋", "箱根", "伊豆", "关西", "关东",
             "札幌", "小樽", "登别", "洞爷湖", "旭川", "函馆", "名古屋"],
    "韩国": ["韩国", "南韩", "首尔", "济州", "济州岛", "牛岛", "釜山", "仁川", "明洞", "江原道"],
    "新加坡": ["新加坡", "狮城", "圣淘沙", "星洲"],
    "马来西亚": ["马来西亚", "马来", "大马", "吉隆坡", "马六甲", "沙巴", "亚庇", "波德申",
                 "布城", "槟城", "兰卡威", "仙本那"],
    "澳大利亚": ["澳大利亚", "澳洲", "悉尼", "墨尔本", "黄金海岸", "凯恩斯", "布里斯班",
                 "阿德莱德", "珀斯", "塔斯马尼亚", "霍巴特", "乌鲁鲁", "大堡礁", "蓝山"],
    "新西兰": ["新西兰", "纽西兰", "奥克兰", "皇后镇", "基督城", "库克山", "特卡波",
               "瓦纳卡", "米福峡湾", "北岛", "南岛", "霍比特", "罗托鲁瓦", "但尼丁"],
}
MULTI_DEST = {"日韩": ["日本", "韩国"], "澳新": ["澳大利亚", "新西兰"],
              "新马": ["新加坡", "马来西亚"], "澳新连线": ["澳大利亚", "新西兰"]}

CN_NUM = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7,
          "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12, "十三": 13, "十四": 14,
          "十五": 15, "十六": 16, "十七": 17}

TYPE_WORDS = {"拼小团": "拼小团", "小团": "拼小团", "跟团游": "跟团游", "跟团": "跟团游",
              "私家团": "__私家团"}

EXCLUDE_LABEL = {
    "PRIVATE_TOUR": "私家团（不在范围）",
    "FREE_TRAVEL": "自由行（不在范围）",
    "DAY_TOUR": "一日游/半日游（不在范围）",
    "NOT_GROUP_TOUR": "非跟团类（研学/邮轮等）",
    "TYPE_UNKNOWN": "类型无法判定",
    "MISSING_DAYS": "缺少行程天数",
}

FIELD_LABEL = {"price_from": "起价", "diamond_level": "钻级", "departure_city": "出发地",
               "brand_status": "自营凭据", "includes_flight": "机票口径"}

BRAND_LABEL = {
    "verified_self_operated": "✓自营",
    "unverified_no_brand_field": "未核验",
}


# ---------------------------------------------------------------- 基础工具
def load():
    with open(DATA, encoding="utf-8") as f:
        return json.load(f)


def disp_w(s):
    w = 0
    for ch in str(s):
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def pad(s, width):
    s = "" if s is None else str(s)
    return s + " " * max(0, width - disp_w(s))


def table(headers, rows):
    widths = [disp_w(h) for h in headers]
    for r in rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], disp_w(c if c is not None else ""))
    line = "  ".join(pad(h, widths[i]) for i, h in enumerate(headers))
    out = [line, "-" * disp_w(line)]
    for r in rows:
        out.append("  ".join(pad(c if c is not None else "-", widths[i]) for i, c in enumerate(r)))
    return "\n".join(out)


def fmt_diamond(p):
    lvl = p.get("diamond_level")
    return f"{lvl}钻" if lvl else "未披露"


def fmt_flight(p):
    if p.get("includes_flight") is True:
        return "含机票"
    if p.get("includes_flight") is False:
        return "不含机票"
    return "不唯一"


def fmt_mode(p):
    m = p.get("departure_mode")
    if m:
        return m
    return "两处均在售"


def fmt_brand(p):
    return BRAND_LABEL.get(p.get("brand_status"), "-")


# ---------------------------------------------------------------- 查询解析
def parse_query(q):
    q = q.strip()
    low = q.lower()
    dests = []
    for k, names in MULTI_DEST.items():
        if k in q:
            for d in names:
                if d not in dests:
                    dests.append(d)
    for country, aliases in DEST_ALIASES.items():
        if any(a in q for a in aliases) and country not in dests:
            dests.append(country)

    days = None
    m = re.search(r"(\d{1,2})\s*(?:天|日)", q)
    if m:
        days = int(m.group(1))
    else:
        m = re.search(r"([一二两三四五六七八九十]{1,3})\s*(?:天|日)", q)
        if m and m.group(1) in CN_NUM:
            days = CN_NUM[m.group(1)]

    ptype = None
    for w, t in TYPE_WORDS.items():
        if w in q:
            ptype = t
            break

    flight = None
    if re.search(r"不含机票|不含往返|当地参团|目的地参团", q):
        flight = "不含"
    elif re.search(r"含机票|含往返|出发地参团", q):
        flight = "含"

    return {"raw": q, "dests": dests, "days": days, "type": ptype, "flight": flight}


def match_dest(p, dests):
    return not dests or p.get("destination_group") in dests


def filter_base(p, parsed):
    """目的地/天数/类型/机票 四类硬条件"""
    if not match_dest(p, parsed["dests"]):
        return False
    if parsed["days"] is not None and p.get("days") != parsed["days"]:
        return False
    if parsed["type"] and p.get("product_type") != parsed["type"]:
        return False
    if parsed["flight"] == "含" and p.get("includes_flight") is not True:
        return False
    if parsed["flight"] == "不含" and p.get("includes_flight") is not False:
        return False
    return True


def search(products, parsed, include_unverified=False):
    verified, unverified, excluded = [], [], []
    for p in products:
        if not filter_base(p, parsed):
            continue
        if p.get("status") != "qualified":
            excluded.append(p)
        elif p.get("is_self_operated"):
            verified.append(p)
        else:
            unverified.append(p)
    key = lambda p: (p.get("days") or 99, p["product_id"])
    for lst in (verified, unverified, excluded):
        lst.sort(key=key)
    if include_unverified:
        return verified + unverified, excluded, unverified
    return verified, excluded, unverified


def near_days(products, dests, days, span=2, self_only=True):
    cands = [p for p in products
             if p.get("status") == "qualified"
             and (p.get("is_self_operated") or not self_only)
             and match_dest(p, dests)
             and p.get("days") and p["days"] != days and abs(p["days"] - days) <= span]
    cands.sort(key=lambda p: (abs(p["days"] - days), p["product_id"]))
    return cands


# ---------------------------------------------------------------- 输出
def render(parsed, hits, excluded, unverified, products, include_unverified, strict=False):
    lines = []
    dl = "、".join(parsed["dests"]) if parsed["dests"] else "全部在范围目的地"
    dd = f"{parsed['days']}天" if parsed["days"] is not None else "全部天数"
    extra = []
    if parsed["type"]:
        extra.append(f"类型={parsed['type']}")
    if parsed["flight"]:
        extra.append(f"机票={parsed['flight']}")
    head = f"查询：{parsed['raw']}  →  目的地={dl}  天数={dd}"
    if extra:
        head += "  " + "  ".join(extra)
    lines.append(head)
    lines.append("")

    if hits:
        rows = [[p["product_id"], p["destination_group"], f"{p['days']}天", fmt_diamond(p),
                 p.get("product_type") or "-", fmt_mode(p), p.get("departure_city") or "-",
                 fmt_brand(p)] for p in hits]
        title = f"✅ 命中 {len(hits)} 条"
        title += "（自营已核验 · 拼小团/跟团游）" if not include_unverified else "（含未核验品牌）"
        lines.append(title)
        lines.append(table(["产品编号", "目的地", "天数", "钻级", "类型", "参团方式", "出发地", "自营"],
                           rows))
    else:
        lines.append("⚠️ 无精确匹配")

    # 天数分类视图
    if hits and parsed["days"] is None:
        c = Counter(p["days"] for p in hits)
        lines.append("")
        lines.append("天数分布：" + "  ".join(f"{k}天={v}" for k, v in sorted(c.items())))

    # 兜底：自营命中过少时，把「品牌未核验」的候选单独列出（明确标注，不与自营混淆）
    if unverified and not include_unverified:
        if len(hits) < 3 and not strict:
            lines.append("")
            lines.append(f"⚠️ 自营命中仅 {len(hits)} 条，以下 {min(len(unverified), 12)} 条为同条件"
                         f"「品牌未核验」候选（共 {len(unverified)} 条）")
            lines.append("   这些产品在携程列表页未披露供应商，尚不能确认为自营，仅供人工核验参考：")
            rows = [[p["product_id"], p["destination_group"], f"{p['days']}天", fmt_diamond(p),
                     p.get("product_type") or "-", fmt_mode(p), p.get("departure_city") or "-"]
                    for p in unverified[:12]]
            lines.append(table(["产品编号", "目的地", "天数", "钻级", "类型", "参团方式", "出发地"], rows))
            if len(unverified) > 12:
                lines.append(f"   … 另有 {len(unverified) - 12} 条，加 --include-unverified 查看全部")
        else:
            lines.append("")
            lines.append(f"⚠️ 另有 {len(unverified)} 条同条件产品因列表页未披露供应商、无自营凭据，未纳入结果")
            lines.append("   （加 --include-unverified 查看；--strict 可完全关闭兜底展示）")

    if excluded:
        lines.append("")
        lines.append(f"⛔ 排除 {len(excluded)} 条（同目的地/天数，但不符合筛选条件）")
        rows = [[p["product_id"], p.get("product_type") or "-", f"{p.get('days')}天",
                 EXCLUDE_LABEL.get(p.get("exclusion_code"), p.get("exclusion_code") or "-"),
                 (p.get("title") or "")[:34]]
                for p in excluded[:15]]
        lines.append(table(["产品编号", "类型", "天数", "排除原因", "标题"], rows))
        if len(excluded) > 15:
            lines.append(f"… 其余 {len(excluded) - 15} 条同因排除，略")

    if not hits and parsed["days"] and parsed["dests"]:
        near = near_days(products, parsed["dests"], parsed["days"],
                         self_only=not include_unverified)
        if near:
            lines.append("")
            lines.append("↔️ 同目的地邻近天数（可替代方案，自营已核验）")
            rows = [[p["product_id"], p["destination_group"], f"{p['days']}天", fmt_diamond(p),
                     p.get("product_type") or "-", fmt_flight(p), p.get("departure_city") or "-"]
                    for p in near[:10]]
            lines.append(table(["产品编号", "目的地", "天数", "钻级", "类型", "机票", "出发地"], rows))

    return "\n".join(lines)


# ---------------------------------------------------------------- 子命令
def cmd_search(argv):
    if not argv:
        print('用法：search "澳大利亚5天" [--json] [--no-excluded] [--include-unverified]')
        return 2
    as_json = "--json" in argv
    show_excluded = "--no-excluded" not in argv
    include_unverified = "--include-unverified" in argv
    strict = "--strict" in argv
    query = " ".join(a for a in argv if not a.startswith("--"))
    parsed = parse_query(query)
    products = load()["products"]
    hits, excluded, unverified = search(products, parsed, include_unverified)
    if as_json:
        print(json.dumps({"query": parsed, "count": len(hits), "results": hits,
                          "excluded": excluded if show_excluded else [],
                          "unverified_not_included": [] if include_unverified else unverified},
                         ensure_ascii=False, indent=2))
    else:
        print(render(parsed, hits, excluded if show_excluded else [], unverified,
                     products, include_unverified, strict))
    return 0


def cmd_list(argv):
    opts = {}
    i = 0
    while i < len(argv):
        if argv[i].startswith("--") and i + 1 < len(argv):
            opts[argv[i][2:]] = argv[i + 1]
            i += 2
        else:
            i += 1
    q = []
    if opts.get("dest"):
        q.append(str(opts["dest"]))
    if opts.get("days"):
        q.append(f"{opts['days']}天")
    if opts.get("type"):
        q.append(str(opts["type"]))
    if opts.get("flight"):
        v = str(opts["flight"]).lower()
        q.append("含机票" if v in ("含", "true", "yes", "1") else "不含机票")
    return cmd_search(q)


def cmd_index(argv):
    products = load()["products"]
    qual = [p for p in products if p.get("status") == "qualified"]
    ver = [p for p in qual if p.get("is_self_operated")]

    def build(items):
        by_day = defaultdict(lambda: defaultdict(list))
        for p in items:
            by_day[p["days"]][p["destination_group"]].append(p)
        out = {}
        for d in sorted(by_day):
            out[str(d)] = {
                "days": d,
                "total": sum(len(v) for v in by_day[d].values()),
                "destinations": {dest: sorted(x["product_id"] for x in lst)
                                 for dest, lst in sorted(by_day[d].items())},
            }
        return out

    all_days = sorted({p["days"] for p in qual})
    index = {
        "generated_from": "data/products.json",
        "scope": "携程自营 · 拼小团/跟团游 · 日韩新马澳新",
        "captured_at": load()["meta"].get("captured_at"),
        "note": "self_operated 为自营已核验口径；all_qualified 含品牌未核验产品",
        "day_buckets_self_operated": build(ver),
        "day_buckets_all_qualified": build(qual),
    }
    with open(INDEX, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    dests = sorted({p["destination_group"] for p in qual})
    b_ver = index["day_buckets_self_operated"]
    b_all = index["day_buckets_all_qualified"]
    rows = []
    for d in all_days:
        row = [f"{d}天", str(b_ver.get(str(d), {}).get("total", 0)),
               str(b_all.get(str(d), {}).get("total", 0))]
        for dest in dests:
            row.append(str(len(b_ver.get(str(d), {}).get("destinations", {}).get(dest, []))))
        rows.append(row)
    print("按行程天数分类索引（自营已核验 / 全部合格）")
    print(table(["天数", "自营", "合格"] + dests, rows))
    t_ver = sum(v["total"] for v in b_ver.values())
    t_all = sum(v["total"] for v in b_all.values())
    print(f"\n合计：自营已核验 {t_ver} 条 / 合格 {t_all} 条；天数段 {len(all_days)} 个"
          f"（{all_days[0]}–{all_days[-1]} 天）")
    print(f"索引已写入 {INDEX}")
    return 0


def cmd_stats(argv):
    data = load()
    products = data["products"]
    qual = [p for p in products if p.get("status") == "qualified"]
    ver = [p for p in qual if p.get("is_self_operated")]
    exc = [p for p in products if p.get("status") == "excluded"]
    m = data["meta"]
    print(f"快照 {m.get('captured_at')}  |  总记录 {len(products)}  |  合格 {len(qual)}"
          f"  |  自营已核验 {len(ver)}  |  排除 {len(exc)}")
    print()
    print("按目的地（合格 / 自营已核验 / 核验率）")
    rows = []
    for dest in sorted({p["destination_group"] for p in qual}):
        a = sum(1 for p in qual if p["destination_group"] == dest)
        b = sum(1 for p in ver if p["destination_group"] == dest)
        rows.append([dest, str(a), str(b), f"{b / a * 100:.0f}%"])
    print(table(["目的地", "合格", "自营", "核验率"], rows))
    print()
    print("按类型 / 参团方式")
    c = Counter((p.get("product_type"), fmt_mode(p)) for p in ver)
    print(table(["类型", "参团方式", "数量"], [[k[0], k[1], str(v)] for k, v in sorted(c.items())]))
    print()
    print("按天数（自营已核验）")
    c2 = Counter(p["days"] for p in ver)
    print(table(["天数", "数量"], [[f"{k}天", str(v)] for k, v in sorted(c2.items())]))
    print()
    print("排除原因分布")
    c3 = Counter(EXCLUDE_LABEL.get(p.get("exclusion_code"), p.get("exclusion_code")) for p in exc)
    print(table(["排除原因", "数量"], [[k, str(v)] for k, v in c3.most_common()]))
    print()
    miss = Counter(f for p in qual for f in p.get("missing_fields", []))
    if miss:
        print("合格产品字段缺失（已标注，不静默丢弃）")
        print(table(["字段", "缺失条数"], [[FIELD_LABEL.get(k, k), str(v)] for k, v in miss.most_common()]))
    return 0


def cmd_validate(argv):
    data = load()
    products = data["products"]
    need = ["product_id", "title", "product_type", "destination_group", "days", "status",
            "exclusion_code", "brand_status", "is_self_operated", "source_url"]
    errs, ids = [], set()
    for i, p in enumerate(products):
        for f in need:
            if f not in p:
                errs.append(f"[{i}] {p.get('product_id','?')} 缺字段 {f}")
        pid = p.get("product_id")
        if pid in ids:
            errs.append(f"编号重复：{pid}")
        ids.add(pid)
        if p.get("status") == "qualified":
            if p.get("exclusion_code"):
                errs.append(f"{pid} 合格却带排除码")
            if p.get("product_type") not in ("拼小团", "跟团游"):
                errs.append(f"{pid} 类型非法：{p.get('product_type')}")
            if p.get("destination_group") not in DEST_ALIASES:
                errs.append(f"{pid} 目的地越界：{p.get('destination_group')}")
            if not isinstance(p.get("days"), int):
                errs.append(f"{pid} 天数字段非法")
            if p.get("brand_status") == "verified_self_operated" and p.get("is_self_operated") is not True:
                errs.append(f"{pid} brand_status 与 is_self_operated 矛盾")
            if p.get("includes_flight") is not None and p.get("departure_mode") is None:
                errs.append(f"{pid} 有机票结论但无参团方式")
            if not p.get("brand_evidence"):
                errs.append(f"{pid} 缺少自营凭据说明")
        else:
            if not p.get("exclusion_code"):
                errs.append(f"{pid} 被排除但未写排除码")
    if errs:
        print(f"❌ 校验失败，{len(errs)} 个问题：")
        for e in errs[:40]:
            print("  -", e)
        return 1
    print(f"✅ 校验通过：{len(products)} 条记录，字段完整、编号唯一、筛选逻辑自洽")
    return 0


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd, argv = sys.argv[1], sys.argv[2:]
    return {
        "search": cmd_search,
        "list": cmd_list,
        "index": cmd_index,
        "stats": cmd_stats,
        "validate": cmd_validate,
    }.get(cmd, lambda a: (print(f"未知子命令 {cmd}"), 2)[1])(argv)


if __name__ == "__main__":
    sys.exit(main())

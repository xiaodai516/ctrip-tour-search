# 字段字典（data/products.json）

一条记录 = 一个携程产品。`status` 决定它是否算「结果」；被排除的记录同样保留，用于解释「为什么没有它」。

| 字段 | 类型 | 说明 |
|---|---|---|
| `product_id` | string | 携程产品编号（详情页 URL 的 `p{数字}`）。**主键** |
| `title` | string | 标题原文：主标题 + `·` + 副标题，含「X日Y晚」与「拼小团/跟团游」字样 |
| `product_type` | enum | `拼小团` / `跟团游`；排除记录为 `null` |
| `destination_group` | enum | 归一化国家：日本/韩国/新加坡/马来西亚/澳大利亚/新西兰 |
| `destinations` | string[] | 行程涉及的城市/区域（取自 `ROUTE_LEVEL1_NAME`），如 `["悉尼","墨尔本","凯恩斯"]` |
| `days` | int | **行程天数**，取 `minDays`。索引按此字段分桶 |
| `nights` | int\|null | 住宿晚数，取 `extras.NIGHTS`；可与天数不等（夜宿飞机） |
| `days_raw` | string\|null | 拼接值，如 `6日5晚` |
| `departure_city` | string\|null | 出发地，多城市用「、」连接，如 `上海、北京、青岛` |
| `departure_mode` | enum\|null | `出发地参团` / `当地参团`；两类列表都在售时为 `null` |
| `includes_flight` | bool\|null | 含机票。`出发地参团=true`、`当地参团=false`、两处均在售 `null` |
| `flight_basis` | string | 判定依据说明（列表归属规则或「不唯一」原因） |
| `diamond_level` | int\|null | 产品钻级 1–5；未披露为 `null` |
| `diamond_basis` | string | 固定 `product_level`（取 `basicInfo.level`） |
| `price_from` | null | 本轮统一 `null`：列表页 SSR 不返回价格 |
| `price_currency` | string | 固定 `CNY` |
| `brand_status` | enum | `verified_self_operated` / `unverified_no_brand_field` |
| `brand_evidence` | string | 自营凭据原文说明，无凭据时写清「列表页未披露供应商字段」 |
| `is_self_operated` | bool | 仅当 `brand_status=verified_self_operated` 时为 `true` |
| `source_url` | string | 产品详情页 URL |
| `status` | enum | `qualified` / `excluded` |
| `exclusion_code` | string\|null | 排除码，见 rules.md |
| `confidence` | enum | `high`（合格且自营已核验）/ `medium`（合格但品牌未核验） |
| `missing_fields` | string[] | 合格产品缺失字段名，输出时显示为「缺：起价」 |

## 索引结构（data/index.json）

```json
{
  "day_buckets_self_operated": {
    "5": {
      "days": 5,
      "total": 91,
      "destinations": {"韩国": ["38409920", "61034684"], "日本": ["35859450"]}
    }
  },
  "day_buckets_all_qualified": { "5": { "days": 5, "total": 319, "destinations": {"...": []} } }
}
```

两套桶并存：

- `day_buckets_self_operated`：自营已核验口径，`search` 默认返回它的成员
- `day_buckets_all_qualified`：全部合格口令（含品牌未核验），用于「总量/缺口」对比

`total` 为该天数下的产品数，支撑「N天有哪些产品」这类聚合问答。

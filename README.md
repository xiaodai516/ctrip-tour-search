# ctrip-tour-search

携程旅行「拼小团 / 跟团游」产品检索工具。按 **目的地 + 行程天数** 组合查询，输出产品编号、目的地、钻级标准、天数分类，并区分拼小团/跟团游、含机票/不含机票、自营是否已核验。

## 数据范围

| 维度 | 取值 |
|---|---|
| 平台 | 携程旅行 `vacations.ctrip.com` |
| 模块 | 旅行板块 > 拼小团跟团 |
| 目的地 | 日本 / 韩国 / 新加坡 / 马来西亚 / 澳大利亚 / 新西兰 |
| 类型 | 拼小团、跟团游（私家团/自由行/一日游/研学/邮轮已排除） |
| 供应商 | 携程自营（分「已核验 / 未核验」两层） |
| 天数 | 2–17 天，16 个天数段全部有数据 |
| 规模 | 2985 条记录：1630 合格 / 1355 排除；其中 430 条自营已核验 |

快照时间：2026-11-22。

## 依赖

Python 3.8+，**仅标准库**，无需安装任何包。

## 用法

```bash
# 自然语言组合查询
python scripts/ctrip_tour.py search "澳大利亚5天"
python scripts/ctrip_tour.py search "日本6天 拼小团 含机票"
python scripts/ctrip_tour.py search "新西兰12天 不含机票"

# 结构化查询
python scripts/ctrip_tour.py list --dest 韩国 --days 4 --type 跟团游

# 天数 × 目的地 索引矩阵
python scripts/ctrip_tour.py index

# 数据集概览 / 校验
python scripts/ctrip_tour.py stats
python scripts/ctrip_tour.py validate
```

参数：`--json` 机器可读、`--include-unverified` 列出未核验、`--strict` 只给自营已核验、`--no-excluded` 隐藏排除列表。

输出示例：

```
$ python scripts/ctrip_tour.py search "澳大利亚5天"
✅ 命中 1 条
产品编号    目的地    天数  钻级      类型    参团方式  出发地  自营
78234405   澳大利亚  5天   未披露    跟团游  当地参团  悉尼    ✓自营

⛔ 被排除 3 条
78069338  拼小团  纵览山河旅行  非携程自营
72579544  拼小团  寰宇纵横      非携程自营
79270524  拼小团  未披露        供应商未披露
```

## 判定口径

1. **钻级** = 产品钻级（列表页 `level`，1–5 钻），非酒店钻级；缺失写 `未披露`，不猜。
2. **含机票**按参团方式判定：`出发地参团 = 含机票`，`当地参团 = 不含机票`。同一编号出现在两类列表时记 `不唯一`。
3. **自营分层**：`✓自营` = 有凭据（详情页供应商=携程自营，或标题自带「携程自营/携程国旅/自营」）；`未核验` = 列表页未披露供应商，不可直接对外称自营。
4. **价格不提供**：列表页 SSR 不返回价格字段，一律 `null`，不编造报价。

详见 `references/rules.md`（全部判定规则与排除码）与 `references/schema.md`（字段字典）。

## 数据刷新

列表页 SSR 可直读，页面内嵌 `"products":[...]` JSON：

```
https://vacations.ctrip.com/list/{around|whole}/d-{slug}-{id}.html?p={page}&startcity={cityid}
```

- `around` = 目的地参团 → 不含机票；`whole` = 出发地参团 → 含机票
- 目的地 ID：日本 100041、韩国 100042、新加坡 21396、马来西亚 100022、澳大利亚 100048、新西兰 100078
- `startcity` 会换一批结果，多城市枚举可显著扩量
- 该页 SSR **不响应任何品牌/钻级筛选参数**（`filter=cb|zscb1|cb1`、`?cb=`、`?zscb=`、`?brand=`、`?filterJson=` 均实测与原结果逐条相同），品牌必须另证
- 详情页 `/travel/detail/p{id}` 为 JS 渲染，无登录态拿不到供应商

## 已知限制

- 快照非实时：班期、在售状态以携程页面为准。
- 自营核验率不均：新加坡 62% / 韩国 59% / 马来西亚 46% / 新西兰 35% / 澳大利亚 18% / **日本 1%**。日本线路标题普遍不带自营字样，工具会自动补出未核验候选并逐条标注。
- 覆盖 6 国主流线路，不等于携程全量在售产品；`stats` 会如实报告条数与核验率。

## 目录结构

```
SKILL.md               # 技能定义（触发条件、工作流、输出口径）
scripts/ctrip_tour.py  # 全部逻辑，仅标准库
data/products.json     # 数据集（含排除记录与自营凭据字段）
data/index.json        # 天数索引（由 index 子命令生成）
references/schema.md   # 字段字典
references/rules.md    # 判定规则与排除码
```

## 免责声明

`data/products.json` 内容抓取自携程公开页面，仅用于技术研究与内部选品参考，版权归携程所有。请勿用于商业转载或对外发布。数据可能过期，实际预订信息以携程官方页面为准。

## License

MIT（仅覆盖代码与文档；数据集内容版权归原权利人所有）

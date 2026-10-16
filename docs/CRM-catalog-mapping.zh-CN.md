# VERA 官网与现用模板目录映射

实施补记：后续已支持管理员私有导入模板，保持原ID并创建五系列展示/模板订购范围，Ashwood仍仅展示。下文为迁移前的来源对照，最新实现见 [Excel自动化实施](CRM-excel-automation.zh-CN.md)。

日期：2026-10-16。官网正文来自已保存的 https://verashading.com/products（`output/vera_products_source_20261016.html`）。模板代码来自 `output/VERA_template_inspection_20261016.json` 的 Product Listing A2:A24 及对应颜色、叶片行。这是名称级对照，不是可上线的产品种子，也不改 `service.py`。

## 已对齐的百叶窗系列

官网只介绍五种 plantation shutters。下面四项与模板代码、公开颜色、叶片尺寸一致。

| 官网 | 模板代码 | 颜色 | 叶片 |
|---|---|---|---|
| VERA Classic / PVC Premium，20年 | Shutters_PVC | White 01 至 Chalk 08，共 8 色 | 63/76/89/114mm |
| VERA Eco / PVC，5年，全防潮 | Shutters_PVC_Eco | 只有 White 01 | 63/76/89/114mm |
| VERA Natural / Pinewood，5年 | Shutters_Pinewood | White 01 至 Chalk 08 | 63/76/89/114mm |
| VERA Prime / Basswood，10年 | Shutters_Basswood | 上述 8 色加 Golden Oak 61 至 Provence Blue 70，共 18 色 | 63/76/89/114mm |

框型代码在 Shutters_*C1（如 FBL38-16），本表未把框型写成官网卖点。

## 不能直接替换的差异

- VERA Deluxe / Ashwood 在官网有 10 个着色（Golden Oak 61 至 Provence Blue 70），模板 A2:A24 没有 Ashwood 代码。先标为仅展示，不新增 Shutters_Ashwood。
- Shutters_Aluminium 在模板可订购。颜色是 Satin White、Gloss White、Surfmist、Matt Black、Monument。叶片是 63/89/114/125mm，没有 76mm。官网五系列页没有这一项，不能套用 PVC/木材的颜色和叶片。
- 模板另有 18 个非百叶窗代码，官网产品页没有对应介绍：Roller_Blinds_BO_VIBE、LeReve、Skye、Karma、Mantra、Sunscreen；Roller_Blinds_LF_LeReve、Skye、Mantra；Venetian_Blinds_PVC、Wood、Aluminium_25mm、Aluminium_50mm；Vertical_Blinds_VIBE_89mm、VIBE_100mm、Karma_89mm；Exterior_Blinds_Mesh、ClearPVC。保留为模板可订购配置，不编造官网文案。
- 现有系统种子仍是三条示例百叶，既不是这五个系列，也不是这 23 个代码。迁移时保留原 ID，避免历史订单改指向。

## 还不能做的事

不把 23 个代码压成 5 个 SKU，不按颜色生成 SKU，不把面积公式套到 roller/venetian。价格、安装和供应商输出仍以模板核对稿为准。Ashwood 是否批发可订、铝百叶是否对外销售，需要客户确认后再做独立目录迁移。

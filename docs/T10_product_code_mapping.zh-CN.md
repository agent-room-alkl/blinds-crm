# 23 个 Excel 产品代码 与 官网 5 系列 的对照（T-10）

复核人：Claude（Agent Room）
日期：2026-10-18
数据来源：`D:\workspace\vera\Shutter Studio Wholesale Order Template - native repaired.xlsm`（536,487 字节）

读取方式：以 ZIP/XML 只读解析，**未启动 Excel、未执行宏、未写回原文件**。下面每个结论都附单元格或命名区域引用，可自行复核。

---

## 零、会议原话（决定性证据，后补）

本文第一版只对照了工作簿。Robin 随后要求核对会议记录 `与 BIN E 的会议.docx`，其中 BIN E 对产品模型讲得非常明确，**直接解决了这个问题**，故置于最前：

> 「我现在就是就刚刚网上看的那5个item，**那就是最终5个产品**，其实最常销售的最最多，卖的只有只有两款，然后这两款里面还是有一个28比例的，80%都买那一款。」

> 「然后再选择这个商务上用什么产品，**就是刚刚那5选1的问题**」

> 「大部分目前所有的订单记录，基本上都是属于**尺寸和规格上面的区别**……他可能选的是89尺寸的叶片，另外订单选的是63的，或者这个窗户选的是 L 的边框、那个窗户选的是 Z 的边框，只是它这些规格上的变化，但它对我们来说……**本质对我们来说它是同一个产品**」

> 「还有大概有差不多10个左右的细节调整，就是选什么样颜色、什么叶片尺寸、什么开合方式，包括什么样的安装方式」

> 「它有差不多有4个选项是会影响价格的，**其他的选项它都不影响价格，只是视觉上不一样**」

> 「它不是那种 SKU 和库存的方式」「如果一个 item 就算一个 SKU 的话，那你以后未来就会积攒无限多的 SKU」

**结论因此收窄为：**

1. **客户下单的产品模型就是 5 选 1**，即官网五系列。叶片尺寸、边框、控制杆、安装方式等属于**同一产品内的规格变化**，客户自己也是这么理解的。
2. **那 18 个卷帘/威尼斯/垂直/户外帘不在这个下单流程的范围内**。它们存在于批发价表中，但 BIN E 描述客户下单时从头到尾只说 5 款。所以问题不是「配置 vs 产品」，而是**它们本来就不属于这套客户门户要卖的东西**。
3. 下面第一节的技术对照依然成立，且与此不矛盾：工作簿中 C1/C2/C4 装的正是 BIN E 所说的「规格变化」。那 18 个有独立价表与不同字段，这解释了**为什么不能把它们混进 5 系列的配置里**，但它们是否保留属于另一个决定。
4. **仍然缺口：VERA DELUXE / Ashwood 在工作簿中整行不存在，没有任何价格。** 5 选 1 的第 5 项点进去没有价格来源。此项必须由客户补齐，不作推测。

---

## 一、工作簿层面的对照：「这 18 个是不是那 5 个配出来的」

**部分成立，但主体不成立。**精确说法是：

| | 结论 | 证据 |
|---|---|---|
| **安装方式是共用配置** | ✅ 成立 | 命名区域 `Fitting = 'Product Listing'!$B$101:$D$101` = **In Fit / Out Fit / Make Size**，全部 23 个产品共用这一组，不区分品类 |
| **尺寸是共用配置** | ✅ 成立 | `Order!C` = Width(mm)、`Order!D` = Drop(mm)，对全部 23 个产品通用（`Order!B` 是 Window Location，不是尺寸）|
| **18 个 blinds 是 5 个 shutters 的配置项** | ❌ 不成立 | 见下 |
| **Shutters_Aluminium 是百叶窗家族的第 6 个** | ✅ 成立 | 同为 shutter、同样面积计价、同样有叶片尺寸与控制杆配置，只是官网没展示 |

也就是说：**安装方式和尺寸确实是「选配出来的」，但产品本身不是。**那 18 个在客户自己的表里是**与 5 个并列的产品**，不是 5 个的下级选项。

### 不成立的三条硬证据

**1. 下单时它们是平级选项，不是子选项**

```
命名区域  Product = 'Product Listing'!$A$2:$A$24
```

`Order!E8:E36`（产品列）的数据验证引用的就是这个 `Product` 区域。也就是说在客户现用的表里，**一条窗户明细是从这 23 个里挑一个**。23 个是兄弟关系。如果 18 个是 5 个的配置，它们不会出现在同一个产品下拉里。

**2. 每个产品有各自独立的价格来源，两套计价引擎**

5 个 shutters 走**面积单价**（㎡ 费率 + 最小面积 + 进位）。18 个 blinds 每个都有自己独立的**宽×高二维价表**：

```
Roller_Blinds_BO_VIBE_Price      = Pricing!$B$4:$Z$32
Roller_Blinds_BO_LeReve_Price    = Pricing!$B$35:$Z$63
Venetian_Blinds_PVC_Price        = Pricing!$B$286:$V$302
Vertical_Blinds_VIBE_89mm_Price  = Pricing!$B$404:$AS$433
Exterior_Blinds_ClearPVC_Price   = Pricing!$B$475:$G$478
（共 18 个独立价表，彼此不重叠）
```

若把卷帘当作 shutters 的配置项，就会套用面积公式。**报出来的价会错，而且错得不明显——要到客户下单才发现。**

**3. C1/C2/C4 三个配置槽，不同品类含义完全不同**

表里每个产品都有 C1/C2/C4 三个选项槽（`Order!L/M/N/O` 列通过 INDIRECT 随产品切换）。槽的名字一样，装的东西完全不是一回事：

| 产品 | C1 | C2 | C4 |
|---|---|---|---|
| Shutters_PVC | **框型** FBL38-16 / BL38-16 / 70B-F / PB68-19 / P50B-F / BZ20-16 / PBZ44-16 | **叶片** 63/76/89/114mm | **控制杆** Back Hidden / Front Centre / Front Side / Internal Concealed |
| Shutters_Aluminium | （无） | **叶片** 63/89/114/**125**mm（无 76mm） | **控制杆** 仅 Back Hidden |
| Roller_Blinds_BO_VIBE | **支架颜色** White/Ivory/Grey/Black | **链条颜色** White/Ivory/Grey/Black/Metal | **底轨颜色** White/Ivory/Grey/Black/Anodised Silver |
| Venetian_Blinds_PVC | （无） | **叶片** 50mm | （无） |
| Vertical_Blinds_VIBE_89mm | （无） | **叶片宽** 89mm | （无） |

卷帘的「支架/链条/底轨颜色」在百叶窗上根本不存在；百叶窗的「框型/控制杆」在卷帘上也不存在。**同一个槽位在不同品类是不同字段，不能当成同一个配置项的不同取值。**

---

## 二、23 个代码逐条对照

颜色数 = 该产品在 `Product Listing` 自己那一行的可选颜色/面料数量。

**「官网系列」这一列是推断，不是工作簿里写的。** 工作簿只有 Excel 产品代码，没有任何一处写着「Shutters_PVC = VERA Classic」。对应关系是我按材质和质保年数与官网五个详情页逐项比对得出的（例如 Shutters_PVC 的 8 个漆色与 20 年质保对上 PVC Premium / VERA Classic）。证据强，但仍属推断，正式确认需要客户点头。

| 行 | Excel 代码 | 官网系列 | 计价 | 价格区域 | 颜色/面料 | 配置槽 |
|---|---|---|---|---|---|---|
| 2 | Shutters_PVC | VERA CLASSIC / PVC Premium（推断） | 面积 | `Pricing!A485:B489` | 8 | C1 框型 / C2 叶片 / C4 控制杆 |
| 3 | Shutters_PVC_Eco | VERA ECO / PVC（推断） | 面积 | `Pricing!A485:B489` | 1（仅 White 01） | C1 / C2 / C4 |
| 4 | Shutters_Pinewood | VERA NATURAL / Pinewood（推断） | 面积 | `Pricing!A485:B489` | 8 | C1 / C2 / C4 |
| 5 | Shutters_Basswood | VERA PRIME / Basswood（推断） | 面积 | `Pricing!A485:B489` | 18（8 色 + Golden Oak 61…Provence Blue 70） | C1 / C2 / C4 |
| — | *(无代码)* | **VERA DELUXE / Ashwood** | — | **模板中不存在** | — | — |
| 6 | Shutters_Aluminium | 官网无，但**属百叶窗家族** | 面积 | `Pricing!A485:B489` | 5（Satin White/Gloss White/Surfmist/Matt Black/Monument） | C2 叶片 / C4 控制杆 |
| 7 | Roller_Blinds_BO_VIBE | 无 | 矩阵 | `Pricing!$B$4:$Z$32` | 26 | C1 支架 / C2 链条 / C4 底轨 |
| 8 | Roller_Blinds_BO_LeReve | 无 | 矩阵 | `Pricing!$B$35:$Z$63` | 10 | 同上 |
| 9 | Roller_Blinds_BO_Skye | 无 | 矩阵 | `Pricing!$B$66:$Z$94` | 9 | 同上 |
| 10 | Roller_Blinds_BO_Karma | 无 | 矩阵 | `Pricing!$B$255:$Z$283` | 12 | 同上 |
| 11 | Roller_Blinds_BO_Mantra | 无 | 矩阵 | `Pricing!$B$159:$Z$187` | 14 | 同上 |
| 12 | Roller_Blinds_Sunscreen | 无 | 矩阵 | `Pricing!$B$221:$Z$249` | 17 | 同上 |
| 13 | Roller_Blinds_LF_LeReve | 无 | 矩阵 | `Pricing!$B$97:$Z$125` | 10 | 同上 |
| 14 | Roller_Blinds_LF_Skye | 无 | 矩阵 | `Pricing!$B$128:$Z$156` | 9 | 同上 |
| 15 | Roller_Blinds_LF_Mantra | 无 | 矩阵 | `Pricing!$B$190:$Z$218` | 14 | 同上 |
| 16 | Venetian_Blinds_PVC | 无 | 矩阵 | `Pricing!$B$286:$V$302` | 2 | C2 叶片 50mm |
| 17 | Venetian_Blinds_Wood | 无 | 矩阵 | `Pricing!$B$329:$V$345` | 2 | C2 叶片 |
| 18 | Venetian_Blinds_Aluminium_25mm | 无 | 矩阵 | `Pricing!$B$348:$Z$369` | 2 | C2 叶片 25mm |
| 19 | Venetian_Blinds_Aluminium_50mm | 无 | 矩阵 | `Pricing!$B$305:$Z$326` | 2 | C2 叶片 50mm |
| 20 | Vertical_Blinds_VIBE_89mm | 无 | 矩阵 | `Pricing!$B$404:$AS$433` | 26 | C2 叶片宽 89mm |
| 21 | Vertical_Blinds_VIBE_100mm | 无 | 矩阵 | `Pricing!$B$372:$AS$401` | 26 | C2 叶片宽 100mm |
| 22 | Vertical_Blinds_Karma_89mm | 无 | 矩阵 | `Pricing!$B$437:$AS$466` | 12 | C2 叶片宽 89mm |
| 23 | Exterior_Blinds_Mesh | 无 | 矩阵 | `Pricing!$B$469:$G$472` | 3 | — |
| 24 | Exterior_Blinds_ClearPVC | 无 | 矩阵 | `Pricing!$B$475:$G$478` | 1（Clear） | — |

**合计**：官网 5 系列 → 模板里只有 4 个有代码和价格；Ashwood 没有。另有 1 个同族百叶窗（铝）官网未展示。其余 18 个属四个不同品类。

### 计价与尺寸的实际依据（复核后补正）

以下为 Grok Bot 复核时指出、我重新从工作簿读取确认的内容。**本文只给单元格/区域引用，不抄录实际批发价数字** —— 仓库是公开的，价格属于客户商业信息。

| 项 | 实际依据 |
|---|---|
| 尺寸列 | `Order!C` = Width(mm)，`Order!D` = Drop(mm)。`Order!B` 是 Window Location，不是尺寸 |
| 面板数 | `Order!G` = Panel Q'ty |
| 安装开关 | `Order!I4`；为 TRUE 时才计安装费，按面板数 × 费率 |
| 面积公式 | `Order!V8` = `IF(E8="","",IF(ISNUMBER(SEARCH("Shutters",E8)),MAX(ROUNDUP(C8*D8/1000000,2),0.5),1))` |
| 面积最小值 | **0.5 ㎡**，由上式的 `MAX(...,0.5)` 保证；且只对名称含 "Shutters" 的产品走面积计价 |
| 五个 shutters 的 ㎡ 费率 | `Pricing!A485:B489`（A 列产品代码，B 列费率；五行分别对应 PVC / PVC_Eco / Pinewood / Basswood / Aluminium）|
| blinds 取价方式 | 宽高各自向上取到 `*_w` / `*_h` 命名区域里的下一档；**超过最大一档时 IFERROR 返回 0**，不是报错 |

最后一条值得单独强调：**超出最大尺寸档位时工作簿算出来是 0，不是拒绝**。系统侧必须把这种情况当作错误拒掉，不能把 0 当成真实价格放行。

### 两处命名对不上的地方（复核后补）

安装费表 `Pricing!A500:A513` 里有两行跟产品代码对不上：

- `Pricing!A507` = `Vertical_Blinds_Karma_100mm` —— **这个产品代码在 `Product Listing` A2:A24 里不存在**（那里只有 `Vertical_Blinds_Karma_89mm`）。是孤立行，来源待客户确认。
- `Pricing!A509` = `Exterior_Blinds_Clear` —— 产品代码是 `Exterior_Blinds_ClearPVC`，两者不一致。这就是之前记录的 ClearPVC 安装别名对不上，系统因此拒绝给该产品出安装报价。

### 关于安装方式（这次特别要求核对的）

`Fitting = In Fit / Out Fit / Make Size`，**23 个产品共用**。
安装**费用**另有来源，且 10-16 的核对已记录一处缺口：**ClearPVC 的安装代码与安装费表里的 `Clear` 对不上**，系统因此拒绝给该产品出安装报价，不猜测对应关系。这一条仍待客户确认。

---

## 三、这对「围绕 5 个系列做客户自定义下单」意味着什么

可以直接复用的（已在系统里，且本轮已实测）：

- 一条明细 = 一个命名窗户 + 宽/高 + 产品 + 配置
- 安装方式 In Fit / Out Fit / Make Size 作为通用配置项
- 配置随产品动态切换（系统已按产品各自的 `configuration_schema` 渲染，不是所有产品共用一组选项）
- 提交前实时看价

需要先定的（**不定就只能猜，猜了价格会错**）：

1. **VERA DELUXE / Ashwood 的价格与配置**。官网第 5 个系列在模板里**完全没有**，不是缺一列，是整行不存在。要做「围绕 5 个系列下单」，这一项必须由客户补齐，否则第 5 个系列点进去没有价格。
2. **Shutters_Aluminium 怎么处理**。它是实打实的第 6 种百叶窗材质（面积计价、有叶片和控制杆），只是官网没放。要么官网补上，要么明确它只在登录后可订。
3. **那 18 个 blinds 的去留**。按本文证据它们不是 5 个系列的配置，属于独立品类。保留就要承认可订范围大于官网；下架就等于关掉这些品类的下单能力。**本文不做这个决定，也未改动任何产品数据。**

---

## 四、本次核对没有动过任何东西

- 未停用、未删除任何产品
- 未修改数据库
- 未改动代码
- 工作簿以只读方式解析，未执行宏，未写回

---

*提取脚本在会话临时目录，非仓库文件。本文只回答「23 个代码与官网 5 系列的对应关系」，不含下单流程设计。*

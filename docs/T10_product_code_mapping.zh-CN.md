# 23 个 Excel 产品代码 与 官网 5 系列 的对照（T-10）

复核人：Claude（Agent Room）
日期：2026-10-18
数据来源：`D:\workspace\vera\Shutter Studio Wholesale Order Template - native repaired.xlsm`（536,487 字节）

读取方式：以 ZIP/XML 只读解析，**未启动 Excel、未执行宏、未写回原文件**。下面每个结论都附单元格或命名区域引用，可自行复核。

---

## 一、直接回答「这 18 个是不是那 5 个配出来的」

**部分成立，但主体不成立。**精确说法是：

| | 结论 | 证据 |
|---|---|---|
| **安装方式是共用配置** | ✅ 成立 | 命名区域 `Fitting = 'Product Listing'!$B$101:$D$101` = **In Fit / Out Fit / Make Size**，全部 23 个产品共用这一组，不区分品类 |
| **尺寸是共用配置** | ✅ 成立 | `Order!B/C` 列的宽(mm)/drop(mm)对所有产品通用 |
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

| 行 | Excel 代码 | 官网系列 | 计价 | 价格区域 | 颜色/面料 | 配置槽 |
|---|---|---|---|---|---|---|
| 2 | Shutters_PVC | **VERA CLASSIC / PVC Premium** | 面积 | 面积费率 | 8 | C1 框型 / C2 叶片 / C4 控制杆 |
| 3 | Shutters_PVC_Eco | **VERA ECO / PVC** | 面积 | 面积费率 | 1（仅 White 01） | C1 / C2 / C4 |
| 4 | Shutters_Pinewood | **VERA NATURAL / Pinewood** | 面积 | 面积费率 | 8 | C1 / C2 / C4 |
| 5 | Shutters_Basswood | **VERA PRIME / Basswood** | 面积 | 面积费率 | 18（8 色 + Golden Oak 61…Provence Blue 70） | C1 / C2 / C4 |
| — | *(无代码)* | **VERA DELUXE / Ashwood** | — | **模板中不存在** | — | — |
| 6 | Shutters_Aluminium | 官网无，但**属百叶窗家族** | 面积 | 面积费率 | 5（Satin White/Gloss White/Surfmist/Matt Black/Monument） | C2 叶片 / C4 控制杆 |
| 7 | Roller_Blinds_BO_VIBE | 无 | 矩阵 | `Pricing!$B$4:$Z$32` | 26 | C1 支架 / C2 链条 / C4 底轨 |
| 8 | Roller_Blinds_BO_LeReve | 无 | 矩阵 | `Pricing!$B$35:$Z$63` | 25 | 同上 |
| 9 | Roller_Blinds_BO_Skye | 无 | 矩阵 | `Pricing!$B$66:$Z$94` | 25 | 同上 |
| 10 | Roller_Blinds_BO_Karma | 无 | 矩阵 | `Pricing!$B$255:$Z$283` | 26 | 同上 |
| 11 | Roller_Blinds_BO_Mantra | 无 | 矩阵 | `Pricing!$B$159:$Z$187` | 26 | 同上 |
| 12 | Roller_Blinds_Sunscreen | 无 | 矩阵 | `Pricing!$B$221:$Z$249` | 26 | 同上 |
| 13 | Roller_Blinds_LF_LeReve | 无 | 矩阵 | `Pricing!$B$97:$Z$125` | 26 | 同上 |
| 14 | Roller_Blinds_LF_Skye | 无 | 矩阵 | `Pricing!$B$128:$Z$156` | 26 | 同上 |
| 15 | Roller_Blinds_LF_Mantra | 无 | 矩阵 | `Pricing!$B$190:$Z$218` | 26 | 同上 |
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

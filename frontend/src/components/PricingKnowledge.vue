<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { request } from "../crm-api";

const props = defineProps<{ admin: boolean }>();
const { locale } = useI18n();
const tx = (zh: string, en: string) => locale.value === "zh" ? zh : en;
type Fact = Record<string, any>;
type Draft = { id: string; title: string; summary: string; status: string; facts: Fact[]; manifest: any; source_ids: string[]; published_version?: string };
const state = ref<any>({ current: null, sources: [], drafts: [], ai_configured: false });
const selected = ref<Draft | null>(null);
const busy = ref(false);
const error = ref("");
const notice = ref("");
const upload = ref<File | null>(null);
const defaultSources = ref(false);
const knowledgeTab = ref<"products" | "addons" | "order" | "logic" | "evidence">("products");
const knowledgeTabs = computed(() => [
  {id:"products",label:tx("系列价格 / 面积","Series rates / area")},
  {id:"addons",label:tx("附加项","Add-ons")},
  {id:"order",label:tx("整单参数","Order parameters")},
  {id:"logic",label:tx("折扣 / 固定规则","Discounts / fixed rules")},
  {id:"evidence",label:tx("来源事实 / 引用","Source facts / citations")},
]);
function selectKnowledgeTab(id: string) { knowledgeTab.value = id as typeof knowledgeTab.value; }
const products = [
  ["Shutters_PVC_Eco", "Eco / PVC Eco"], ["Shutters_PVC", "Classic / PVC"],
  ["Shutters_Pinewood", "Natural / Pinewood"], ["Shutters_Basswood", "Prime / Basswood"],
  ["VERA_Ashwood_provisional", "Deluxe / Ashwood"],
];
const ruleTypes = ["base_price_per_sqm", "addon_fixed", "addon_per_sqm", "addon_percent", "minimum_area_per_window", "minimum_area_per_order", "tax_rate", "deposit_rate", "installation_per_panel", "minimum_installation", "reference_only"];
const ruleNames: Record<string,string> = {base_price_per_sqm:"Base price / sqm",addon_fixed:"Fixed add-on",addon_per_sqm:"Add-on / sqm",addon_percent:"Add-on percent",minimum_area_per_window:"Minimum area / window",minimum_area_per_order:"Minimum area / order",tax_rate:"Tax rate",deposit_rate:"Deposit rate",installation_per_panel:"Installation / panel",minimum_installation:"Minimum installation",reference_only:"Reference only"};
const current = computed(() => selected.value?.manifest || state.value.current);
const activeVersion = computed(() => state.value.current?.version || "");

async function load() { state.value = await request("operations/pricing-knowledge"); }
onMounted(() => { void load().catch(showError); });
function showError(e: unknown) { error.value = e instanceof Error ? e.message : String(e); }
function clearMessages() { error.value = ""; notice.value = ""; }
function editDraft(d: Draft) { selected.value = JSON.parse(JSON.stringify(d)); }
function clearDraft() { selected.value = null; }
function editProduct(code: string, key: string, value: string) {
  const row = selected.value?.manifest.products.find((item: any) => item.source_code === code);
  if (row) row[key] = value;
}
function setProductConfirmed(code: string, confirmed: boolean) {
  const row = selected.value?.manifest.products.find((item: any) => item.source_code === code);
  if (!row) return;
  row.provisional = !confirmed;
  row.status = confirmed ? "configured" : "provisional_placeholder";
  row.warnings = confirmed ? [] : ["Administrator confirmation is required before quotes can use this rule."];
}
function addonTitle(addon: any) { return locale.value === "zh" ? addon.label_zh : addon.label_en; }
function addonChoice(addon: any, choice: any) { return `${addonTitle(addon)} · ${choice.value}`; }
function setChoiceAmount(addon: any, choice: any, field: string, value: string) {
  for (const key of ["fixed", "per_sqm", "percent"]) delete choice[key];
  if (value !== "") choice[field] = value;
}
function choiceRuleType(choice: any) { return ["fixed", "per_sqm", "percent"].find((key) => key in choice) || "fixed"; }
function bindingValue(binding: any, manifest: any) {
  if (!manifest) return "—";
  if (binding.source_code) {
    const product = manifest.products?.find((row: any) => row.source_code === binding.source_code);
    return product?.[binding.field] ?? "—";
  }
  if (binding.addon_key) {
    const addon = manifest.addons?.find((row: any) => row.key === binding.addon_key);
    const choice = addon?.choices?.find((row: any) => row.value === binding.choice_value);
    return choice?.[binding.field] ?? "—";
  }
  if (binding.field === "discounts") return (manifest.discounts || []).map((row: any) => typeof row === "object" ? row.value : row).filter((value: any) => value !== null && value !== undefined && value !== "").join(", ") || "—";
  if (binding.field) return manifest[binding.field] ?? "—";
  return tx("代码固定", "Code fixed");
}
function bindingStatus(binding: any, manifest: any) {
  if (!binding.field) return tx("代码固定", "Code fixed");
  if (binding.source_code) {
    const quoteableCodes = ["Shutters_PVC_Eco", "Shutters_PVC", "Shutters_Pinewood", "Shutters_Basswood", "VERA_Ashwood_provisional"];
    if (!quoteableCodes.includes(binding.source_code)) return tx("报价引擎不支持／不可报价", "Unsupported by quote engine / blocked");
    const product = manifest.products?.find((row: any) => row.source_code === binding.source_code);
    return !product || product.provisional || product.status !== "configured" ? tx("待确认／不可报价", "Unconfirmed / blocked") : tx("已关联／可报价", "Bound / quoteable");
  }
  return tx("已关联／可报价", "Bound / quoteable");
}
function pricingVariableMap(manifest: any) {
  if (!manifest) return [];
  const bindings: any[] = [];
  const effects: Record<string,string> = {
    rate_per_m2: tx("重算窗单价、行金额及商品小计，并传导到 GST、总价和定金。", "Recalculates panel price, line amount and subtotal, flowing through GST, total and deposit."),
    minimum_area: tx("改变此系列每窗计费面积、行金额与后续合计。", "Changes billable area per window for this series and the resulting totals."),
    order_minimum_area: tx("触发整单面积补足，重算 shutter 行金额与合计。", "Applies the order area floor and recalculates shutter amounts and totals."),
    installation_per_panel: tx("改变安装费用、GST、总价和定金。", "Changes installation, GST, total and deposit."),
    minimum_installation: tx("改变选择安装时的订单最低安装费及后续合计。", "Changes the minimum installation charge and resulting totals when installation is selected."),
    tax_rate: tx("改变 GST、含税总价与定金。", "Changes GST, tax-inclusive total and deposit."),
    deposit_rate: tx("只改变新订单应付定金金额。", "Changes the deposit due on new orders."),
    discounts: tx("决定员工报价调整可选的折扣值；选中后影响行单价。", "Controls staff adjustment choices; a selected discount changes the line price."),
  };
  for (const product of manifest.products || []) {
    if (product.kind !== "shutter") continue;
    for (const [field, category, label] of [["rate_per_m2", tx("基础单价", "Base rate"), tx("每平方米单价", "Rate per sqm")], ["minimum_area", tx("计价面积", "Billable area"), tx("单窗最低面积", "Minimum area per window")]]) {
      bindings.push({id:`${field}:${product.source_code}`, category, label:`${product.source_code} · ${label}`, variable:`products[${product.source_code}].${field}`, field, source_code:product.source_code, effect:effects[field], source:product.source_code === "VERA_Ashwood_provisional" ? tx("V5 Ashwood 来源事实；Deluxe 映射未确认", "V5 Ashwood evidence; Deluxe mapping unconfirmed") : tx("活动模板与 V5 PDF", "Active template and V5 PDF")});
    }
  }
  for (const addon of manifest.addons || []) for (const choice of addon.choices || []) {
    if (["no", "none"].includes(choice.value)) continue;
    for (const field of ["fixed", "per_sqm", "percent"]) if (field in choice) bindings.push({id:`addon:${addon.key}:${choice.value}:${field}`,category:tx("附加项", "Add-on"),label:`${addon.label_zh || addon.key} · ${choice.label_zh || choice.value}`,variable:`addons[${addon.key}].choices[${choice.value}].${field}`,field,addon_key:addon.key,choice_value:choice.value,effect:tx("改变该附加项对行金额的固定金额、每㎡金额或百分比加价。", "Changes the add-on fixed, per-sqm, or percentage amount on the line."),source:tx("活动知识库规则 / V5 PDF", "Active knowledge rule / V5 PDF")});
  }
  for (const [field,label] of [["order_minimum_area",tx("整单最低计价面积","Order minimum area")],["installation_per_panel",tx("每扇安装费","Installation per panel")],["minimum_installation",tx("最低安装费","Minimum installation")],["tax_rate",tx("GST 税率","GST rate")],["deposit_rate",tx("定金比例","Deposit rate")]]) bindings.push({id:`parameter:${field}`,category:tx("整单参数","Order parameter"),label,variable:field,field,effect:effects[field],source:tx("活动版本 manifest", "Active version manifest")});
  bindings.push({id:"discounts",category:tx("员工折扣","Staff discount"),label:tx("折扣选项","Discount choices"),variable:"discounts[]",field:"discounts",effect:effects.discounts,source:"Product Listing!B102:I102"});
  bindings.push({id:"area-rounding",category:tx("计价规则","Pricing rule"),label:tx("面积和金额 ROUNDUP","Area and amount ROUNDUP"),variable:"excel_rules.up() / code constant",field:null,effect:tx("面积进位到 0.01㎡，金额向上进位到 0.01；代码固定，知识库不能编辑。", "Area rounds up to 0.01 sqm and amounts to 0.01; code-fixed and not editable in knowledge."),source:"backend/excel_rules.py"});
  return bindings;
}
function visiblePricingBindings(manifest: any) {
  const bindings = pricingVariableMap(manifest);
  if (knowledgeTab.value === "products") return bindings.filter((binding) => binding.source_code);
  if (knowledgeTab.value === "addons") return bindings.filter((binding) => binding.addon_key);
  if (knowledgeTab.value === "order") return bindings.filter((binding) => binding.id.startsWith("parameter:"));
  if (knowledgeTab.value === "logic") return bindings.filter((binding) => ["discounts", "area-rounding"].includes(binding.id));
  return [];
}

async function initializeDefault() {
  busy.value = true; clearMessages();
  try {
    const result = await request<any>("operations/pricing-knowledge/initialize-default", {});
    await load();
    notice.value = tx(`已从现有资料初始化默认知识库（${result.version.slice(0,12)}）。四个共同系列可报价；Deluxe/Ashwood 保持待确认。`, `Default knowledge initialized from supplied files (${result.version.slice(0,12)}). The four aligned series are available; Deluxe/Ashwood remains unconfirmed.`);
  } catch(e) { showError(e); } finally { busy.value = false; }
}

async function createDraftFromCurrent() {
  busy.value = true; clearMessages();
  try {
    selected.value = await request<Draft>("operations/pricing-knowledge/drafts/from-current", {});
    await load();
    notice.value = tx("已创建当前知识库的可编辑草稿；无需重新上传来源文件。", "Created an editable draft from the active knowledge; no source re-upload is needed.");
  } catch(e) { showError(e); } finally { busy.value = false; }
}

async function uploadFile() {
  if (!upload.value) return;
  busy.value = true; clearMessages();
  try {
    const file = upload.value;
    if (file.size > 5 * 1024 * 1024) throw new Error(tx("文件超过 5 MB 限制。", "File exceeds the 5 MB limit."));
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary = ""; for (let i=0;i<bytes.length;i+=0x8000) binary += String.fromCharCode(...bytes.subarray(i, i+0x8000));
    const source = await request<any>("operations/pricing-knowledge/sources", {filename:file.name,content_base64:btoa(binary)});
    notice.value = tx("来源已保存。文件不会自动发送给 AI；请明确点击‘AI分析’。", "Source saved. It is not sent to AI until you click Analyze with AI.");
    upload.value = null;
    await load();
    if (!source.parsed_template_available && !state.value.current) notice.value += tx(" 首次初始化需要上传现有批发价格工作簿。", " Upload the existing wholesale pricing workbook to initialize the first rule set.");
  } catch (e) { showError(e); } finally { busy.value = false; }
}
async function analyze(source: any) {
  busy.value = true; clearMessages();
  try { selected.value = await request<Draft>(`operations/pricing-knowledge/sources/${encodeURIComponent(source.id)}/analyze`, {}); await load(); notice.value = tx("分析完成。所有候选规则默认未批准。", "Analysis complete. Every candidate rule starts unapproved."); }
  catch(e) { showError(e); } finally { busy.value = false; }
}
async function saveDraft(showNotice = true) {
  if (!selected.value) return;
  busy.value = true; clearMessages();
  try { selected.value = await request<Draft>(`operations/pricing-knowledge/drafts/${encodeURIComponent(selected.value.id)}`, {manifest:selected.value.manifest,facts:selected.value.facts}); await load(); if (showNotice) notice.value = tx("草稿已保存。", "Draft saved."); }
  catch(e) { showError(e); } finally { busy.value = false; }
}
async function publish() {
  if (!selected.value) return;
  busy.value = true; clearMessages();
  try {
    const id = selected.value.id;
    await request<Draft>(`operations/pricing-knowledge/drafts/${encodeURIComponent(id)}`, {manifest:selected.value.manifest,facts:selected.value.facts});
    const result = await request<any>(`operations/pricing-knowledge/drafts/${encodeURIComponent(id)}/publish`, {});
    notice.value = tx(`已发布版本 ${result.version.slice(0,12)}。仅影响之后的报价。`, `Published ${result.version.slice(0,12)}. Only future quotes are affected.`);
    selected.value = null; await load();
  }
  catch(e) { showError(e); } finally { busy.value = false; }
}
function sourceUrl(id: string) { return `/api/operations/pricing-knowledge/sources/${encodeURIComponent(id)}/file`; }
</script>

<template>
  <section class="knowledge-page">
    <header class="knowledge-heading"><div><p class="eyebrow">VERA · PRICING CONTROL</p><h1>{{ tx("定价知识库", "Pricing knowledge") }}</h1><p>{{ tx("上传价格来源，提取可追溯事实，再编辑并发布实际计价规则。", "Upload source documents, extract cited facts, then edit and publish the rules used for quotes.") }}</p></div><span class="version-pill">{{ activeVersion ? `${tx('当前版本','Active version')} ${activeVersion.slice(0,12)}` : tx("尚未发布价格规则", "No published price rules") }}</span></header>
    <p v-if="error" class="notice error" role="alert">{{ error }}</p><p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <section class="panel"><div class="section-title"><div><h2>{{ tx("来源文件", "Source documents") }}</h2><p>{{ tx("已提供的批发 XLSM 与 V5 PDF 可直接初始化为默认知识库，无需重新上传。", "The supplied wholesale XLSM and V5 PDF can initialize the default knowledge base without another upload.") }}</p></div></div>
      <div v-if="admin && !state.current?.knowledge_curated_at" class="upload-row"><button :disabled="busy" @click="initializeDefault">{{ state.current ? tx("把现有价格转为默认知识库", "Convert active legacy pricing into the default knowledge base") : tx("使用现有资料初始化默认知识库", "Initialize defaults from supplied sources") }}</button><span>{{ tx("从批发工作簿与 V5 PDF 生成可见事实、规则和来源引用；若已有旧 active 价版本，会保留旧版本与订单快照，只切换后续报价。", "Build visible facts, rules, and citations from the wholesale workbook and V5 PDF. If a legacy version is active, preserve it and existing order snapshots while switching future quotes.") }}</span></div>
      <form v-if="admin" class="upload-row" @submit.prevent="uploadFile"><input type="file" accept=".pdf,.xlsx,.xlsm" :disabled="busy" @change="upload = ($event.target as HTMLInputElement).files?.[0] || null"/><button :disabled="busy || !upload">{{ tx("上传来源", "Upload source") }}</button></form>
      <div v-if="state.sources.length" class="source-list"><article v-for="source in [...state.sources].reverse()" :key="source.id" class="source-card"><div><strong>{{ source.filename }}</strong><small>{{ source.uploaded_at }} · {{ source.section_count }} {{ tx("段内容", "sections") }} · SHA-256 {{ source.sha256?.slice(0,16) }}</small><small v-if="source.extraction_truncated" class="warn">{{ tx("提取内容已截断", "Extracted text was truncated") }}</small><small v-if="source.analysis_summary">{{ source.analysis_summary }}</small></div><div class="actions"><a v-if="admin && !source.seeded_reference" :href="sourceUrl(source.id)" target="_blank" rel="noreferrer">{{ tx("查看原文件", "View source") }}</a><button v-if="admin && !source.seeded_reference" :disabled="busy || !state.ai_configured" @click="analyze(source)">{{ tx("AI 分析", "Analyze with AI") }}</button></div></article></div><p v-else class="empty">{{ tx("还没有来源文件。", "No source documents yet.") }}</p><p v-if="admin && !state.ai_configured" class="warn">{{ tx("服务器尚未配置 OPENAI_API_KEY，AI 分析暂不可用。", "The server has no OPENAI_API_KEY configured, so AI analysis is unavailable.") }}</p>
    </section>
    <section v-if="state.current" class="panel"><div class="section-title"><div><h2>{{ tx("知识分类与来源引用", "Knowledge categories and citations") }}</h2><p>{{ tx("已发布版本包含事实、可执行规则、参数、来源对照及待确认项。", "The published version includes facts, executable rules, parameters, source comparisons, and unresolved items.") }}</p></div></div>
      <div v-if="state.current.knowledge_warnings?.length" class="knowledge-warnings"><article v-for="warning in state.current.knowledge_warnings" :key="warning.code"><strong>{{ warning.code }}</strong><p>{{ warning.message }}</p><small>{{ warning.status }}</small></article></div>
      <div class="subsection"><h3>{{ tx("知识规则到报价变量的真实映射", "Knowledge rules bound to quote variables") }}</h3><p>{{ tx("当前值直接读取活动版本 manifest；草稿中的数值会在下方编辑器同步显示。来源事实本身不会自动参与计算。发布后仅影响新报价，历史订单保留原快照。", "Values are read directly from the active version manifest; draft values appear in the editor below. Source facts alone do not enter calculations. Publishing affects future quotes; historical orders keep their snapshots.") }}</p>
        <div class="knowledge-tabs" role="tablist" :aria-label="tx('定价知识类别','Pricing knowledge categories')"><button v-for="tab in knowledgeTabs" :key="tab.id" type="button" role="tab" :aria-selected="knowledgeTab===tab.id" :class="{active:knowledgeTab===tab.id}" @click="selectKnowledgeTab(tab.id)">{{ tab.label }}</button></div>
        <div v-if="knowledgeTab !== 'evidence'" class="table-scroll"><table><thead><tr><th>{{ tx("类别", "Category") }}</th><th>{{ tx("规则", "Rule") }}</th><th>{{ tx("系统变量", "System variable") }}</th><th>{{ tx("当前值", "Current value") }}</th><th>{{ tx("关联状态", "Binding status") }}</th><th>{{ tx("报价影响", "Quote impact") }}</th><th>{{ tx("依据", "Evidence") }}</th></tr></thead><tbody><tr v-for="binding in visiblePricingBindings(state.current)" :key="binding.id"><td>{{ binding.category }}</td><td>{{ binding.label }}</td><td><code>{{ binding.variable }}</code></td><td>{{ bindingValue(binding,state.current) }}</td><td>{{ bindingStatus(binding,state.current) }}</td><td>{{ binding.effect }}</td><td>{{ binding.source }}</td></tr></tbody></table></div>
        <div v-else class="table-scroll"><table><thead><tr><th>{{ tx("分类", "Category") }}</th><th>{{ tx("项目", "Item") }}</th><th>{{ tx("数值 / 规则", "Value / rule") }}</th><th>{{ tx("状态", "Status") }}</th><th>{{ tx("来源位置", "Source location") }}</th><th>{{ tx("原文依据", "Source evidence") }}</th></tr></thead><tbody><tr v-for="fact in state.current.knowledge_facts || []" :key="fact.id"><td>{{ fact.category }}</td><td>{{ fact.label }}</td><td>{{ fact.value }} {{ fact.unit }}</td><td>{{ fact.status }}</td><td>{{ fact.source_location }}</td><td>{{ fact.source_excerpt }}</td></tr><tr v-for="rule in state.current.knowledge_rules || []" :key="rule.id"><td>{{ tx("规则", "Rule") }}</td><td>{{ rule.id }}</td><td>{{ rule.formula }}</td><td>{{ rule.status }}</td><td>{{ rule.source_location }}</td><td>{{ rule.source_id }}</td></tr></tbody></table></div>
      </div>
    </section>
    <section v-if="selected" class="panel editor"><div class="section-title"><div><p class="eyebrow">{{ selected.status === 'published' ? tx('已发布快照','Published snapshot') : tx('待审核草稿','Draft for review') }}</p><h2>{{ selected.title }}</h2><p>{{ selected.summary }}</p></div><button class="quiet" @click="clearDraft">{{ tx("关闭", "Close") }}</button></div>
      <div v-if="knowledgeTab !== 'evidence'" class="subsection"><h3>{{ tx("本版本的实时变量绑定", "Live variable bindings for this version") }}</h3><p>{{ tx("数值直接读取下方草稿/快照 manifest；保存并发布后，报价引擎会从该版本读取同一变量。", "Values are read from this draft or snapshot manifest; after saving and publishing, the quote engine reads these same variables from that version.") }}</p><div class="table-scroll"><table><thead><tr><th>{{ tx("变量", "Variable") }}</th><th>{{ tx("值", "Value") }}</th><th>{{ tx("状态", "Status") }}</th><th>{{ tx("作用", "Effect") }}</th></tr></thead><tbody><tr v-for="binding in visiblePricingBindings(selected.manifest)" :key="binding.id"><td><code>{{ binding.variable }}</code></td><td>{{ bindingValue(binding,selected.manifest) }}</td><td>{{ bindingStatus(binding,selected.manifest) }}</td><td>{{ binding.effect }}</td></tr></tbody></table></div></div>
      <div v-if="selected.manifest.products?.length" class="subsection"><h3>{{ tx("系列基础价格与单窗起算面积", "Series base price and per-window minimum area") }}</h3><div class="table-scroll"><table><thead><tr><th>{{ tx("系列", "Series") }}</th><th>{{ tx("每平方米价格", "Rate per sqm") }}</th><th>{{ tx("单窗最低面积", "Minimum area/window") }}</th><th>{{ tx("人工确认", "Human confirmation") }}</th></tr></thead><tbody><tr v-for="[code,label] in products" :key="code"><td>{{ label }}</td><td><input :value="selected.manifest.products.find((r:any)=>r.source_code===code)?.rate_per_m2" :disabled="!admin || selected.status !== 'draft'" type="number" min="0" step="0.01" @input="editProduct(code,'rate_per_m2',($event.target as HTMLInputElement).value)"/></td><td><input :value="selected.manifest.products.find((r:any)=>r.source_code===code)?.minimum_area" :disabled="!admin || selected.status !== 'draft'" type="number" min="0.01" step="0.01" @input="editProduct(code,'minimum_area',($event.target as HTMLInputElement).value)"/></td><td><label class="approve"><input :checked="selected.manifest.products.find((r:any)=>r.source_code===code)?.status === 'configured' && !selected.manifest.products.find((r:any)=>r.source_code===code)?.provisional" :disabled="!admin || selected.status !== 'draft'" type="checkbox" @change="setProductConfirmed(code,($event.target as HTMLInputElement).checked)"/>{{ tx('已核实来源与价格','Source and rate verified') }}</label></td></tr></tbody></table></div><p v-if="selected.manifest.products.find((r:any)=>r.source_code==='VERA_Ashwood_provisional')?.provisional" class="warn">{{ tx("Deluxe/Ashwood 映射未确认时将保持不可报价；核心四个系列可独立发布。确认其来源映射、价格并勾选人工确认后，才会开放 Deluxe。", "Deluxe/Ashwood stays unavailable for quotes while its mapping is unconfirmed; the four core series can be published separately. Confirm its source mapping and rate to enable Deluxe.") }}</p></div>
      <div class="subsection"><h3>{{ tx("整单计价参数", "Order pricing parameters") }}</h3><div class="parameter-grid"><label>{{ tx("订单最低计价面积（㎡）", "Order minimum billable area (sqm)") }}<input v-model="selected.manifest.order_minimum_area" :disabled="!admin || selected.status !== 'draft'" type="number" min="0.001" step="0.01"/></label><label>{{ tx("每扇安装费", "Installation per panel") }}<input v-model="selected.manifest.installation_per_panel" :disabled="!admin || selected.status !== 'draft'" type="number" min="0" step="0.01"/></label><label>{{ tx("最低安装费", "Minimum installation") }}<input v-model="selected.manifest.minimum_installation" :disabled="!admin || selected.status !== 'draft'" type="number" min="0" step="0.01"/></label><label>{{ tx("GST 税率（小数）", "GST rate (decimal)") }}<input v-model="selected.manifest.tax_rate" :disabled="!admin || selected.status !== 'draft'" type="number" min="0" max="1" step="0.001"/></label><label>{{ tx("定金比例（小数）", "Deposit rate (decimal)") }}<input v-model="selected.manifest.deposit_rate" :disabled="!admin || selected.status !== 'draft'" type="number" min="0" max="1" step="0.01"/></label></div></div>
      <div class="subsection"><h3>{{ tx("附加项价格", "Add-on prices") }}</h3><div v-for="addon in selected.manifest.addons" :key="addon.key" class="addon-row"><strong>{{ addonTitle(addon) }}</strong><label v-for="choice in addon.choices.filter((c:any)=>!['no','none'].includes(c.value))" :key="choice.value">{{ addonChoice(addon,choice) }}<span class="amount-edit"><select :value="choiceRuleType(choice)" :disabled="!admin || selected.status !== 'draft'" @change="setChoiceAmount(addon,choice,($event.target as HTMLSelectElement).value,choice[choiceRuleType(choice)] || '')"><option value="fixed">{{ tx("每件固定", "Fixed each") }}</option><option value="per_sqm">{{ tx("每平方米", "Per sqm") }}</option><option value="percent">%</option></select><input :value="choice[choiceRuleType(choice)] || ''" :disabled="!admin || selected.status !== 'draft'" type="number" min="0" step="0.01" @input="setChoiceAmount(addon,choice,choiceRuleType(choice),($event.target as HTMLInputElement).value)"/></span></label></div></div>
      <div class="subsection"><h3>{{ tx("AI 提取的候选事实", "AI extracted candidate facts") }}</h3><p>{{ tx("逐项核对来源页码/单元格与原文摘录。只有勾选批准的数字规则会影响报价。", "Check each source location and excerpt. Only approved numeric rules affect quotes.") }}</p><div v-for="(fact,index) in selected.facts" :key="index" class="fact-card"><label class="approve"><input v-model="fact.approved" :disabled="!admin || selected.status !== 'draft'" type="checkbox"/><strong>{{ fact.label }}</strong><span>{{ fact.confidence !== undefined ? `${Math.round(fact.confidence*100)}%` : '' }}</span></label><blockquote>{{ fact.source_excerpt }}</blockquote><small>{{ fact.source_location }} · {{ fact.unit }} · {{ fact.scope }}</small><div class="fact-edit"><label>{{ tx("建议规则", "Rule") }}<select v-model="fact.suggested_rule" :disabled="!admin || selected.status !== 'draft'"><option v-for="rule in ruleTypes" :key="rule" :value="rule">{{ ruleNames[rule] }}</option></select></label><label>{{ tx("数值", "Value") }}<input v-model="fact.value" :disabled="!admin || selected.status !== 'draft'"/></label><label v-if="['base_price_per_sqm','minimum_area_per_window'].includes(fact.suggested_rule)">{{ tx("系列映射", "Series mapping") }}<select v-model="fact.suggested_product_code" :disabled="!admin || selected.status !== 'draft'"><option :value="null">{{ tx("待选择", "Choose") }}</option><option v-for="[code,label] in products" :key="code" :value="code">{{ label }}</option></select></label><label v-if="fact.suggested_rule.startsWith('addon_')">{{ tx("附加项", "Add-on") }}<select v-model="fact.suggested_option_key" :disabled="!admin || selected.status !== 'draft'"><option v-for="addon in selected.manifest.addons" :key="addon.key" :value="addon.key">{{ addonTitle(addon) }}</option></select></label><label v-if="fact.suggested_rule.startsWith('addon_')">{{ tx("选项", "Choice") }}<select v-model="fact.choice_value" :disabled="!admin || selected.status !== 'draft'"><option v-for="choice in selected.manifest.addons.find((a:any)=>a.key===fact.suggested_option_key)?.choices || []" :key="choice.value" :value="choice.value">{{ choice.value }}</option></select></label></div></div><p v-if="!selected.facts.length" class="empty">{{ tx("没有候选事实；请在下方手动编辑规则。", "No candidate facts; edit the rules above directly.") }}</p></div>
      <footer v-if="admin && selected.status === 'draft'" class="footer-actions"><button class="quiet" :disabled="busy" @click="saveDraft()">{{ tx("保存草稿", "Save draft") }}</button><button :disabled="busy" @click="publish">{{ tx("发布此版本并用于新报价", "Publish version for future quotes") }}</button></footer>
    </section>
    <section class="panel"><div class="section-title"><div><h2>{{ tx("知识版本", "Knowledge versions") }}</h2><p>{{ tx("初始化默认版本及后续编辑版本均保留版本审计；历史订单保留原价格快照。", "The initialized default and later edited versions retain version history; historical orders keep their price snapshot.") }}</p></div><button v-if="admin && state.current" :disabled="busy" @click="createDraftFromCurrent">{{ tx("从当前知识创建可编辑草稿", "Create editable draft from current knowledge") }}</button></div><div v-if="state.current" class="draft-list"><article class="draft-card"><div><strong>{{ state.current.knowledge_curated_at ? tx("默认定价知识库", "Default pricing knowledge") : tx("当前旧版价格规则", "Existing legacy pricing rules") }}</strong><small>{{ state.current.imported_at }} · {{ tx("已发布", "published") }} · {{ state.current.version?.slice(0,12) }}</small></div><span>{{ state.current.knowledge_curated_at ? tx("来源：批发 XLSM + V5 PDF", "Sources: wholesale XLSM + V5 PDF") : tx("待整理：点击上方按钮", "Needs curation: use the button above") }}</span></article></div><div v-if="state.drafts.length" class="draft-list"><article v-for="draft in [...state.drafts].reverse()" :key="draft.id" class="draft-card"><div><strong>{{ draft.title }}</strong><small>{{ draft.created_at }} · {{ draft.status }}<span v-if="draft.published_version"> · {{ draft.published_version.slice(0,12) }}</span></small></div><button @click="editDraft(draft)">{{ tx(draft.status === 'draft' ? "审阅并编辑" : "查看版本", draft.status === 'draft' ? "Review and edit" : "View version") }}</button></article></div><p v-if="!state.current && !state.drafts.length" class="empty">{{ tx("还没有知识版本。点击上方按钮从现有文件初始化默认版本。", "No knowledge versions yet. Initialize the default version from the supplied files above.") }}</p></section>
  </section>
</template>

<style scoped>
.knowledge-page{max-width:1260px;margin:0 auto;padding:8px 0 32px;color:#19231e}.knowledge-heading{display:flex;justify-content:space-between;align-items:center;gap:20px;margin:12px 0 22px}.knowledge-heading h1{font-size:25px;margin:3px 0 8px}.knowledge-heading p,.section-title p{margin:0;color:#68766f;line-height:1.6}.eyebrow{font-size:11px;letter-spacing:.12em;color:#53705f}.version-pill{background:#e9eee8;padding:10px 13px;border-radius:999px;font-size:12px}.panel{background:#fff;border:1px solid #e0e6e0;border-radius:14px;padding:20px;margin:14px 0;box-shadow:0 2px 8px #1b39220a}.section-title{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:15px}.section-title h2{font-size:17px;margin:0 0 5px}.upload-row,.actions,.footer-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.upload-row{padding:13px;background:#f7f8f5;border-radius:10px}.source-list,.draft-list{display:grid;gap:9px;margin-top:12px}.source-card,.draft-card{display:flex;justify-content:space-between;align-items:center;gap:14px;border:1px solid #e5e9e4;border-radius:10px;padding:13px}.source-card>div:first-child,.draft-card>div{display:grid;gap:4px}.source-card small,.draft-card small{color:#68766f;font-size:11px}.source-card a{color:#286346}.knowledge-page button{border:0;background:#215b3c;color:white;border-radius:8px;padding:10px 13px;cursor:pointer;min-height:40px}.knowledge-page button:disabled{opacity:.5;cursor:not-allowed}.knowledge-page .quiet{background:#eef2ed;color:#26352c}.notice{padding:10px 13px;background:#e9f3ec;border-radius:9px}.notice.error{background:#fff0ed;color:#872e1e}.warn{color:#9a571d}.empty{color:#68766f;padding:7px 0}.subsection{border-top:1px solid #e9ece8;padding-top:14px;margin-top:16px}.subsection h3{font-size:14px;margin:0 0 10px}.knowledge-tabs{display:flex;gap:7px;overflow-x:auto;padding:5px 1px 10px;margin:10px 0 4px;border-bottom:1px solid #e3e8e2}.knowledge-tabs button{flex:0 0 auto;border:1px solid #dbe3da;background:#f6f8f5;color:#405048;padding:9px 12px;min-height:38px}.knowledge-tabs button.active{background:#215b3c;color:#fff;border-color:#215b3c}.table-scroll{overflow:auto}.knowledge-page table{border-collapse:collapse;width:100%;min-width:630px}.knowledge-page th,.knowledge-page td{text-align:left;padding:8px;border-bottom:1px solid #edf0ec;font-size:12px}.knowledge-page input,.knowledge-page select{border:1px solid #d6ded6;border-radius:6px;padding:8px;min-height:36px;max-width:100%;box-sizing:border-box}.knowledge-page td input{width:120px}.parameter-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:12px}.parameter-grid label,.fact-edit label,.addon-row label{display:grid;gap:5px;font-size:12px}.addon-row{display:grid;grid-template-columns:minmax(120px,1fr) 2fr;gap:12px;align-items:center;padding:10px 0;border-bottom:1px solid #edf0ec}.addon-row>label{grid-template-columns:minmax(130px,1fr) minmax(190px,240px);align-items:center}.amount-edit{display:grid;grid-template-columns:1fr 90px;gap:5px}.fact-card{border:1px solid #e4e9e4;border-radius:10px;padding:12px;margin:9px 0}.approve{display:flex;align-items:center;gap:8px}.approve span{color:#718078;font-size:11px}.fact-card blockquote{margin:9px 0 3px;padding-left:10px;border-left:3px solid #cfdbd0;font-size:12px}.fact-card>small{color:#68766f}.fact-edit{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:9px;margin-top:10px}.footer-actions{justify-content:flex-end;border-top:1px solid #e9ece8;padding-top:15px;margin-top:16px}@media(max-width:700px){.knowledge-heading,.source-card,.draft-card{align-items:flex-start;flex-direction:column}.panel{padding:14px}.addon-row{grid-template-columns:1fr}.knowledge-heading h1{font-size:22px}}
</style>

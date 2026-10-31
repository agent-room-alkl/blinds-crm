<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { portalRequest, portalSession } from "../../portal-api";
import { describeConfiguredAddons, isTrackAddon, syncOpeningStyle, trackAddonsLocked, type Addon } from "../../addons";
import { Copy, SlidersHorizontal, Trash2 } from "lucide-vue-next";

const { locale } = useI18n();
const tx = (zh: string, en: string) => locale.value === "zh" ? zh : en;
const router = useRouter();
const catalog = ref<any[]>([]);
const addons = ref<Addon[]>([]);
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const notice = ref("");
const quotePreview = ref<any>(null);
const basePreview = ref<any>(null);
const quoteLoading = ref(false);
const quoteError = ref("");
const draftKey = ref("");
const lastSaved = ref("");
const draft = reactive({ project_name: "", site_address: "", installation_required: false, windows: [] as any[] });

const shutterProducts = computed(() => catalog.value.filter(p => p.category === "shutters" && p.orderable));
const product = (id: number | "") => catalog.value.find(p => Number(p.id) === Number(id));
function schemaFields(id: number | "") { return product(id)?.configuration_schema || []; }
function fieldsFor(window: any) { return schemaFields(window.product_id).filter((f: any) => !["colour", "louver_size", "fitting"].includes(f.key)); }
function colorChoices(window: any) { return schemaFields(window.product_id).find((f: any) => f.key === "colour")?.choices || []; }
function louverChoices(window: any) { return schemaFields(window.product_id).find((f: any) => f.key === "louver_size")?.choices || []; }
function fittingChoices(window: any) { return schemaFields(window.product_id).find((f: any) => f.key === "fitting")?.choices || []; }
function choicesFor(window: any, key: string): string[] { return schemaFields(window.product_id).find((f: any) => f.key === key)?.choices || []; }
// Select fields that start on their first choice, so a new row only needs a name and sizes.
const DEFAULTED_FIELDS = ["opening_style", "frame", "louver_size", "colour", "control_rod", "fitting"];
function availableAddons(window: any) { return addons.value.filter(a => !a.exclude?.includes(product(window.product_id)?.source_code || "")); }
function onSeriesChange(window: any) {
  const allowed = new Map<string, any>(schemaFields(window.product_id).map((field: any) => [field.key, field]));
  const excluded = new Set(addons.value.filter(a => a.exclude?.includes(product(window.product_id)?.source_code || "")).map(a => a.key));
  for (const [key, value] of Object.entries(window.options as Record<string, string>)) {
    if (excluded.has(key)) { delete window.options[key]; continue; }
    const field = allowed.get(key);
    if (field && field.choices?.length && value && !field.choices.includes(value)) delete window.options[key];
    else if (!field && !addons.value.some(a => a.key === key)) delete window.options[key];
  }
  const fields = schemaFields(window.product_id);
  for (const key of DEFAULTED_FIELDS) {
    const field = fields.find((item: any) => item.key === key);
    if (field?.choices?.length && !field.choices.includes(window.options[key])) window.options[key] = field.choices[0];
  }
  syncOpeningStyle(window.options);
}
function addonLocked(window: any, key: string) { return isTrackAddon(key) && trackAddonsLocked(window.options); }
function setAddon(window: any, key: string, value: string) {
  if (!value || value === "no" || value === "none") delete window.options[key];
  else window.options[key] = value;
}
function addonSelected(window: any, key: string) { return Boolean(window.options[key] && !["no", "none"].includes(window.options[key])); }
function addonPriceLabel(addon: Addon) {
  const choice = addon.choices.find((item) => item.value !== "no" && item.value !== "none");
  if (!choice || ![choice.fixed, choice.per_sqm, choice.percent].some((amount) => amount !== undefined)) return "";
  return locale.value === "zh" ? choice.label_zh : choice.label_en;
}
// Internal Concealed carries the Hidden tilt rod charge; the price comes from the published add-on so it never drifts.
function isConcealedRod(value: unknown) { return String(value || "").trim().toLowerCase() === "internal concealed"; }
function rodPriceHint(value: string) {
  if (!isConcealedRod(value)) return "";
  const label = addons.value.find((a) => a.key === "hidden_tilt_rod")?.choices.find((c) => c.per_sqm !== undefined)?.per_sqm;
  return label ? ` (+$${label}/${locale.value === "zh" ? "㎡" : "sqm"})` : "";
}
// The preview prices only rows with a series, width and height; this maps a table row to its preview line.
const pricedRows = ref<number[]>([]);
function rowReady(w: any) { return Boolean(w.product_id) && Number(w.width_mm) > 0 && Number(w.height_mm) > 0; }
const pendingRows = computed(() => draft.windows.map((w, i) => (rowReady(w) ? 0 : i + 1)).filter(Boolean));
function previewLine(preview: any, index: number) {
  const position = pricedRows.value.indexOf(index);
  return position < 0 ? undefined : preview?.lines?.[position];
}
function previewLineAmount(preview: any, window: any, index: number) {
  const line = previewLine(preview, index);
  return line?.amount ? `${preview.currency || "NZD"} ${line.amount}` : "";
}
function money(value: unknown) { return `${quotePreview.value?.currency || "NZD"} ${value ?? "—"}`; }
function addonIncrement(window: any, index: number) {
  const withAddons = Number(previewLine(quotePreview.value, index)?.amount);
  const withoutAddons = Number(previewLine(basePreview.value, index)?.amount);
  if (!Number.isFinite(withAddons) || !Number.isFinite(withoutAddons) || withAddons <= withoutAddons) return "";
  return `${quotePreview.value?.currency || "NZD"} ${(withAddons - withoutAddons).toFixed(2)}`;
}
let quoteTimer: ReturnType<typeof setTimeout> | undefined;
let quoteTicket = 0;
async function refreshQuote() {
  const ticket = ++quoteTicket;
  quoteError.value = "";
  const ready = draft.windows.flatMap((w, i) => (rowReady(w) ? [i] : []));
  if (!ready.length) {
    quotePreview.value = null;
    basePreview.value = null;
    pricedRows.value = [];
    quoteLoading.value = false;
    return;
  }
  // Keep the last figures on screen while the next ones load, so the totals do not flicker on every keystroke.
  quoteLoading.value = true;
  const lines = ready.map((i) => draft.windows[i]).map((w) => ({
    window_name: w.window_name || tx("新窗户", "New window"),
    product_id: Number(w.product_id), width_mm: w.width_mm, height_mm: w.height_mm,
    quantity: 1, panel_count: Number(w.panel_count) || 1, options: { ...w.options },
  }));
  const body = { project_name: draft.project_name.trim() || "Preview", site_address: draft.site_address.trim() || "Preview",
    installation_required: draft.installation_required, submission_key: "pricing-preview", lines };
  const addonKeys = new Set(addons.value.map((a) => a.key));
  // The base price leaves out add-ons, the Internal Concealed rod and the Opening Style (the server adds its track add-on back),
  // so "Extra" shows everything that adds to the plain price.
  const baseBody = { ...body, lines: lines.map((line) => ({ ...line, options: Object.fromEntries(Object.entries(line.options).filter(([key, value]) => !addonKeys.has(key) && key !== "opening_style" && !(key === "control_rod" && isConcealedRod(value)))) })) };
  try {
    const [priced, base] = await Promise.all([
      portalRequest<any>("price", body),
      portalRequest<any>("price", baseBody),
    ]);
    if (ticket === quoteTicket) { quotePreview.value = priced; basePreview.value = base; pricedRows.value = ready; }
  } catch (cause) {
    if (ticket === quoteTicket) { quoteError.value = cause instanceof Error ? cause.message : String(cause); quotePreview.value = null; basePreview.value = null; pricedRows.value = []; }
  } finally {
    if (ticket === quoteTicket) quoteLoading.value = false;
  }
}
watch([() => draft.windows, () => draft.installation_required, () => draft.project_name, () => draft.site_address], () => {
  if (quoteTimer) clearTimeout(quoteTimer);
  quoteTimer = setTimeout(() => void refreshQuote(), 350);
}, { deep: true });
// Short labels for the add-ons a row has picked; the full choice text is in the dialog.
function addonChips(window: any) {
  return availableAddons(window).flatMap(a => {
    const value = window.options[a.key];
    if (!value || value === "no" || value === "none") return [];
    const label = locale.value === "zh" ? a.label_zh : a.label_en;
    if (value === "yes") return [label];
    const choice = a.choices.find(c => c.value === value);
    return [choice ? `${label}: ${locale.value === "zh" ? choice.label_zh : choice.label_en}` : label];
  });
}
// One native modal <dialog> edits the add-ons of whichever row opened it.
const addonDialog = ref<HTMLDialogElement | null>(null);
const addonTarget = ref<{ window: any; index: number } | null>(null);
async function openAddons(window: any, index: number) {
  addonTarget.value = { window, index };
  await nextTick();
  addonDialog.value?.showModal();
}
function onAddonDialogClick(event: MouseEvent) { if (event.target === addonDialog.value) addonDialog.value?.close(); }
function fieldLabel(f: any) { return locale.value === "zh" ? f.label_zh : f.label_en; }
// Customers choose by material, so the series name always carries it (VERA Classic · PVC Premium).
function productLabel(p: any) { return [locale.value === "zh" ? p.name_zh : p.name_en, p.material].filter(Boolean).join(" · "); }
function newWindow(): any {
  const first = shutterProducts.value[0];
  const options: Record<string,string> = {};
  for (const key of DEFAULTED_FIELDS) {
    const choice = first?.configuration_schema?.find((f:any) => f.key === key)?.choices?.[0];
    if (choice) options[key] = choice;
  }
  syncOpeningStyle(options);
  return { id: crypto.randomUUID(), window_name: "", product_id: first?.id || "", width_mm: "", height_mm: "", quantity: 1, panel_count: 1, options };
}
function addWindow() { draft.windows.push(newWindow()); }
function removeWindow(index: number) { draft.windows.splice(index, 1); }
function copyWindow(window: any) { draft.windows.push({ ...window, id: crypto.randomUUID(), window_name: "", options: { ...window.options } }); }

function saveDraft() {
  if (!draftKey.value) return;
  const data = { ...draft, windows: draft.windows, saved_at: Date.now() };
  localStorage.setItem(draftKey.value, JSON.stringify(data));
  lastSaved.value = new Date().toLocaleTimeString();
}
watch(draft, saveDraft, { deep: true });

async function load() {
  if (!portalSession.token) { router.replace("/portal"); return; }
  loading.value = true;
  try {
    const [result, account] = await Promise.all([
      portalRequest<{ products: any[]; addons?: Addon[] }>("catalog"),
      portalRequest<{ customer_id: number }>("me"),
    ]);
    catalog.value = result.products;
    addons.value = result.addons || [];
    draftKey.value = `vera-order-draft:${account.customer_id}`;
    const saved = localStorage.getItem(draftKey.value);
    if (saved) {
      const parsed = JSON.parse(saved);
      Object.assign(draft, parsed);
      if (!Array.isArray(draft.windows)) draft.windows = [];
      draft.windows.forEach(onSeriesChange); // fill fields older drafts left blank
      lastSaved.value = parsed.saved_at ? new Date(parsed.saved_at).toLocaleTimeString() : "";
    }
    if (!draft.windows.length) addWindow();
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally { loading.value = false; }
}

function checkWindow(w: any, index: number) {
  if (!w.window_name.trim()) return tx(`第 ${index + 1} 行请填写窗户名称。`, `Row ${index + 1}: enter a window name.`);
  if (!w.product_id || !(Number(w.width_mm) > 0) || !(Number(w.height_mm) > 0) || !(Number(w.panel_count) > 0)) return tx(`第 ${index + 1} 行的系列、宽、高和扇数都必须填写。`, `Row ${index + 1}: series, width, height and panels are required.`);
  for (const f of schemaFields(w.product_id)) {
    if (f.required && !w.options[f.key]) return tx(`第 ${index + 1} 行请填写${f.label_zh}。`, `Row ${index + 1}: ${f.label_en} is required.`);
    if (f.choices?.length && w.options[f.key] && !f.choices.includes(w.options[f.key])) return tx(`第 ${index + 1} 行的${f.label_zh}与所选系列不匹配。`, `Row ${index + 1}: ${f.label_en} is not valid for the selected series.`);
  }
  const excluded = addons.value.filter(a => a.exclude?.includes(product(w.product_id)?.source_code || ""));
  if (excluded.some(a => w.options[a.key] && !["no", "none"].includes(w.options[a.key]))) return tx(`第 ${index + 1} 行包含该系列不支持的附加项，请清除后继续。`, `Row ${index + 1} contains an add-on unavailable for this series.`);
  return "";
}

async function submit() {
  error.value = ""; notice.value = "";
  if (!draft.project_name.trim() || (draft.installation_required && !draft.site_address.trim())) { error.value = tx("请填写订单名称；需要安装时请填写施工地址。", "Enter the order name; add the installation address when installation is selected."); return; }
  if (!draft.windows.length) { error.value = tx("请至少添加一扇窗。", "Add at least one window."); return; }
  for (let i=0; i<draft.windows.length; i++) { const issue = checkWindow(draft.windows[i], i); if (issue) { error.value=issue; return; } }
  saving.value = true;
  try {
    const saved = await portalRequest<any>("orders", {
      project_name: draft.project_name.trim(), site_address: draft.installation_required ? draft.site_address.trim() : "",
      installation_required: draft.installation_required, submission_key: crypto.randomUUID(),
      // Each spreadsheet row is one window; the customer template has no repeated-window quantity input.
      lines: draft.windows.map(w => ({ window_name: w.window_name.trim(), product_id: Number(w.product_id), width_mm: w.width_mm, height_mm: w.height_mm, quantity: 1, panel_count: Number(w.panel_count), options: w.options })),
    });
    localStorage.removeItem(draftKey.value);
    router.push(`/portal/orders/${saved.id}`);
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { saving.value = false; }
}

load();
</script>

<template>
  <div class="excel-order">
    <header class="table-heading">
      <div><p class="eyebrow">{{ tx("新增订单", "NEW ORDER") }}</p><h1>{{ tx("订单信息", "Order Details") }}</h1><p>{{ tx("按熟悉的表格方式填写订单；每一行代表一扇窗。", "Enter the order in a familiar spreadsheet layout. Each row is one window.") }}</p></div>
      <div class="heading-actions"><span v-if="lastSaved" class="saved">{{ tx("已保存", "Saved") }} {{ lastSaved }}</span></div>
    </header>
    <div v-if="loading" class="notice">{{ tx("正在加载产品…", "Loading products…") }}</div>
    <template v-else>
      <section class="order-fields">
        <label>{{ tx("订单名称", "Order name") }} *<input v-model="draft.project_name" maxlength="200" :placeholder="tx('例如：Sterling House', 'e.g. Sterling House')" /></label>
        <label v-if="draft.installation_required" class="address-field">{{ tx("施工地址", "Installation address") }} *<input v-model="draft.site_address" maxlength="1000" required /></label>
        <label v-else class="address-field address-optional">{{ tx("施工地址", "Installation address") }} · {{ tx("仅安装时填写", "Only needed for installation") }}<input v-model="draft.site_address" maxlength="1000" :placeholder="tx('无需安装可留空', 'Leave blank for supply-only orders')" /></label>
        <label class="install-check"><input v-model="draft.installation_required" type="checkbox" />{{ tx("需要安装", "Installation required") }}</label>
      </section>
      <div class="sheet-title"><div><h2>{{ tx("窗户明细", "Window Details") }}</h2><p>{{ tx("必填列标有 *。表格可横向滚动。", "Required fields are marked *. Scroll horizontally to see all columns.") }}</p></div><button type="button" class="add-row" @click="addWindow">＋ {{ tx("添加一行", "Add Row") }}</button></div>
      <div class="table-wrap">
        <table>
          <thead><tr><th class="row-num">#</th><th>{{ tx("窗户位置 / 名称", "Window Location / Name") }} *</th><th>{{ tx("宽 (mm)", "Width (mm)") }} *</th><th>{{ tx("高 / Drop (mm)", "Height / Drop (mm)") }} *</th><th>{{ tx("产品系列", "Product Series") }} *</th><th>{{ tx("开合方式", "Opening Style") }}</th><th>{{ tx("扇数", "Panels") }} *</th><th>{{ tx("布局代码", "Layout Code") }}</th><th>{{ tx("竖柱", "VT Post") }}</th><th>{{ tx("横柱", "HT Post") }}</th><th>{{ tx("中横档", "Midrail") }}</th><th>{{ tx("框型", "Frame") }} *</th><th>{{ tx("叶片尺寸", "Louver Size") }} *</th><th>{{ tx("颜色", "Colour") }} *</th><th>{{ tx("控制杆", "Control Rod") }} *</th><th>{{ tx("安装尺寸", "Fitting") }} *</th><th>{{ tx("附加项 / 特殊要求", "Add-ons / Special Request") }}</th><th>{{ tx("操作", "Actions") }}</th><th class="price-col">{{ tx("行金额（含附加项）", "Line total (incl. add-ons)") }}</th></tr></thead>
          <tbody>
            <tr v-for="(w,index) in draft.windows" :key="w.id">
              <td class="row-num">{{ index+1 }}</td>
              <td><input v-model="w.window_name" :placeholder="tx('例如：Bedroom 1', 'e.g. Bedroom 1')" /></td>
              <td><input v-model="w.width_mm" inputmode="decimal" /></td>
              <td><input v-model="w.height_mm" inputmode="decimal" /></td>
              <td><select v-model.number="w.product_id" @change="onSeriesChange(w)"><option value="">{{ tx("选择系列", "Select") }}</option><option v-for="p in shutterProducts" :key="p.id" :value="p.id">{{ productLabel(p) }}</option></select></td>
              <td><select v-if="choicesFor(w,'opening_style').length" v-model="w.options.opening_style" @change="syncOpeningStyle(w.options)"><option v-for="v in choicesFor(w,'opening_style')" :key="v" :value="v">{{ v }}</option></select><input v-else v-model="w.options.opening_style" @change="syncOpeningStyle(w.options)" /></td>
              <td><input v-model.number="w.panel_count" type="text" inputmode="numeric" /></td>
              <td><input v-model="w.options.layout_code" /></td>
              <td><input v-model="w.options.vt_post" /></td>
              <td><input v-model="w.options.ht_post" /></td>
              <td><input v-model="w.options.midrail" /></td>
              <td><select v-if="choicesFor(w,'frame').length" v-model="w.options.frame"><option value="">—</option><option v-for="v in choicesFor(w,'frame')" :key="v" :value="v">{{ v }}</option></select><input v-else v-model="w.options.frame" /></td>
              <td><select v-model="w.options.louver_size"><option value="">—</option><option v-for="v in louverChoices(w)" :key="v" :value="v">{{ v }}</option></select></td>
              <td><select v-model="w.options.colour"><option value="">—</option><option v-for="v in colorChoices(w)" :key="v" :value="v">{{ v }}</option></select></td>
              <td><select v-if="choicesFor(w,'control_rod').length" v-model="w.options.control_rod"><option value="">—</option><option v-for="v in choicesFor(w,'control_rod')" :key="v" :value="v">{{ v }}{{ rodPriceHint(v) }}</option></select><input v-else v-model="w.options.control_rod" /></td>
              <td><select v-model="w.options.fitting"><option value="">—</option><option v-for="v in fittingChoices(w)" :key="v" :value="v">{{ v }}</option></select></td>
              <td class="addons-cell">
                <input class="special-request" v-model="w.options.special_request" :placeholder="tx('特殊要求 / 定制边框备注', 'Special request / custom frame notes')" />
                <button type="button" class="addons-trigger" :title="describeConfiguredAddons(w.options, locale, availableAddons(w)).join(' · ') || undefined" @click="openAddons(w, index)"><SlidersHorizontal :size="14" aria-hidden="true" />{{ addonChips(w).length ? tx(`附加项 · ${addonChips(w).length}`, `Add-ons · ${addonChips(w).length}`) : tx('选择附加项', 'Choose add-ons') }}</button>
                <span v-for="chip in addonChips(w)" :key="chip" class="addon-chip">{{ chip }}</span>
                <span v-if="addonIncrement(w,index)" class="addon-total">{{ tx('附加项', 'Add-ons') }} +{{ addonIncrement(w,index) }}</span>
              </td>
              <td class="row-actions"><button type="button" :title="tx('复制此行','Copy row')" @click="copyWindow(w)"><Copy :size="14" aria-hidden="true" />{{ tx('复制','Copy') }}</button><button type="button" class="row-delete" :title="tx('删除此行','Delete row')" @click="removeWindow(index)"><Trash2 :size="14" aria-hidden="true" />{{ tx('删除','Delete') }}</button></td>
              <td class="price-col">
                <strong v-if="previewLineAmount(quotePreview,w,index)">{{ previewLineAmount(quotePreview,w,index) }}</strong>
                <span v-else-if="!rowReady(w)" class="muted">{{ tx('填写系列和尺寸后显示', 'Add series and size') }}</span>
                <span v-else-if="quoteLoading" class="muted">{{ tx('计算中…', 'Calculating…') }}</span>
                <span v-else class="muted">—</span>
              </td>
            </tr>
          </tbody>
        </table>
        <dialog ref="addonDialog" class="addon-dialog" :aria-label="tx('附加项','Add-ons')" @close="addonTarget = null" @click="onAddonDialogClick">
          <form v-if="addonTarget" method="dialog">
            <header><div><strong>{{ tx("附加项", "Add-ons") }}</strong><span>{{ tx(`第 ${addonTarget.index + 1} 行`, `Row ${addonTarget.index + 1}`) }}<template v-if="addonTarget.window.window_name"> · {{ addonTarget.window.window_name }}</template></span></div></header>
            <label v-for="a in availableAddons(addonTarget.window)" :key="a.key" :class="{ 'priced-addon': addonPriceLabel(a) }">
              <span><strong>{{ locale==='zh'?a.label_zh:a.label_en }}</strong><small v-if="addonPriceLabel(a)">{{ addonPriceLabel(a) }}</small><em v-if="addonLocked(addonTarget.window,a.key)" class="locked-note">{{ tx('由开合方式自动决定', 'Set by the Opening Style') }}</em></span>
              <select v-if="a.key==='extra_installation'" :value="addonTarget.window.options[a.key] || 'none'" @change="setAddon(addonTarget.window,a.key,($event.target as HTMLSelectElement).value)"><option v-for="choice in a.choices" :key="choice.value" :value="choice.value">{{ locale==='zh'?choice.label_zh:choice.label_en }}</option></select>
              <input v-else type="checkbox" :checked="addonSelected(addonTarget.window,a.key)" :disabled="addonLocked(addonTarget.window,a.key)" @change="setAddon(addonTarget.window,a.key,($event.target as HTMLInputElement).checked?'yes':'no')" />
            </label>
            <p v-if="quoteError" class="quote-error" role="status">{{ tx('价格预览暂不可用，提交时服务器仍会校验价格。','Price preview is unavailable. The server will validate pricing at submission.') }}</p>
            <p v-else-if="addonTarget && addonIncrement(addonTarget.window,addonTarget.index)" class="quote-total">{{ tx('已选附加项额外金额','Selected add-ons extra') }}: {{ addonIncrement(addonTarget.window,addonTarget.index) }}</p>
            <footer><button type="submit" class="add-row">{{ tx("完成", "Done") }}</button></footer>
          </form>
        </dialog>
      </div>
      <section class="price-summary" aria-live="polite">
        <div class="summary-status">
          <strong>{{ tx("价格预览", "Price preview") }}</strong>
          <span v-if="quoteLoading">{{ tx("正在更新…", "Updating…") }}</span>
          <span v-else-if="quoteError" class="summary-error">{{ tx("暂时无法计算价格：", "Price could not be calculated: ") }}{{ quoteError }}</span>
          <span v-else-if="!quotePreview">{{ tx("填写系列、宽和高后自动计算。", "Prices appear once a row has a series, width and height.") }}</span>
          <span v-if="pendingRows.length && quotePreview" class="summary-warn">{{ tx(`第 ${pendingRows.join("、")} 行未填完，暂未计入。`, `Row ${pendingRows.join(", ")} not complete yet and not included.`) }}</span>
        </div>
        <dl v-if="quotePreview" :class="{ stale: quoteLoading }">
          <div><dt>{{ tx("产品小计", "Products") }}</dt><dd>{{ money(quotePreview.subtotal) }}</dd></div>
          <div v-if="draft.installation_required"><dt>{{ tx("安装费", "Installation") }}</dt><dd>{{ money(quotePreview.installation) }}</dd></div>
          <div><dt>GST</dt><dd>{{ money(quotePreview.tax) }}</dd></div>
          <div class="summary-total"><dt>{{ tx("订单总价（含 GST）", "Order total (incl. GST)") }}</dt><dd>{{ money(quotePreview.total) }}</dd></div>
          <div><dt>{{ tx("定金", "Deposit") }} {{ Math.round(Number(quotePreview.deposit_rate || 0.6) * 100) }}%</dt><dd>{{ money(quotePreview.deposit) }}</dd></div>
        </dl>
      </section>
      <p class="table-note">{{ tx("这是网页订单输入表格，字段会按所选产品系列显示并校验。价格由系统根据已发布的价格规则计算。", "This is an online order-entry table. Fields are validated for the selected series, and prices are calculated from the published pricing rules.") }}</p>
      <div v-if="error" class="error-box" role="alert">{{ error }}</div>
      <div class="footer-actions"><button type="button" class="switch-button" @click="router.push('/portal/orders')">{{ tx("取消", "Cancel") }}</button><button type="button" class="submit-button" :disabled="saving || loading || !draft.windows.length" @click="submit">{{ saving?tx("提交中…","Submitting…"):tx("提交订单", "Submit Order") }}</button></div>
    </template>
  </div>
</template>

<style scoped>
.excel-order{max-width:100%;color:var(--ink,#1b2421)}.table-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:18px;margin-bottom:22px}.eyebrow{margin:0 0 5px;color:var(--cord);font-size:11px;font-weight:700;letter-spacing:.12em}.table-heading h1{margin:0;font-size:26px}.table-heading p{margin:6px 0;color:#62716b}.heading-actions{display:flex;align-items:center;gap:12px}.saved{font-size:12px;color:#62716b;white-space:nowrap}.switch-button,.add-row,.submit-button{min-height:42px;padding:9px 15px;border-radius:5px;font-weight:650;cursor:pointer}.switch-button{border:1px solid #9aac9f;background:#fff;color:#29493d}.order-fields{display:grid;grid-template-columns:1fr 2fr auto;gap:14px;align-items:end;padding:16px;background:#f3f6f3;border:1px solid #dbe4dd;border-radius:8px;margin-bottom:22px}.order-fields label{display:grid;gap:6px;font-size:12px;font-weight:650}.order-fields input:not([type=checkbox]){width:100%;height:40px;box-sizing:border-box;padding:8px 10px;border:1px solid #ccd7cf;border-radius:4px;font:inherit;font-weight:400;background:white}.install-check{display:flex!important;align-items:center;gap:8px;min-height:40px;white-space:nowrap}.sheet-title{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:10px}.sheet-title h2{margin:0;font-size:18px}.sheet-title p{margin:4px 0;color:#718078;font-size:12px}.add-row,.submit-button{border:0;background:var(--cord,#0f6e5c);color:white}.table-wrap{width:100%;overflow:auto;border:1px solid #d7e0d9;border-radius:7px;background:#fff}.table-wrap table{border-collapse:separate;border-spacing:0;min-width:2060px;width:100%;font-size:12px}.table-wrap th{position:sticky;top:0;z-index:1;background:#edf2ee;color:#2c3f35;text-align:left;white-space:nowrap;font-size:11px}.table-wrap td,.table-wrap th{padding:8px 7px;border-right:1px solid #e4eae5;border-bottom:1px solid #e4eae5;vertical-align:top}.table-wrap td input,.table-wrap td select{width:105px;height:34px;box-sizing:border-box;padding:5px 7px;border:1px solid #d0dad2;border-radius:4px;background:#fff;font:inherit}.table-wrap td:nth-child(2) input{width:150px}.table-wrap td:nth-child(5) select{width:205px}.row-num{position:sticky;left:0;z-index:2;min-width:26px;text-align:center;background:#f5f7f5}.table-wrap td.row-num{z-index:0}.addons-cell{min-width:150px;max-width:220px}.addons-trigger{display:inline-flex;align-items:center;gap:6px;min-height:34px;height:34px;padding:0 10px;border:1px dashed #a9b8ad;border-radius:4px;background:#fff;color:#29493d;font-size:12px;font-weight:600;cursor:pointer;white-space:nowrap}.addons-trigger:hover{border-color:var(--cord,#0f6e5c);background:#f2f7f4}.addon-chip{display:inline-block;margin:5px 4px 0 0;padding:2px 7px;border-radius:999px;background:#e7f0eb;color:#29493d;font-size:11px;line-height:1.5}.addon-dialog{width:min(440px,calc(100vw - 32px));padding:0;border:0;border-radius:8px;box-shadow:0 18px 50px rgba(20,35,30,.25)}.addon-dialog::backdrop{background:rgba(20,30,26,.35)}.addon-dialog form{padding:20px 22px}.addon-dialog header{margin-bottom:14px}.addon-dialog header strong{display:block;font-size:17px}.addon-dialog header span{font-size:12px;color:#62716b}.addon-dialog label{display:grid;grid-template-columns:1fr 170px;gap:12px;align-items:center;padding:4px 0;border-bottom:1px solid #edf1ee;font-size:13px}.addon-dialog select{min-height:0;height:34px;padding:5px 7px;border:1px solid #d0dad2;border-radius:4px;background:#fff;font:inherit}.addon-dialog footer{display:flex;justify-content:flex-end;margin-top:16px}.row-actions{white-space:nowrap}.row-actions button{display:inline-flex;align-items:center;gap:5px;min-height:30px;height:30px;padding:0 9px;margin-right:4px;border:1px solid #c5d0c8;border-radius:4px;background:#fff;color:#29493d;cursor:pointer;font-size:12px;font-weight:600}.row-actions button:hover{border-color:var(--cord,#0f6e5c);background:#f2f7f4}.row-actions .row-delete{color:#9b3a32}.row-actions .row-delete:hover{border-color:#c4655c;background:#fbf1ef}.table-note{font-size:12px;color:#65736c;margin:9px 0 22px}.error-box{padding:12px 14px;margin:14px 0;background:#fff0ed;color:#8f3425;border-radius:6px}.footer-actions{display:flex;justify-content:space-between;padding-top:16px;border-top:1px solid #dce4dd}.submit-button:disabled{opacity:.55;cursor:not-allowed}.notice{padding:18px;color:#65736c}
@media(max-width:760px){.table-heading{display:block}.heading-actions{justify-content:space-between;margin-top:12px}.order-fields{grid-template-columns:1fr}.install-check{min-height:28px}.sheet-title{align-items:flex-start}.table-wrap table{min-width:1980px}}
.address-optional{color:#64746b;font-weight:500!important}.addons-cell{min-width:230px}.addons-cell .special-request{width:205px!important;margin:0 0 5px}.addon-total,.line-price{display:block;margin-top:4px;color:#17523a;font-size:11px;font-weight:650}.line-price.muted{color:#68776f;font-weight:400}.addon-dialog label{grid-template-columns:minmax(0,1fr) auto;min-height:46px}.addon-dialog label span{display:grid;gap:2px}.addon-dialog label small{color:#8a4d14;font-size:11px;font-weight:600}.addon-dialog input[type=checkbox]{width:20px;height:20px;accent-color:var(--cord,#0f6e5c)}.addon-dialog .priced-addon{background:#fffaf1}.locked-note{color:#5d6d64;font-size:11px;font-style:normal}
.table-wrap th.price-col,.table-wrap td.price-col{position:sticky;right:0;z-index:1;min-width:130px;background:#f7faf8;border-left:1px solid #d7e0d9;white-space:nowrap}.table-wrap th.price-col{z-index:2;background:#edf2ee}.table-wrap td.price-col strong{color:#17523a;font-size:13px}.table-wrap td.price-col .muted{color:#7a8880;font-size:11px;white-space:normal}
.price-summary{position:sticky;bottom:0;z-index:3;display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:10px 24px;margin-top:12px;padding:12px 16px;background:#f3f8f4;border:1px solid #cfe0d4;border-radius:8px;box-shadow:0 -4px 14px rgba(20,35,30,.06)}.summary-status{display:grid;gap:3px;font-size:12px;color:#5d6d64}.summary-status strong{color:#1b2421;font-size:14px}.summary-error{color:#8f3425}.summary-warn{color:#8a4d14}.price-summary dl{display:flex;flex-wrap:wrap;gap:6px 22px;margin:0;transition:opacity .2s}.price-summary dl.stale{opacity:.55}.price-summary dl div{display:grid;gap:1px}.price-summary dt{font-size:11px;color:#62716b}.price-summary dd{margin:0;font-size:14px;font-weight:650;white-space:nowrap}.price-summary .summary-total dd{font-size:18px;color:#0f6e5c}
@media(max-width:760px){.price-summary{position:static}.price-summary dl{gap:6px 16px}}
.quote-total{padding:9px 11px;border-radius:5px;background:#edf5ef;color:#17523a;font-weight:650}.quote-error{font-size:12px;color:#8f3425}
</style>

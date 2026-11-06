<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { request } from '../crm-api';

const emit = defineEmits<{ created: [] }>();
const { locale } = useI18n();
const tx = (zh: string, en: string) => locale.value === 'zh' ? zh : en;
type Customer = { customer_id: number; company: string; customer_code?: string; contact_name?: string; email?: string };
type Product = { id: number; source_code: string; name_en?: string; name_zh?: string; material?: string; orderable?: boolean };
type EntryLine = { window_name: string; product_id: number | ''; width_mm: string; height_mm: string; quantity: number; panel_count: number; options: string };
type OrderDraft = { ref: string; customer_id: number | ''; project_name: string; site_address: string; installation_required: boolean; lines: EntryLine[]; submit: boolean };
type Preview = { customer_id: number; project_name: string; subtotal: string; installation?: string; tax: string; total: string; deposit: string; currency?: string; line_count: number };
const customers = ref<Customer[]>([]);
const products = ref<Product[]>([]);
const mode = ref<'single'|'bulk'>('single');
const busy = ref(false);
const error = ref('');
const notice = ref('');
const pasted = ref('');
const previews = ref<Preview[]>([]);
const readyOrders = ref<OrderDraft[]>([]);
const preparedPayloads = ref<any[]>([]);
const draft = reactive<OrderDraft>({ ref: 'single', customer_id: '', project_name: '', site_address: '', installation_required: false, lines: [], submit: false });
const bulkHeaders = ['Order Ref','Customer Code','Project Name','Site Address','Installation Required','Window Name','Series','Width (mm)','Height (mm)','Quantity','Panels','Options JSON'];
const headerText = computed(() => bulkHeaders.join('\t'));
watch(draft, () => clearPreview(), { deep: true });
const productLabel = (p: Product) => `${p.name_en || p.source_code}${p.material ? ` · ${p.material}` : ''}`;
const customerLabel = (c: Customer) => `${c.customer_code ? `${c.customer_code} · ` : ''}${c.company}${c.contact_name ? ` · ${c.contact_name}` : ''}`;
function newLine(): EntryLine { return { window_name: '', product_id: products.value.find(p => p.orderable)?.id || '', width_mm: '', height_mm: '', quantity: 1, panel_count: 1, options: '{}' }; }
function addLine() { draft.lines.push(newLine()); }
async function copyHeader() { await navigator.clipboard?.writeText(headerText.value); }
function clearPreview() { previews.value = []; readyOrders.value = []; preparedPayloads.value = []; error.value = ''; notice.value = ''; }
function linePayload(line: EntryLine) {
  let options: Record<string,string>;
  try { const parsed = JSON.parse(line.options || '{}'); if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error(); options = parsed; }
  catch { throw new Error(tx(`“${line.window_name || tx('未命名窗位','Unnamed window')}”的 Options JSON 格式无效。`, `Invalid Options JSON for “${line.window_name || 'unnamed window'}”.`)); }
  return { window_name: line.window_name.trim(), product_id: Number(line.product_id), width_mm: Number(line.width_mm), height_mm: Number(line.height_mm), quantity: Number(line.quantity), panel_count: Number(line.panel_count), options };
}
function orderPayload(order: OrderDraft) {
  if (!order.customer_id) throw new Error(tx('请选择客户。','Select a customer.'));
  if (!order.project_name.trim()) throw new Error(tx('请填写项目名称。','Enter a project name.'));
  if (!order.lines.length) throw new Error(tx('订单至少需要一行产品。','Each order needs at least one product line.'));
  const lines = order.lines.map(linePayload);
  if (lines.some(line => !line.window_name || !line.product_id || !(line.width_mm > 0) || !(line.height_mm > 0) || !(line.quantity > 0) || !(line.panel_count > 0))) throw new Error(tx('请完整填写每行的窗位、系列、尺寸、数量和扇数。','Complete the window, series, dimensions, quantity and panel count on every line.'));
  return { customer_id: Number(order.customer_id), project_name: order.project_name.trim(), site_address: order.site_address.trim(), installation_required: order.installation_required, lines, submit: order.submit, submission_key: crypto.randomUUID() };
}
function parseBulk(): OrderDraft[] {
  const rows = pasted.value.trim().split(/\r?\n/).filter(Boolean).map(row => row.split('\t'));
  if (rows.length < 2) throw new Error(tx('请先复制表头和至少一行订单数据。','Paste the header and at least one order row.'));
  const headers = rows[0].map(h => h.trim().toLowerCase());
  const required = bulkHeaders.map(h => h.toLowerCase());
  if (required.some(h => !headers.includes(h))) throw new Error(tx(`表头不匹配。请使用页面提供的模板列。缺少：${required.filter(h => !headers.includes(h)).join('、')}`, `The header does not match the template. Missing: ${required.filter(h => !headers.includes(h)).join(', ')}`));
  const ix = Object.fromEntries(required.map(h => [h, headers.indexOf(h)])) as Record<string,number>;
  const groups = new Map<string, OrderDraft>();
  const customerByCode = new Map(customers.value.flatMap(c => c.customer_code ? [[c.customer_code.toLowerCase(),c] as const] : []));
  const productByCode = new Map(products.value.map(p => [p.source_code.toLowerCase(),p] as const));
  const productByName = new Map(products.value.flatMap(p => [[(p.name_en || '').toLowerCase(),p] as const,[(p.name_zh || '').toLowerCase(),p] as const]));
  rows.slice(1).forEach((cells, index) => {
    const cell = (name: string) => (cells[ix[name]] || '').trim();
    const rowNo = index + 2;
    const ref = cell('order ref'); const code = cell('customer code'); const series = cell('series');
    if (!ref || !code || !cell('project name') || !cell('window name') || !series) throw new Error(tx(`第 ${rowNo} 行缺少订单编号、客户代码、项目名、窗位名称或系列。`,`Row ${rowNo} is missing order ref, customer code, project, window name or series.`));
    const customer = customerByCode.get(code.toLowerCase());
    if (!customer) throw new Error(tx(`第 ${rowNo} 行客户代码“${code}”未匹配到系统客户。`,`Row ${rowNo}: customer code “${code}” was not found.`));
    const product = productByCode.get(series.toLowerCase()) || productByName.get(series.toLowerCase());
    if (!product?.orderable) throw new Error(tx(`第 ${rowNo} 行系列“${series}”没有可用的已确认价格。`,`Row ${rowNo}: series “${series}” has no confirmed order price.`));
    const key = ref.toLowerCase();
    let order = groups.get(key);
    const project = cell('project name'); const address = cell('site address'); const install = ['yes','true','1','是'].includes(cell('installation required').toLowerCase());
    if (!order) { order = { ref, customer_id: customer.customer_id, project_name: project, site_address: address, installation_required: install, lines: [], submit: false }; groups.set(key,order); }
    if (order.customer_id !== customer.customer_id || order.project_name !== project || order.site_address !== address || order.installation_required !== install) throw new Error(tx(`第 ${rowNo} 行与订单编号“${ref}”已有行的客户或项目信息不一致。`,`Row ${rowNo} has different customer or project details from the other rows for order “${ref}”.`));
    let options: unknown;
    try { options = JSON.parse(cell('options json') || '{}'); } catch { throw new Error(tx(`第 ${rowNo} 行 Options JSON 无效。`,`Row ${rowNo} has invalid Options JSON.`)); }
    order.lines.push({ window_name: cell('window name'), product_id: product.id, width_mm: cell('width (mm)'), height_mm: cell('height (mm)'), quantity: Number(cell('quantity') || 1), panel_count: Number(cell('panels') || 1), options: JSON.stringify(options) });
  });
  return [...groups.values()].map(order => ({ ...order, submit: false }));
}
async function preview() {
  clearPreview(); busy.value = true;
  try {
    const orders = mode.value === 'single' ? [orderPayload(draft)] : parseBulk().map(orderPayload);
    const result = await request<Preview[]>('operations/orders/staff/preview',{ orders });
    readyOrders.value = mode.value === 'single' ? [draft] : parseBulk();
    preparedPayloads.value = orders;
    previews.value = result;
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { busy.value = false; }
}
async function createOrders() {
  if (!previews.value.length || readyOrders.value.length !== previews.value.length) return;
  busy.value = true; error.value = ''; notice.value = '';
  try {
    const orders = preparedPayloads.value.map((order,index) => ({ ...order, submit: readyOrders.value[index].submit }));
    const created = await request<any[]>('operations/orders/staff',{ orders });
    notice.value = tx(`已创建 ${created.length} 个订单。`,`Created ${created.length} order(s).`);
    clearPreview(); pasted.value = '';
    draft.project_name = ''; draft.site_address = ''; draft.customer_id = ''; draft.lines = [newLine()];
    emit('created');
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { busy.value = false; }
}
onMounted(async () => {
  busy.value = true;
  try {
    const [customerRows,catalog] = await Promise.all([request<Customer[]>('operations/customers'),request<{products:Product[]}>('operations/order-catalog')]);
    customers.value = customerRows; products.value = catalog.products;
    draft.lines.push(newLine());
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { busy.value = false; }
});
</script>

<template>
  <section class="staff-order-entry card">
    <header class="entry-heading"><div><h2>{{ tx('新增订单','New order') }}</h2><p>{{ tx('选择客户，按客户订单的相同价格规则录入产品；金额由系统计算。','Choose a customer and enter products using the customer order pricing rules. Prices are calculated by the system.') }}</p></div><div class="entry-modes"><button type="button" :aria-pressed="mode==='single'" @click="mode='single';clearPreview()">{{ tx('单个订单','Single order') }}</button><button type="button" :aria-pressed="mode==='bulk'" @click="mode='bulk';clearPreview()">{{ tx('粘贴 Excel','Paste from Excel') }}</button></div></header>
    <p v-if="error" class="entry-alert" role="alert">{{ error }}</p><p v-if="notice" class="entry-success" role="status">{{ notice }}</p>
    <template v-if="mode==='single'">
      <div class="entry-fields"><label>{{ tx('客户','Customer') }}<select v-model.number="draft.customer_id"><option value="">{{ tx('选择客户','Select customer') }}</option><option v-for="c in customers" :key="c.customer_id" :value="c.customer_id">{{ customerLabel(c) }}</option></select></label><label>{{ tx('项目 / 订单名称','Project / order name') }}<input v-model="draft.project_name" /></label><label>{{ tx('安装地址（如需安装）','Installation address (if needed)') }}<input v-model="draft.site_address" /></label><label class="entry-check"><input v-model="draft.installation_required" type="checkbox" />{{ tx('需要安装','Installation required') }}</label></div>
      <div class="entry-lines"><table><thead><tr><th>{{ tx('窗位','Window') }}</th><th>{{ tx('系列','Series') }}</th><th>{{ tx('宽 mm','Width mm') }}</th><th>{{ tx('高 mm','Height mm') }}</th><th>{{ tx('数量','Qty') }}</th><th>{{ tx('扇数','Panels') }}</th><th>{{ tx('配置选项 JSON','Options JSON') }}</th><th></th></tr></thead><tbody><tr v-for="(line,i) in draft.lines" :key="i"><td><input v-model="line.window_name" /></td><td><select v-model.number="line.product_id"><option value="">—</option><option v-for="p in products.filter(p=>p.orderable)" :key="p.id" :value="p.id">{{ productLabel(p) }}</option></select></td><td><input v-model="line.width_mm" type="number" min="1" /></td><td><input v-model="line.height_mm" type="number" min="1" /></td><td><input v-model.number="line.quantity" type="number" min="1" /></td><td><input v-model.number="line.panel_count" type="number" min="1" /></td><td><input v-model="line.options" placeholder="{}" /></td><td><button class="entry-remove" type="button" :disabled="draft.lines.length<2" @click="draft.lines.splice(i,1);clearPreview()">×</button></td></tr></tbody></table></div>
      <button type="button" class="entry-secondary" @click="addLine();clearPreview()">＋ {{ tx('添加产品行','Add product line') }}</button>
      <label class="entry-submit"><input v-model="draft.submit" type="checkbox" />{{ tx('创建后提交审核（不勾选则保存为草稿）','Submit for review after creation (otherwise save as draft)') }}</label>
    </template>
    <template v-else>
      <div class="entry-template"><strong>{{ tx('固定列顺序（第一行为表头）','Required column order (first row is the header)') }}</strong><code>{{ headerText }}</code><button class="entry-secondary" type="button" @click="copyHeader">{{ tx('复制表头','Copy header') }}</button><p>{{ tx('每个订单可占多行产品；Order Ref 相同的行会合并为一个订单。Customer Code 使用系统客户代码。Options JSON 可留空 {}。不需要粘贴价格。','Use multiple product rows per order. Rows with the same Order Ref become one order. Customer Code must match the system. Options JSON can be {}. Do not include prices.') }}</p></div>
      <textarea v-model="pasted" class="entry-paste" spellcheck="false" :placeholder="headerText" @input="clearPreview()"></textarea>
    </template>
    <div class="entry-actions"><button type="button" :disabled="busy || !customers.length || !products.length" @click="preview">{{ busy ? tx('处理中…','Working…') : tx('预览匹配与系统价格','Preview matches and system prices') }}</button><button v-if="previews.length" type="button" :disabled="busy" @click="createOrders">{{ tx(`确认创建 ${previews.length} 个订单`,`Create ${previews.length} order(s)`) }}</button></div>
    <div v-if="previews.length" class="entry-preview"><h3>{{ tx('创建预览','Creation preview') }}</h3><div v-for="(preview,i) in previews" :key="`${preview.customer_id}-${preview.project_name}-${i}`" class="entry-preview-row"><strong>{{ preview.project_name }}</strong><span>{{ customers.find(c=>c.customer_id===preview.customer_id)?.company }} · {{ preview.line_count }} {{ tx('行','lines') }}</span><span>{{ preview.currency || 'NZD' }} {{ preview.total }} <small>({{ tx('定金','deposit') }} {{ preview.deposit }})</small></span></div></div>
  </section>
</template>

<style scoped>
.staff-order-entry{max-width:none;padding:16px;display:grid;gap:12px}.entry-heading{display:flex;justify-content:space-between;align-items:center;gap:12px}.entry-heading h2{font-size:18px;margin:0}.entry-heading p{margin:3px 0;color:#52635a}.entry-modes,.entry-actions{display:flex;gap:8px;flex-wrap:wrap}.entry-modes button,.entry-secondary{background:#fff;color:#315844;border:1px solid #dce5df}.entry-modes button[aria-pressed=true]{background:#203d35;color:#fff}.entry-fields{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;align-items:end}.entry-fields label{margin:0}.entry-fields .entry-check{display:flex;align-items:center;gap:8px;min-height:40px}.entry-fields .entry-check input,.entry-submit input{width:16px;height:16px;min-height:16px;margin:0}.entry-lines{max-width:100%;overflow:auto}.entry-lines table{min-width:980px;border-collapse:collapse}.entry-lines th,.entry-lines td{padding:6px;border-bottom:1px solid #e4eae5;text-align:left}.entry-lines input,.entry-lines select{min-width:75px;min-height:36px;margin:0;padding:5px}.entry-lines td:first-child input{min-width:130px}.entry-lines td:nth-child(7) input{min-width:160px}.entry-remove{min-width:32px!important;min-height:32px!important;padding:0 8px;background:#fff;color:#8a3b2c;border:1px solid #ead6d1}.entry-submit{display:flex;align-items:center;gap:8px;margin:0!important}.entry-template{display:grid;gap:6px}.entry-template code{display:block;overflow:auto;padding:8px;background:#f5f8f5;border:1px solid #dce5df;border-radius:5px;white-space:nowrap}.entry-template p{margin:0;color:#52635a}.entry-paste{width:100%;min-height:220px;resize:vertical;font:12px/1.5 ui-monospace,Consolas,monospace;padding:10px;border:1px solid #cdd9d1;border-radius:6px}.entry-actions{justify-content:flex-end}.entry-preview{border-top:1px solid #dce5df;padding-top:8px}.entry-preview h3{margin:0 0 6px}.entry-preview-row{display:grid;grid-template-columns:minmax(160px,1fr) minmax(140px,1fr) auto;gap:12px;padding:6px 0;border-bottom:1px solid #edf1ee}.entry-preview-row small{color:#52635a}.entry-alert,.entry-success{padding:8px 10px;border-radius:5px;margin:0}.entry-alert{background:#fae8e1;color:#842b16}.entry-success{background:#e5efdd;color:#17523a}
@media(max-width:850px){.entry-fields{grid-template-columns:repeat(2,minmax(0,1fr))}.entry-preview-row{grid-template-columns:1fr}}
@media(max-width:560px){.entry-heading{align-items:flex-start;flex-direction:column}.entry-fields{grid-template-columns:1fr}.staff-order-entry{padding:12px}}
</style>

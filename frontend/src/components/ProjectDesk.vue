<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import { request, session } from "../crm-api";

interface Line {
  rule_version?: string;
  id: string;
  window_name: string;
  product_id?: number;
  width_mm?: string | number;
  height_mm?: string | number;
  options?: Record<string, string>;
  quantity: number;
  arrived: number;
  delivered: number;
  amount?: string | null;
  discount?: string | number;
  product_surcharge?: string | number;
  installation_surcharge?: string | number;
}
interface Invoice {
  id: string;
  customer_id: number;
  kind: string;
  amount: string;
  currency: string;
  status: string;
  payment_status?: string;
  order_ids?: string[];
}
interface Notice {
  customer_id: number;
  id: string;
  status: string;
  recipient: string;
  subject: string;
}
interface Rebate {
  source_order_ids?: string[];
  allocations?: {invoice_id?:string;amount?:string}[];
  id: string;
  customer_id: number;
  month: string;
  amount: string;
  currency: string;
  used?: string;
  remaining?: string;
  evidence?: string;
}
interface Provider {
  orders?: {id:string;order_number?:string;project_name:string;template_id?:number}[];
  id: number;
  name: string;
  contact_email: string;
  notes: string;
  active: number;
}
interface ProviderTemplate {
  revision?: number;
  supersedes_id?: number;
  id: number;
  provider_id: number;
  name: string;
  sheet_name: string;
  column_mappings: string;
  active: number;
}
interface OrderProvider {
  provider_id: number;
  provider_name: string;
  provider_active: number;
  template_id?: number;
  template_name?: string;
  sheet_name?: string;
}
interface ProjectOrder {
  history?: {action:string;created_at:string;provider_id?:number;template_id?:number;template_revision?:number}[];
  order_number?: string;
  id: string;
  customer_id: number;
  company: string;
  project_name: string;
  site_address: string;
  status: string;
  payment_status: string;
  arrival_status?: string;
  delivery_status?: string;
  total: string | null;
  currency?: string;
  supplier_reference?: string;
  lines: Line[];
  invoices?: Invoice[];
}

const props = withDefaults(defineProps<{ admin: boolean; workspace?: string; emailEnabled?: boolean; emailMode?: string }>(), { workspace: 'projects',emailEnabled:false,emailMode:'demo' });
const route = useRoute();
const templateStatus = ref("");
interface PricingVersion {id:string;version:string;active:boolean;source?:string;imported_at?:string;products:string[];provider_ids:number[];applicability_confirmed:boolean;orders:{id:string;order_number?:string;project_name:string}[]}
const pricingVersions = ref<PricingVersion[]>([]);
const applicability = reactive<Record<string,number[]>>({});
const financeCustomer = ref(String(route.query.customer || ''));
const financePane = ref<'balance'|'rebates'|'notifications'>('balance');
const customers = ref<{customer_id:number;company:string}[]>([]);
const financeOrders = computed(()=>orders.value.filter(o=>!financeCustomer.value || String(o.customer_id)===financeCustomer.value));
const financeInvoices = computed(()=>invoices.value.filter(i=>!financeCustomer.value || String(i.customer_id)===financeCustomer.value));
const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);
const orders = ref<ProjectOrder[]>([]);
const invoices = ref<Invoice[]>([]);
const notices = ref<Notice[]>([]);
const rebates = ref<Rebate[]>([]);
const providers = ref<Provider[]>([]);
const providerTemplates = ref<ProviderTemplate[]>([]);
const rebateStatus = ref("");
const settlementEvidence = ref("");
const rebateForm = reactive({ month: "", amount: "", evidence: "" });
const receiptNote = reactive<Record<string, string>>({});
const adjustNote = reactive<Record<string, string>>({});
const busy = ref(false);
const loaded = ref(false);
const error = ref("");
const notice = ref("");
const statusFilter = ref("");
const picked = ref<string[]>([]);
const invoicePick = ref<string[]>([]);
const transitRows = ref<{ order_id: string; status: string; reason?: string }[]>([]);
const arrivalRows = ref<{ order_id: string; status: string; detail: string }[]>([]);
const batch = reactive<Record<string, number>>({});
const operationKeys = new Map<string, string>();
const supplierRef = reactive<Record<string, string>>({});
const providerForm = reactive({
  name: "",
  contact_email: "",
  notes: "",
});
const templateForm = reactive({
  supersedes_id: null as number|null,
  provider_id: 0,
  name: "",
  sheet_name: "",
  column_mappings: {} as Record<string, string>,
});
const mappingField = ref("");
const mappingColumn = ref("");
const orderProviderForm = reactive<Record<string, { provider_id: number; template_id: number }>>({});
function defaultTemplateId(providerId:number):number {
  return [...providerTemplates.value].filter(t=>t.provider_id===providerId && t.active)
    .sort((a,b)=>(b.revision||1)-(a.revision||1)||b.id-a.id)[0]?.id || 0;
}
function chooseProvider(orderId:string, providerId:number) {
  orderProviderForm[orderId]={provider_id:providerId,template_id:defaultTemplateId(providerId)};
}
function readySupplierExport(orderId:string) {
  const form=orderProviderForm[orderId];
  return !!form && providers.value.some(p=>p.id===form.provider_id && p.active) &&
    providerTemplates.value.some(t=>t.id===form.template_id && t.provider_id===form.provider_id && t.active);
}
const activeSection = computed(() => (({pricing:'pricing',providers:'providers',finance:'settlement'} as Record<string,string>)[props.workspace] || 'operations'));
const validFields = ["order_number", "order_id", "project_name", "company", "contact_name", "company_address", "site_address", "phone", "email", "window_name", "product_id", "width_mm", "height_mm", "quantity", "panel_count", "options", "arrived", "delivered"];

const visibleOrders = computed(() => orders.value.filter((order) => !statusFilter.value || order.status === statusFilter.value || order.payment_status === statusFilter.value));
const listPage = ref(0);
const mobileListOpen = ref(false);
const pageCount = computed(() => Math.max(1, Math.ceil(visibleOrders.value.length / 5)));
const pageOrders = computed(() => visibleOrders.value.slice(Math.min(listPage.value, pageCount.value - 1) * 5, (Math.min(listPage.value, pageCount.value - 1) + 1) * 5));
const selectedId = ref(String(route.query.order || ''));
const detailSection = ref("fulfilment");
const selectedOrder = computed(() => visibleOrders.value.find((order) => order.id === selectedId.value) || visibleOrders.value[0] || null);
watch(()=>selectedOrder.value?.id,()=>{if(props.workspace==='projects') invoicePick.value=[]});
watch(()=>selectedOrder.value?.invoices?.map(i=>`${i.id}:${i.status}`).join('|'),()=>{
  if(props.workspace!=='projects') return;
  const drafts=selectedOrder.value?.invoices?.filter(i=>i.status==='draft') || [];
  invoicePick.value=drafts.length===1?[drafts[0].id]:[];
},{immediate:true});
function nextOrderSection(order: ProjectOrder): string {
  if (order.status === 'pending_review') return 'adjustment';
  if (order.payment_status === 'deposit_unpaid') return 'invoices';
  if (order.status === 'accepted') return 'supplier';
  return 'fulfilment';
}
const nextOrderHint = computed(() => {
  const order=selectedOrder.value;
  if (!order) return '';
  if (order.status==='pending_review') return tx('核对价格和配置，再确认接收。','Check price and configuration, then accept review.');
  if (order.payment_status==='deposit_unpaid') return tx('定金发票已生成；核实到账后记录定金已收。','The deposit invoice is ready; record receipt only after funds are confirmed.');
  if (order.status==='accepted') return tx('确认供应商并导出订单文件，再记录供应商参考号。','Confirm the supplier and export the order file, then record its reference.');
  if (order.status==='supplier_ordered') return tx('供应商下单已记录；可将订单标为在途。','Supplier order recorded; mark it in transit when dispatched.');
  if (order.status==='in_transit'||order.status==='partially_arrived') return tx('按本批实际数量记录到货。','Record the actual quantities received in this batch.');
  if (order.status==='arrived'||order.status==='partially_delivered') return tx('按本批实际数量记录交付。','Record the actual quantities delivered in this batch.');
  return tx('订单已交付；在账款与返利中处理尾款。','Order delivered; complete the balance in Accounts & rebates.');
});
watch(()=>[selectedOrder.value?.id,selectedOrder.value?.status,selectedOrder.value?.payment_status],()=>{
  if(selectedOrder.value) detailSection.value=nextOrderSection(selectedOrder.value);
},{immediate:true});
const editingProvider = ref<Provider | null>(null);
const editProviderForm = reactive({
  name: "",
  contact_email: "",
  notes: "",
  active: true,
});

onMounted(() => {
  void load().catch(cause=>{error.value=cause instanceof Error?cause.message:String(cause)}).finally(()=>{loaded.value=true});
});

function stableKey(signature: string) {
  const existing = operationKeys.get(signature);
  if (existing) return existing;
  const created = crypto.randomUUID();
  operationKeys.set(signature, created);
  return created;
}

async function load() {
  const [listed, billed, mailed, credits, providerList, templateList, versions, companies] = await Promise.all([
    request<ProjectOrder[]>("operations/orders"),
    request<Invoice[]>("operations/invoices"),
    request<Notice[]>("operations/notifications"),
    request<{ calculation_status: string; credits: Rebate[] }>("operations/rebates"),
    request<Provider[]>("operations/providers"),
    request<ProviderTemplate[]>("operations/provider-templates"),
    request<PricingVersion[]>("operations/pricing-templates"),
    request<{customer_id:number;company:string}[]>("operations/customers"),
  ]);
  orders.value = listed;
  invoices.value = billed;
  notices.value = mailed;
  rebates.value = credits.credits;
  providers.value = providerList;
  providerTemplates.value = templateList;
  pricingVersions.value = versions;
  customers.value = companies;
  if(props.workspace==='finance' && financeCustomer.value && !picked.value.length) {
    const eligible=listed.filter(order=>String(order.customer_id)===financeCustomer.value &&
      order.status==='delivered' && order.payment_status==='deposit_received' &&
      !billed.some(invoice=>invoice.kind==='balance' && invoice.order_ids?.includes(order.id)));
    if(eligible.length===1) picked.value=[eligible[0].id];
  }
  for(const v of versions) applicability[v.id]=[...v.provider_ids];
  await refreshTemplate();
  rebateStatus.value = credits.calculation_status;
  const assignmentRequests:Promise<void>[]=[];
  for (const order of props.workspace === 'projects' ? orders.value : []) {
    supplierRef[order.id] = order.supplier_reference || supplierRef[order.id] || "";
    if (!orderProviderForm[order.id]) {
      orderProviderForm[order.id] = { provider_id: 0, template_id: 0 };
      assignmentRequests.push(loadOrderProviders(order.id));
    }
    for (const line of order.lines) {
      batch[`${order.id}:${line.id}:discount`] = Number(line.discount ?? 0);
      batch[`${order.id}:${line.id}:product_surcharge`] = Number(line.product_surcharge ?? 0);
      batch[`${order.id}:${line.id}:installation_surcharge`] = Number(line.installation_surcharge ?? 0);
    }
  }
  await Promise.all(assignmentRequests);
}

function orderLabel(id:string) { return orders.value.find(o=>o.id===id)?.order_number || id.slice(-12); }

function orderStatus(value: string) {
  const labels: Record<string, [string, string]> = {
    pending_review: ["待审核", "Review pending"], accepted: ["已接收", "Accepted"],
    deposit_unpaid: ["待收定金", "Deposit unpaid"], deposit_received: ["定金已收", "Deposit received"],
    supplier_ordered: ["已向供应商下单", "Supplier ordered"], in_transit: ["运输中", "In transit"],
    partially_arrived: ["部分到货", "Partly arrived"], arrived: ["已到货", "Arrived"],
    partially_delivered: ["部分交付", "Partly delivered"], delivered: ["已交付", "Delivered"], paid: ["已结清", "Paid"],
  };
  return labels[value] ? tx(...labels[value]) : value;
}

function mailStatus(status: string) {
  const labels: Record<string, [string, string]> = {
    demo_suppressed: ['演示记录 · 未发送', 'Demo recorded · not sent'],
    demo_sent: ['演示邮件已发给自己', 'Demo email sent to owner'],
    draft: ['草稿', 'Draft'],
    pending: ["待发送", "Pending"],
    sending: ["发送中，需核对邮箱", "Sending; check the mailbox"],
    sent: ["已发出", "Sent"],
    not_configured: ["邮箱未配置", "Mail is not configured"],
    delivery_unknown: ["投递未知，不能当成已送达", "Delivery unknown; not treated as sent"],
  };
  return labels[status] ? tx(...labels[status]) : status;
}

async function act(fn: () => Promise<void>) {
  busy.value = true;
  error.value = "";
  notice.value = "";
  try {
    await fn();
    await load();
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    busy.value = false;
  }
}

function review(id: string) {
  return act(async () => {
    await request(`operations/orders/${id}/review`, {});
    notice.value = tx("已确认接收。定金发票是草稿，发送是另一步。价格未配置时会拒绝。", "Accepted. The deposit invoice is a draft; sending it is a separate step. This is refused when price rules are missing.");
  });
}

function deposit(id: string) {
  return act(async () => {
    await request(`operations/orders/${id}/deposit-received`, {});
    notice.value = tx("已记录定金已收。这一步不发货、不开尾款。", "Deposit received is recorded. This does not ship goods or issue the balance invoice.");
  });
}

function supplier(order: ProjectOrder) {
  return act(async () => {
    await request(`operations/orders/${order.id}/supplier-order`, { reference: supplierRef[order.id] });
    notice.value = tx("已记录供应商参考号。正式工厂格式仍会拒绝，直到模板确认。生产资料草稿可以下载。", "Supplier reference recorded. The formal factory file is still refused until its template is confirmed. Production drafts can be downloaded.");
  });
}

async function exportBlocked(id: string) {
  await act(async () => {
    await request(`operations/orders/${id}/supplier-export`);
  });
}

function toggleOrder(id: string) {
  picked.value = picked.value.includes(id) ? picked.value.filter((item) => item !== id) : [...picked.value, id];
}

function transitSelected() {
  const ids = [...picked.value].sort();
  if (!ids.length) {
    error.value = tx("先勾选要标为在途的订单。", "Select the orders to mark in transit.");
    return;
  }
  const signature = `transit:${ids.join(",")}`;
  const operationKey = stableKey(signature);
  return act(async () => {
    const result = await request<{ results: { order_id: string; status: string; reason?: string }[] }>("operations/transit", {
      order_ids: ids,
      operation_key: operationKey,
    });
    operationKeys.delete(signature);
    transitRows.value = result.results;
    notice.value = result.results.map((row) => `${orderLabel(row.order_id)}: ${row.status}${row.reason ? ` (${row.reason})` : ""}`).join("; ");
  });
}

function transitOne(id:string) {
  const signature=`transit:${id}`;
  const operationKey=stableKey(signature);
  return act(async()=>{
    const result=await request<{results:{order_id:string;status:string;reason?:string}[]}>('operations/transit',
      {order_ids:[id],operation_key:operationKey});
    operationKeys.delete(signature);
    const row=result.results[0];
    notice.value=row ? `${orderLabel(id)}: ${row.status}${row.reason?` (${row.reason})`:''}` : tx('状态未更新','Status was not updated');
  });
}

function batchLines(order: ProjectOrder, kind: "arrival" | "delivery") {
  return order.lines
    .map((line) => ({ line_id: line.id, quantity: Number(batch[`${order.id}:${line.id}:${kind}`] || 0) }))
    .filter((line) => line.quantity > 0);
}

function fillRemaining(order:ProjectOrder,kind:'arrival'|'delivery') {
  for(const line of order.lines) batch[`${order.id}:${line.id}:${kind}`]=
    kind==='arrival' ? Math.max(0,line.quantity-line.arrived) : Math.max(0,line.arrived-line.delivered);
}

function optionText(line: Line) {
  return Object.entries(line.options || {}).map(([name, value]) => `${name}: ${value}`).join(", ");
}

async function arriveSelected() {
  const targets = orders.value.filter((order) => picked.value.includes(order.id));
  if (!targets.length) {
    error.value = tx("先勾选要记录到货的订单。", "Select the orders whose arrival to record.");
    return;
  }
  busy.value = true;
  error.value = "";
  notice.value = "";
  arrivalRows.value = [];
  for (const order of targets) {
    const lines = batchLines(order, "arrival");
    if (!lines.length) {
      arrivalRows.value.push({ order_id: order.id, status: "skipped", detail: tx("没有填写本批数量", "No quantity entered for this batch") });
      continue;
    }
    const signature = JSON.stringify({ order_id: order.id, kind: "arrival", lines });
    const operationKey = stableKey(signature);
    try {
      const result = await request<{ notification?: { status: string } }>("operations/fulfilment", {
        order_id: order.id,
        kind: "arrival",
        operation_key: operationKey,
        lines,
      });
      operationKeys.delete(signature);
      for (const line of order.lines) batch[`${order.id}:${line.id}:arrival`] = 0;
      arrivalRows.value.push({
        order_id: order.id,
        status: "success",
        detail: result.notification ? mailStatus(result.notification.status) : tx("已记录", "Recorded"),
      });
    } catch (cause) {
      arrivalRows.value.push({ order_id: order.id, status: "failed", detail: cause instanceof Error ? cause.message : String(cause) });
    }
  }
  try {
    await load();
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  }
  notice.value = arrivalRows.value.map((row) => `${orderLabel(row.order_id)}: ${row.status} ${row.detail}`).join("; ");
  busy.value = false;
}

function fulfil(order: ProjectOrder, kind: "arrival" | "delivery") {
  const lines = batchLines(order, kind);
  if (!lines.length) {
    error.value = tx("先填写本批数量。", "Enter this batch’s quantities first.");
    return;
  }
  const signature = JSON.stringify({ order_id: order.id, kind, lines });
  const operationKey = stableKey(signature);
  return act(async () => {
    const result = await request<{ notification?: { status: string } }>("operations/fulfilment", {
      order_id: order.id,
      kind,
      operation_key: operationKey,
      lines,
    });
    operationKeys.delete(signature);
    for (const line of order.lines) batch[`${order.id}:${line.id}:${kind}`] = 0;
    const mailed = result.notification ? mailStatus(result.notification.status) : "";
    notice.value = kind === "arrival"
      ? tx(`已记录本批到货。通知状态：${mailed || "无"}。收款状态不会被覆盖。`, `This arrival batch is recorded. Notification status: ${mailed || "none"}. Payment status is left unchanged.`)
      : tx("已记录本批交付。交付不能超过已到货。", "This delivery batch is recorded. Delivery cannot exceed what has arrived.");
  });
}

function sendSelectedInvoices() {
  const chosen = invoices.value.filter((invoice) => invoicePick.value.includes(invoice.id));
  if (!chosen.length) {
    error.value = tx("先勾选要发送的发票。", "Select the invoices to send.");
    return;
  }
  if (new Set(chosen.map((invoice) => invoice.customer_id)).size !== 1) {
    error.value = tx("不同公司的发票要分开发送。", "Invoices from different companies must be sent separately.");
    return;
  }
  return act(async () => {
    const results: string[] = [];
    for (const invoice of chosen) {
      try {
        const sent = await request<Invoice>(`operations/invoices/${invoice.id}/send`, {});
        results.push(`${invoice.id}: ${mailStatus(sent.status)}`);
      } catch (cause) {
        results.push(`${invoice.id}: failed ${cause instanceof Error ? cause.message : String(cause)}`);
      }
    }
    notice.value = results.join("; ");
  });
}

function selectedOrders() {
  return orders.value.filter((order) => picked.value.includes(order.id));
}

function oneCompany(rows: ProjectOrder[]) {
  const ids = [...new Set(rows.map((order) => order.customer_id))];
  if (!rows.length) {
    error.value = tx("先勾选同一公司的订单。", "Select orders from one company.");
    return null;
  }
  if (ids.length !== 1) {
    error.value = tx("不能把不同公司放进同一张尾款或同一笔返利。", "Projects from different companies cannot share one balance invoice or one rebate.");
    return null;
  }
  if(new Set(rows.map(o=>o.currency)).size !== 1){error.value=tx('只能选择同一币种的订单','Select orders in one currency');return null;}
  return ids[0];
}

function settleSelected() {
  const rows = selectedOrders();
  const customerId = oneCompany(rows);
  if (customerId == null) return;
  if (settlementEvidence.value.trim().length < 5) {
    error.value = tx("尾款需要至少 5 个字的已确认规则说明。没有说明不会生成发票。", "A balance invoice needs at least 5 characters of confirmed-rule evidence. Nothing is created without it.");
    return;
  }
  const orderIds = rows.map((order) => order.id).sort();
  const body = {
    order_ids: orderIds,
    operation_key: stableKey(JSON.stringify({ settle: orderIds, evidence: settlementEvidence.value.trim() })),
    rules_evidence: settlementEvidence.value.trim(),
    billing_basis: "fully_delivered_remaining_total" as const,
  };
  return act(async () => {
    const invoice = await request<Invoice>("operations/settlements", body);
    operationKeys.delete(JSON.stringify({ settle: orderIds, evidence: settlementEvidence.value.trim() }));
    notice.value = tx(
      `已生成尾款草稿 ${invoice.id}，金额 ${invoice.currency} ${invoice.amount}。部分到货或未收定金会被拒绝。发送仍是另一步。`,
      `Balance draft ${invoice.id} created for ${invoice.currency} ${invoice.amount}. Partial arrival or an unpaid deposit is refused. Sending stays a separate step.`,
    );
    picked.value=[];
  });
}

function recordRebate() {
  const rows = selectedOrders();
  const customerId = oneCompany(rows);
  if (customerId == null) return;
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(rebateForm.month) || Number(rebateForm.amount) <= 0 || rebateForm.evidence.trim().length < 5) {
    error.value = tx("返利要写年月（2026-10）、金额和至少 5 个字的确认依据。页面不计算阶梯。", "A rebate needs a month such as 2026-10, an amount, and at least 5 characters of evidence. This page does not calculate a tier.");
    return;
  }
  return act(async () => {
    await request("operations/rebates", {
      customer_id: customerId,
      source_order_ids: rows.map((order) => order.id),
      month: rebateForm.month,
      amount: rebateForm.amount,
      evidence: rebateForm.evidence.trim(),
      currency: rows[0]?.currency || 'NZD',
    });
    rebateForm.amount = "";
    rebateForm.evidence = "";
    notice.value = tx("已记入一笔已确认返利。这不是自动月度计算。", "Recorded one confirmed rebate. This is not an automatic monthly calculation.");
  });
}

function markBalanceReceived(invoice: Invoice) {
  if (invoice.kind !== "balance") {
    error.value = tx("定金到账仍用「定金已收」。这里只确认尾款。", "Deposit receipt still uses Deposit received. This confirms a balance invoice only.");
    return;
  }
  return act(async () => {
    await request(`operations/invoices/${invoice.id}/received`, { note: receiptNote[invoice.id] || tx("尾款已收", "Balance received") });
    notice.value = tx("已记录尾款已收。", "Balance receipt recorded.");
  });
}

function adjust(order: ProjectOrder) {
  if (order.status !== "pending_review") {
    error.value = tx("只有待审核订单可以改折扣和附加费。客户页面不能填这些数。", "Only an order awaiting review can change a discount or surcharge. The customer page cannot enter these figures.");
    return;
  }
  const note = (adjustNote[order.id] || "").trim();
  if (note.length < 5) {
    error.value = tx("调整说明至少要 5 个字。页面不会代填一句过短的默认说明。", "The adjustment note needs at least 5 characters. This page does not send a short default.");
    return;
  }
  const lines = order.lines.map((line) => ({
    line_id: line.id,
    discount: Number(batch[`${order.id}:${line.id}:discount`] ?? line.discount ?? 0),
    product_surcharge: String(batch[`${order.id}:${line.id}:product_surcharge`] ?? line.product_surcharge ?? 0),
    installation_surcharge: String(batch[`${order.id}:${line.id}:installation_surcharge`] ?? line.installation_surcharge ?? 0),
  }));
  if (lines.some((line) => line.discount < 0 || line.discount > 1)) {
    error.value = tx("折扣是 0 到 1 的比例。0.1 表示减 10%，不是填 10。", "Discount is a ratio from 0 to 1. 0.1 means ten percent off, not the integer 10.");
    return;
  }
  return act(async () => {
    await request(`operations/orders/${order.id}/adjust`, { note, lines });
    notice.value = tx("已按员工调整重算，并保留履历。", "Recalculated from the staff adjustment and kept the history.");
  });
}

async function refreshTemplate() {
  if (!props.admin) return;
  try {
    const status = await request<{ version?: string; products_count?: number; warnings?: string[] }>("operations/template-status");
    templateStatus.value = tx(
      `当前价表 ${(status.version || "—").slice(0,12)}。Deluxe 暂定价格仍需商业确认。`,
      `Active price version ${(status.version || "—").slice(0,12)}. Deluxe provisional pricing still requires confirmation.`,
    );
  } catch (cause) {
    templateStatus.value = cause instanceof Error ? cause.message : String(cause);
  }
}

async function importTemplate(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  busy.value = true;
  error.value = "";
  notice.value = "";
  try {
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary = "";
    const chunk = 0x8000;
    for (let index = 0; index < bytes.length; index += chunk) {
      binary += String.fromCharCode(...bytes.subarray(index, index + chunk));
    }
    const result = await request<{ version?: string; products_count?: number; warnings?: string[] }>("operations/template-import", {
      filename: file.name,
      content_base64: btoa(binary),
    });
    notice.value = tx(
      `已导入私有模板。版本 ${result.version || "—"}，产品 ${result.products_count ?? "—"}。原文件不会进公开仓库。`,
      `Imported the private template. Version ${result.version || "—"}, products ${result.products_count ?? "—"}. The original file is not added to the public repository.`,
    );
    templateStatus.value = (result.warnings || []).join(" ");
    await load();
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    input.value = "";
    busy.value = false;
  }
}

async function downloadSheet(id: string, kind: "production-sheet" | "job-sheet") {
  busy.value = true;
  error.value = "";
  notice.value = "";
  try {
    const response = await fetch(`/api/operations/orders/${id}/${kind}`, {
      headers: session.token ? { Authorization: `Bearer ${session.token}` } : {},
    });
    if (!response.ok) {
      const data = (await response.json().catch(() => ({}))) as { detail?: string };
      throw new Error(typeof data.detail === "string" ? data.detail : response.statusText);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${kind}-draft-${orderLabel(id)}.xlsx`;
    link.click();
    URL.revokeObjectURL(url);
    notice.value = tx("已下载生产资料草稿。这还不是已验收的工厂收单格式。", "Downloaded a production draft. This is not a confirmed factory order format.");
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    busy.value = false;
  }
}

function retryNotice(id: string) {
  return act(async () => {
    const sent = await request<Notice>(`operations/notifications/${id}/retry`, {});
    notice.value = tx(`通知状态：${mailStatus(sent.status)}`, `Notification status: ${mailStatus(sent.status)}`);
  });
}

function createProvider() {
  if (!providerForm.name.trim()) {
    error.value = tx("供应商名称不能为空", "Provider name is required");
    return;
  }
  return act(async () => {
    await request("operations/providers", { ...providerForm });
    providerForm.name = "";
    providerForm.contact_email = "";
    providerForm.notes = "";
    notice.value = tx("已创建供应商", "Provider created");
  });
}

function startEditProvider(provider: Provider) {
  editingProvider.value = provider;
  editProviderForm.name = provider.name;
  editProviderForm.contact_email = provider.contact_email;
  editProviderForm.notes = provider.notes;
  editProviderForm.active = !!provider.active;
}

function updateProvider() {
  if (!editingProvider.value) return;
  return act(async () => {
    await request(`operations/providers/${editingProvider.value!.id}`, { ...editProviderForm });
    editingProvider.value = null;
    notice.value = tx("已更新供应商", "Provider updated");
  });
}

function addMapping() {
  if (!mappingField.value || !mappingColumn.value) {
    error.value = tx("请选择字段和输入列号", "Select field and enter column letter");
    return;
  }
  if (!validFields.includes(mappingField.value)) {
    error.value = tx("无效字段", "Invalid field");
    return;
  }
  if (!/^[A-Z]+$/.test(mappingColumn.value.toUpperCase())) {
    error.value = tx("列号必须是字母（如 A, B, C）", "Column must be letters (e.g. A, B, C)");
    return;
  }
  templateForm.column_mappings[mappingField.value] = mappingColumn.value.toUpperCase();
  mappingField.value = "";
  mappingColumn.value = "";
}

function removeMapping(field: string) {
  delete templateForm.column_mappings[field];
}

function createTemplate() {
  if (!templateForm.provider_id || !templateForm.name || !templateForm.sheet_name || Object.keys(templateForm.column_mappings).length === 0) {
    error.value = tx("请填写供应商、模板名称、表单名和至少一个字段映射", "Provider, template name, sheet name and at least one field mapping required");
    return;
  }
  return act(async () => {
    await request("operations/provider-templates", { ...templateForm });
    templateForm.provider_id = 0;
    templateForm.name = "";
    templateForm.sheet_name = "";
    templateForm.column_mappings = {};
    templateForm.supersedes_id = null;
    notice.value = tx("已创建供应商模板", "Provider template created");
  });
}

function reviseTemplate(template:ProviderTemplate) {
  templateForm.provider_id=template.provider_id;
  templateForm.name=template.name;
  templateForm.sheet_name=template.sheet_name;
  templateForm.column_mappings={...JSON.parse(template.column_mappings)};
  templateForm.supersedes_id=template.id;
}
function saveApplicability(version:PricingVersion) { return act(async()=>{ await request(`operations/pricing-templates/${encodeURIComponent(version.id)}/applicability`,{provider_ids:applicability[version.id] || []}); notice.value=tx('已保存此版本的供应商适用范围','Supplier applicability saved for this version'); }); }
function activateVersion(version:PricingVersion) { return act(async()=>{await request(`operations/pricing-templates/${encodeURIComponent(version.id)}/activate`,{}); notice.value=tx('已启用此价表；历史订单价格保持不变','Pricing version activated; historical prices unchanged');}); }

async function assignProvider(orderId: string) {
  const form = orderProviderForm[orderId];
  if (!form || !form.provider_id) {
    error.value = tx("请选择供应商", "Select a provider");
    return;
  }
  return act(async () => {
    await request(`operations/orders/${orderId}/assign-provider`, {
      provider_id: form.provider_id,
      template_id: form.template_id || null,
      is_preferred: true,
    });
    notice.value = tx("已分配供应商", "Provider assigned to order");
  });
}

async function exportWithProvider(orderId: string, providerId?: number, allowFallback = false) {
  busy.value = true;
  error.value = "";
  notice.value = "";
  try {
    if (!allowFallback && (!providerId || !readySupplierExport(orderId))) {
      throw new Error(tx('请先选择已启用的供应商及其导出模板；也可下载未验证的基本草稿。','Select an active supplier and export template, or download the unverified basic draft.'));
    }
    if (providerId && !allowFallback) {
      const form = orderProviderForm[orderId];
      await request(`operations/orders/${orderId}/assign-provider`, { provider_id: providerId, template_id: form.template_id || null, is_preferred: true });
    }
    const params = new URLSearchParams();
    if (providerId) params.set("provider_id", String(providerId));
    if (allowFallback) params.set("allow_basic_fallback", "true");
    const response = await fetch(`/api/operations/orders/${orderId}/supplier-export?${params}`, {
      headers: session.token ? { Authorization: `Bearer ${session.token}` } : {},
    });
    if (!response.ok) {
      const data = (await response.json().catch(() => ({}))) as { detail?: string };
      throw new Error(typeof data.detail === "string" ? data.detail : response.statusText);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const disposition = response.headers.get("content-disposition") || "";
    const match = /filename="([^"]+)"/.exec(disposition);
    const filename = match ? match[1] : `supplier-export-${orderId}.xlsx`;
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
    if (filename.includes("BASIC-NOT-VERIFIED")) {
      notice.value = tx("已下载基本模板（未经供应商验证）", "Downloaded basic template (not supplier-verified)");
    } else {
      notice.value = tx("已下载供应商专用模板", "Downloaded provider-specific template");
    }
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    busy.value = false;
  }
}

async function loadOrderProviders(orderId: string) {
  try {
    const assigned = await request<OrderProvider[]>(`operations/orders/${orderId}/providers`);
    if (assigned.length > 0) {
      const first = assigned[0];
      orderProviderForm[orderId] = {
        provider_id: first.provider_id,
        template_id: first.template_id || defaultTemplateId(first.provider_id),
      };
    } else {
      const active=providers.value.filter(p=>p.active);
      if (active.length===1) chooseProvider(orderId,active[0].id);
    }
  } catch (e) {
    console.error("Failed to load order providers:", e);
  }
}
</script>

<template>
  <section class="desk" :class="{ 'workspace-layout': true, 'global-workspace': workspace !== 'projects' }">
    <p v-if="error" class="alert card" role="alert">{{ error }}</p>
    <p v-if="notice" class="success card" role="status">{{ notice }}</p>

    <p v-if="!loaded" role="status">{{ tx('加载中…','Loading…') }}</p>
    <div v-show="loaded" class="workspace-grid">
      <aside v-if="workspace === 'projects'" class="card order-list" :class="{ 'mobile-expanded': mobileListOpen }">
        <div class="list-heading"><h3>{{ tx("订单列表", "Orders") }}</h3><span>{{ visibleOrders.length }}</span></div>
        <label class="filter-row">{{ tx("筛选", "Filter") }}
          <select v-model="statusFilter" @change="listPage = 0">
            <option value="">{{ tx("全部", "All") }}</option>
            <option v-for="status in [...new Set(orders.flatMap((order) => [order.status, order.payment_status]))]" :key="status" :value="status">{{ orderStatus(status) }}</option>
          </select>
        </label>
        <div class="mobile-project-picker">
          <label>{{ tx("当前订单", "Current order") }}<select :value="selectedOrder?.id" @change="selectedId = ($event.target as HTMLSelectElement).value"><option v-for="order in visibleOrders" :key="order.id" :value="order.id">{{ order.project_name }}</option></select></label>
          <button type="button" class="secondary" @click="mobileListOpen = !mobileListOpen">{{ mobileListOpen ? tx("收起列表", "Collapse list") : tx("批量选择", "Select multiple") }}</button>
        </div>
        <div class="order-scroll">
          <div v-for="order in pageOrders" :key="order.id" class="order-row">
            <label class="pick-mark">
              <input type="checkbox" :aria-label="tx('批量选择订单','Select order for batch')+' '+order.order_number" :checked="picked.includes(order.id)" @change="toggleOrder(order.id)" />
            </label>
            <button type="button" :title="order.project_name" :aria-pressed="selectedOrder?.id === order.id" class="order-pick" :class="{ current: selectedOrder?.id === order.id }" @click="selectedId = order.id">
              <strong>{{ order.project_name }}</strong>
              <span>{{ order.order_number }}</span>
              <span>{{ order.company }}</span>
              <small>{{ orderStatus(order.status) }} · {{ order.total ? `${order.currency || ""} ${order.total}` : tx("待计价", "Unpriced") }}</small>
            </button>
          </div>
        </div>
        <div v-if="pageCount > 1" class="list-pagination">
          <button type="button" :disabled="listPage <= 0" @click="listPage--" aria-label="Previous projects">←</button>
          <span>{{ Math.min(listPage + 1, pageCount) }} / {{ pageCount }}</span>
          <button type="button" :disabled="listPage >= pageCount - 1" @click="listPage++" aria-label="Next projects">→</button>
        </div>
      </aside>

      <div class="detail-panel">
        <div v-if="workspace === 'projects' && picked.length" class="card batch-toolbar"><strong>{{ tx('已选', 'Selected') }} {{ picked.length }}</strong><button :disabled="busy" @click="transitSelected">{{ tx('批量标为在途','Mark in transit') }}</button><button :disabled="busy" @click="arriveSelected">{{ tx('批量记录到货','Record arrivals') }}</button><button class="secondary" @click="picked = []">{{ tx('取消选择','Clear selection') }}</button><p v-if="transitRows.length || arrivalRows.length">{{ notice }}</p></div>

        <div class="section-content">
          <section v-if="activeSection === 'operations'" class="card section-card">

            <div v-if="!selectedOrder">
              <p>{{ tx("选择一个订单查看详情", "Select an order to view details") }}</p>
            </div>
            <article v-else class="order-detail">
              <header class="order-header">
                <div>
                  <h2>{{ selectedOrder.project_name }}</h2>
                  <p class="order-identity"><strong>{{ selectedOrder.order_number }}</strong><span>{{ selectedOrder.company }}</span></p>
                </div>
                <div class="status-badges">
                  <span class="badge">{{ orderStatus(selectedOrder.status) }}</span>
                  <span class="badge">{{ orderStatus(selectedOrder.payment_status) }}</span>
                  <span v-if="selectedOrder.arrival_status" class="badge">{{ orderStatus(selectedOrder.arrival_status) }}</span>
                </div>
              </header>
              <div class="order-meta">
                <p><strong>{{ tx("施工地址", "Site") }}:</strong> {{ selectedOrder.site_address }}</p>
                <p><strong>{{ tx("总价", "Total") }}:</strong> {{ selectedOrder.total ? `${selectedOrder.currency || ""} ${selectedOrder.total}` : tx("待计价", "Unpriced") }}</p>
                <p v-if="selectedOrder.supplier_reference"><strong>{{ tx("供应商参考", "Supplier ref") }}:</strong> {{ selectedOrder.supplier_reference }}</p>
              </div>
              <div class="detail-navigation"><nav class="detail-tabs" aria-label="Project details">
                <button type="button" :class="{active: detailSection === 'lines'}" @click="detailSection = 'lines'">{{ tx("明细", "Lines") }}</button>
                <button type="button" :class="{active: detailSection === 'fulfilment'}" @click="detailSection = 'fulfilment'">{{ tx("履约", "Fulfilment") }}</button>
                <button type="button" :class="{active: detailSection === 'supplier'}" @click="detailSection = 'supplier'">{{ tx("供应商与导出", "Supplier & files") }}</button>
                <button type="button" :class="{active: detailSection === 'adjustment'}" @click="detailSection = 'adjustment'">{{ tx("计价与审核", "Pricing & review") }}</button>
                <button type="button" :class="{active: detailSection === 'invoices'}" @click="detailSection = 'invoices'">{{ tx("发票与收款", "Invoices & payments") }}</button>
                <button type="button" :class="{active: detailSection === 'history'}" @click="detailSection = 'history'">{{ tx('操作记录','Activity') }}</button>
              </nav><div class="next-action"><strong>{{ tx('建议下一步','Suggested next step') }}</strong><p>{{ nextOrderHint }}</p><RouterLink v-if="selectedOrder.status==='delivered'" :to="{path:'/crm/finance',query:{customer:selectedOrder.customer_id}}">{{ tx('打开客户账款','Open customer accounts') }} →</RouterLink><button v-else-if="detailSection!==nextOrderSection(selectedOrder)" type="button" class="secondary" @click="detailSection=nextOrderSection(selectedOrder)">{{ tx('打开当前步骤','Open current step') }}</button></div></div>
<div v-show="detailSection === 'lines' || detailSection === 'fulfilment'">              <h3>{{ detailSection === 'lines' ? tx('产品明细','Product lines') : tx('履约数量','Fulfilment quantities') }}</h3>
              <div v-if="detailSection === 'fulfilment'" class="actions"><button v-if="['in_transit','partially_arrived'].includes(selectedOrder.status)" type="button" class="secondary" @click="fillRemaining(selectedOrder,'arrival')">{{ tx('填入全部未到数量','Fill all remaining arrivals') }}</button><button v-if="selectedOrder.lines.some(line=>line.arrived>line.delivered)" type="button" class="secondary" @click="fillRemaining(selectedOrder,'delivery')">{{ tx('填入全部待交付数量','Fill all ready deliveries') }}</button></div>
              <div class="table-scroll"><table>
                <thead><tr><th>{{ tx("窗户", "Window") }}</th><th>{{ tx("订购", "Ordered") }}</th><th>{{ tx("已到", "Arrived") }}</th><th>{{ tx("已交付", "Delivered") }}</th><th v-if="detailSection === 'fulfilment'">{{ tx("本批到货", "Arrival") }}</th><th v-if="detailSection === 'fulfilment'">{{ tx("本批交付", "Delivery") }}</th></tr></thead>
                <tbody>
                  <tr v-for="line in selectedOrder.lines" :key="line.id">
                    <td>
                      <strong>{{ line.window_name }}</strong>
                      <small>{{ tx("系列", "Series") }} {{ line.product_id || "—" }} · {{ line.width_mm || "—" }}×{{ line.height_mm || "—" }} mm<span v-if="optionText(line)"> · {{ optionText(line) }}</span></small>
                    </td>
                    <td>{{ line.quantity }}</td>
                    <td>{{ line.arrived }}</td>
                    <td>{{ line.delivered }}</td>
                    <td v-if="detailSection === 'fulfilment'"><input v-model.number="batch[`${selectedOrder.id}:${line.id}:arrival`]" type="number" min="0" step="1" /></td>
                    <td v-if="detailSection === 'fulfilment'"><input v-model.number="batch[`${selectedOrder.id}:${line.id}:delivery`]" type="number" min="0" step="1" /></td>
                  </tr>
                </tbody>
              </table></div>

              <h3 v-if="detailSection === 'fulfilment' && (selectedOrder.status==='supplier_ordered' || ['in_transit','partially_arrived'].includes(selectedOrder.status) || selectedOrder.lines.some(line=>line.arrived>line.delivered))">{{ tx("履约操作", "Fulfilment actions") }}</h3>
              <div v-if="detailSection === 'fulfilment'" class="actions">
                <button v-if="selectedOrder.status==='supplier_ordered'" type="button" class="secondary" :disabled="busy" @click="transitOne(selectedOrder.id)">{{ tx('标为在途','Mark in transit') }}</button>
                <button v-if="['in_transit','partially_arrived'].includes(selectedOrder.status)" type="button" class="secondary" :disabled="busy" @click="fulfil(selectedOrder, 'arrival')">{{ tx("记录本批到货", "Record arrival") }}</button>
                <button v-if="selectedOrder.lines.some(line=>line.arrived>line.delivered)" type="button" class="secondary" :disabled="busy" @click="fulfil(selectedOrder, 'delivery')">{{ tx("记录本批交付", "Record delivery") }}</button>
              </div>

</div><div v-show="detailSection === 'supplier'">              <h3>{{ tx("供应商与导出", "Provider & Export") }}</h3>
              <div class="provider-section">
                <div class="form-row">
                  <label>{{ tx("选择供应商", "Select provider") }}
                    <select :value="orderProviderForm[selectedOrder.id].provider_id" @change="chooseProvider(selectedOrder.id,Number(($event.target as HTMLSelectElement).value))">
                      <option :value="0">{{ tx("未分配", "Not assigned") }}</option>
                      <option v-for="p in providers.filter(p => p.active)" :key="p.id" :value="p.id">{{ p.name }}</option>
                    </select>
                  </label>
                  <label v-if="orderProviderForm[selectedOrder.id].provider_id && providerTemplates.some(t=>t.provider_id===orderProviderForm[selectedOrder.id].provider_id && t.active)">{{ tx("选择模板", "Select template") }}
                    <select v-model="orderProviderForm[selectedOrder.id].template_id">
                      <option :value="0">{{ tx("默认", "Default") }}</option>
                      <option v-for="t in providerTemplates.filter(t => t.provider_id === orderProviderForm[selectedOrder.id].provider_id && t.active)" :key="t.id" :value="t.id">{{ t.name }}</option>
                    </select>
                  </label>
                  <details class="provider-advanced"><summary>{{ tx('只保存分配，不导出','Save assignment only') }}</summary><button type="button" :disabled="busy || !orderProviderForm[selectedOrder.id].provider_id" @click="assignProvider(selectedOrder.id)">{{ tx("保存分配", "Save assignment") }}</button></details>
                  <RouterLink to="/crm/providers">{{ tx('管理共享供应商','Manage shared suppliers') }}</RouterLink>
                </div>
                <p class="hint" v-if="!providers.some(p=>p.active)">{{ tx('尚无已启用供应商；先在供应商页面确认并启用。','No active supplier yet. Confirm and activate one under Suppliers.') }}</p>
                <p class="hint" v-else-if="orderProviderForm[selectedOrder.id].provider_id && !providers.some(p=>p.id===orderProviderForm[selectedOrder.id].provider_id && p.active)">{{ tx('原供应商已停用，请重新选择已启用的供应商。','The assigned supplier is inactive; choose an active supplier.') }}</p>
                <p class="hint" v-else-if="orderProviderForm[selectedOrder.id].provider_id && !orderProviderForm[selectedOrder.id].template_id">{{ tx('该供应商还没有可用输出模板；可先下载未验证的基本草稿。','This supplier has no active export template yet; use the unverified basic draft for review.') }}</p>
                <p class="hint" v-else-if="orderProviderForm[selectedOrder.id].template_id && !readySupplierExport(selectedOrder.id)">{{ tx('原输出模板已停用，请选择当前有效版本。','The assigned export template is inactive; choose a current revision.') }}</p>
                <p class="hint" v-else>{{ tx('已自动选择可用模板；下载时会同时保存本单供应商分配。','An available template is selected automatically; downloading also saves this order’s supplier assignment.') }}</p>
                <div class="form-row">
                  <button v-if="readySupplierExport(selectedOrder.id)" type="button" :disabled="busy || selectedOrder.status==='pending_review'" @click="exportWithProvider(selectedOrder.id, orderProviderForm[selectedOrder.id].provider_id, false)">{{ tx("下载供应商订单 Excel（自动保存分配）", "Download supplier order Excel (saves assignment)") }}</button>
                  <button v-else type="button" :disabled="busy || selectedOrder.status==='pending_review'" @click="exportWithProvider(selectedOrder.id, undefined, true)">{{ tx('下载订单 Excel 草稿（格式未验证）','Download draft order Excel (unverified format)') }}</button>
                  <details class="provider-advanced"><summary>{{ tx('其他文件','Other files') }}</summary><div class="form-row"><button v-if="orderProviderForm[selectedOrder.id].template_id" type="button" class="secondary" :disabled="busy || selectedOrder.status==='pending_review'" @click="exportWithProvider(selectedOrder.id, undefined, true)">{{ tx("基本模板草稿", "Basic draft") }}</button><button type="button" class="secondary" :disabled="busy" @click="downloadSheet(selectedOrder.id, 'production-sheet')">{{ tx("生产资料草稿", "Production draft") }}</button><button type="button" class="secondary" :disabled="busy" @click="downloadSheet(selectedOrder.id, 'job-sheet')">{{ tx("安装工作单草稿", "Job sheet") }}</button></div></details>
                </div>
              </div>
              <div v-if="selectedOrder.status==='accepted' && selectedOrder.payment_status==='deposit_received'" class="actions"><label>{{ tx('供应商参考号','Supplier reference') }}<input v-model="supplierRef[selectedOrder.id]" /></label><button type="button" :disabled="busy || !supplierRef[selectedOrder.id]" @click="supplier(selectedOrder)">{{ tx('记录供应商下单','Record supplier order') }}</button></div>

</div><div v-show="detailSection === 'adjustment'">
              <h3>{{ tx('本单计价依据','Pricing applied to this order') }}</h3><p v-for="version in [...new Set(selectedOrder.lines.map(l=>l.rule_version).filter(Boolean))]" :key="version"><RouterLink :to="{path:'/crm/pricing',query:{version}}">{{ tx('定价版本','Pricing version') }} {{ version?.slice(0,12) }}</RouterLink></p><p v-if="selectedOrder.status !== 'pending_review'">{{ tx('审核后价格已冻结','Prices frozen after acceptance') }}</p>
              <div v-if="selectedOrder.status === 'pending_review'" class="adjustment-section">
                <h3>{{ tx("价格调整", "Price adjustment") }}</h3>
                <div class="table-scroll"><table>
                  <thead><tr><th>{{ tx("窗户", "Window") }}</th><th>{{ tx("折扣比例", "Discount") }}</th><th>{{ tx("商品附加", "Product surcharge") }}</th><th>{{ tx("安装附加", "Install surcharge") }}</th></tr></thead>
                  <tbody>
                    <tr v-for="line in selectedOrder.lines" :key="line.id">
                      <td>{{ line.window_name }}</td>
                      <td><input v-model.number="batch[`${selectedOrder.id}:${line.id}:discount`]" type="number" min="0" max="1" step="0.01" /></td>
                      <td><input v-model.number="batch[`${selectedOrder.id}:${line.id}:product_surcharge`]" type="number" min="0" step="0.01" /></td>
                      <td><input v-model.number="batch[`${selectedOrder.id}:${line.id}:installation_surcharge`]" type="number" min="0" step="0.01" /></td>
                    </tr>
                  </tbody>
                </table></div>
                <div class="review-footer"><label>{{ tx("调整说明（仅改价时填写）", "Adjustment note (only when changing price)") }}<input v-model="adjustNote[selectedOrder.id]" /></label><button type="button" class="secondary" :disabled="busy" @click="adjust(selectedOrder)">{{ tx("保存调整", "Save adjustment") }}</button><button type="button" :disabled="busy" @click="review(selectedOrder.id)">{{ tx('确认接收并生成定金草稿','Accept and create deposit draft') }}</button></div>
              </div>

</div><div v-show="detailSection === 'invoices'">              <div v-if="selectedOrder.invoices && selectedOrder.invoices.length">
                <h3>{{ tx("发票", "Invoices") }}</h3>
                <div v-for="invoice in selectedOrder.invoices" :key="invoice.id" class="invoice">
                  <label><input type="checkbox" :value="invoice.id" v-model="invoicePick" /> {{ invoice.kind === 'deposit' ? tx('定金','Deposit') : tx('尾款','Balance') }} · {{ invoice.currency }} {{ invoice.amount }} · {{ mailStatus(invoice.status) }} · {{ invoice.payment_status === "received" ? tx("已收", "Received") : tx("未收", "Unpaid") }}</label>
                  <template v-if="invoice.kind === 'balance'">
                    <input v-model="receiptNote[invoice.id]" :placeholder="tx('尾款备注', 'Balance note')" />
                    <button type="button" class="secondary" :disabled="busy" @click="markBalanceReceived(invoice)">{{ tx("尾款已收", "Balance received") }}</button>
                  </template>
                </div>
              </div>
<div v-if="selectedOrder.status!=='pending_review' && selectedOrder.payment_status==='deposit_unpaid'" class="actions"><button type="button" :disabled="busy" @click="deposit(selectedOrder.id)">{{ tx('核实到账后记录定金已收','Record deposit after confirming receipt') }}</button></div><p v-if="!selectedOrder.invoices?.length" class="hint">{{ tx("暂无发票", "No invoices yet") }}</p><div class="invoice-actions"><button v-if="selectedOrder.invoices?.length" :disabled="busy || !invoicePick.length" @click="sendSelectedInvoices">{{ emailMode==='demo' ? (emailEnabled ? tx('发送演示邮件（仅自己）','Send demo email to owner only') : tx('记录模拟发送（不投递）','Record demo send (no delivery)')) : tx('发送勾选的本单发票','Send selected order invoices') }}</button><RouterLink :to="{path:'/crm/finance',query:{customer:selectedOrder.customer_id}}">{{ tx('客户结算与返利账本','Customer settlement & rebate ledger') }}</RouterLink></div></div>
              <div v-show="detailSection === 'history'"><h3>{{ tx('操作记录','Activity') }}</h3><p v-for="(item,index) in selectedOrder.history || []" :key="index">{{ item.created_at }} · {{ item.action }}<span v-if="item.template_id"> · {{ tx('导出模板','Export template') }} #{{ item.template_id }} · {{ item.template_revision ? 'v'+item.template_revision : tx('历史版本未标记','Historical revision unspecified') }}</span></p></div>
            </article>
          </section>

          <section v-if="activeSection === 'pricing'" class="card section-card">
            <h2>{{ tx("共享定价模板", "Shared pricing templates") }}</h2>
            <p class="hint">{{ tx("在此统一管理价表。新版本影响后续计价，已审核订单保留原价。供应商导出格式在供应商模块单独管理。", "Manage shared pricing versions here. New versions affect future pricing; accepted orders retain their prices. Supplier export formats are managed under Suppliers.") }}</p>
            <label v-if="admin">{{ tx('导入并启用新价表（影响后续计价）','Import & activate a price workbook (affects future pricing)') }}<input type="file" accept=".xlsm,.xlsx" :disabled="busy" @change="importTemplate" /></label>
            <p v-if="templateStatus" class="template-status">{{ templateStatus }}</p>
            <p v-if="!pricingVersions.length">{{ tx('尚未导入定价模板','No pricing workbook imported') }}</p>
            <article v-for="version in pricingVersions" :key="version.id" class="template-card" :class="{highlight:route.query.version===version.version}">
              <h3>{{ version.version.slice(0,12) }} · {{ version.active ? tx('当前启用','Active') : tx('历史版本','Historical') }}</h3><p>{{ version.imported_at }} · {{ tx('系列','Products') }}: {{ version.products.map(code=>({'Shutters_PVC':'Classic','Shutters_PVC_Eco':'Eco','Shutters_Pinewood':'Natural','Shutters_Basswood':'Prime','VERA_Ashwood_provisional':'Deluxe'} as Record<string,string>)[code] || code).join(', ') }}</p>
              <button v-if="admin && !version.active" :disabled="busy" @click="activateVersion(version)">{{ tx('启用此版本（仅后续计价）','Activate for future pricing') }}</button>
              <h4>{{ tx('适用供应商（明确配置）','Applicable suppliers (explicit configuration)') }}</h4><p v-if="!version.applicability_confirmed">{{ tx('尚未确认，不从付款抬头推断','Unspecified; never inferred from payment issuer') }}</p><label v-for="provider in providers" :key="provider.id" class="checkbox-label"><input type="checkbox" v-model="applicability[version.id]" :value="provider.id" :disabled="!admin" />{{ provider.name }}</label><button v-if="admin" :disabled="busy" @click="saveApplicability(version)">{{ tx('保存适用范围','Save applicability') }}</button>
              <h4>{{ tx('引用订单','Referenced by orders') }} ({{ version.orders.length }})</h4><div class="resource-orders"><p v-for="order in version.orders" :key="order.id"><RouterLink :to="{path:'/crm/projects',query:{order:order.id}}">{{ order.order_number }} · {{ order.project_name }}</RouterLink></p></div>
            </article>
          </section>

          <section v-if="activeSection === 'providers'" class="card section-card">
            <h2>{{ tx("供应商管理", "Provider management") }}</h2>
            
            <h3>{{ tx("创建供应商", "Create provider") }}</h3>
            <form v-if="admin" @submit.prevent="createProvider" class="form-grid">
              <label>{{ tx("供应商名称", "Provider name") }}<input v-model="providerForm.name" required /></label>
              <label>{{ tx("联系邮箱", "Contact email") }}<input v-model="providerForm.contact_email" type="email" /></label>
              <label>{{ tx("备注", "Notes") }}<input v-model="providerForm.notes" /></label>
              <button :disabled="busy">{{ tx("创建", "Create") }}</button>
            </form>

            <h3>{{ tx("现有供应商", "Existing providers") }}</h3>
            <div class="provider-list">
              <div v-for="provider in providers" :key="provider.id" class="provider-card">
                <div v-if="editingProvider?.id !== provider.id">
                  <h4>{{ provider.name }} <span :class="{ 'status-active': provider.active, 'status-inactive': !provider.active }">{{ provider.active ? tx("活跃", "Active") : tx("停用", "Inactive") }}</span></h4>
                  <p v-if="provider.contact_email"><strong>{{ tx("邮箱", "Email") }}:</strong> {{ provider.contact_email }}</p>
                  <p v-if="provider.notes"><strong>{{ tx("备注", "Notes") }}:</strong> {{ provider.notes }}</p>
                  <button v-if="admin" type="button" class="secondary" @click="startEditProvider(provider)">{{ tx("编辑", "Edit") }}</button>
                  <h4>{{ tx('关联订单','Assigned orders') }} ({{ provider.orders?.length || 0 }})</h4><p v-for="order in provider.orders" :key="order.id"><RouterLink :to="{path:'/crm/projects',query:{order:order.id}}">{{ order.order_number }} · {{ order.project_name }}</RouterLink> · {{ tx('导出模板','Export template') }} #{{ order.template_id || '—' }}</p>
                  <h4>{{ tx('适用价表','Applicable pricing versions') }}</h4><p v-for="version in pricingVersions.filter(v=>v.provider_ids.includes(provider.id))" :key="version.id"><RouterLink :to="{path:'/crm/pricing',query:{version:version.version}}">{{ version.version.slice(0,12) }}</RouterLink></p><p v-if="!pricingVersions.some(v=>v.provider_ids.includes(provider.id))">{{ tx('尚未确认','Unspecified') }}</p>
                </div>
                <form v-else @submit.prevent="updateProvider" class="edit-form">
                  <label>{{ tx("名称", "Name") }}<input v-model="editProviderForm.name" required /></label>
                  <label>{{ tx("邮箱", "Email") }}<input v-model="editProviderForm.contact_email" type="email" /></label>
                  <label>{{ tx("备注", "Notes") }}<input v-model="editProviderForm.notes" /></label>
                  <label class="checkbox-label"><input type="checkbox" v-model="editProviderForm.active" /> {{ tx("活跃", "Active") }}</label>
                  <div class="button-group">
                    <button type="submit" :disabled="busy">{{ tx("保存", "Save") }}</button>
                    <button type="button" class="secondary" @click="editingProvider = null">{{ tx("取消", "Cancel") }}</button>
                  </div>
                </form>
              </div>
            </div>

            <h3>{{ tx("配置供应商输出模板", "Configure provider template") }}</h3>
            <p class="hint">{{ tx("为每个供应商配置专用Excel模板，定义字段到列的映射关系。", "Configure custom Excel templates for each provider with field-to-column mappings.") }}</p>
            <form v-if="admin" @submit.prevent="createTemplate" class="template-form">
              <p v-if="templateForm.supersedes_id">{{ tx('正在创建新版本，历史模板不会修改','Creating a new revision; historical template stays unchanged') }} #{{ templateForm.supersedes_id }} <button type="button" @click="templateForm.supersedes_id=null">{{ tx('改为独立模板','Create a separate template') }}</button></p>
              <div class="form-grid">
                <label>{{ tx("供应商", "Provider") }}
                  <select v-model="templateForm.provider_id" required>
                    <option :value="0">{{ tx("选择供应商", "Select provider") }}</option>
                    <option v-for="p in providers.filter(p => p.active)" :key="p.id" :value="p.id">{{ p.name }}</option>
                  </select>
                </label>
                <label>{{ tx("模板名称", "Template name") }}<input v-model="templateForm.name" required /></label>
                <label>{{ tx("工作表名称", "Sheet name") }}<input v-model="templateForm.sheet_name" required /></label>
              </div>

              <h4>{{ tx("字段映射", "Field mappings") }}</h4>
              <div class="mapping-controls">
                <select v-model="mappingField">
                  <option value="">{{ tx("选择字段", "Select field") }}</option>
                  <option v-for="field in validFields" :key="field" :value="field">{{ field }}</option>
                </select>
                <input v-model="mappingColumn" :placeholder="tx('列号 (A, B, C...)', 'Column (A, B, C...)')" />
                <button type="button" class="secondary" @click="addMapping">{{ tx("添加", "Add") }}</button>
              </div>

              <div v-if="Object.keys(templateForm.column_mappings).length" class="mappings-list">
                <div v-for="(col, field) in templateForm.column_mappings" :key="field" class="mapping-item">
                  <span><strong>{{ field }}</strong> → {{ tx("列", "Col") }} {{ col }}</span>
                  <button type="button" class="link-button" @click="removeMapping(field)">{{ tx("删除", "Remove") }}</button>
                </div>
              </div>

              <button :disabled="busy">{{ tx("创建模板", "Create template") }}</button>
            </form>

            <h3>{{ tx("现有模板", "Existing templates") }}</h3>
            <div class="template-list">
              <div v-for="template in providerTemplates" :key="template.id" class="template-card">
                <h4>{{ template.name }} · {{ template.revision ? 'v'+template.revision : tx('历史版本未标记','Historical revision unspecified') }} <span class="provider-badge">{{ providers.find(p => p.id === template.provider_id)?.name }}</span></h4><button v-if="admin" class="secondary" @click="reviseTemplate(template)">{{ tx('基于此版创建新版本','Create revision from this version') }}</button>
                <p><strong>{{ tx("工作表", "Sheet") }}:</strong> {{ template.sheet_name }}</p>
                <p><strong>{{ tx("映射", "Mappings") }}:</strong> {{ Object.keys(JSON.parse(template.column_mappings)).length }} {{ tx("个字段", "fields") }}</p>
                <p><strong>{{ tx("状态", "Status") }}:</strong> {{ template.active ? tx("活跃", "Active") : tx("停用", "Inactive") }}</p>
                <details>
                  <summary>{{ tx("查看映射", "View mappings") }}</summary>
                  <div class="mapping-display">
                    <div v-for="(col, field) in JSON.parse(template.column_mappings)" :key="field">
                      <strong>{{ field }}</strong> → {{ tx("列", "Col") }} {{ col }}
                    </div>
                  </div>
                </details>
              </div>
            </div>
          </section>

          <section v-if="activeSection === 'settlement'" class="card section-card finance-workspace">
            <header class="finance-header"><h2>{{ tx('账款与返利','Accounts & rebates') }}</h2><label>{{ tx('客户账本','Customer ledger') }}<select v-model="financeCustomer" @change="picked=[];invoicePick=[]"><option value="">{{ tx('全部客户','All customers') }}</option><option v-for="customer in customers" :key="customer.customer_id" :value="String(customer.customer_id)">{{ customer.company }}</option></select></label></header>
            <div class="finance-grid">
              <div class="finance-panel"><div class="finance-panel-head"><h3>{{ tx('来源订单','Source orders') }}</h3><span>{{ tx('已选','Selected') }} {{ picked.length }}</span></div><div class="finance-list">
                <div v-for="order in financeOrders" :key="order.id" class="finance-order"><label class="checkbox-label"><input type="checkbox" v-model="picked" :value="order.id" /><span>{{ order.order_number }} · {{ orderStatus(order.status) }}</span></label><RouterLink :to="{path:'/crm/projects',query:{order:order.id}}">{{ order.project_name }}</RouterLink></div><p v-if="!financeOrders.length">{{ tx('此客户暂无订单','No orders for this customer') }}</p>
              </div></div>
              <div class="finance-panel"><div class="finance-panel-head"><h3>{{ tx('发票与收款','Invoices & receipts') }}</h3><span>{{ financeInvoices.length }}</span></div><div class="finance-list">
                <div v-for="invoice in financeInvoices" :key="invoice.id" class="invoice"><label class="checkbox-label"><input type="checkbox" v-model="invoicePick" :value="invoice.id" />{{ invoice.kind === 'deposit' ? tx('定金','Deposit') : tx('尾款','Balance') }} · {{ invoice.currency }} {{ invoice.amount }} · {{ mailStatus(invoice.status) }} · {{ invoice.payment_status === 'received' ? tx('已收','Received') : tx('未收','Unpaid') }}</label><p v-for="oid in invoice.order_ids" :key="oid"><RouterLink :to="{path:'/crm/projects',query:{order:oid}}">{{ orders.find(o=>o.id===oid)?.order_number }} · {{ orders.find(o=>o.id===oid)?.project_name }}</RouterLink></p><template v-if="invoice.kind==='balance'"><input v-model="receiptNote[invoice.id]" :placeholder="tx('收款备注','Receipt note')" /><button :disabled="busy" @click="markBalanceReceived(invoice)">{{ tx('确认尾款收款','Confirm balance receipt') }}</button></template></div>
                <p v-if="!financeInvoices.length" class="hint">{{ tx('此客户暂无发票','No invoices for this customer') }}</p>
              </div><div class="finance-panel-foot"><button :disabled="busy || !invoicePick.length" @click="sendSelectedInvoices">{{ emailMode==='demo' ? (emailEnabled ? tx('发送演示邮件（仅自己）','Send demo email to owner only') : tx('记录模拟发送（不投递）','Record demo send (no delivery)')) : tx('发送勾选发票','Send selected invoices') }}</button></div></div>
              <div class="finance-panel finance-action-panel"><nav class="finance-pane-tabs" aria-label="Finance actions"><button type="button" :class="{active:financePane==='balance'}" @click="financePane='balance'">{{ tx('尾款','Balance') }}</button><button type="button" :class="{active:financePane==='rebates'}" @click="financePane='rebates'">{{ tx('返利','Rebates') }}</button><button type="button" :class="{active:financePane==='notifications'}" @click="financePane='notifications'">{{ tx('通知','Notices') }}</button></nav>
                <div v-show="financePane==='balance'" class="finance-action-content"><h3>{{ tx('生成尾款草稿','Create balance draft') }}</h3><p class="hint">{{ tx('仅限同公司、同币种、全部交付且定金已收。金额扣除已保存定金。','Same company and currency, fully delivered with deposit received. Stored deposits are deducted.') }}</p><label>{{ tx('已确认的规则说明','Confirmed rule evidence') }}<textarea v-model="settlementEvidence" rows="2" /></label><button type="button" :disabled="busy || !picked.length" @click="settleSelected">{{ tx('生成尾款草稿','Create balance draft') }}</button></div>
                <div v-show="financePane==='rebates'" class="finance-action-content"><h3>{{ tx('已确认返利','Confirmed rebates') }}</h3><p class="hint">{{ tx('只录入已确认月度金额；不自动推算返利。','Record only confirmed monthly amounts; rebate tiers are not inferred.') }}</p><div v-if="admin" class="form-grid"><label>{{ tx('年月','Month') }}<input v-model="rebateForm.month" placeholder="2026-10" /></label><label>{{ tx('金额','Amount') }}<input v-model="rebateForm.amount" inputmode="decimal" /></label><label class="finance-evidence">{{ tx('确认依据','Evidence') }}<input v-model="rebateForm.evidence" /></label><button type="button" :disabled="busy || !picked.length" @click="recordRebate">{{ tx('记入已确认返利','Record confirmed rebate') }}</button></div><div class="finance-list"><div v-for="credit in rebates.filter(c=>!financeCustomer || String(c.customer_id)===financeCustomer)" :key="credit.id" class="rebate-item"><strong>{{ credit.month }} · {{ credit.currency }} {{ credit.amount }}</strong><p>{{ tx('已用','Used') }} {{ credit.used || '0.00' }} · {{ tx('余额','Remaining') }} {{ credit.remaining || '0.00' }} · {{ credit.evidence }}</p><p v-for="oid in credit.source_order_ids" :key="oid"><RouterLink :to="{path:'/crm/projects',query:{order:oid}}">{{ orders.find(o=>o.id===oid)?.order_number }} · {{ orders.find(o=>o.id===oid)?.project_name }}</RouterLink></p><p v-for="(allocation,index) in credit.allocations" :key="index">{{ tx('已抵扣发票','Invoice allocation') }} {{ allocation.invoice_id }} · {{ allocation.amount }}</p></div></div></div>
                <div v-show="financePane==='notifications'" class="finance-action-content"><h3>{{ tx('通知记录','Notifications') }}</h3><div class="finance-list"><div v-for="item in notices.filter(n=>!financeCustomer || String(n.customer_id)===financeCustomer)" :key="item.id" class="notification-item"><span>{{ item.subject }} · {{ mailStatus(item.status) }}</span><button v-if="item.status==='not_configured'" :disabled="busy" @click="retryNotice(item.id)">{{ tx('重试','Retry') }}</button></div></div></div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.desk {
  --fs-page-title: 18px; --lh-page-title: 1.35;
  --fs-title: 15px; --lh-title: 1.5;
  --fs-heading: 13px; --lh-heading: 1.5;
  --fs-body: 13px; --lh-body: 1.55;
  --fs-meta: 12px; --lh-meta: 1.5;
  --fw-body: 400;
  --fw-emphasis: 600;
  font-size: var(--fs-body); line-height: var(--lh-body); min-width: 0; max-width: 100%;
}
.desk .card { padding: 16px; background: white; border: 1px solid #e1e6df; border-radius: 8px; }
.alert { padding: 12px 16px; background: #fae8e1; color: #842b16; border-radius: 6px; margin-bottom: 12px; }
.success { padding: 12px 16px; background: #e5efdd; color: #2d4a1e; border-radius: 6px; margin-bottom: 12px; }
.workspace-grid { display: grid; grid-template-columns: 280px 1fr; gap: 24px; align-items: start; min-width: 0; }
.order-list { display: flex; flex-direction: column; gap: 8px; position: static; min-width: 0; }
.order-list h3 { font-size: var(--fs-title); line-height: var(--lh-title); font-weight: var(--fw-emphasis); margin: 0 0 12px; }
.filter-row { font-size: var(--fs-heading); line-height: var(--lh-heading); margin-bottom: 8px; }
.filter-row select { width: 100%; margin-top: 4px; line-height: var(--lh-body); }
.order-scroll { display: flex; flex-direction: column; gap: 4px; }
.order-row { display: flex; gap: 6px; align-items: stretch; }
.pick-mark { display: flex; align-items: center; padding: 0 4px; }
.pick-mark input { width: 18px; height: 18px; margin: 0; cursor: pointer; line-height: 1; }
.order-pick { flex: 1; display: grid; gap: 4px; text-align: left; padding: 10px 12px; border: 1px solid #d5ddd6; background: #fff; color: #1b2421; border-radius: 6px; cursor: pointer; transition: all 0.2s; min-width: 0; max-width: 100%; }
.order-pick:hover { border-color: #3d6b4f; background: #f9faf8; }
.order-pick.current { border-color: #0f6e5c; background: #f4f8f2; box-shadow: 0 0 0 2px rgba(15, 110, 92, 0.1); }
.order-pick strong { font-size: var(--fs-heading); line-height: var(--lh-heading); font-weight: var(--fw-emphasis); color: #1b2421; overflow-wrap: anywhere; word-break: break-word; }
.order-pick span { font-size: var(--fs-body); line-height: var(--lh-body); color: #52615c; overflow-wrap: anywhere; word-break: break-word; }
.order-pick.current span { color: #1b2421; }
.order-pick small { font-size: var(--fs-meta); line-height: var(--lh-meta); color: #52615c; margin-top: 2px; overflow-wrap: anywhere; word-break: break-word; }
.order-pick.current small { color: #3d4a44; }
.detail-panel { display: flex; flex-direction: column;  min-width: 0; }
.section-tabs { display: flex; gap: 4px; padding: 8px; background: white; border: 1px solid #e1e6df; border-radius: 8px 8px 0 0; border-bottom: none; overflow-x: auto; -webkit-overflow-scrolling: touch; max-width: 100%; box-sizing: border-box; }
.section-tabs button { padding: 12px 16px; border: none; background: transparent; color: #3d4a44; font-size: var(--fs-heading); line-height: var(--lh-heading); font-weight: var(--fw-body); border-radius: 6px; cursor: pointer; transition: all 0.2s; white-space: nowrap; flex-shrink: 0; min-height: 44px; }
.section-tabs button:hover { background: #f5f6f2; }
.section-tabs button.active { background: #0f6e5c; color: white; }
.section-content { flex: 1; min-width: 0; }
.section-card { border-radius: 0 0 8px 8px; overflow: visible; min-width: 0; box-sizing: border-box; }
.order-detail h2, .section-card h2 { font-size: var(--fs-page-title); line-height: var(--lh-page-title); font-weight: var(--fw-emphasis); margin: 0; }
.order-detail h3, .section-card h3 { font-size: var(--fs-title); line-height: var(--lh-title); font-weight: var(--fw-emphasis); margin: 24px 0 12px; padding-bottom: 8px; border-bottom: 2px solid #e1e6df; }
.order-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 16px; padding-bottom: 16px; border-bottom: 1px solid #e1e6df; }
.company-name { font-size: var(--fs-heading); line-height: var(--lh-heading); color: #5d6b64; margin: 6px 0 0; }
.status-badges { display: flex; gap: 8px; flex-wrap: wrap; }
.badge { display: inline-block; padding: 6px 12px; background: #f5f6f2; color: #3d4a44; border-radius: 6px; font-size: var(--fs-meta); line-height: var(--lh-meta); font-weight: var(--fw-body); }
.order-meta { display: grid; gap: 8px; margin-bottom: 20px; font-size: var(--fs-body); line-height: var(--lh-body); }
.order-meta p { margin: 0; }
.table-scroll { overflow-x: auto; margin: 12px 0; max-width: 100%; -webkit-overflow-scrolling: touch; }
.table-scroll table { width: 100%; min-width: 600px; border-collapse: collapse; }
@media (max-width: 390px) {
  .table-scroll table { min-width: 100%; width: max-content; }
}
th, td { text-align: left; border-bottom: 1px solid #e1e6df; padding: 12px 10px; font-size: var(--fs-body); line-height: var(--lh-body); vertical-align: top; }
th { background: #f9faf8; font-weight: var(--fw-emphasis); color: #1b2421; }
td strong, .desk strong, .desk b, .desk h1, .desk h2, .desk h3, .desk h4, .desk h5, .desk h6 { font-weight: var(--fw-emphasis); }
td small { display: block; color: #5d6b64; font-size: var(--fs-meta); line-height: var(--lh-meta); margin-top: 4px; }
td input { width: 80px; padding: 6px 8px; border: 1px solid #d5ddd6; border-radius: 4px; font-size: var(--fs-body); line-height: var(--lh-body); }
.provider-section, .adjustment-section { margin-top: 20px; padding-top: 20px; border-top: 1px solid #e1e6df; }
.form-row { display: flex; gap: 12px; align-items: end; flex-wrap: wrap; margin-bottom: 12px; }
.form-row label { flex: 1; min-width: 180px; font-size: var(--fs-body); line-height: var(--lh-body); }
.form-row button { flex-shrink: 0; }
.actions { display: flex; flex-wrap: wrap; gap: 12px; align-items: end; margin-top: 12px; }
.actions label { min-width: 200px; font-size: var(--fs-body); line-height: var(--lh-body); }
.desk input, .desk textarea, .desk button { line-height: var(--lh-body); }
.desk input, .desk select, .desk textarea { width: 100%; box-sizing: border-box; padding: 10px 12px; border: 1px solid #d5ddd6; border-radius: 6px; font-size: var(--fs-body); font-family: inherit; min-width: 0; max-width: 100%; min-height: 44px; height: auto; }
.desk select {
  -webkit-appearance: none;
  appearance: none;
  line-height: var(--lh-body);
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 16 16'%3E%3Cpath fill='%2352615c' d='M4 6l4 4 4-4z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
  padding-right: 30px;
}
.desk select:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.desk option { line-height: var(--lh-body); }
.desk button { min-height: 44px; padding: 10px 18px; border: 1px solid #0f6e5c; background: #0f6e5c; color: white; border-radius: 6px; font-size: var(--fs-body); font-weight: var(--fw-body); cursor: pointer; transition: all 0.2s; }
.desk button:hover:not(:disabled) { background: #0d5a4a; border-color: #0d5a4a; }
.desk button.secondary { background: white; color: #3d4a44; border-color: #d5ddd6; }
.desk button.secondary:hover:not(:disabled) { background: #f5f6f2; border-color: #c5d0c8; }
.desk button:disabled { opacity: 0.5; cursor: not-allowed; }
.desk label { display: block; font-size: var(--fs-body); line-height: var(--lh-body); font-weight: var(--fw-body); color: #1b2421; }
.desk label input, .desk label select, .desk label textarea { margin-top: 6px; }
.hint { color: #5d6b64; font-size: var(--fs-body); line-height: var(--lh-body); margin: 8px 0; }
.form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin-top: 16px; }
.form-grid button { grid-column: 1 / -1; justify-self: start; }
@media (max-width: 600px) {
  .form-grid { grid-template-columns: 1fr; }
}
.invoice { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; padding: 12px; background: #f9faf8; border-radius: 6px; margin-top: 8px; font-size: var(--fs-body); line-height: var(--lh-body); }
.invoice label { margin: 0; display: flex; align-items: center; gap: 8px; line-height: var(--lh-body); }
.invoice input[type="checkbox"] { line-height: 1; }
.provider-list, .template-list { display: grid; gap: 12px; margin-top: 16px; }
.provider-card, .template-card { padding: 16px; background: #f9faf8; border: 1px solid #e1e6df; border-radius: 6px; min-width: 0; max-width: 100%; }
.provider-card h4, .template-card h4 { font-size: var(--fs-heading); line-height: var(--lh-heading); font-weight: var(--fw-emphasis); margin: 0 0 12px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; overflow-wrap: anywhere; word-break: break-word; }
.provider-card p, .template-card p { overflow-wrap: anywhere; word-break: break-word; }
.status-active { color: #0f6e5c; font-size: var(--fs-meta); line-height: var(--lh-meta); font-weight: var(--fw-body); }
.status-inactive { color: #8a3b2c; font-size: var(--fs-meta); line-height: var(--lh-meta); font-weight: var(--fw-body); }
.provider-badge { padding: 4px 8px; background: #e1e6df; color: #3d4a44; border-radius: 4px; font-size: var(--fs-meta); line-height: var(--lh-meta); font-weight: var(--fw-body); }
.edit-form { display: grid; gap: 12px; }
.checkbox-label { display: flex; align-items: center; gap: 8px; font-weight: normal; }
.checkbox-label input { width: auto; margin: 0; line-height: 1; }
.button-group { display: flex; gap: 8px; }
.template-form { margin-top: 16px; padding-top: 16px; border-top: 1px solid #e1e6df; }
.template-form h4 { font-size: var(--fs-heading); line-height: var(--lh-heading); font-weight: var(--fw-emphasis); margin: 16px 0 8px; }
.mapping-controls { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
.mapping-controls select, .mapping-controls input { flex: 1; line-height: var(--lh-body); }
.mappings-list { display: grid; gap: 6px; margin: 12px 0; padding: 12px; background: #f9faf8; border-radius: 6px; }
.mapping-item { display: flex; justify-content: space-between; align-items: center; padding: 8px; background: white; border-radius: 4px; }
.link-button { background: none; border: none; color: #0f6e5c; padding: 4px 8px; min-height: auto; text-decoration: underline; cursor: pointer; font-size: var(--fs-body); line-height: var(--lh-body); }
.mapping-display { display: grid; gap: 4px; margin-top: 8px; font-size: var(--fs-meta); line-height: var(--lh-meta); }
.batch-actions { display: flex; gap: 12px; margin: 16px 0; flex-wrap: wrap; }
.notification-item, .rebate-item { padding: 12px; background: #f9faf8; border-radius: 6px; margin-top: 8px; display: flex; justify-content: space-between; align-items: center; gap: 12px; }
/* A long unbroken reference must break inside the text instead of pushing the row past the viewport.
   min-width:0 lets the flex item shrink below its content width; flex-wrap would break the line
   before shrinking, which drops the action button onto its own row, so it is deliberately not used. */
.notification-item > span, .rebate-item > span { min-width: 0; overflow-wrap: anywhere; word-break: break-word; }
.notification-item > button, .rebate-item > button { flex-shrink: 0; }
/* Status and prose paragraphs in the detail panel carry machine values - template SHAs,
   invoice references, error text - that have no break opportunity. Every ancestor here is
   overflow-x:visible, so one long token reaches the root and scrolls the whole page sideways. */
.desk .section-content p, .desk .template-status { overflow-wrap: anywhere; word-break: break-word; }
@media (max-width: 1000px) {
  .workspace-grid { grid-template-columns: 1fr; }
  .order-list { position: static; max-height: none; }
  .section-card { max-height: none; }
}
@media (max-width: 760px) {
  .workspace-grid { grid-template-columns: minmax(0, 1fr); }
  .order-list, .detail-panel, .section-content, .section-card { min-width: 0; }
  .desk .card { width: 100%; box-sizing: border-box; }
  .order-detail, .provider-list, .template-list { min-width: 0; }
}
@media (max-width: 390px) {
  .workspace-grid { gap: 12px; grid-template-columns: minmax(0, 1fr); }
  .desk .card { padding: 12px; min-width: 0; max-width: 100%; width: 100%; box-sizing: border-box; }
  .order-list { max-height: none; min-width: 0; width: 100%; }
  .detail-panel { min-width: 0; width: 100%; }
  .section-tabs { padding: 6px; gap: 2px; min-width: 0; }
  .section-tabs button { padding: 11px 12px; font-size: var(--fs-meta); line-height: var(--lh-meta); min-height: 44px; }
  .section-content { min-width: 0; width: 100%; }
  .section-card { min-width: 0; width: 100%; }
  .form-grid { grid-template-columns: 1fr; }
  .form-row, .actions, .batch-actions { flex-direction: column; align-items: stretch; min-width: 0; }
  .form-row button, .actions button { width: 100%; box-sizing: border-box; }
  .form-row label, .actions label { min-width: 0; max-width: 100%; width: 100%; box-sizing: border-box; }
  .desk input, .desk select, .desk textarea { font-size: var(--fs-body); line-height: var(--lh-body); width: 100%; box-sizing: border-box; }
  .desk button { font-size: var(--fs-body); line-height: var(--lh-body); }
  .mapping-controls { flex-direction: column; min-width: 0; }
  .mapping-controls select, .mapping-controls input, .mapping-controls button { width: 100%; box-sizing: border-box; }
  .order-row { min-width: 0; }
  .order-scroll { min-width: 0; }
  .order-detail { min-width: 0; width: 100%; }
  .provider-list, .template-list { min-width: 0; width: 100%; }
  .provider-card, .template-card { min-width: 0; width: 100%; box-sizing: border-box; }
  .order-header { flex-wrap: wrap; }
  .order-meta { min-width: 0; }
  .table-scroll { min-width: 0; width: 100%; overflow-x: auto; }
}

/* Navigation rows are distinct from action buttons. */
.desk { color: #24342e; }
.desk .card { border-color: #e0e7e3; border-radius: 12px; padding: 22px; box-shadow: 0 2px 8px #1a382b04; }
.list-heading { display: flex; align-items: center; justify-content: space-between; }
.list-heading h3 { margin: 0; font-size: var(--fs-title); line-height: var(--lh-title); font-weight: var(--fw-emphasis); }
.list-heading > span { font-size: var(--fs-meta); line-height: var(--lh-meta); background: #eef3f0; padding: 2px 8px; border-radius: 20px; color: #52615c; }
.desk .order-pick { background: transparent; border: 1px solid transparent; color: #24342e; padding: 12px; border-radius: 8px; gap: 3px; min-height: 0; box-shadow: none; }
.desk .order-pick:hover:not(:disabled) { background: #f3f6f4; border-color: #e0e7e3; }
.desk .order-pick.current { background: #edf5f1; border-color: #b8d7c9; box-shadow: inset 3px 0 #237356; }
.desk .order-pick strong { font-size: var(--fs-heading); line-height: var(--lh-heading); font-weight: var(--fw-emphasis); color: #203c30; }
.desk .order-pick span, .desk .order-pick small { color: #53655d; font-size: var(--fs-meta); line-height: var(--lh-meta); }
.desk .pick-mark { display: flex; align-items: center; margin: 0; padding: 0 3px; }
.desk .pick-mark input { width: 15px; height: 15px; min-height: 0; margin: 0; accent-color: #237356; line-height: 1; }
.desk .section-tabs { flex-wrap: wrap; overflow: visible; gap: 4px; border: 0; border-bottom: 1px solid #dce5df; background: transparent; padding: 0 0 12px; margin-bottom: 16px; border-radius: 0; }
.desk .section-tabs button { background: transparent; color: #52615c; border: 0; padding: 11px 12px; min-height: 44px; border-radius: 7px; font-size: var(--fs-body); line-height: var(--lh-body); font-weight: var(--fw-body); }
.desk .section-tabs button.active { background: #e5f0e9; color: #17523a; font-weight: var(--fw-emphasis); }
.desk button:focus-visible { outline: 2px solid #237356; outline-offset: 3px; }
.desk .section-card { border-radius: 12px; max-height: none; }
.desk .order-header { margin-bottom: 20px; padding-bottom: 20px; }
.desk .order-detail h2, .desk .section-card h2 { font-size: var(--fs-page-title); line-height: var(--lh-page-title); font-weight: var(--fw-emphasis); letter-spacing: -.02em; }
.desk .order-detail h3, .desk .section-card h3 { font-size: var(--fs-title); line-height: var(--lh-title); font-weight: var(--fw-emphasis); margin: 24px 0 12px; border-bottom-width: 1px; }
.desk .badge { padding: 4px 9px; border-radius: 20px; font-size: var(--fs-meta); line-height: var(--lh-meta); background: #eff4f1; }
.desk .actions { gap: 8px; }
.desk .form-row { gap: 12px; }
.desk label { font-size: var(--fs-body); line-height: var(--lh-body); }
.desk input, .desk select, .desk textarea { background-color: #fff; min-height: 44px; border-color: #cdd9d1; border-radius: 7px; }
.desk .provider-card, .desk .template-card { background: #f8faf9; padding: 18px; border-radius: 10px; }
@media (max-width: 1000px) { .workspace-grid { grid-template-columns: minmax(0,1fr); } .order-scroll { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); } }
@media (max-width: 600px) { .order-scroll { display: flex; } .desk .card { padding: 16px; } .desk .section-tabs { gap: 3px; } .desk .section-tabs button { padding: 11px 10px; font-size: var(--fs-meta); line-height: var(--lh-meta); min-height: 44px; font-weight: var(--fw-body); } }

.detail-tabs { display: flex; flex-wrap: wrap; gap: 6px; margin: 16px 0; border-bottom: 1px solid #e0e7e3; padding-bottom: 12px; }
.desk .detail-tabs button { background: transparent; color: #52615c; border: 0; padding: 10px 10px; min-height: 44px; font-size: var(--fs-body); line-height: var(--lh-body); font-weight: var(--fw-body); }
.desk .detail-tabs button.active { background: #edf5f1; color: #17523a; font-weight: var(--fw-emphasis); }
.desk th { white-space: nowrap; font-size: var(--fs-meta); line-height: var(--lh-meta); }
.desk td:first-child { min-width: 170px; }
.desk .order-meta { grid-template-columns: 1fr auto; padding: 12px 0; border-bottom: 1px solid #edf1ee; }
.desk .provider-section { border: 0; margin-top: 0; padding-top: 0; }
@media(max-width:600px) { .desk .order-meta { grid-template-columns: 1fr; } }

.list-pagination { display: flex; align-items: center; justify-content: space-between; padding-top: 12px; border-top: 1px solid #edf1ee; margin-top: 8px; color: #52615c; font-size: var(--fs-meta); line-height: var(--lh-meta); }
.desk .list-pagination button { background: #fff; color: #315844; border-color: #dce5df; padding: 11px 10px; min-height: 44px; font-size: var(--fs-meta); line-height: var(--lh-meta); font-weight: var(--fw-body); }

.mobile-project-picker { display: none; }
@media(max-width:600px) {
  .mobile-project-picker { display: grid; gap: 10px; }
  .order-list:not(.mobile-expanded) .order-scroll, .order-list:not(.mobile-expanded) .list-pagination { display: none; }
  .order-list:not(.mobile-expanded) .filter-row { display: none; }
  .order-list .filter-row { margin: 0; }
  .desk .mobile-project-picker button { justify-self: start; font-size: var(--fs-meta); line-height: var(--lh-meta); padding: 11px 10px; min-height: 44px; font-weight: var(--fw-body); }
}

/* Keep navigation hover colors independent of primary action buttons. */
.desk .section-tabs button:hover:not(:disabled),
.desk .detail-tabs button:hover:not(:disabled) { background: #edf3ef; color: #234b37; border-color: transparent; }
.desk .section-tabs button.active:hover:not(:disabled),
.desk .detail-tabs button.active:hover:not(:disabled) { background: #dcebe1; color: #17432d; }
.desk .order-pick:hover:not(:disabled) { color: #24342e; }
.desk .list-pagination button:hover:not(:disabled) { background: #edf3ef; color: #234b37; border-color: #bfd1c5; }
.desk .link-button:hover:not(:disabled) { background: #edf3ef; color: #17432d; }
.global-workspace .workspace-grid{grid-template-columns:minmax(0,1fr)}
.global-workspace .detail-panel{width:100%;min-width:0}.global-workspace .section-card{max-width:1200px;margin:0 auto}
.template-card,.template-status{overflow-wrap:anywhere}.checkbox-label{display:flex;align-items:center;gap:8px;min-height:44px}.checkbox-label input[type=checkbox]{width:20px;height:20px;min-height:20px;flex:none}
.batch-toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:12px}.batch-toolbar button,.global-workspace button{min-height:44px}.finance-order{display:flex;flex-wrap:wrap;gap:12px;align-items:center;border-bottom:1px solid #e1e6df;padding:8px 0}.finance-order label{margin:0}.highlight{border:2px solid #17523a}.global-workspace a{color:#17523a;text-decoration:underline}.global-workspace select{max-width:100%}
@media(max-width:700px){.global-workspace .section-card{padding:12px}.global-workspace .form-grid{grid-template-columns:minmax(0,1fr)}.global-workspace .mapping-controls{display:flex;flex-wrap:wrap}.global-workspace .mapping-controls>*{min-width:0;max-width:100%}.finance-order{display:block}}
.global-workspace .template-card{padding:14px;margin-top:12px}.global-workspace .template-card h3,.global-workspace .template-card h4{margin:8px 0}.global-workspace .template-card p{margin:6px 0}.resource-orders{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px 16px}.resource-orders p{margin:0!important}.resource-orders a{min-height:44px}.pick-mark{min-width:44px;min-height:44px}.global-workspace .template-card>.checkbox-label{display:inline-flex;margin-right:20px}@media(max-width:700px){.resource-orders{grid-template-columns:minmax(0,1fr)}}
.desk .order-pick{grid-template-columns:minmax(0,1fr);justify-content:stretch;justify-items:stretch;text-align:left;min-height:44px}
.desk .order-pick>strong,.desk .order-pick>span,.desk .order-pick>small{display:block;width:100%;min-width:0;text-align:left}
.desk .pick-mark{flex:0 0 44px;justify-content:center}
.invoice-actions{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin-top:12px}.invoice-actions a{min-height:44px;color:#17523a}.desk .invoice{padding:12px;margin:8px 0}.desk .invoice label{justify-content:flex-start;min-height:44px;gap:10px}.desk .invoice p{margin:4px 0}.desk .section-card h2{margin:0 0 12px}.desk .section-card h3{margin:16px 0 10px}.desk .detail-tabs{gap:6px}.desk .form-grid{gap:12px}.desk .form-grid button{justify-self:start}
.next-action{background:#eef5ef;border:1px solid #c8ddcd;border-radius:8px;padding:12px 14px;margin:12px 0;display:flex;align-items:center;flex-wrap:wrap;gap:8px 16px}.next-action strong{font-size:14px}.next-action p{margin:0;flex:1 1 260px;line-height:1.5}.provider-advanced{align-self:center}.provider-advanced summary{cursor:pointer;min-height:44px;display:flex;align-items:center;color:#17523a}.provider-advanced button{margin-top:8px}

/* Dense, consistent task workspaces. Controls retain a 44px target. */
.desk .card{padding:16px}
@media(min-width:1001px){.desk:not(.global-workspace) .workspace-grid{grid-template-columns:285px minmax(0,1fr);gap:12px}.desk .order-list{max-height:calc(100vh - 174px);overflow:hidden}.desk .order-scroll{overflow-y:auto;min-height:0}}
.desk .order-list{gap:6px}
.desk .order-row{position:relative;display:block;min-width:0}
.desk .pick-mark{position:absolute;z-index:2;left:2px;top:0;bottom:0;width:44px;min-width:44px;padding:0;display:flex;align-items:center;justify-content:center}
.desk .pick-mark input{width:18px;height:18px;min-height:18px;flex:0 0 18px}
.desk .order-pick{box-sizing:border-box;width:100%;min-height:76px;padding:6px 8px 6px 48px;display:grid;grid-template-columns:auto minmax(0,1fr);grid-template-rows:auto auto auto;align-items:center;column-gap:8px;row-gap:1px}
.desk .order-pick>strong,.desk .order-pick>span,.desk .order-pick>small{width:auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;line-height:1.25}
.desk .order-pick>strong{grid-column:1/-1;grid-row:1;font-size:13px}
.desk .order-pick>span:first-of-type{grid-column:1;grid-row:2;font-variant-numeric:tabular-nums}
.desk .order-pick>span:nth-of-type(2){grid-column:2;grid-row:2}
.desk .order-pick>small{grid-column:1/-1;grid-row:3;margin:0;text-align:left;max-width:none}
.desk .order-header{margin-bottom:8px;padding-bottom:8px}
.desk .order-meta{margin-bottom:8px;padding:6px 0}
.desk .next-action{margin:8px 0;padding:8px 10px}
.desk .detail-tabs{margin:6px 0 10px;padding-bottom:6px}
.desk .order-detail h3,.desk .section-card h3{margin:12px 0 6px;padding-bottom:4px}
.desk .table-scroll{margin:6px 0}
.desk th,.desk td{padding:6px 8px}
.desk .adjustment-section{margin-top:8px;padding-top:8px}
.desk .adjustment-section .table-scroll{max-height:min(205px,calc(100vh - 540px));overflow-y:auto}
.desk .adjustment-section thead th{position:sticky;top:0;z-index:1}
.review-footer{display:flex;align-items:end;gap:8px;flex-wrap:wrap;margin-top:8px}
.review-footer label{flex:1 1 200px;min-width:200px}
.review-footer button{flex:0 0 auto;white-space:nowrap}
.desk .review-footer .secondary{background:#fff;color:#17523a;border-color:#c9d8ce}
.finance-header{display:flex;align-items:end;justify-content:space-between;gap:12px;margin-bottom:12px}
.finance-header label{width:min(300px,100%)}
.finance-grid{display:grid;grid-template-columns:minmax(0,.85fr) minmax(0,1.05fr) minmax(0,1.1fr);gap:10px;min-width:0}
.finance-panel{height:min(594px,calc(100vh - 280px));min-height:360px;display:flex;flex-direction:column;min-width:0;border:1px solid #dce5df;border-radius:8px;background:#fff;overflow:hidden}
.finance-panel-head{display:flex;align-items:center;justify-content:space-between;padding:10px 12px;border-bottom:1px solid #e4eae5}
.desk .finance-panel-head h3{margin:0;padding:0;border:0;font-size:14px}
.finance-panel-head span{color:#52635a;font-size:12px}
.finance-list{flex:1;min-height:0;overflow-y:auto;padding:4px 10px;overflow-wrap:anywhere}
.finance-panel-foot{padding:10px;border-top:1px solid #e4eae5}
.finance-panel-foot button{width:100%}
.finance-order{display:block;padding:8px 0;border-bottom:1px solid #e4eae5}
.finance-order label{min-height:32px}
.finance-order a{display:block;padding-left:28px;line-height:1.35}
.desk .finance-panel .invoice{display:block;padding:8px;margin:6px 0}
.finance-panel .invoice label{line-height:1.35}
.finance-panel .invoice p{padding-left:28px}
.finance-panel .invoice input:not([type=checkbox]){margin-top:6px}
.finance-panel .invoice button{margin-top:6px}
.finance-pane-tabs{display:flex;gap:4px;padding:8px;border-bottom:1px solid #e4eae5}
.desk .finance-pane-tabs button{flex:1;min-width:0;padding:8px 4px;background:#f4f7f5;color:#315844;border-color:transparent}
.desk .finance-pane-tabs button.active{background:#dcece2;color:#17462f;font-weight:600}
.finance-action-content{flex:1;min-height:0;overflow-y:auto;padding:10px 12px}
.desk .finance-action-content h3{margin:0 0 6px;padding:0;border:0;font-size:14px}
.finance-action-content>.hint{margin:0 0 10px}
.finance-action-content>button{margin-top:8px;width:100%}
.finance-action-content .form-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
.finance-action-content .finance-evidence,.finance-action-content .form-grid button{grid-column:1/-1}
.finance-action-content .finance-list{padding:8px 0;overflow:visible}
@media(max-width:1100px){.finance-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.finance-action-panel{grid-column:1/-1;height:auto;min-height:280px}.finance-action-content{max-height:420px}}
@media(max-width:700px){.finance-header{display:block}.finance-header label{display:block;margin-top:10px;width:100%}.finance-grid{display:block}.finance-panel{height:auto;min-height:0;margin-top:10px}.finance-list{max-height:none;overflow:visible}.finance-action-content{max-height:none;overflow:visible}.review-footer{display:grid;grid-template-columns:minmax(0,1fr)}.review-footer label,.review-footer button{width:100%;min-width:0}.desk .order-pick>small{max-width:125px}}
.detail-navigation{display:flex;align-items:center;gap:8px;min-width:0;border-bottom:1px solid #e0e7e3;margin:4px 0 8px}
.desk .detail-navigation .detail-tabs{flex:0 0 auto;margin:0;padding:0;border:0}
.desk .detail-navigation .next-action{flex:1;min-width:0;margin:4px 0;padding:6px 10px;background:#eef6fb;border:1px solid #c9e1ee;border-radius:7px;color:#244d60;gap:4px 8px;font-size:12px}
.detail-navigation .next-action strong{font-size:12px;white-space:nowrap}
.detail-navigation .next-action p{flex:1 1 160px}
.detail-navigation .next-action button{padding:6px 8px;min-height:44px}
.desk .order-pick>span:first-of-type{grid-column:1;white-space:nowrap}
.desk .order-pick>span:nth-of-type(2){grid-column:2;white-space:nowrap}
@media(min-width:1001px){.desk .order-list{margin-top:0}}
@media(max-width:1250px){.detail-navigation{display:block}.desk .detail-navigation .next-action{margin:2px 0 6px}}
.order-identity{display:flex;align-items:center;gap:8px;margin:4px 0 0;flex-wrap:wrap;font-size:12px;line-height:1.3}
.order-identity span{color:#53655d}
</style>

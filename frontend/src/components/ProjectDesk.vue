<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import { request, session } from "../crm-api";
import ManualInvoiceForm from "./ManualInvoiceForm.vue";

interface Line {
  rule_version?: string;
  id: string;
  window_name: string;
  product_id?: number;
  product_name?: string;
  source_code?: string;
  width_mm?: string | number;
  height_mm?: string | number;
  panel_count?: number;
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
  invoice_number?: string;
  created_at?: string;
  received_at?: string;
}
interface ShipmentOrder { id: string; order_number?: string; company?: string; project_name: string; status: string; eta?: string; factory_price_usd?: string | null; measured_sqm?: string | null; purchase_cost?: string | null; freight_cost?: string | null; duty_cost?: string | null; duty_basis?: string | null; }
interface Shipment { id: string; name: string; eta?: string | null; status: string; created_at?: string; arrived_at?: string; order_ids: string[]; orders?: ShipmentOrder[]; freight_land?: string; freight_sea?: string; duty_total?: string | null; invoice_ids?: string[]; }
interface ShipmentCandidate { id: string; order_number?: string; company: string; project_name: string; eta?: string; deposit_paid_at?: string; }
interface MailPreview {
  invoice_id: string;
  subject: string;
  body: string;
  html: string;
  attachment: string;
  invoice_number: string;
  customer_recipient: string;
  email_mode: string;
  delivery_enabled: boolean;
  delivered_to: string;
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
  order_number_confirmed?: boolean;
  id: string;
  customer_id: number;
  company: string;
  contact_name?: string;
  phone?: string;
  email?: string;
  company_address?: string;
  customer_type?: 'retail' | 'wholesale';
  project_name: string;
  site_address: string;
  created_at?: string;
  deposit_paid_at?: string;
  ready_at?: string;
  completed_at?: string;
  eta?: string;
  batch_name?: string;
  status: string;
  payment_status: string;
  arrival_status?: string;
  delivery_status?: string;
  subtotal?: string | null;
  installation?: string | null;
  installation_required?: boolean;
  tax?: string | null;
  total: string | null;
  deposit?: string | null;
  currency?: string;
  supplier_reference?: string;
  lead_time?: { text?: string } | string;
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
const financePane = ref<'rebates'|'notifications'>('rebates');
const customers = ref<{customer_id:number;company:string;customer_code?:string;customer_type?:'retail'|'wholesale'}[]>([]);
const financeOrders = computed(()=>orders.value.filter(o=>!financeCustomer.value || String(o.customer_id)===financeCustomer.value));
const financeInvoices = computed(()=>invoices.value.filter(i=>!financeCustomer.value || String(i.customer_id)===financeCustomer.value));
// Finance page work queues: each order or invoice lands in the one step that needs a staff action, or in "waiting"/"done".
const SENT_INVOICE_STATES = ['sent','demo_sent','demo_suppressed','sending'];
const invoiceSent = (invoice: Invoice) => SENT_INVOICE_STATES.includes(invoice.status);
const allLinesArrived = (order: ProjectOrder) => order.lines.every((line) => line.arrived === line.quantity);
const balanceInvoiceFor = (order: ProjectOrder) => invoices.value.find((invoice) => invoice.kind === 'balance' && invoice.order_ids?.includes(order.id));
const depositInvoiceFor = (order: ProjectOrder) => invoices.value.find((invoice) => invoice.kind === 'deposit' && invoice.order_ids?.includes(order.id)) || order.invoices?.find((invoice) => invoice.kind === 'deposit');
const financeQueues = computed(() => {
  const depositDue = financeOrders.value.filter((order) => order.status !== 'pending_review' && order.payment_status === 'deposit_unpaid');
  const depositDueIds = new Set(depositDue.map((order) => order.id));
  const balanceReady = financeOrders.value.filter((order) => order.payment_status === 'deposit_received' && allLinesArrived(order) && !balanceInvoiceFor(order));
  // A deposit invoice for an order still in step 1 is sent from step 1, so it is not listed twice.
  const toSend = financeInvoices.value.filter((invoice) => !invoiceSent(invoice) && invoice.payment_status !== 'received' &&
    !(invoice.kind === 'deposit' && invoice.order_ids?.some((id) => depositDueIds.has(id))));
  const balanceDue = financeInvoices.value.filter((invoice) => invoice.kind === 'balance' && invoiceSent(invoice) && invoice.payment_status !== 'received');
  const done = financeInvoices.value.filter((invoice) => invoice.payment_status === 'received');
  const active = new Set([...depositDue, ...balanceReady].map((order) => order.id));
  for (const invoice of [...toSend, ...balanceDue]) for (const id of invoice.order_ids || []) active.add(id);
  const waiting = financeOrders.value.filter((order) => !active.has(order.id));
  return { depositDue, balanceReady, toSend, balanceDue, done, waiting };
});
const financeSteps = computed(() => [
  { key: 'deposit', no: '1', title: tx('确认定金到账', 'Confirm deposits'), count: financeQueues.value.depositDue.length },
  { key: 'balance', no: '2', title: tx('开尾款', 'Create balance invoices'), count: financeQueues.value.balanceReady.length },
  { key: 'send', no: '3', title: tx('发送发票', 'Send invoices'), count: financeQueues.value.toSend.length },
  { key: 'receipt', no: '4', title: tx('确认尾款收款', 'Confirm balance receipts'), count: financeQueues.value.balanceDue.length },
]);
const financeTodoTotal = computed(() => financeSteps.value.reduce((sum, step) => sum + step.count, 0));
const balancePicked = computed(() => picked.value.filter((id) => financeQueues.value.balanceReady.some((order) => order.id === id)));
const rebatePick = ref<string[]>([]);
const sendLabel = computed(() => props.emailMode === 'demo' ? (props.emailEnabled ? tx('发送演示邮件（仅自己）', 'Send demo email to owner only') : tx('记录模拟发送（不投递）', 'Record demo send (no delivery)')) : tx('发送', 'Send'));
function financeWaitingReason(order: ProjectOrder) {
  if (order.status === 'pending_review') return tx('待审核，在订单页处理', 'Awaiting review on the orders page');
  const balance = balanceInvoiceFor(order);
  if (balance?.payment_status === 'received' || order.payment_status === 'paid') return tx('已结清', 'Settled');
  if (balance) return tx('尾款已开', 'Balance invoiced');
  if (order.payment_status === 'deposit_received' && !allLinesArrived(order)) return tx(`定金已收，等待到货（${orderStatus(order.status)}）`, `Deposit received; waiting for arrival (${orderStatus(order.status)})`);
  return orderStatus(order.status);
}
function scrollFinanceStep(key: string) { document.getElementById(`fin-${key}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
function previewOneInvoice(invoice: Invoice) { invoicePick.value = [invoice.id]; return previewInvoiceMail(); }
function sendOneInvoice(invoice: Invoice) { invoicePick.value = [invoice.id]; return sendSelectedInvoices(); }
function settleReadyOrders() { picked.value = [...balancePicked.value]; return settleSelected(); }
async function recordRebateForPick() {
  const balanceSelection = [...picked.value];
  picked.value = [...rebatePick.value];
  await recordRebate();
  if (!error.value) rebatePick.value = [];
  picked.value = balanceSelection.filter((id) => financeQueues.value.balanceReady.some((order) => order.id === id));
}
const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);
const orders = ref<ProjectOrder[]>([]);
const invoices = ref<Invoice[]>([]);
const shipments = ref<Shipment[]>([]);
const shipmentCandidates = ref<ShipmentCandidate[]>([]);
const projectPane = ref<'orders'|'shipments'|'overview'>('orders');
const shipmentPick = ref<string[]>([]);
const shipmentForm = reactive({ name: '', eta: '' });
const shipmentEta = reactive<Record<string, string>>({});
const shipmentCosts = reactive<Record<string, { freight_land: string; freight_sea: string; duty_total: string }>>({});
const purchaseForm = reactive<Record<string, { usd: string; sqm: string }>>({});
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
const fulfilError = ref("");
const statusFilter = ref("");
const picked = ref<string[]>([]);
const invoicePick = ref<string[]>([]);
const mailPreview = ref<MailPreview | null>(null);
const transitRows = ref<{ order_id: string; status: string; reason?: string }[]>([]);
const arrivalRows = ref<{ order_id: string; status: string; detail: string }[]>([]);
const batch = reactive<Record<string, number>>({});
const orderNumberConfirmation = reactive<Record<string, boolean>>({});
const operationKeys = new Map<string, string>();
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
const pageCount = computed(() => Math.max(1, Math.ceil(visibleOrders.value.length / 6)));
const pageOrders = computed(() => visibleOrders.value.slice(Math.min(listPage.value, pageCount.value - 1) * 6, (Math.min(listPage.value, pageCount.value - 1) + 1) * 6));
const selectedId = ref(String(route.query.order || ''));
const detailSection = ref("order");
const selectedOrder = computed(() => visibleOrders.value.find((order) => order.id === selectedId.value) || visibleOrders.value[0] || null);
const selectedIsWholesale = computed(() => selectedOrder.value?.customer_type === 'wholesale' ||
  (!selectedOrder.value?.customer_type && customers.value.find(c => c.customer_id === selectedOrder.value?.customer_id)?.customer_type !== 'retail'));
function quoteMoney(amount?: string | null, currency = "NZD") {
  if (amount == null || amount === "") return "—";
  const value = Number(amount);
  return Number.isFinite(value) ? `${currency} ${value.toFixed(2)}` : `${currency} ${amount}`;
}
function quoteDate(value?: string) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(locale.value === "zh" ? "zh-NZ" : "en-NZ", { dateStyle: "medium" }).format(date);
}
function quoteBalance(order: ProjectOrder) {
  if (order.total == null || order.deposit == null) return "—";
  const amount = Number(order.total) - Number(order.deposit);
  return Number.isFinite(amount) ? quoteMoney(amount.toFixed(2), order.currency || "NZD") : "—";
}
watch(()=>selectedOrder.value?.id,()=>{if(props.workspace==='projects') invoicePick.value=[];fulfilError.value=''});
watch(invoicePick,()=>{mailPreview.value=null});
watch(picked, () => {
  // Refresh the generated text for a new selection, but never overwrite wording the user changed.
  if (!settlementEvidence.value.trim() || settlementEvidence.value === lastAutoEvidence) fillEvidence();
}, { deep: true });
watch(()=>selectedOrder.value?.invoices?.map(i=>`${i.id}:${i.status}`).join('|'),()=>{
  if(props.workspace!=='projects') return;
  const drafts=selectedOrder.value?.invoices?.filter(i=>i.status==='draft') || [];
  invoicePick.value=drafts.length===1?[drafts[0].id]:[];
},{immediate:true});
function nextOrderSection(order: ProjectOrder): string {
  if (order.status === 'pending_review') return 'order';
  if (order.payment_status === 'deposit_unpaid') return 'invoices';
  if (order.status === 'accepted') return 'supplier';
  return 'order';
}
const nextOrderHint = computed(() => {
  const order=selectedOrder.value;
  if (!order) return '';
  if (order.status==='pending_review') return tx('核对价格和配置，再确认接收。','Check price and configuration, then accept review.');
  if (order.payment_status==='deposit_unpaid') return tx('定金发票已生成；核实到账后记录定金已收。','The deposit invoice is ready; record receipt only after funds are confirmed.');
  if (order.status==='accepted') return tx('定金确认后下载供应商订单，再标为已下单。','After the deposit is confirmed, download the supplier order, then mark it ordered.');
  if (order.status==='supplier_ordered') return tx('供应商下单已记录；可将订单标为在途。','Supplier order recorded; mark it in transit when dispatched.');
  if (order.status==='in_transit'||order.status==='partially_arrived') return tx('所有货物到齐后，记录整单到货。','Record the whole order as arrived once all goods are in.');
  if (order.status==='arrived'||order.status==='ready'||order.status==='partially_delivered') return tx('货物已到，可记录提货或完成；账款在财务页单独跟进。','Goods are ready; record collection or completion. Track payment separately in finance.');
  return tx('订单已完成；在账款与返利中处理尾款。','Order completed; complete the balance in Accounts & rebates.');
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
  const [listed, billed, mailed, credits, providerList, templateList, versions, companies, shipmentList, candidates] = await Promise.all([
    request<ProjectOrder[]>("operations/orders"),
    request<Invoice[]>("operations/invoices"),
    request<Notice[]>("operations/notifications"),
    request<{ calculation_status: string; credits: Rebate[] }>("operations/rebates"),
    request<Provider[]>("operations/providers"),
    request<ProviderTemplate[]>("operations/provider-templates"),
    request<PricingVersion[]>("operations/pricing-templates"),
    request<{customer_id:number;company:string}[]>("operations/customers"),
    request<Shipment[]>("operations/shipments"),
    request<ShipmentCandidate[]>("operations/shipments/candidates"),
  ]);
  orders.value = listed;
  invoices.value = billed;
  notices.value = mailed;
  rebates.value = credits.credits;
  providers.value = providerList;
  providerTemplates.value = templateList;
  pricingVersions.value = versions;
  customers.value = companies;
  shipments.value = shipmentList;
  shipmentCandidates.value = candidates;
  for (const shipment of shipmentList) {
    shipmentEta[shipment.id] = shipment.eta || '';
    shipmentCosts[shipment.id] ||= { freight_land: shipment.freight_land || '', freight_sea: shipment.freight_sea || '', duty_total: shipment.duty_total || '' };
    for (const order of shipment.orders || []) purchaseForm[order.id] = { usd: order.factory_price_usd || '', sqm: '' };
  }
  if(props.workspace==='finance' && financeCustomer.value && !picked.value.length) {
    const eligible=listed.filter(order=>String(order.customer_id)===financeCustomer.value &&
      order.payment_status==='deposit_received' && order.lines.every((line) => line.arrived === line.quantity) &&
      !billed.some(invoice=>invoice.kind==='balance' && invoice.order_ids?.includes(order.id)));
    if(eligible.length===1) picked.value=[eligible[0].id];
  }
  for(const v of versions) applicability[v.id]=[...v.provider_ids];
  await refreshTemplate();
  rebateStatus.value = credits.calculation_status;
  const assignmentRequests:Promise<void>[]=[];
  for (const order of props.workspace === 'projects' ? orders.value : []) {
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
function leadLabel(order: ProjectOrder) {
  const lead = order.lead_time;
  if (!lead) return "";
  return typeof lead === "string" ? lead : lead.text || "";
}
function customerCode(order: ProjectOrder) {
  return customers.value.find((row) => row.customer_id === order.customer_id)?.customer_code || "";
}
// Invoices are always shown by their readable number, never by the internal record id.
function invoiceLabel(invoice: Invoice) { return invoice.invoice_number || `${orderLabel(invoice.order_ids?.[0] || invoice.id)}-${invoice.kind === 'deposit' ? 'D' : 'B'}`; }
// Notification subjects stored before readable numbers existed still contain record ids; show them readably.
function prettySubject(text: string) {
  let out = text;
  for (const invoice of invoices.value) out = out.split(invoice.id).join(invoiceLabel(invoice));
  return out.replace(/(?:project|deposit|balance):[0-9a-f]{16,}/g, (raw) => orderLabel(raw));
}
// Rebate allocations store the raw invoice record id; always resolve it to the readable number.
function allocationLabel(id?: string) {
  const invoice = id ? invoices.value.find((item) => item.id === id) : undefined;
  return invoice ? invoiceLabel(invoice) : tx('（发票不可用）', '(invoice unavailable)');
}
const previewDialog = ref<HTMLDialogElement | null>(null);
const sheetDialog = ref<HTMLDialogElement | null>(null);
// A native modal <dialog> traps Tab inside, makes the page behind inert, handles Escape and
// returns focus to the button that opened it when it closes.
function closePreview() {
  if (previewDialog.value?.open) previewDialog.value.close();
  mailPreview.value = null;
}
function openSheetPreview() { sheetDialog.value?.showModal(); }
function closeSheetPreview() { sheetDialog.value?.close(); }
function onSheetDialogClick(event: MouseEvent) {
  if (event.target === sheetDialog.value) closeSheetPreview();
}
function onDialogClosed() { document.body.style.overflow = ''; mailPreview.value = null; }
function onDialogClick(event: MouseEvent) {
  const box = previewDialog.value?.getBoundingClientRect();
  if (box && (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom)) closePreview();
}
function forwardEscape(event: Event) {
  // The email is shown in a same-origin iframe without scripts; forward Escape so it still closes the dialog.
  const doc = (event.target as HTMLIFrameElement).contentDocument;
  doc?.addEventListener('keydown', (key) => { if (key.key === 'Escape') closePreview(); });
}
watch(mailPreview, async (value) => {
  await nextTick();
  const dialog = previewDialog.value;
  if (!dialog) return;
  if (value && !dialog.open) { document.body.style.overflow = 'hidden'; dialog.showModal(); }
  if (!value && dialog.open) dialog.close();
});
onBeforeUnmount(() => { document.body.style.overflow = ''; });
async function openInvoicePdf() {
  const chosen = invoices.value.find((invoice) => invoicePick.value.includes(invoice.id));
  if (!chosen) return;
  try {
    const response = await fetch(`/api/operations/invoices/${encodeURIComponent(chosen.id)}/pdf`, { headers: session.token ? { Authorization: `Bearer ${session.token}` } : {} });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const url = URL.createObjectURL(await response.blob());
    window.open(url, "_blank", "noopener");
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  }
}

function orderStatus(value: string) {
  const labels: Record<string, [string, string]> = {
    pending_review: ["待审核", "Review pending"], accepted: ["已接收", "Accepted"],
    deposit_unpaid: ["待收定金", "Deposit unpaid"], deposit_received: ["定金已收", "Deposit received"],
    supplier_ordered: ["已下单", "Ordered"], in_transit: ["运输中", "In transit"],
    partially_arrived: ["部分到货", "Partly arrived"], arrived: ["可提货", "Ready for collection"], ready: ["可提货", "Ready for collection"],
    partially_delivered: ["部分交付", "Partly delivered"], delivered: ["已完成", "Complete"], complete: ["已完成", "Complete"], paid: ["已结清", "Paid"],
  };
  return labels[value] ? tx(...labels[value]) : value;
}

function mailStatus(status: string) {
  const labels: Record<string, [string, string]> = {
    // The send was recorded in demo mode; nothing reached the customer, but the invoice counts as sent.
    demo_suppressed: ['已发送（演示，未真实投递）', 'Sent (demo, not delivered)'],
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
    const order = orders.value.find((item) => item.id === id);
    const body = order?.order_number_confirmed === false
      ? { order_number: order.order_number, confirm_order_number: orderNumberConfirmation[id] === true }
      : {};
    await request(`operations/orders/${id}/review`, body);
    notice.value = tx("已确认接收。定金发票是草稿，发送是另一步。价格未配置时会拒绝。", "Accepted. The deposit invoice is a draft; sending it is a separate step. This is refused when price rules are missing.");
  });
}

function saveOrderNumber(id: string) {
  return act(async () => {
    const order = orders.value.find((item) => item.id === id);
    if (!order) throw new Error(tx("未找到此订单。", "Order not found."));
    await request(`operations/orders/${id}/order-number`, {order_number:order.order_number});
    notice.value = tx("未确认订单号已保存，客户暂时看不到。", "Unconfirmed order number saved; the customer cannot see it yet.");
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
    await request(`operations/orders/${order.id}/supplier-order`, {});
    notice.value = tx("已标为已下单。", "Marked as ordered.");
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

function remainingLines(order: ProjectOrder, kind: "arrival" | "delivery") {
  return order.lines
    .map((line) => ({ line_id: line.id, quantity: Math.max(0, kind === "arrival" ? line.quantity-line.arrived : line.quantity-line.delivered) }))
    .filter((line) => line.quantity > 0);
}

function cell(line: Line, key: string) {
  const value = line.options?.[key];
  return value == null || value === "" ? "—" : String(value);
}
function addonCell(line: Line) {
  const keys = ["tracked_bifold", "tracked_sliding", "stained_colour", "stainless_hinges", "hidden_hinges", "hidden_tilt_rod", "tier_on_tier", "double_closure", "shaped_cutout", "extra_installation"];
  const parts = keys.flatMap((key) => {
    const value = line.options?.[key];
    if (!value || value === "no" || value === "none") return [];
    return [`${key.replaceAll("_", " ")}: ${value}`];
  });
  return parts.join(" · ") || "—";
}
function optionText(line: Line) {
  const labels: Record<string, [string, string]> = {
    opening_style: ["开合方式", "Opening"], layout_code: ["Layout Code", "Layout Code"],
    vt_post: ["VT Post", "VT Post"], ht_post: ["HT Post", "HT Post"],
    midrail: ["中横档", "Mid-Rail"], frame: ["框型", "Frame"], louver_size: ["叶片", "Louver"],
    colour: ["颜色", "Colour"], control_rod: ["控制杆", "Control rod"], fitting: ["内装/外装", "In/Out fit"],
    special_request: ["备注", "Notes"], tracked_bifold: ["轨道对开", "Tracked bifold"],
    tracked_sliding: ["轨道推拉", "Tracked sliding"], stained_colour: ["染色", "Stained colour"],
    stainless_hinges: ["不锈钢合页", "Stainless hinges"], hidden_hinges: ["隐藏合页", "Hidden hinges"],
    hidden_tilt_rod: ["隐藏拉杆", "Hidden tilt rod"], tier_on_tier: ["上下分段", "Tier on tier"],
    double_closure: ["双闭合", "Double closure"], shaped_cutout: ["异形开孔", "Shaped cutout"],
    extra_installation: ["额外安装条件", "Extra installation"],
  };
  return Object.entries(line.options || {}).map(([name, value]) => `${labels[name] ? tx(...labels[name]) : name.replaceAll("_", " ")}: ${value}`).join(" · ");
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
    const lines = remainingLines(order, "arrival");
    if (!lines.length) {
      arrivalRows.value.push({ order_id: order.id, status: "skipped", detail: tx("没有待确认的到货数量", "No outstanding arrival quantities") });
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
  if (kind === "delivery" && !order.lines.every((line) => line.arrived === line.quantity)) {
    fulfilError.value = tx("全部货物到齐后才能安排整单交付。", "All goods must have arrived before the whole order can be delivered.");
    return;
  }
  const lines = remainingLines(order, kind);
  if (!lines.length) {
    fulfilError.value = kind === 'arrival'
      ? tx('整单已记录到货。', 'The whole order is already recorded as arrived.')
      : tx('整单已记录交付。', 'The whole order is already recorded as delivered.');
    return;
  }
  fulfilError.value = '';
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
    const mailed = result.notification ? mailStatus(result.notification.status) : "";
    notice.value = kind === "arrival"
      ? tx(`已记录整单到货。通知状态：${mailed || "无"}。收款状态不会被覆盖。`, `The whole order is recorded as arrived. Notification status: ${mailed || "none"}. Payment status is left unchanged.`)
      : tx("已记录整单交付。", "The whole order is recorded as delivered.");
  });
}

function createShipment() {
  if (!shipmentForm.name.trim() || !shipmentPick.value.length) return;
  return act(async () => {
    const ids = [...shipmentPick.value].sort();
    await request('operations/shipments', { name: shipmentForm.name.trim(), order_ids: ids, eta: shipmentForm.eta || undefined, operation_key: stableKey(JSON.stringify({ shipment: shipmentForm.name.trim().toLowerCase(), ids })) });
    shipmentForm.name = ''; shipmentForm.eta = ''; shipmentPick.value = [];
    notice.value = tx('已创建批次并将订单标为在途。', 'Shipment created; orders are now in transit.');
  });
}
function updateShipmentEta(shipment: Shipment) {
  return act(async () => { await request(`operations/shipments/${encodeURIComponent(shipment.id)}/eta`, { eta: shipmentEta[shipment.id] }); notice.value = tx('已更新批次预计到货日期。', 'Shipment ETA updated.'); });
}
function savePurchase(order: ShipmentOrder) {
  const form = purchaseForm[order.id];
  if (!form || !form.usd.trim()) { error.value = tx('请先填写工厂价（USD）。', 'Enter the factory price (USD) first.'); return; }
  return act(async () => {
    await request(`operations/orders/${encodeURIComponent(order.id)}/purchase-cost`, { factory_price_usd: form.usd.trim(), ...(form.sqm.trim() ? { measured_sqm: form.sqm.trim() } : {}) });
    notice.value = tx(`已保存 ${order.order_number || ''} 的工厂价。`, `Factory price saved for ${order.order_number || 'the order'}.`);
  });
}
function saveShipmentCosts(shipment: Shipment) {
  const cost = shipmentCosts[shipment.id];
  return act(async () => { await request(`operations/shipments/${encodeURIComponent(shipment.id)}/costs`, { freight_land: cost.freight_land || '0', freight_sea: cost.freight_sea || '0', duty_total: cost.duty_total || null }); notice.value = tx('已保存批次运费和关税。', 'Shipment costs saved.'); });
}
function arriveShipment(shipment: Shipment) {
  return act(async () => { const result = await request<Shipment & {invoice_ids?: string[]}>(`operations/shipments/${encodeURIComponent(shipment.id)}/arrive`, {}); notice.value = tx(`批次已到货；自动生成 ${result.invoice_ids?.length || 0} 张尾款草稿。`, `Shipment arrived; ${result.invoice_ids?.length || 0} balance draft(s) created automatically.`); });
}

async function previewInvoiceMail() {
  const chosen = invoices.value.find((invoice) => invoicePick.value.includes(invoice.id));
  if (!chosen) {
    error.value = tx("先勾选要预览的发票。", "Select an invoice to preview.");
    return;
  }
  error.value = "";
  try {
    mailPreview.value = await request<MailPreview>(`operations/invoices/${chosen.id}/mail-preview`);
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  }
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
        results.push(`${invoiceLabel(invoice)}: ${mailStatus(sent.status)}`);
      } catch (cause) {
        results.push(`${invoiceLabel(invoice)}: failed ${cause instanceof Error ? cause.message : String(cause)}`);
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

const AUTO_EVIDENCE_MAX_ORDERS = 8;
function autoEvidence(rows: ProjectOrder[]) {
  // Built only from stored facts. It states the billing basis; it never claims a rebate rule exists.
  if (!rows.length) return "";
  const parts = rows.slice(0, AUTO_EVIDENCE_MAX_ORDERS).map((order) => {
    const deposit = order.invoices?.find((invoice) => invoice.kind === "deposit");
    const ref = order.order_number || order.id;
    const money = `${order.currency || ""} ${order.total ?? "?"}`.trim();
    return tx(
      `${ref}：订单总额 ${money}，每一行已到货，定金${deposit ? ` ${deposit.currency} ${deposit.amount}` : ""}已收`,
      `${ref}: order total ${money}, every line arrived, deposit${deposit ? ` ${deposit.currency} ${deposit.amount}` : ""} received`,
    );
  });
  const more = rows.length > AUTO_EVIDENCE_MAX_ORDERS ? tx(`；另有 ${rows.length - AUTO_EVIDENCE_MAX_ORDERS} 单`, `; ${rows.length - AUTO_EVIDENCE_MAX_ORDERS} more orders`) : "";
  return tx(
    `按系统记录生成：每一行都已到货且定金已收的订单，应收尾款=订单总额-已保存定金。${parts.join("；")}${more}。仅扣除早于本月、已确认的返利余额；不自动计算返利。`,
    `Generated from system records: orders with every line arrived and the deposit received; balance = order total minus the stored deposit. ${parts.join("; ")}${more}. Only confirmed rebate balances from earlier months are deducted; no rebate is calculated automatically.`,
  );
}
let lastAutoEvidence = "";
function fillEvidence() {
  const text = autoEvidence(selectedOrders()).slice(0, 1000); // backend limit
  settlementEvidence.value = text;
  lastAutoEvidence = text;
}

function settleSelected() {
  const rows = selectedOrders();
  const customerId = oneCompany(rows);
  if (customerId == null) return;
  if (rows.some((order) => order.payment_status !== "deposit_received" || order.lines.some((line) => line.arrived !== line.quantity))) {
    error.value = tx("只能给每一行都已到货且定金已收的订单开尾款。", "A balance invoice needs every line arrived and the deposit received.");
    return;
  }
  if (settlementEvidence.value.trim().length < 5) {
    error.value = tx("尾款需要至少 5 个字的已确认规则说明。没有说明不会生成发票。", "A balance invoice needs at least 5 characters of confirmed-rule evidence. Nothing is created without it.");
    return;
  }
  const orderIds = rows.map((order) => order.id).sort();
  const body = {
    order_ids: orderIds,
    operation_key: stableKey(JSON.stringify({ settle: orderIds, evidence: settlementEvidence.value.trim() })),
    rules_evidence: settlementEvidence.value.trim(),
    billing_basis: "all_arrived_remaining_total" as const,
  };
  return act(async () => {
    const invoice = await request<Invoice>("operations/settlements", body);
    operationKeys.delete(JSON.stringify({ settle: orderIds, evidence: settlementEvidence.value.trim() }));
    notice.value = tx(
      `已生成尾款草稿 ${invoiceLabel(invoice)}，金额 ${invoice.currency} ${invoice.amount}。部分到货或未收定金会被拒绝。发送仍是另一步。`,
      `Balance draft ${invoiceLabel(invoice)} created for ${invoice.currency} ${invoice.amount}. Partial arrival or an unpaid deposit is refused. Sending stays a separate step.`,
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

async function downloadJobSheet(id: string) {
  busy.value = true;
  error.value = "";
  notice.value = "";
  try {
    const response = await fetch(`/api/operations/orders/${id}/job-sheet`, {
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
    link.download = `job-sheet-${orderLabel(id)}.xlsx`;
    link.click();
    URL.revokeObjectURL(url);
    notice.value = tx("已下载安装工作单。", "Downloaded the job sheet.");
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

// One download for every case: the export is the VERA Order sheet, and a chosen active supplier is saved with it.
async function exportSupplierOrder(orderId: string) {
  busy.value = true;
  error.value = "";
  notice.value = "";
  try {
    const form = orderProviderForm[orderId];
    const providerId = form?.provider_id && providers.value.some(p => p.id === form.provider_id && p.active) ? form.provider_id : 0;
    if (providerId) {
      const templateId = providerTemplates.value.some(t => t.id === form.template_id && t.provider_id === providerId && t.active) ? form.template_id : null;
      await request(`operations/orders/${orderId}/assign-provider`, { provider_id: providerId, template_id: templateId, is_preferred: true });
    }
    const response = await fetch(`/api/operations/orders/${orderId}/supplier-export`, {
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
    notice.value = providerId
      ? tx("已下载供应商订单，并保存了本单供应商。", "Downloaded the supplier order and saved this order's supplier.")
      : tx("已下载供应商订单。", "Downloaded the supplier order.");
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
    <nav v-if="workspace === 'projects'" class="project-panes" :aria-label="tx('项目视图','Project views')">
      <button type="button" :aria-pressed="projectPane==='orders'" @click="projectPane='orders'">{{ tx('订单工作台','Orders') }}</button>
      <button type="button" :aria-pressed="projectPane==='shipments'" @click="projectPane='shipments'">{{ tx('批次管理','Shipments') }}</button>
      <button type="button" :aria-pressed="projectPane==='overview'" @click="projectPane='overview'">{{ tx('订单总览','Order overview') }}</button>
    </nav>
    <div v-show="loaded && (workspace !== 'projects' || projectPane === 'orders')" class="workspace-grid">
      <aside v-if="workspace === 'projects'" class="card order-list">
        <div class="list-heading"><h3>{{ tx("订单列表", "Orders") }}</h3><span>{{ visibleOrders.length }}</span></div>
        <label class="filter-row">{{ tx("筛选", "Filter") }}
          <select v-model="statusFilter" @change="listPage = 0">
            <option value="">{{ tx("全部", "All") }}</option>
            <option v-for="status in [...new Set(orders.flatMap((order) => [order.status, order.payment_status]))]" :key="status" :value="status">{{ orderStatus(status) }}</option>
          </select>
        </label>
        <div class="mobile-project-picker">
          <label>{{ tx("当前订单", "Current order") }}<select :value="selectedOrder?.id" @change="selectedId = ($event.target as HTMLSelectElement).value"><option v-for="order in visibleOrders" :key="order.id" :value="order.id">{{ order.project_name }}</option></select></label>
        </div>
        <div class="order-scroll">
          <div v-for="order in pageOrders" :key="order.id" class="order-row">
            <button type="button" :title="order.project_name" :aria-pressed="selectedOrder?.id === order.id" class="order-pick" :class="{ current: selectedOrder?.id === order.id }" @click="selectedId = order.id">
              <strong>{{ order.project_name }}</strong>
              <span>{{ order.order_number_confirmed === false ? tx('订单号待管理员确认','Order number pending admin confirmation') : order.order_number }}</span>
              <span>{{ order.company }}</span>
              <small>{{ orderStatus(order.status) }} · {{ order.total ? `${order.currency || ""} ${order.total}` : tx("待计价", "Unpriced") }}</small>
            </button>
            <label class="card-pick" @click.stop><input type="checkbox" :aria-label="tx('批量选择订单','Select order for batch')+' '+order.order_number" :checked="picked.includes(order.id)" @click.stop @change="toggleOrder(order.id)" /></label>
          </div>
        </div>
        <div v-if="pageCount > 1" class="list-pagination">
          <button type="button" :disabled="listPage <= 0" @click="listPage--" :aria-label="tx('上一页','Previous page')">‹</button>
          <span>{{ Math.min(listPage + 1, pageCount) }} / {{ pageCount }}</span>
          <button type="button" :disabled="listPage >= pageCount - 1" @click="listPage++" :aria-label="tx('下一页','Next page')">›</button>
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
                  <p class="order-identity"><strong>{{ selectedOrder.order_number }}</strong><span>{{ selectedOrder.company }}</span><span v-if="customerCode(selectedOrder)">{{ customerCode(selectedOrder) }}</span></p>
                </div>
                <div class="status-badges">
                  <span class="badge">{{ orderStatus(selectedOrder.status) }}</span>
                  <span class="badge">{{ orderStatus(selectedOrder.payment_status) }}</span>
                  <span v-if="selectedOrder.arrival_status" class="badge">{{ orderStatus(selectedOrder.arrival_status) }}</span>
                </div>
              </header>
              <div class="order-meta">
                <p v-if="leadLabel(selectedOrder)"><strong>{{ tx("预计交期", "Lead time") }}:</strong> {{ leadLabel(selectedOrder) }}</p>
                <p><strong>{{ tx("联系人", "Contact") }}:</strong> {{ selectedOrder.contact_name || "—" }} · {{ selectedOrder.phone || "—" }} · {{ selectedOrder.email || "—" }}</p>
                <p><strong>{{ tx("公司地址", "Company address") }}:</strong> {{ selectedOrder.company_address || "—" }}</p>
                <p><strong>{{ tx("施工地址", "Site") }}:</strong> {{ selectedOrder.site_address || "—" }}</p>
                <p><strong>{{ tx("提交日期", "Submitted") }}:</strong> {{ quoteDate(selectedOrder.created_at) }}</p>
                <p><strong>{{ tx("安装", "Installation") }}:</strong> {{ selectedOrder.installation_required ? tx("需要", "Required") : tx("不需要", "Not required") }}</p>
                <p><strong>{{ tx("总价", "Total") }}:</strong> {{ selectedOrder.total ? `${selectedOrder.currency || ""} ${selectedOrder.total}` : tx("待计价", "Unpriced") }}</p>
                <p v-if="selectedOrder.supplier_reference"><strong>{{ tx("供应商参考", "Supplier ref") }}:</strong> {{ selectedOrder.supplier_reference }}</p>
              </div>
              <div class="detail-navigation"><nav class="detail-tabs" aria-label="Project details">
                <button type="button" :class="{active: detailSection === 'order'}" @click="detailSection = 'order'">{{ tx("订单、报价与履约", "Order, quote & fulfilment") }}</button>
                <button type="button" :class="{active: detailSection === 'supplier'}" @click="detailSection = 'supplier'">{{ tx("供应商与导出", "Supplier & files") }}</button>
                <button type="button" :class="{active: detailSection === 'invoices'}" @click="detailSection = 'invoices'">{{ tx("发票与收款", "Invoices & payments") }}</button>
                <button type="button" :class="{active: detailSection === 'history'}" @click="detailSection = 'history'">{{ tx('操作记录','Activity') }}</button>
              </nav><div class="next-action"><strong>{{ tx('建议下一步','Suggested next step') }}</strong><p>{{ nextOrderHint }}</p><RouterLink v-if="selectedOrder.status==='delivered' || selectedOrder.status==='complete' || (selectedOrder.payment_status==='deposit_received' && selectedOrder.lines.every(line => line.arrived === line.quantity))" :to="{path:'/crm/finance',query:{customer:selectedOrder.customer_id}}">{{ tx('打开客户账款','Open customer accounts') }} →</RouterLink><button v-else-if="detailSection!==nextOrderSection(selectedOrder)" type="button" class="secondary" @click="detailSection=nextOrderSection(selectedOrder)">{{ tx('打开当前步骤','Open current step') }}</button></div></div>
<div v-show="detailSection === 'order'">              <div class="section-title-row"><h3>{{ tx('产品明细与客户提交配置','Product details and customer-submitted configuration') }}</h3><button type="button" class="secondary" @click="openSheetPreview">{{ tx('预览整单','Preview whole order') }}</button></div>
              <div class="table-scroll"><table class="quote-sheet">
                <thead><tr>
                  <th>{{ tx("窗位", "Window") }}</th><th>{{ tx("宽", "Width") }}</th><th>Drop</th><th>{{ tx("产品", "Product") }}</th>
                  <th>{{ tx("开合", "Opening") }}</th><th>Panel Qty</th><th>Layout Code</th><th>VT Post</th><th>HT Post</th><th>Mid-Rail</th>
                  <th>Frame</th><th>Louver Size</th><th>Colour</th><th>Control Rod</th><th>In/Out Fit</th><th>Special Request</th>
                  <th>Discount</th><th>Final Price</th><th>{{ tx("附加项", "Add-ons") }}</th>
                </tr></thead>
                <tbody>
                  <tr v-for="line in selectedOrder.lines" :key="line.id">
                    <td>{{ line.window_name || "—" }}</td>
                    <td>{{ line.width_mm || "—" }}</td>
                    <td>{{ line.height_mm || "—" }}</td>
                    <td>{{ line.product_name || line.source_code || line.product_id || "—" }}</td>
                    <td>{{ cell(line, "opening_style") }}</td>
                    <td>{{ line.panel_count || "—" }}</td>
                    <td>{{ cell(line, "layout_code") }}</td>
                    <td>{{ cell(line, "vt_post") }}</td>
                    <td>{{ cell(line, "ht_post") }}</td>
                    <td>{{ cell(line, "midrail") }}</td>
                    <td>{{ cell(line, "frame") }}</td>
                    <td>{{ cell(line, "louver_size") }}</td>
                    <td>{{ cell(line, "colour") }}</td>
                    <td>{{ cell(line, "control_rod") }}</td>
                    <td>{{ cell(line, "fitting") }}</td>
                    <td>{{ cell(line, "special_request") }}</td>
                    <td>{{ Number(line.discount) ? `${Number(line.discount) * 100}%` : "—" }}</td>
                    <td>{{ quoteMoney(line.amount, selectedOrder.currency || "NZD") }}</td>
                    <td>{{ addonCell(line) }}</td>
                  </tr>
                </tbody>
              </table></div>
              <p class="fulfil-hint">{{ tx('每一列对应 Wholesale Quote 的一个字段，没填的显示为“—”，方便看出缺项。到货与交付按整单记录。','Each column is one Wholesale Quote field. A blank stays as “—” so a missing item is visible. Arrival and delivery are recorded for the whole order.') }}</p>
              <p class="hint">{{ tx('本报价 14 天内有效，确认和定金需书面确认。付款请用订单号作为参考。账户名 VCG Group Ltd，GST 139-745-388，ASB 12-3233-0714884-00。','This quotation is valid for 14 days. Confirmation and the deposit need to be in writing. Use the order number as the payment reference. Account name VCG Group Ltd, GST 139-745-388, ASB 12-3233-0714884-00.') }}</p>
              <div v-if="selectedOrder.status==='pending_review' && selectedIsWholesale" class="wholesale-quote-summary">
                <h3>{{ tx('批发报价汇总','Wholesale quote summary') }}</h3>
                <dl class="quote-summary-grid">
                  <div><dt>{{ tx('客户/联系人','Customer / contact') }}</dt><dd>{{ selectedOrder.company }} · {{ selectedOrder.contact_name || '—' }} · {{ selectedOrder.phone || '—' }} · {{ selectedOrder.email || '—' }}</dd></div>
                  <div><dt>{{ tx('订单号 / 日期','Order / date') }}</dt><dd>{{ selectedOrder.order_number || '—' }} · {{ quoteDate(selectedOrder.created_at) }}</dd></div>
                  <div><dt>{{ tx('公司地址','Company address') }}</dt><dd>{{ selectedOrder.company_address || '—' }}</dd></div>
                  <div><dt>{{ tx('施工地址 / 安装','Site / installation') }}</dt><dd>{{ selectedOrder.site_address || '—' }} · {{ selectedOrder.installation_required ? tx('需要','Required') : tx('仅供货','Supply only') }}</dd></div>
                  <div><dt>{{ tx('产品小计','Sub total') }}</dt><dd>{{ quoteMoney(selectedOrder.subtotal, selectedOrder.currency || 'NZD') }}</dd></div>
                  <div><dt>{{ tx('安装费用','Installation') }}</dt><dd>{{ selectedOrder.installation_required ? quoteMoney(selectedOrder.installation, selectedOrder.currency || 'NZD') : tx('仅供货','Supply only') }}</dd></div>
                  <div><dt>{{ tx('GST / 总额','GST / total') }}</dt><dd>{{ quoteMoney(selectedOrder.tax, selectedOrder.currency || 'NZD') }} · <strong>{{ quoteMoney(selectedOrder.total, selectedOrder.currency || 'NZD') }}</strong></dd></div>
                  <div><dt>{{ tx('60% 定金 / 40% 尾款','60% deposit / 40% balance') }}</dt><dd>{{ quoteMoney(selectedOrder.deposit, selectedOrder.currency || 'NZD') }} · {{ quoteBalance(selectedOrder) }}</dd></div>
                </dl>
              </div>
              <h3 v-if="selectedOrder.status==='supplier_ordered' || ['in_transit','partially_arrived'].includes(selectedOrder.status) || selectedOrder.lines.some(line=>line.arrived>line.delivered)">{{ tx("履约操作", "Fulfilment actions") }}</h3>
              <div class="actions">
                <button v-if="selectedOrder.status==='supplier_ordered'" type="button" class="secondary" :disabled="busy" @click="transitOne(selectedOrder.id)">{{ tx('标为在途','Mark in transit') }}</button>
                <button v-if="['in_transit','partially_arrived'].includes(selectedOrder.status)" type="button" class="secondary" :disabled="busy" @click="fulfil(selectedOrder, 'arrival')">{{ tx("确认整单货物已到齐", "Confirm all goods arrived") }}</button>
                <button v-if="selectedOrder.lines.some(line=>line.arrived>line.delivered)" type="button" class="secondary" :disabled="busy || !selectedOrder.lines.every(line=>line.arrived===line.quantity)" @click="fulfil(selectedOrder, 'delivery')">{{ tx("记录整单交付", "Record whole-order completion") }}</button>
              </div>
              <p v-if="fulfilError" class="fulfil-error" role="alert">{{ fulfilError }}</p>
              <div v-if="selectedOrder.status!=='pending_review'" class="actions"><button type="button" class="secondary" :disabled="busy" @click="downloadJobSheet(selectedOrder.id)">{{ tx('下载安装工作单','Download job sheet') }}</button></div>

</div><div v-show="detailSection === 'supplier'">              <h3>{{ tx("供应商与导出", "Provider & Export") }}</h3>
              <div v-if="orderProviderForm[selectedOrder.id]" class="provider-section">
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
                  <RouterLink to="/crm/providers">{{ tx('管理共享供应商','Manage shared suppliers') }}</RouterLink>
                </div>
                <p class="hint" v-if="!providers.some(p=>p.active)">{{ tx('尚无已启用供应商；先在供应商页面确认并启用。','No active supplier yet. Confirm and activate one under Suppliers.') }}</p>
                <p class="hint" v-else-if="orderProviderForm[selectedOrder.id].provider_id && !providers.some(p=>p.id===orderProviderForm[selectedOrder.id].provider_id && p.active)">{{ tx('原供应商已停用，请重新选择已启用的供应商。','The assigned supplier is inactive; choose an active supplier.') }}</p>
                <p class="hint" v-else-if="orderProviderForm[selectedOrder.id].template_id && !readySupplierExport(selectedOrder.id)">{{ tx('原输出模板已停用，请选择当前有效版本。','The assigned export template is inactive; choose a current revision.') }}</p>
                <p class="hint" v-else-if="orderProviderForm[selectedOrder.id].provider_id">{{ tx('下载供应商订单时会同时保存本单供应商。','Downloading the supplier order also saves this order’s supplier.') }}</p>
                <p v-if="!['deposit_received','paid'].includes(selectedOrder.payment_status)" class="hint">{{ tx('定金确认后再导出给供应商。','Export the supplier file after the deposit is confirmed.') }}</p>
                <div class="form-row">
                  <button type="button" :disabled="busy || selectedOrder.status==='pending_review' || !['deposit_received','paid'].includes(selectedOrder.payment_status)" @click="exportSupplierOrder(selectedOrder.id)">{{ tx('下载供应商订单','Download supplier order') }}</button>
                </div>
              </div>
              <div v-if="selectedOrder.status==='accepted' && selectedOrder.payment_status==='deposit_received'" class="actions"><button type="button" :disabled="busy" @click="supplier(selectedOrder)">{{ tx('标为已下单','Mark as ordered') }}</button></div>

</div><div v-show="detailSection === 'order'">
              <div class="pricing-basis"><h3>{{ tx('本单计价依据','Pricing applied to this order') }}</h3><p v-for="version in [...new Set(selectedOrder.lines.map(l=>l.rule_version).filter(Boolean))]" :key="version"><RouterLink :to="{path:'/crm/pricing',query:{version}}">{{ tx('定价版本','Pricing version') }} {{ version?.slice(0,12) }}</RouterLink></p><span v-if="selectedOrder.status !== 'pending_review'">{{ tx('审核后价格已冻结','Prices frozen after acceptance') }}</span></div>
              <div v-if="selectedOrder.status === 'pending_review' && selectedOrder.order_number_confirmed === false" class="order-number-confirmation" role="alert">
                <strong>{{ tx('先确认订单号，再确认接收报价','Confirm the order number before accepting this quote') }}</strong>
                <p>{{ tx('系统已按客户类型自动生成订单号。确认前客户看不到；管理员可修改并保存。勾选确认后点击“确认接收”，订单接受和订单号确认会一起完成。', 'The system generated this number from the customer type. The customer cannot see it before confirmation. Admins may edit and save it. Check the confirmation box, then accept the quote to confirm both together.') }}</p>
                <label>{{ tx('待确认订单号','Order number to confirm') }}<input v-model="selectedOrder.order_number" maxlength="200" /></label>
                <button type="button" class="secondary" :disabled="busy" @click="saveOrderNumber(selectedOrder.id)">{{ tx('保存修改','Save number') }}</button>
                <label class="number-confirm-check"><input v-model="orderNumberConfirmation[selectedOrder.id]" type="checkbox" />{{ tx('我已核对并确认此订单号；接受报价后该号码将显示给客户。','I have reviewed and confirm this order number; it will be shown to the customer after accepting the quote.') }}</label>
              </div>
              <div v-if="selectedOrder.status === 'pending_review'" class="adjustment-section">
                <template v-if="selectedIsWholesale">
                <h3>{{ tx('价格调整与审核','Price adjustments & review') }}</h3>
                <div class="wholesale-quote-summary">
                  <p class="hint">{{ tx('付款请用订单号作为参考。账户名 VCG Group Ltd，GST 139-745-388，ASB 12-3233-0714884-00。逐窗配置已在本页上方展示。','Use the order number as the payment reference. Account name VCG Group Ltd, GST 139-745-388, ASB 12-3233-0714884-00. Window configuration is shown above on this page.') }}</p>
                  <details class="quote-line-details">
                    <summary>{{ tx('逐窗改价','Window price adjustments') }}</summary>
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
                    <div class="review-footer"><label>{{ tx("调整说明（仅改价时填写）", "Adjustment note (only when changing price)") }}<input v-model="adjustNote[selectedOrder.id]" /></label><button type="button" class="secondary" :disabled="busy" @click="adjust(selectedOrder)">{{ tx("保存调整", "Save adjustment") }}</button></div>
                  </details>
                  <div class="review-footer"><button type="button" :disabled="busy || (selectedOrder.order_number_confirmed === false && !orderNumberConfirmation[selectedOrder.id])" @click="review(selectedOrder.id)">{{ tx('确认订单号、接收报价并生成定金草稿','Confirm order number, accept quote and create deposit draft') }}</button></div>
                </div>
                </template>
                <template v-else>
                  <div class="table-scroll"><table>
                    <thead><tr><th>{{ tx("窗户", "Window") }}</th><th>{{ tx("折扣比例", "Discount") }}</th><th>{{ tx("商品附加", "Product surcharge") }}</th><th>{{ tx("安装附加", "Install surcharge") }}</th></tr></thead>
                    <tbody>
                      <tr v-for="line in selectedOrder.lines" :key="line.id">
                        <td>{{ line.window_name }}</td>
                        <td><input v-model.number="batch[`${selectedOrder.id}:${line.id}:discount` ]" type="number" min="0" max="1" step="0.01" /></td>
                        <td><input v-model.number="batch[`${selectedOrder.id}:${line.id}:product_surcharge` ]" type="number" min="0" step="0.01" /></td>
                        <td><input v-model.number="batch[`${selectedOrder.id}:${line.id}:installation_surcharge` ]" type="number" min="0" step="0.01" /></td>
                      </tr>
                    </tbody>
                  </table></div>
                  <div class="review-footer"><label>{{ tx("调整说明（仅改价时填写）", "Adjustment note (only when changing price)") }}<input v-model="adjustNote[selectedOrder.id]" /></label><button type="button" class="secondary" :disabled="busy" @click="adjust(selectedOrder)">{{ tx("保存调整", "Save adjustment") }}</button><button type="button" :disabled="busy || (selectedOrder.order_number_confirmed === false && !orderNumberConfirmation[selectedOrder.id])" @click="review(selectedOrder.id)">{{ tx('确认订单号、接收报价并生成定金草稿','Confirm order number, accept quote and create deposit draft') }}</button></div>
                </template>
              </div>

</div><div v-show="detailSection === 'invoices'">              <div v-if="selectedOrder.invoices && selectedOrder.invoices.length">
                <h3>{{ tx("发票", "Invoices") }}</h3>
                <div v-for="invoice in selectedOrder.invoices" :key="invoice.id" class="invoice">
                  <label><input type="checkbox" :value="invoice.id" v-model="invoicePick" /> {{ invoiceLabel(invoice) }} · {{ invoice.kind === 'deposit' ? tx('定金','Deposit') : tx('尾款','Balance') }} · {{ invoice.currency }} {{ invoice.amount }} · {{ mailStatus(invoice.status) }} · {{ invoice.payment_status === "received" ? tx("已收", "Received") : tx("未收", "Unpaid") }}</label>
                  <template v-if="invoice.kind === 'balance'">
                    <input v-model="receiptNote[invoice.id]" :placeholder="tx('尾款备注', 'Balance note')" />
                    <button type="button" class="secondary" :disabled="busy" @click="markBalanceReceived(invoice)">{{ tx("尾款已收", "Balance received") }}</button>
                  </template>
                </div>
              </div>
<div v-if="selectedOrder.status!=='pending_review' && selectedOrder.payment_status==='deposit_unpaid'" class="actions"><button type="button" :disabled="busy" @click="deposit(selectedOrder.id)">{{ tx('核实到账后记录定金已收','Record deposit after confirming receipt') }}</button></div><p v-if="!selectedOrder.invoices?.length" class="hint">{{ tx("暂无发票", "No invoices yet") }}</p><div class="invoice-actions"><button v-if="selectedOrder.invoices?.length" :disabled="busy || !invoicePick.length" @click="sendSelectedInvoices">{{ emailMode==='demo' ? (emailEnabled ? tx('发送演示邮件（仅自己）','Send demo email to owner only') : tx('记录模拟发送（不投递）','Record demo send (no delivery)')) : tx('发送勾选的本单发票','Send selected order invoices') }}</button><button type="button" :disabled="busy || !invoicePick.length" @click="previewInvoiceMail">{{ tx('预览邮件','Preview email') }}</button><RouterLink :to="{path:'/crm/finance',query:{customer:selectedOrder.customer_id}}">{{ tx('客户结算与返利账本','Customer settlement & rebate ledger') }}</RouterLink></div></div>
              <div v-show="detailSection === 'history'"><h3>{{ tx('操作记录','Activity') }}</h3><p v-for="(item,index) in selectedOrder.history || []" :key="index">{{ item.created_at }} · {{ item.action }}<span v-if="item.template_id"> · {{ tx('导出模板','Export template') }} #{{ item.template_id }} · {{ item.template_revision ? 'v'+item.template_revision : tx('历史版本未标记','Historical revision unspecified') }}</span></p></div>
            </article>
          </section>

          <section v-if="activeSection === 'pricing'" class="card section-card">
            <h2>{{ tx("定价知识库", "Pricing knowledge") }}</h2>
            <p class="hint">{{ tx("维护价格事实、计价规则和来源依据。审核发布后影响新报价，已审核订单保留原价。供应商订单格式在供应商模块独立管理。", "Maintain price facts, calculation rules and their sources. Published versions affect new quotes; accepted orders keep their prices. Supplier order formats stay under Suppliers.") }}</p>
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
            <p class="hint">{{ tx("先看已启用的供应商和它关联的订单。下载供应商订单仍在订单页，定金确认之后。", "Start with the active supplier and its orders. The supplier file is still downloaded from the order, after the deposit is confirmed.") }}</p>

            <h3>{{ tx("已启用供应商", "Active suppliers") }}</h3>
            <div class="provider-list">
              <div v-for="provider in providers.filter(item => item.active)" :key="provider.id" class="provider-card">
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
              <p v-if="!providers.some(item => item.active)">{{ tx("还没有已启用的供应商。", "No active supplier yet.") }}</p>
            </div>

            <h3>{{ tx("创建供应商", "Create provider") }}</h3>
            <form v-if="admin" @submit.prevent="createProvider" class="form-grid">
              <label>{{ tx("供应商名称", "Provider name") }}<input v-model="providerForm.name" required /></label>
              <label>{{ tx("联系邮箱", "Contact email") }}<input v-model="providerForm.contact_email" type="email" /></label>
              <label>{{ tx("备注", "Notes") }}<input v-model="providerForm.notes" /></label>
              <button :disabled="busy">{{ tx("创建", "Create") }}</button>
            </form>

            <details>
              <summary>{{ tx("停用的供应商", "Inactive suppliers") }}</summary>
              <div class="provider-list">
                <div v-for="provider in providers.filter(item => !item.active)" :key="provider.id" class="provider-card">
                  <div v-if="editingProvider?.id !== provider.id">
                    <h4>{{ provider.name }} <span class="status-inactive">{{ tx("停用", "Inactive") }}</span></h4>
                    <p v-if="provider.contact_email"><strong>{{ tx("邮箱", "Email") }}:</strong> {{ provider.contact_email }}</p>
                    <button v-if="admin" type="button" class="secondary" @click="startEditProvider(provider)">{{ tx("编辑", "Edit") }}</button>
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
                <p v-if="!providers.some(item => !item.active)">{{ tx("没有停用的供应商。", "No inactive suppliers.") }}</p>
              </div>
            </details>

            <details>
              <summary>{{ tx("字段列映射（不改变当前下载的供应商订单）", "Column mapping (does not change the downloaded supplier order)") }}</summary>
            <p class="hint">{{ tx("这里的列映射只作记录。订单页下载的供应商订单不读取这张表。ISWELL 原表另做。", "These column mappings are a record only. The supplier file downloaded from an order does not use this table. Filling the ISWELL workbook is separate.") }}</p>
            <h3>{{ tx("配置供应商输出模板", "Configure provider template") }}</h3>
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
            </details>
          </section>

          <section v-if="activeSection === 'settlement'" class="card section-card finance-workspace">
            <ManualInvoiceForm v-if="admin" :customers="customers" :locale="locale" @created="load" />
            <header class="finance-header">
              <div><h2>{{ tx('账款与返利','Accounts & rebates') }}</h2><p class="fin-sub">{{ financeTodoTotal ? tx(`还有 ${financeTodoTotal} 件事要处理，按 1 → 4 的顺序做。`, `${financeTodoTotal} items need action. Work through steps 1 → 4.`) : tx('没有待处理的账款，全部处理完了。', 'Nothing to do. All accounts are up to date.') }}</p></div>
              <label>{{ tx('客户账本','Customer ledger') }}<select v-model="financeCustomer" @change="picked=[];invoicePick=[];rebatePick=[]"><option value="">{{ tx('全部客户','All customers') }}</option><option v-for="customer in customers" :key="customer.customer_id" :value="String(customer.customer_id)">{{ customer.company }}</option></select></label>
            </header>
            <nav class="fin-steps" :aria-label="tx('账款步骤','Accounts steps')">
              <button v-for="step in financeSteps" :key="step.key" type="button" class="fin-step" :class="{ idle: !step.count }" @click="scrollFinanceStep(step.key)"><span class="fin-no">{{ step.no }}</span><span class="fin-step-text"><strong>{{ step.title }}</strong><small>{{ step.count ? tx(`${step.count} 项待办`, `${step.count} to do`) : tx('无需处理', 'Nothing to do') }}</small></span></button>
            </nav>

            <section id="fin-deposit" class="fin-block" :class="{ clear: !financeQueues.depositDue.length }">
              <header class="fin-block-head"><span class="fin-no">1</span><div><h3>{{ tx('确认定金到账','Confirm deposits') }}</h3><p>{{ tx('先把定金发票发给客户；客户付款后核实到账，再点「记录定金已收」。','Send the deposit invoice first; once the customer pays and the money has arrived, record the deposit.') }}</p></div><span class="fin-count">{{ financeQueues.depositDue.length }}</span></header>
              <p v-if="!financeQueues.depositDue.length" class="fin-clear">✓ {{ tx('没有等待确认的定金','No deposits waiting') }}</p>
              <ul v-else class="fin-rows">
                <li v-for="order in financeQueues.depositDue" :key="order.id" class="fin-row">
                  <div class="fin-row-main"><RouterLink :to="{path:'/crm/projects',query:{order:order.id}}">{{ order.order_number }} · {{ order.project_name }}</RouterLink><small>{{ order.company }} · {{ tx('定金','Deposit') }} {{ depositInvoiceFor(order) ? `${depositInvoiceFor(order)!.currency} ${depositInvoiceFor(order)!.amount}` : (order.deposit ? `${order.currency || ''} ${order.deposit}` : '—') }}</small></div>
                  <span class="fin-state" :class="depositInvoiceFor(order) && invoiceSent(depositInvoiceFor(order)!) ? 'wait' : 'todo'">{{ depositInvoiceFor(order) && invoiceSent(depositInvoiceFor(order)!) ? tx('已发发票，等客户付款','Invoice sent; waiting for payment') : tx('定金发票还没发','Deposit invoice not sent') }}</span>
                  <div class="fin-row-actions">
                    <template v-if="depositInvoiceFor(order) && !invoiceSent(depositInvoiceFor(order)!)"><button type="button" class="secondary" :disabled="busy" @click="previewOneInvoice(depositInvoiceFor(order)!)">{{ tx('预览邮件','Preview email') }}</button><button type="button" :disabled="busy" @click="sendOneInvoice(depositInvoiceFor(order)!)">{{ sendLabel }}</button></template>
                    <button type="button" :class="{ secondary: depositInvoiceFor(order) && !invoiceSent(depositInvoiceFor(order)!) }" :disabled="busy" @click="deposit(order.id)">{{ tx('核实到账后记录定金已收','Record deposit after confirming receipt') }}</button>
                  </div>
                </li>
              </ul>
            </section>

            <section id="fin-balance" class="fin-block" :class="{ clear: !financeQueues.balanceReady.length }">
              <header class="fin-block-head"><span class="fin-no">2</span><div><h3>{{ tx('开尾款','Create balance invoices') }}</h3><p>{{ tx('整单到货且定金已收的订单可以开尾款。勾选同一客户、同一币种的订单，生成尾款草稿；草稿不会直接发给客户。','Orders with every line arrived and the deposit received can be invoiced. Tick orders from one customer and currency to create a balance draft; drafts are not sent automatically.') }}</p></div><span class="fin-count">{{ financeQueues.balanceReady.length }}</span></header>
              <p v-if="!financeQueues.balanceReady.length" class="fin-clear">✓ {{ tx('目前没有可以开尾款的订单','No orders ready for a balance invoice') }}</p>
              <template v-else>
                <ul class="fin-rows">
                  <li v-for="order in financeQueues.balanceReady" :key="order.id" class="fin-row">
                    <label class="checkbox-label fin-check"><input type="checkbox" v-model="picked" :value="order.id" /><span class="fin-row-main"><strong>{{ order.order_number }} · {{ order.project_name }}</strong><small>{{ order.company }} · {{ tx('订单总额','Order total') }} {{ order.currency }} {{ order.total ?? '—' }}<template v-if="order.deposit"> · {{ tx('已收定金','Deposit received') }} {{ order.deposit }}</template></small></span></label>
                    <span class="fin-state todo">{{ tx('可开尾款','Ready to invoice') }}</span>
                    <div class="fin-row-actions"><RouterLink :to="{path:'/crm/projects',query:{order:order.id}}">{{ tx('查看订单','View order') }}</RouterLink></div>
                  </li>
                </ul>
                <div v-if="balancePicked.length" class="fin-compose">
                  <label>{{ tx('规则说明（按所选订单自动生成，可修改）','Rule note (generated from the selected orders; editable)') }}<textarea v-model="settlementEvidence" rows="3" /></label>
                  <div class="fin-row-actions"><button type="button" class="secondary" :disabled="busy" @click="fillEvidence">{{ tx('重新生成说明','Regenerate note') }}</button><button type="button" :disabled="busy" @click="settleReadyOrders">{{ tx(`生成尾款草稿（已选 ${balancePicked.length} 单）`, `Create balance draft (${balancePicked.length} selected)`) }}</button></div>
                </div>
                <p v-else class="hint">{{ tx('先勾选要开尾款的订单。','Tick the orders to invoice first.') }}</p>
              </template>
            </section>

            <section id="fin-send" class="fin-block" :class="{ clear: !financeQueues.toSend.length }">
              <header class="fin-block-head"><span class="fin-no">3</span><div><h3>{{ tx('发送发票','Send invoices') }}</h3><p>{{ tx('尾款草稿等还没发出的发票都在这里。可以先预览邮件，确认后发送。','Balance drafts and other unsent invoices. Preview the email, then send.') }}</p></div><span class="fin-count">{{ financeQueues.toSend.length }}</span></header>
              <p v-if="!financeQueues.toSend.length" class="fin-clear">✓ {{ tx('没有待发送的发票','No invoices to send') }}</p>
              <template v-else>
                <ul class="fin-rows">
                  <li v-for="invoice in financeQueues.toSend" :key="invoice.id" class="fin-row">
                    <label class="checkbox-label fin-check"><input type="checkbox" v-model="invoicePick" :value="invoice.id" /><span class="fin-row-main"><strong>{{ invoiceLabel(invoice) }} · {{ invoice.kind === 'deposit' ? tx('定金','Deposit') : tx('尾款','Balance') }} · {{ invoice.currency }} {{ invoice.amount }}</strong><small>{{ (invoice.order_ids || []).map(oid => `${orders.find(o=>o.id===oid)?.order_number ?? ''} · ${orders.find(o=>o.id===oid)?.project_name ?? ''}`).join(', ') }}</small></span></label>
                    <span class="fin-state todo">{{ mailStatus(invoice.status) }}</span>
                    <div class="fin-row-actions"><button type="button" class="secondary" :disabled="busy" @click="previewOneInvoice(invoice)">{{ tx('预览邮件','Preview email') }}</button><button type="button" :disabled="busy" @click="sendOneInvoice(invoice)">{{ sendLabel }}</button></div>
                  </li>
                </ul>
                <div v-if="invoicePick.length > 1" class="fin-bulk"><span>{{ tx(`已勾选 ${invoicePick.length} 张`, `${invoicePick.length} selected`) }}</span><button type="button" :disabled="busy" @click="sendSelectedInvoices">{{ tx('一起发送（同一客户）','Send together (one customer)') }}</button></div>
              </template>
            </section>

            <section id="fin-receipt" class="fin-block" :class="{ clear: !financeQueues.balanceDue.length }">
              <header class="fin-block-head"><span class="fin-no">4</span><div><h3>{{ tx('确认尾款收款','Confirm balance receipts') }}</h3><p>{{ tx('尾款发票已发出，客户付款后在这里确认。提货与订单完成状态单独记录。','Confirm receipt here after the customer pays. Collection and order completion are recorded separately.') }}</p></div><span class="fin-count">{{ financeQueues.balanceDue.length }}</span></header>
              <p v-if="!financeQueues.balanceDue.length" class="fin-clear">✓ {{ tx('没有等待收款的尾款','No balance payments waiting') }}</p>
              <ul v-else class="fin-rows">
                <li v-for="invoice in financeQueues.balanceDue" :key="invoice.id" class="fin-row">
                  <div class="fin-row-main"><strong>{{ invoiceLabel(invoice) }} · {{ invoice.currency }} {{ invoice.amount }}</strong><small>{{ (invoice.order_ids || []).map(oid => `${orders.find(o=>o.id===oid)?.order_number ?? ''} · ${orders.find(o=>o.id===oid)?.project_name ?? ''}`).join(', ') }}</small></div>
                  <span class="fin-state wait">{{ tx('已发出，等客户付款','Sent; waiting for payment') }}</span>
                  <div class="fin-row-actions"><input v-model="receiptNote[invoice.id]" :placeholder="tx('收款备注（可选）','Receipt note (optional)')" /><button type="button" :disabled="busy" @click="markBalanceReceived(invoice)">{{ tx('确认尾款收款','Confirm balance receipt') }}</button></div>
                </li>
              </ul>
            </section>

            <details class="fin-more">
              <summary>{{ tx('已完成','Done') }} <span>{{ financeQueues.done.length }}</span></summary>
              <p v-if="!financeQueues.done.length" class="hint">{{ tx('还没有已收款的发票。','No paid invoices yet.') }}</p>
              <ul v-else class="fin-rows compact"><li v-for="invoice in financeQueues.done" :key="invoice.id" class="fin-row"><div class="fin-row-main"><strong>{{ invoiceLabel(invoice) }} · {{ invoice.kind === 'deposit' ? tx('定金','Deposit') : tx('尾款','Balance') }} · {{ invoice.currency }} {{ invoice.amount }}</strong><small>{{ (invoice.order_ids || []).map(oid => orders.find(o=>o.id===oid)?.order_number ?? '').join(', ') }}</small></div><span class="fin-state ok">{{ tx('已收款','Paid') }}</span></li></ul>
            </details>
            <details class="fin-more">
              <summary>{{ tx('暂时不用处理的订单','Orders with nothing to do now') }} <span>{{ financeQueues.waiting.length }}</span></summary>
              <p v-if="!financeQueues.waiting.length" class="hint">{{ tx('没有。','None.') }}</p>
              <ul v-else class="fin-rows compact"><li v-for="order in financeQueues.waiting" :key="order.id" class="fin-row"><div class="fin-row-main"><RouterLink :to="{path:'/crm/projects',query:{order:order.id}}">{{ order.order_number }} · {{ order.project_name }}</RouterLink><small>{{ order.company }}</small></div><span class="fin-state idle">{{ financeWaitingReason(order) }}</span></li></ul>
            </details>
            <details class="fin-more">
              <summary>{{ tx('返利与通知记录','Rebates & notifications') }}</summary>
              <nav class="fin-tabs" role="tablist"><button type="button" role="tab" :aria-selected="financePane==='rebates'" :class="{active:financePane==='rebates'}" @click="financePane='rebates'">{{ tx('返利','Rebates') }}</button><button type="button" role="tab" :aria-selected="financePane==='notifications'" :class="{active:financePane==='notifications'}" @click="financePane='notifications'">{{ tx('通知记录','Notifications') }}</button></nav>
              <div v-if="financePane==='rebates'" class="fin-pane">
                <p class="hint">{{ tx('只录入已确认的月度返利金额，系统不自动推算返利。','Record only confirmed monthly amounts; rebate tiers are not inferred.') }}</p>
                <div v-if="admin" class="fin-rebate-form">
                  <div class="form-grid"><label>{{ tx('年月','Month') }}<input v-model="rebateForm.month" placeholder="2026-10" /></label><label>{{ tx('金额','Amount') }}<input v-model="rebateForm.amount" inputmode="decimal" /></label><label class="finance-evidence">{{ tx('确认依据','Evidence') }}<input v-model="rebateForm.evidence" /></label></div>
                  <fieldset class="fin-rebate-orders"><legend>{{ tx('来源订单（同一客户）','Source orders (one customer)') }}</legend><label v-for="order in financeOrders" :key="order.id" class="checkbox-label"><input type="checkbox" v-model="rebatePick" :value="order.id" /><span>{{ order.order_number }} · {{ order.project_name }} <small>{{ order.company }}</small></span></label></fieldset>
                  <button type="button" :disabled="busy || !rebatePick.length" @click="recordRebateForPick">{{ tx('记入已确认返利','Record confirmed rebate') }}</button>
                </div>
                <p v-if="!rebates.filter(c=>!financeCustomer || String(c.customer_id)===financeCustomer).length" class="hint">{{ tx('还没有返利记录。','No rebates recorded.') }}</p>
                <div v-for="credit in rebates.filter(c=>!financeCustomer || String(c.customer_id)===financeCustomer)" :key="credit.id" class="rebate-item"><strong>{{ credit.month }} · {{ credit.currency }} {{ credit.amount }}</strong><p>{{ tx('已用','Used') }} {{ credit.used || '0.00' }} · {{ tx('余额','Remaining') }} {{ credit.remaining || '0.00' }} · {{ credit.evidence }}</p><p v-for="oid in credit.source_order_ids" :key="oid"><RouterLink :to="{path:'/crm/projects',query:{order:oid}}">{{ orders.find(o=>o.id===oid)?.order_number }} · {{ orders.find(o=>o.id===oid)?.project_name }}</RouterLink></p><p v-for="(allocation,index) in credit.allocations" :key="index">{{ tx('已抵扣发票','Invoice allocation') }} {{ allocationLabel(allocation.invoice_id) }} · {{ allocation.amount }}</p></div>
              </div>
              <div v-else class="fin-pane">
                <p v-if="!notices.filter(n=>!financeCustomer || String(n.customer_id)===financeCustomer).length" class="hint">{{ tx('还没有通知记录。','No notifications yet.') }}</p>
                <div v-for="item in notices.filter(n=>!financeCustomer || String(n.customer_id)===financeCustomer)" :key="item.id" class="notification-item"><span>{{ prettySubject(item.subject) }} · {{ mailStatus(item.status) }}</span><button v-if="item.status==='not_configured'" type="button" :disabled="busy" @click="retryNotice(item.id)">{{ tx('重试','Retry') }}</button></div>
              </div>
            </details>
          </section>
        </div>
      </div>
    </div>
    <section v-if="workspace === 'projects' && projectPane === 'shipments'" class="card shipment-workspace">
      <header><div><h2>{{ tx('批次管理','Shipment batches') }}</h2><p>{{ tx('将已向供应商下单且尚未分批的卷帘订单加入海运批次。创建后会自动标为在途。','Create a sea shipment from supplier-ordered shutter orders that are not already batched. Orders move to in transit on creation.') }}</p></div></header>
      <div class="shipment-create">
        <label>{{ tx('批次名称','Batch name') }}<input v-model="shipmentForm.name" :placeholder="tx('例如 P4261008','e.g. P4261008')" /></label>
        <label>{{ tx('预计到货','ETA') }}<input v-model="shipmentForm.eta" type="date" /></label>
        <button type="button" :disabled="busy || !shipmentForm.name.trim() || !shipmentPick.length" @click="createShipment">{{ tx(`创建批次（${shipmentPick.length} 单）`,`Create batch (${shipmentPick.length} selected)`) }}</button>
      </div>
      <h3>{{ tx('可加入的订单','Eligible orders') }} · {{ shipmentCandidates.length }}</h3>
      <p v-if="!shipmentCandidates.length" class="hint">{{ tx('没有可加入的订单。','No eligible orders available.') }}</p>
      <div v-else class="shipment-candidates"><label v-for="order in shipmentCandidates" :key="order.id"><input v-model="shipmentPick" type="checkbox" :value="order.id" /><span><strong>{{ order.order_number || order.id }}</strong> · {{ order.project_name }}<small>{{ order.company }} · {{ order.eta ? quoteDate(order.eta) : tx('尚無預計日期','No ETA') }}</small></span></label></div>
      <h3>{{ tx('现有批次','Current batches') }} · {{ shipments.length }}</h3>
      <p v-if="!shipments.length" class="hint">{{ tx('尚未建立批次。','No shipment batches yet.') }}</p>
      <article v-for="shipment in shipments" :key="shipment.id" class="shipment-card">
        <header><div><h3>{{ shipment.name }}</h3><span class="badge">{{ orderStatus(shipment.status) }}</span></div><small>{{ shipment.orders?.length || shipment.order_ids.length }} {{ tx('个订单','orders') }}</small></header>
        <ul class="shipment-orders"><li v-for="order in shipment.orders" :key="order.id">
          <div class="shipment-order-main"><strong>{{ order.order_number || order.id }}</strong> · {{ order.company }} · {{ order.project_name }} · {{ orderStatus(order.status) }}</div>
          <div v-if="purchaseForm[order.id]" class="shipment-fields">
            <label>{{ tx('工厂价 (USD)','Factory price (USD)') }}<input v-model="purchaseForm[order.id].usd" inputmode="decimal" /></label>
            <label>{{ tx('实测面积 ㎡（可选）','Measured m² (optional)') }}<input v-model="purchaseForm[order.id].sqm" inputmode="decimal" :placeholder="order.measured_sqm || ''" /></label>
            <button type="button" class="secondary" :disabled="busy" @click="savePurchase(order)">{{ tx('保存工厂价','Save price') }}</button>
          </div>
          <small v-if="order.freight_cost != null" class="shipment-share">{{ tx('已摊分','Allocated') }}: {{ tx('运费','freight') }} NZD {{ order.freight_cost }} · {{ tx('关税','duty') }} NZD {{ order.duty_cost }} ({{ order.duty_basis === 'actual' ? tx('实际','actual') : tx('估算','estimate') }})</small>
        </li></ul>
        <div class="shipment-fields"><label>{{ tx('预计到货','ETA') }}<input v-model="shipmentEta[shipment.id]" type="date" /></label><button type="button" :disabled="busy || shipment.status==='arrived'" @click="updateShipmentEta(shipment)">{{ tx('更新 ETA','Update ETA') }}</button></div>
        <div class="shipment-fields"><label>{{ tx('陆运运费','Land freight') }}<input v-model="shipmentCosts[shipment.id].freight_land" inputmode="decimal" /></label><label>{{ tx('海运运费','Sea freight') }}<input v-model="shipmentCosts[shipment.id].freight_sea" inputmode="decimal" /></label><label>{{ tx('实际关税（可选）','Actual duty (optional)') }}<input v-model="shipmentCosts[shipment.id].duty_total" inputmode="decimal" /></label><button type="button" :disabled="busy" @click="saveShipmentCosts(shipment)">{{ tx('保存成本','Save costs') }}</button></div>
        <button v-if="shipment.status!=='arrived'" type="button" :disabled="busy" @click="arriveShipment(shipment)">{{ tx('记录整批到货并开尾款草稿','Mark batch arrived and draft balance invoices') }}</button>
        <p v-else class="success">{{ tx('批次已到货','Shipment arrived') }} · {{ shipment.invoice_ids?.length || 0 }} {{ tx('张尾款草稿','balance drafts') }}</p>
      </article>
    </section>
    <section v-if="workspace === 'projects' && projectPane === 'overview'" class="card order-overview">
      <header><div><h2>{{ tx('订单总览','Order overview') }}</h2><p>{{ tx('仅显示订单级别的付款和履约摘要，不展开窗户行。','Order-level payment and fulfilment summary; window rows are omitted.') }}</p></div></header>
      <div class="overview-scroll"><table><thead><tr><th>{{ tx('订单 / 项目','Order / project') }}</th><th>{{ tx('提交日期','Submitted') }}</th><th>{{ tx('状态','Status') }}</th><th>{{ tx('定金','Deposit') }}</th><th>{{ tx('定金日期','Deposit date') }}</th><th>{{ tx('尾款','Balance') }}</th><th>{{ tx('尾款日期','Balance date') }}</th><th>{{ tx('完成日期','Completed') }}</th><th>ETA</th><th>{{ tx('批次','Batch') }}</th></tr></thead><tbody>
        <tr v-for="order in orders" :key="order.id"><td><strong>{{ order.order_number || order.id }}</strong><small>{{ order.company }} · {{ order.project_name }}</small></td><td>{{ quoteDate(order.created_at) }}</td><td>{{ orderStatus(order.status) }}</td><td>{{ quoteMoney(order.deposit, order.currency || 'NZD') }}</td><td>{{ quoteDate(order.deposit_paid_at || depositInvoiceFor(order)?.received_at) }}</td><td>{{ quoteBalance(order) }}</td><td>{{ quoteDate(balanceInvoiceFor(order)?.received_at || balanceInvoiceFor(order)?.created_at) }}</td><td>{{ quoteDate(order.completed_at || [...(order.history || [])].reverse().find(h => h.action === 'delivery')?.created_at) }}</td><td>{{ quoteDate(order.eta) }}</td><td>{{ order.batch_name || '—' }}</td></tr>
      </tbody></table></div>
    </section>
    <Teleport to="body">
      <dialog ref="previewDialog" class="mail-dialog" :aria-label="tx('邮件预览','Email preview')" @close="onDialogClosed" @click="onDialogClick">
        <section v-if="mailPreview" class="mail-modal-card">
          <header class="mail-modal-head">
            <div>
              <p class="mail-eyebrow">{{ tx('邮件预览 · 尚未发送', 'EMAIL PREVIEW · NOT SENT') }}</p>
              <h2>{{ mailPreview.subject }}</h2>
            </div>
            <button type="button" class="mail-x" :aria-label="tx('关闭预览','Close preview')" @click="closePreview">✕</button>
          </header>
          <dl class="mail-meta">
            <div><dt>{{ tx('实际收件人','Actual recipient') }}</dt><dd>{{ mailPreview.delivered_to || tx('未配置','Not configured') }}</dd></div>
            <div><dt>{{ tx('发送方式','Mode') }}</dt><dd>{{ mailPreview.email_mode === 'demo' ? tx('演示模式：不会发给客户','Demo mode: never sent to the customer') : tx('正式发送','Live sending') }}<small v-if="mailPreview.email_mode === 'demo'"> · {{ tx('客户邮箱','customer address') }}: {{ mailPreview.customer_recipient }}</small></dd></div>
            <div><dt>{{ tx('发信通道','Delivery') }}</dt><dd :class="mailPreview.delivery_enabled ? 'ok' : 'warn'">{{ mailPreview.delivery_enabled ? tx('已启用','Enabled') : tx('未启用：点发送只会记录，不会真正发出','Not enabled: sending only records it') }}</dd></div>
            <div><dt>{{ tx('附件','Attachment') }}</dt><dd>{{ mailPreview.attachment }}</dd></div>
          </dl>
          <iframe class="mail-frame" :title="tx('邮件正文预览','Email body preview')" sandbox="allow-same-origin" :srcdoc="mailPreview.html" @load="forwardEscape"></iframe>
          <footer class="mail-modal-foot">
            <button type="button" class="mail-btn primary" @click="openInvoicePdf">{{ tx('打开 PDF 附件','Open PDF attachment') }}</button>
            <button type="button" class="mail-btn" @click="closePreview">{{ tx('关闭','Close') }}</button>
          </footer>
        </section>
      </dialog>
    </Teleport>
    <Teleport to="body">
      <dialog v-if="selectedOrder" ref="sheetDialog" class="sheet-dialog" :aria-label="tx('整单明细预览','Whole-order preview')" @click="onSheetDialogClick">
        <section class="sheet-card">
          <header class="quote-doc-head">
            <dl class="quote-party">
              <div><dt>To</dt><dd>{{ selectedOrder.company || "—" }}</dd></div>
              <div><dt>Order ID</dt><dd>{{ selectedOrder.project_name || selectedOrder.order_number || "—" }}</dd></div>
              <div><dt>Mobile</dt><dd>{{ selectedOrder.phone || "—" }}</dd></div>
              <div><dt>Address</dt><dd>{{ selectedOrder.company_address || "—" }}</dd></div>
            </dl>
            <div class="quote-mark" aria-hidden="true"><strong>VERA</strong><span>SHADING SOLUTIONS</span></div>
            <div class="quote-title-block">
              <button type="button" class="mail-x" :aria-label="tx('关闭预览','Close preview')" @click="closeSheetPreview">✕</button>
              <p>QUOTE</p>
              <small>Date: {{ quoteDate(selectedOrder.created_at) }}</small>
            </div>
          </header>
          <div class="table-scroll quote-doc-scroll"><table class="quote-doc">
            <thead><tr>
              <th>#</th><th>Window Location</th><th>Width (mm)</th><th>Drop (mm)</th><th>Product</th>
              <th>Opening</th><th>Panel Qty</th><th>Layout Code</th><th>VT Post</th><th>HT Post</th><th>Mid-Rail</th>
              <th>Frame</th><th>Louver Size</th><th>Colour</th><th>Control Rod</th><th>In/Out Fit</th><th>Special Request</th><th>Final Price</th>
            </tr></thead>
            <tbody>
              <tr v-for="(line, index) in selectedOrder.lines" :key="line.id">
                <td>{{ index + 1 }}</td>
                <td>{{ line.window_name || "—" }}</td>
                <td>{{ line.width_mm || "—" }}</td>
                <td>{{ line.height_mm || "—" }}</td>
                <td>{{ line.product_name || line.source_code || line.product_id || "—" }}</td>
                <td>{{ cell(line, "opening_style") }}</td>
                <td>{{ line.panel_count || "—" }}</td>
                <td>{{ cell(line, "layout_code") }}</td>
                <td>{{ cell(line, "vt_post") }}</td>
                <td>{{ cell(line, "ht_post") }}</td>
                <td>{{ cell(line, "midrail") }}</td>
                <td>{{ cell(line, "frame") }}</td>
                <td>{{ cell(line, "louver_size") }}</td>
                <td>{{ cell(line, "colour") }}</td>
                <td>{{ cell(line, "control_rod") }}</td>
                <td>{{ cell(line, "fitting") }}</td>
                <td>{{ [cell(line, "special_request"), addonCell(line)].filter((part) => part !== "—").join(" · ") || "—" }}</td>
                <td class="num">{{ quoteMoney(line.amount, selectedOrder.currency || "NZD") }}</td>
              </tr>
            </tbody>
          </table></div>
          <p class="quote-note">Note: This quotation is valid for 14 days. The confirmation will need to be in written via email, and deposit is required.</p>
          <footer class="quote-doc-foot">
            <section>
              <h3>Payment Instruction</h3>
              <dl>
                <div><dt>Account Name</dt><dd>VCG Group Ltd</dd></div>
                <div><dt>GST Number</dt><dd>139-745-388</dd></div>
                <div><dt>Account Number</dt><dd>ASB 12-3233-0714884-00</dd></div>
              </dl>
              <p>Please use your Order Number as reference when you pay by online banking.</p>
            </section>
            <dl class="quote-totals">
              <div><dt>Sub Total</dt><dd>{{ quoteMoney(selectedOrder.subtotal, selectedOrder.currency || "NZD") }}</dd></div>
              <div><dt>Installation</dt><dd>{{ selectedOrder.installation_required ? quoteMoney(selectedOrder.installation, selectedOrder.currency || "NZD") : "Supply Only" }}</dd></div>
              <div><dt>GST</dt><dd>{{ quoteMoney(selectedOrder.tax, selectedOrder.currency || "NZD") }}</dd></div>
              <div class="grand"><dt>Total</dt><dd>{{ quoteMoney(selectedOrder.total, selectedOrder.currency || "NZD") }}</dd></div>
              <div><dt>60% Deposit</dt><dd>{{ quoteMoney(selectedOrder.deposit, selectedOrder.currency || "NZD") }}</dd></div>
            </dl>
          </footer>
        </section>
      </dialog>
    </Teleport>
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

.list-pagination { display: flex; align-items: center; justify-content: center; gap: 8px; flex-wrap: nowrap; white-space: nowrap; padding-top: 12px; border-top: 1px solid #edf1ee; margin-top: 8px; color: #52615c; font-size: var(--fs-meta); line-height: var(--lh-meta); }
.desk .list-pagination button { background: #fff; color: #315844; border-color: #dce5df; width: 44px; min-width: 44px; max-width: 44px; height: 44px; padding: 0; flex: 0 0 44px; font-size: 18px; line-height: 1; font-weight: var(--fw-body); }

.mobile-project-picker { display: none; }
@media(max-width:600px) {
  .mobile-project-picker { display: grid; gap: 10px; }
  .order-list .filter-row { margin: 0; }
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
.next-action{background:#eef5ef;border:1px solid #c8ddcd;border-radius:8px;padding:12px 14px;margin:12px 0;display:flex;align-items:center;flex-wrap:wrap;gap:8px 16px}.next-action strong{font-size:14px}.next-action p{margin:0;flex:1 1 260px;line-height:1.5}

/* Dense, consistent task workspaces. Controls retain a 44px target. */
.desk .card{padding:16px}
@media(min-width:1001px){.desk:not(.global-workspace) .workspace-grid{grid-template-columns:236px minmax(0,1fr);gap:12px;align-items:stretch}.desk .order-list,.desk:not(.global-workspace) .detail-panel{max-height:none;overflow:visible;min-height:calc(100dvh - 92px)}.desk .order-scroll{overflow-y:visible;min-height:0;gap:8px}.desk:not(.global-workspace) .section-content{display:flex;flex-direction:column}.desk:not(.global-workspace) .section-card{flex:1}}
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
.order-number-confirmation{margin:12px 0;padding:14px;border:2px solid #c47b17;border-left-width:7px;border-radius:8px;background:#fff6e5;color:#3f2b10}
.order-number-confirmation>strong{display:block;font-size:16px}
.order-number-confirmation p{margin:6px 0 10px;line-height:1.5}
.order-number-confirmation>label:not(.number-confirm-check){display:grid;gap:5px;max-width:520px;margin:8px 0}
.order-number-confirmation input:not([type=checkbox]){min-height:40px;padding:8px;border:1px solid #cbb98e;border-radius:6px}
.order-number-confirmation .number-confirm-check{display:flex;align-items:flex-start;gap:9px;margin-top:10px;font-weight:600}
.order-number-confirmation .number-confirm-check input{width:20px;height:20px;flex:0 0 20px}
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
.finance-panel-foot button{width:100%}.finance-panel-foot button+button{margin-top:8px}
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
.detail-navigation{display:flex;align-items:center;gap:8px;min-width:0;min-height:66px;border-bottom:1px solid #e0e7e3;margin:4px 0 8px}
.desk .detail-navigation .detail-tabs{flex:0 0 auto;margin:0;padding:0;border:0}
.desk .detail-navigation .next-action{flex:1;min-width:0;margin:4px 0;padding:6px 10px;background:#eef6fb;border:1px solid #c9e1ee;border-radius:7px;color:#244d60;gap:4px 8px;font-size:12px}
.detail-navigation .next-action strong{font-size:12px;white-space:nowrap}
.detail-navigation .next-action p{flex:1 1 160px}
.detail-navigation .next-action button{padding:6px 8px;min-height:44px}
.desk .order-pick>span:first-of-type{grid-column:1;white-space:nowrap}
.desk .order-pick>span:nth-of-type(2){grid-column:2;white-space:nowrap}
@media(min-width:1001px){.desk .order-list{margin-top:0}}
@media(max-width:1250px){.detail-navigation{display:block;min-height:0}.desk .detail-navigation .next-action{margin:2px 0 6px}}
.order-identity{display:flex;align-items:center;gap:8px;margin:4px 0 0;flex-wrap:wrap;font-size:12px;line-height:1.3}
.order-identity span{color:#53655d}
.product-pagination{margin:0 0 8px;padding:6px 0;gap:8px}
.product-pagination span{white-space:nowrap}
.fulfil-hint{margin:4px 0 8px;color:#53655d;font-size:12px}
.fulfil-error{margin:8px 0 0;padding:10px 12px;border:1px solid #e3bdab;border-radius:7px;background:#fff4ef;color:#8a3218;font-size:13px}
.pricing-basis{display:flex;align-items:center;flex-wrap:wrap;gap:6px 12px;padding-bottom:8px;border-bottom:1px solid #e0e7e3}
.desk .pricing-basis h3{margin:0;padding:0;border:0}
.pricing-basis p{margin:0}
.pricing-basis span{color:#53655d;font-size:12px}
.desk .order-row{position:relative}
.desk .order-row > label.card-pick{position:absolute;left:6px;top:7px;z-index:2;display:inline-flex;width:14px;height:14px;min-width:0;min-height:0;margin:0;padding:0}
.desk .card-pick input[type="checkbox"]{width:14px!important;height:14px!important;min-width:14px!important;max-width:14px!important;min-height:14px!important;flex:0 0 14px!important;margin:0!important;padding:0!important;accent-color:#237356}
.desk .order-list{padding:14px 12px}
.desk .order-pick{padding:6px 8px 6px 24px;min-height:0;row-gap:0}
.section-title-row{display:flex;align-items:center;justify-content:space-between;gap:12px}
.section-title-row h3{margin:0}
.sheet-dialog{padding:0;border:0;background:transparent;width:min(1280px,calc(100vw - 24px));max-width:none;max-height:none;color:#1b2421}
.sheet-dialog:not([open]){display:none}
.sheet-dialog::backdrop{background:rgba(16,28,22,.55)}
.sheet-card{background:#f7f4ee;border-radius:18px;max-height:calc(100vh - 24px);overflow:auto;padding:18px 20px 16px}
.quote-doc-head{display:grid;grid-template-columns:minmax(180px,1fr) auto minmax(160px,1fr);align-items:center;gap:16px;margin-bottom:12px}
.quote-party{display:grid;gap:2px;margin:0}
.quote-party div{display:grid;grid-template-columns:72px minmax(0,1fr);gap:8px}
.quote-party dt{color:#6b6258;font-size:11px}
.quote-party dd{margin:0;font-weight:600;overflow-wrap:anywhere}
.quote-mark{display:flex;flex-direction:column;align-items:center;justify-content:center;width:148px;height:64px;border:2px solid #1b2421;border-radius:40px;background:#fff}
.quote-mark strong{font-size:22px;letter-spacing:.18em;line-height:1}
.quote-mark span{font-size:8px;letter-spacing:.16em}
.quote-title-block{justify-self:end;text-align:right}
.quote-title-block p{margin:8px 0 0;font-size:28px;letter-spacing:.14em;line-height:1}
.quote-title-block small{color:#6b6258}
.quote-doc-scroll{background:#fff;border:1px solid #e4ddd2;border-radius:12px;overflow-x:auto;max-width:100%}
.quote-doc{width:max-content;min-width:100%;border-collapse:collapse;font-size:11px}
.quote-doc th{position:sticky;top:0;background:#1f3d32;color:#fff;font-weight:600;text-align:left;padding:6px 7px;white-space:nowrap}
.quote-doc td{padding:4px 7px;border-top:1px solid #efe8de;white-space:nowrap;background:#fff}
.quote-doc tbody tr:nth-child(even) td{background:#fbf8f3}
.quote-doc td.num{text-align:right;font-variant-numeric:tabular-nums}
.quote-note{margin:10px 0;padding:8px 10px;background:#fff;border-left:3px solid #1f3d32;font-size:12px}
.quote-doc-foot{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(220px,.8fr);gap:16px;align-items:start}
.quote-doc-foot h3{margin:0 0 6px;font-size:13px}
.quote-doc-foot section{background:#fff;border-radius:12px;padding:12px 14px}
.quote-doc-foot dl{margin:0}
.quote-doc-foot section div{display:grid;grid-template-columns:120px minmax(0,1fr);gap:6px;margin-top:4px}
.quote-doc-foot dt{color:#6b6258;font-size:11px}
.quote-doc-foot dd,.quote-doc-foot p{margin:4px 0 0;font-size:13px}
.quote-totals{background:#1f3d32;color:#fff;border-radius:12px;padding:12px 14px}
.quote-totals div{display:flex;justify-content:space-between;gap:12px;margin-top:4px}
.quote-totals dt{color:#d7e4dc}
.quote-totals dd{margin:0;font-variant-numeric:tabular-nums}
.quote-totals .grand{margin-top:8px;padding-top:8px;border-top:1px solid rgba(255,255,255,.25);font-size:16px;font-weight:700}
@media(max-width:800px){.quote-doc-head,.quote-doc-foot{grid-template-columns:minmax(0,1fr)}.quote-title-block,.quote-mark{justify-self:start}}
.quote-sheet th,.quote-sheet td{white-space:nowrap;vertical-align:top}
.quote-sheet td:last-child{white-space:normal;min-width:140px}
.wholesale-quote-summary{margin-top:10px;padding:12px;border:1px solid #dce5df;border-radius:8px;background:#f8faf9}
.wholesale-quote-summary h4{margin:0 0 10px}
.quote-summary-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px 16px;margin:0}
.quote-summary-grid div{min-width:0}
.quote-summary-grid dt{font-size:12px;color:#52615c}
.quote-summary-grid dd{margin:2px 0 0;overflow-wrap:anywhere;font-weight:600}
.quote-line-details{margin-top:12px;border-top:1px solid #dce5df;padding-top:10px}
.quote-line-details summary{cursor:pointer;font-weight:600;min-height:36px}
@media(max-width:700px){.quote-summary-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}

.mail-dialog { padding: 0; border: 0; background: transparent; max-width: none; max-height: none; width: min(900px, calc(100% - 48px)); height: min(860px, calc(100% - 48px)); overflow: visible; color: inherit; }
.mail-dialog:not([open]) { display: none; }
.mail-dialog::backdrop { background: rgba(16, 28, 22, .55); }
.mail-modal-card { display: flex; flex-direction: column; width: 100%; height: 100%; background: #f7f9f8; border-radius: 18px; box-shadow: 0 30px 80px rgba(16, 28, 22, .35); overflow: hidden; outline: none; }
.mail-modal-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; padding: 22px 28px 14px; background: #fff; border-bottom: 1px solid #e1e8e3; }
.mail-modal-head h2 { margin: 0; font-size: 22px; line-height: 1.25; overflow-wrap: anywhere; }
.mail-eyebrow { margin: 0 0 4px; font-size: 11px; letter-spacing: .12em; color: #64766b; }
.mail-x { flex: none; min-width: 44px; min-height: 44px; padding: 0; border-radius: 50%; border: 1px solid #dfe7e1; background: #fff; color: #1b2421; cursor: pointer; }
.mail-meta { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 24px; margin: 0; padding: 16px 28px; background: #fff; border-bottom: 1px solid #e1e8e3; }
.mail-meta div { min-width: 0; }
.mail-meta dt { font-size: 11px; letter-spacing: .08em; color: #64766b; text-transform: none; }
.mail-meta dd { margin: 2px 0 0; font-size: 14px; overflow-wrap: anywhere; }
.mail-meta dd small { color: #64766b; font-size: 12px; }
.mail-meta .ok { color: #0f6e5c; font-weight: 600; } .mail-meta .warn { color: #a5611c; }
.mail-frame { display: block; flex: 1 1 auto; width: 100%; min-height: min(520px, 55vh); border: 0; background: #f4f7f5; }
.mail-modal-foot { display: flex; justify-content: flex-end; gap: 12px; padding: 16px 28px; background: #fff; border-top: 1px solid #e1e8e3; }
.mail-btn { min-height: 44px; padding: 0 22px; border-radius: 999px; border: 1px solid #cddbd1; background: #fff; color: #1b2421; cursor: pointer; font: inherit; }
.mail-btn.primary { background: #0f6e5c; border-color: #0f6e5c; color: #fff; font-weight: 600; }
@media (max-width: 700px) {
  .mail-dialog { width: 100%; height: 100%; max-height: 100%; }
  .mail-modal-card { width: 100%; height: 100%; border-radius: 0; }
  .mail-modal-head, .mail-meta, .mail-modal-foot { padding-left: 16px; padding-right: 16px; }
  .mail-meta { grid-template-columns: minmax(0, 1fr); }
  .mail-modal-foot { position: sticky; bottom: 0; }
  .mail-modal-foot .mail-btn { flex: 1; }
}

/* Accounts page: numbered work queues (to do / waiting / done). */
.fin-sub { margin: 4px 0 0; color: #52635a; font-size: 13px; }
.fin-steps { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin: 4px 0 16px; }
.desk .fin-step { display: flex; align-items: center; justify-content: flex-start; gap: 10px; min-height: 60px; padding: 10px 12px; text-align: left; background: transparent; color: #17462f; border: 1px solid #dce5df; border-left: 4px solid #0f6e5c; border-radius: 12px; font-weight: 400; }
.desk .fin-step.idle { border-color: #e5eae6; border-left-color: #cbd8cf; color: #52635a; }
.desk .fin-step:hover:not(:disabled), .desk .fin-step:focus-visible, .desk .fin-step:active { background: #f2f7f3; border-color: #bfd1c5; border-left-color: #0f6e5c; color: #17462f; }
.desk .fin-step.idle:hover:not(:disabled), .desk .fin-step.idle:focus-visible, .desk .fin-step.idle:active { background: #f7f9f7; border-color: #d5ded8; border-left-color: #b9c8be; color: #52635a; }
.fin-step-text { display: grid; gap: 2px; min-width: 0; }
.fin-step-text strong { font-size: 14px; }
.fin-step-text small { font-size: 12px; }
.fin-step:not(.idle) .fin-step-text small { color: #8a3b2c; font-weight: 600; }
.fin-no { display: inline-grid; place-items: center; flex: none; width: 26px; height: 26px; border-radius: 50%; background: #17523a; color: #fff; font-size: 13px; font-weight: 600; }
.fin-step.idle .fin-no, .fin-block.clear .fin-no { background: #dce5df; color: #52635a; }
.fin-block { border: 1px solid #dce5df; border-radius: 8px; background: #fff; padding: 14px 16px; margin-bottom: 12px; scroll-margin-top: 16px; }
.fin-block:not(.clear) { border-color: #9fbfab; }
.fin-block.clear { background: #fafbf9; padding-top: 10px; padding-bottom: 10px; }
.fin-block-head { display: flex; align-items: flex-start; gap: 12px; }
.fin-block-head > div { flex: 1; min-width: 0; }
.desk .fin-block-head h3 { margin: 0; padding: 0; border: 0; font-size: 15px; }
.fin-block-head p { margin: 2px 0 0; color: #52635a; font-size: 13px; line-height: 1.5; }
.fin-block.clear .fin-block-head p { display: none; }
.fin-count { flex: none; min-width: 28px; padding: 2px 8px; border-radius: 12px; background: #fbefec; color: #8a3b2c; text-align: center; font-size: 13px; font-weight: 600; }
.fin-block.clear .fin-count { background: #edf0ec; color: #52635a; }
.fin-clear { margin: 6px 0 0 38px; color: #52635a; font-size: 13px; }
.fin-block.clear .fin-clear { margin-top: 0; }
.fin-rows { list-style: none; margin: 10px 0 0; padding: 0; }
.fin-row { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 8px 14px; align-items: center; padding: 10px 0; border-top: 1px solid #edf0ec; }
.fin-rows.compact .fin-row { grid-template-columns: minmax(0, 1fr) auto; padding: 8px 0; }
.fin-row-main { display: grid; gap: 2px; min-width: 0; overflow-wrap: anywhere; }
.fin-row-main small { color: #52635a; font-size: 12px; }
.fin-row-main a, .fin-row-actions a { color: #17523a; }
.desk .fin-check { min-height: 0; align-items: flex-start; }
.desk .fin-check input[type=checkbox] { margin-top: 2px; }
.fin-state { justify-self: start; padding: 3px 10px; border-radius: 4px; font-size: 12px; white-space: nowrap; background: #f5f6f2; color: #3d4a44; }
.fin-state.todo { background: #fbefec; color: #8a3b2c; }
.fin-state.wait { background: #fdf5e3; color: #7a5a17; }
.fin-state.ok { background: #e6f2ea; color: #17523a; }
.fin-state.idle { background: #f5f6f2; color: #52635a; }
.fin-row-actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 6px; }
.desk .fin-row-actions button { min-height: 36px; padding: 6px 12px; font-size: 13px; }
.fin-row-actions input { width: 180px; min-height: 36px; }
.fin-compose { display: grid; gap: 8px; margin-top: 10px; padding: 12px; background: #f6f9f6; border-radius: 6px; }
.fin-compose .fin-row-actions { justify-content: flex-start; }
.fin-bulk { display: flex; align-items: center; justify-content: flex-end; gap: 10px; margin-top: 8px; font-size: 13px; color: #52635a; }
.fin-more { border: 1px solid #dce5df; border-radius: 8px; background: #fff; padding: 0 16px; margin-bottom: 10px; }
.fin-more > summary { cursor: pointer; min-height: 44px; display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 14px; color: #315844; }
.fin-more > summary span { padding: 1px 8px; border-radius: 10px; background: #edf0ec; color: #52635a; font-size: 12px; font-weight: 500; }
.fin-more[open] { padding-bottom: 12px; }
.fin-tabs { display: flex; gap: 4px; border-bottom: 1px solid #e4eae5; margin-bottom: 10px; }
.desk .fin-tabs button { min-height: 38px; padding: 0 14px; background: transparent; color: #52635a; border: 0; border-bottom: 2px solid transparent; font-weight: 500; }
.desk .fin-tabs button.active { color: #17462f; border-bottom-color: #17523a; font-weight: 600; }
.desk .fin-tabs button:hover:not(:disabled) { background: #f3f6f4; color: #17462f; border-color: transparent; border-bottom-color: #9fbfab; }
.desk .fin-tabs button.active:hover:not(:disabled) { border-bottom-color: #17523a; }
.fin-pane { display: grid; gap: 10px; }
.fin-rebate-form { display: grid; gap: 10px; padding: 12px; background: #f6f9f6; border-radius: 6px; }
.fin-rebate-form .form-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.fin-rebate-form .finance-evidence { grid-column: 1 / -1; }
.fin-rebate-orders { border: 0; margin: 0; padding: 0; display: grid; gap: 2px; max-height: 220px; overflow-y: auto; }
.fin-rebate-orders legend { font-size: 13px; font-weight: 600; margin-bottom: 4px; }
.desk .fin-rebate-orders .checkbox-label { min-height: 34px; }
.fin-rebate-orders small { color: #52635a; }
.fin-rebate-form > button { justify-self: start; }
.project-panes { display:flex; gap:8px; overflow:auto; margin:0 0 14px; }
.desk .project-panes button { flex:none; }
.desk .project-panes button[aria-pressed="true"] { background:#17523a; color:#fff; }
.shipment-workspace,.order-overview { padding:clamp(16px,3vw,28px); }
.shipment-workspace > header,.order-overview > header { margin-bottom:16px; }
.shipment-workspace > header h2,.order-overview > header h2 { margin:0; }
.shipment-workspace > header p,.order-overview > header p { margin:5px 0; color:#52635a; }
.shipment-create,.shipment-fields { display:flex; flex-wrap:wrap; align-items:end; gap:10px; margin:12px 0; }
.shipment-create label,.shipment-fields label { display:grid; gap:4px; min-width:150px; }
.shipment-candidates { display:grid; grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); gap:8px; margin-bottom:20px; }
.shipment-candidates label { display:flex; gap:9px; align-items:flex-start; padding:10px; border:1px solid #dce5df; border-radius:8px; }
.shipment-candidates small,.order-overview td small { display:block; color:#52635a; }
.shipment-card { border:1px solid #dce5df; border-radius:10px; padding:16px; margin:12px 0; }
.shipment-card > header { display:flex; justify-content:space-between; gap:12px; align-items:center; }
.shipment-card > header h3 { display:inline-block; margin:0 10px 0 0; }
.shipment-card ul { padding-left:22px; }
.shipment-card ul.shipment-orders { list-style:none; padding:0; display:grid; gap:12px; }
.shipment-card ul.shipment-orders li { padding:10px 12px; border:1px solid #e4eae5; border-radius:8px; display:grid; gap:8px; }
.shipment-share { color:#17523a; }
.overview-scroll { overflow:auto; }
.order-overview table { border-collapse:collapse; width:100%; min-width:1050px; }
.order-overview th,.order-overview td { text-align:left; padding:10px 9px; border-bottom:1px solid #e4eae5; white-space:nowrap; }
.order-overview th { background:#f5f8f5; }
@media(max-width:700px) { .shipment-create,.shipment-fields { display:grid; grid-template-columns:minmax(0,1fr); } .shipment-create label,.shipment-fields label { min-width:0; } .shipment-candidates { grid-template-columns:minmax(0,1fr); } .shipment-card { padding:12px; } }
@media (max-width: 1100px) { .fin-steps { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 700px) {
  .fin-steps { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; }
  .desk .fin-step { min-height: 48px; padding: 8px; gap: 8px; }
  .fin-row { grid-template-columns: minmax(0, 1fr); }
  .fin-row-actions { justify-content: flex-start; }
  .fin-row-actions input { width: 100%; }
  .fin-rebate-form .form-grid { grid-template-columns: minmax(0, 1fr); }
  .fin-clear, .fin-block.clear .fin-clear { margin-left: 0; margin-top: 6px; }
}
</style>

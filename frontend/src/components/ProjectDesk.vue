<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { request, session } from "../crm-api";

interface Line {
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
  id: string;
  status: string;
  recipient: string;
  subject: string;
}
interface Rebate {
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
  id: number;
  name: string;
  contact_email: string;
  notes: string;
  active: number;
}
interface ProviderTemplate {
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

const props = defineProps<{ admin: boolean }>();
const templateStatus = ref("");
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
const account = reactive({
  company: "",
  contact_name: "",
  email: "",
  phone: "",
  company_address: "",
  username: "",
  password: "",
});
const providerForm = reactive({
  name: "",
  contact_email: "",
  notes: "",
});
const templateForm = reactive({
  provider_id: 0,
  name: "",
  sheet_name: "",
  column_mappings: {} as Record<string, string>,
});
const mappingField = ref("");
const mappingColumn = ref("");
const orderProviderForm = reactive<Record<string, { provider_id: number; template_id: number }>>({});
const activeSection = ref("operations");
const validFields = ["order_id", "project_name", "company", "contact_name", "company_address", "site_address", "phone", "email", "window_name", "product_id", "width_mm", "height_mm", "quantity", "panel_count", "options", "arrived", "delivered"];

const visibleOrders = computed(() => orders.value.filter((order) => !statusFilter.value || order.status === statusFilter.value || order.payment_status === statusFilter.value));
const selectedId = ref("");
const selectedOrder = computed(() => visibleOrders.value.find((order) => order.id === selectedId.value) || visibleOrders.value[0] || null);
const editingProvider = ref<Provider | null>(null);
const editProviderForm = reactive({
  name: "",
  contact_email: "",
  notes: "",
  active: true,
});

onMounted(() => {
  void load();
});

function stableKey(signature: string) {
  const existing = operationKeys.get(signature);
  if (existing) return existing;
  const created = crypto.randomUUID();
  operationKeys.set(signature, created);
  return created;
}

async function load() {
  const [listed, billed, mailed, credits, providerList, templateList] = await Promise.all([
    request<ProjectOrder[]>("operations/orders"),
    request<Invoice[]>("operations/invoices"),
    request<Notice[]>("operations/notifications"),
    request<{ calculation_status: string; credits: Rebate[] }>("operations/rebates"),
    request<Provider[]>("operations/providers"),
    request<ProviderTemplate[]>("operations/provider-templates"),
  ]);
  orders.value = listed;
  invoices.value = billed;
  notices.value = mailed;
  rebates.value = credits.credits;
  providers.value = providerList;
  providerTemplates.value = templateList;
  await refreshTemplate();
  rebateStatus.value = credits.calculation_status;
  for (const order of orders.value) {
    supplierRef[order.id] = order.supplier_reference || supplierRef[order.id] || "";
    if (!orderProviderForm[order.id]) {
      orderProviderForm[order.id] = { provider_id: 0, template_id: 0 };
      await loadOrderProviders(order.id);
    }
    for (const line of order.lines) {
      batch[`${order.id}:${line.id}:discount`] = Number(line.discount ?? 0);
      batch[`${order.id}:${line.id}:product_surcharge`] = Number(line.product_surcharge ?? 0);
      batch[`${order.id}:${line.id}:installation_surcharge`] = Number(line.installation_surcharge ?? 0);
    }
  }
}

function mailStatus(status: string) {
  const labels: Record<string, [string, string]> = {
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

function openAccount() {
  return act(async () => {
    await request("operations/customers", { ...account });
    account.company = "";
    account.contact_name = "";
    account.email = "";
    account.phone = "";
    account.company_address = "";
    account.username = "";
    account.password = "";
    notice.value = tx("已开通一个客户账号和一个联系人。", "Opened one customer account with one contact.");
  });
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
    error.value = tx("先勾选要标为在途的项目。", "Select the projects to mark in transit.");
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
    notice.value = result.results.map((row) => `${row.order_id}: ${row.status}${row.reason ? ` (${row.reason})` : ""}`).join("; ");
  });
}

function batchLines(order: ProjectOrder, kind: "arrival" | "delivery") {
  return order.lines
    .map((line) => ({ line_id: line.id, quantity: Number(batch[`${order.id}:${line.id}:${kind}`] || 0) }))
    .filter((line) => line.quantity > 0);
}

function optionText(line: Line) {
  return Object.entries(line.options || {}).map(([name, value]) => `${name}: ${value}`).join(", ");
}

async function arriveSelected() {
  const targets = orders.value.filter((order) => picked.value.includes(order.id));
  if (!targets.length) {
    error.value = tx("先勾选要记录到货的项目。", "Select the projects whose arrival to record.");
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
  notice.value = arrivalRows.value.map((row) => `${row.order_id}: ${row.status} ${row.detail}`).join("; ");
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
    error.value = tx("先勾选同一公司的项目。", "Select projects from one company.");
    return null;
  }
  if (ids.length !== 1) {
    error.value = tx("不能把不同公司放进同一张尾款或同一笔返利。", "Projects from different companies cannot share one balance invoice or one rebate.");
    return null;
  }
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
      currency: "NZD",
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
    error.value = tx("只有待审核项目可以改折扣和附加费。客户页面不能填这些数。", "Only a project awaiting review can change a discount or surcharge. The customer page cannot enter these figures.");
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
      `模板版本 ${status.version || "—"}，产品 ${status.products_count ?? "—"}。${(status.warnings || []).join(" ")}`,
      `Template version ${status.version || "—"}, products ${status.products_count ?? "—"}. ${(status.warnings || []).join(" ")}`,
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
    link.download = `${kind}-draft-${id}.xlsx`;
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
    notice.value = tx("已创建供应商模板", "Provider template created");
  });
}

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
        template_id: first.template_id || 0,
      };
    }
  } catch (e) {
    console.error("Failed to load order providers:", e);
  }
}
</script>

<template>
  <section class="desk" :class="{ 'workspace-layout': true }">
    <p v-if="error" class="alert card" role="alert">{{ error }}</p>
    <p v-if="notice" class="success card" role="status">{{ notice }}</p>

    <div class="workspace-grid">
      <aside class="card order-list">
        <h3>{{ tx("项目列表", "Projects") }}</h3>
        <label class="filter-row">{{ tx("筛选", "Filter") }}
          <select v-model="statusFilter">
            <option value="">{{ tx("全部", "All") }}</option>
            <option v-for="status in [...new Set(orders.flatMap((order) => [order.status, order.payment_status]))]" :key="status" :value="status">{{ status }}</option>
          </select>
        </label>
        <div class="order-scroll">
          <div v-for="order in visibleOrders" :key="order.id" class="order-row">
            <label class="pick-mark">
              <input type="checkbox" :checked="picked.includes(order.id)" @change="toggleOrder(order.id)" />
            </label>
            <button type="button" class="order-pick" :class="{ current: selectedOrder?.id === order.id }" @click="selectedId = order.id">
              <strong>{{ order.project_name }}</strong>
              <span>{{ order.company }}</span>
              <small>{{ order.status }} · {{ order.total ? `${order.currency || ""} ${order.total}` : tx("待计价", "Unpriced") }}</small>
            </button>
          </div>
        </div>
      </aside>

      <div class="detail-panel">
        <nav class="section-tabs">
          <button type="button" :class="{ active: activeSection === 'operations' }" @click="activeSection = 'operations'">{{ tx("订单操作", "Operations") }}</button>
          <button type="button" :class="{ active: activeSection === 'pricing' }" @click="activeSection = 'pricing'">{{ tx("定价模板", "Pricing") }}</button>
          <button type="button" :class="{ active: activeSection === 'customers' }" @click="activeSection = 'customers'">{{ tx("客户账号", "Customers") }}</button>
          <button type="button" :class="{ active: activeSection === 'providers' }" @click="activeSection = 'providers'">{{ tx("供应商管理", "Providers") }}</button>
          <button type="button" :class="{ active: activeSection === 'batch' }" @click="activeSection = 'batch'">{{ tx("批量操作", "Batch") }}</button>
          <button type="button" :class="{ active: activeSection === 'settlement' }" @click="activeSection = 'settlement'">{{ tx("结算返利", "Settlement") }}</button>
        </nav>

        <div class="section-content">
          <section v-if="activeSection === 'operations'" class="card section-card">

            <div v-if="!selectedOrder">
              <p>{{ tx("选择一个项目查看详情", "Select a project to view details") }}</p>
            </div>
            <article v-else class="order-detail">
              <header class="order-header">
                <div>
                  <h2>{{ selectedOrder.project_name }}</h2>
                  <p class="company-name">{{ selectedOrder.company }}</p>
                </div>
                <div class="status-badges">
                  <span class="badge">{{ selectedOrder.status }}</span>
                  <span class="badge">{{ selectedOrder.payment_status }}</span>
                  <span v-if="selectedOrder.arrival_status" class="badge">{{ selectedOrder.arrival_status }}</span>
                </div>
              </header>
              <div class="order-meta">
                <p><strong>{{ tx("施工地址", "Site") }}:</strong> {{ selectedOrder.site_address }}</p>
                <p><strong>{{ tx("总价", "Total") }}:</strong> {{ selectedOrder.total ? `${selectedOrder.currency || ""} ${selectedOrder.total}` : tx("待计价", "Unpriced") }}</p>
                <p v-if="selectedOrder.supplier_reference"><strong>{{ tx("供应商参考", "Supplier ref") }}:</strong> {{ selectedOrder.supplier_reference }}</p>
              </div>
              <h3>{{ tx("产品明细", "Product lines") }}</h3>
              <div class="table-scroll"><table>
                <thead><tr><th>{{ tx("窗户", "Window") }}</th><th>{{ tx("订购", "Ordered") }}</th><th>{{ tx("已到", "Arrived") }}</th><th>{{ tx("已交付", "Delivered") }}</th><th>{{ tx("本批到货", "Arrival") }}</th><th>{{ tx("本批交付", "Delivery") }}</th></tr></thead>
                <tbody>
                  <tr v-for="line in selectedOrder.lines" :key="line.id">
                    <td>
                      <strong>{{ line.window_name }}</strong>
                      <small>{{ tx("系列", "Series") }} {{ line.product_id || "—" }} · {{ line.width_mm || "—" }}×{{ line.height_mm || "—" }} mm<span v-if="optionText(line)"> · {{ optionText(line) }}</span></small>
                    </td>
                    <td>{{ line.quantity }}</td>
                    <td>{{ line.arrived }}</td>
                    <td>{{ line.delivered }}</td>
                    <td><input v-model.number="batch[`${selectedOrder.id}:${line.id}:arrival`]" type="number" min="0" step="1" /></td>
                    <td><input v-model.number="batch[`${selectedOrder.id}:${line.id}:delivery`]" type="number" min="0" step="1" /></td>
                  </tr>
                </tbody>
              </table></div>

              <h3>{{ tx("供应商与导出", "Provider & Export") }}</h3>
              <div class="provider-section">
                <div class="form-row">
                  <label>{{ tx("选择供应商", "Select provider") }}
                    <select v-model="orderProviderForm[selectedOrder.id].provider_id" @change="() => { orderProviderForm[selectedOrder.id].template_id = 0; }">
                      <option :value="0">{{ tx("未分配", "Not assigned") }}</option>
                      <option v-for="p in providers.filter(p => p.active)" :key="p.id" :value="p.id">{{ p.name }}</option>
                    </select>
                  </label>
                  <label v-if="orderProviderForm[selectedOrder.id].provider_id">{{ tx("选择模板", "Select template") }}
                    <select v-model="orderProviderForm[selectedOrder.id].template_id">
                      <option :value="0">{{ tx("默认", "Default") }}</option>
                      <option v-for="t in providerTemplates.filter(t => t.provider_id === orderProviderForm[selectedOrder.id].provider_id && t.active)" :key="t.id" :value="t.id">{{ t.name }}</option>
                    </select>
                  </label>
                  <button type="button" :disabled="busy || !orderProviderForm[selectedOrder.id].provider_id" @click="assignProvider(selectedOrder.id)">{{ tx("分配供应商", "Assign provider") }}</button>
                </div>
                <div class="form-row">
                  <button type="button" class="secondary" :disabled="busy" @click="exportWithProvider(selectedOrder.id, orderProviderForm[selectedOrder.id].provider_id || undefined, false)">{{ tx("导出供应商模板", "Export provider template") }}</button>
                  <button type="button" class="secondary" :disabled="busy" @click="exportWithProvider(selectedOrder.id, undefined, true)">{{ tx("导出基本模板（未验证）", "Export basic (not verified)") }}</button>
                  <button type="button" class="secondary" :disabled="busy" @click="downloadSheet(selectedOrder.id, 'production-sheet')">{{ tx("生产资料草稿", "Production draft") }}</button>
                  <button type="button" class="secondary" :disabled="busy" @click="downloadSheet(selectedOrder.id, 'job-sheet')">{{ tx("安装工作单草稿", "Job sheet") }}</button>
                </div>
              </div>

              <h3>{{ tx("订单操作", "Order actions") }}</h3>
              <div class="actions">
                <button type="button" :disabled="busy" @click="review(selectedOrder.id)">{{ tx("确认接收", "Accept review") }}</button>
                <button type="button" class="secondary" :disabled="busy" @click="deposit(selectedOrder.id)">{{ tx("定金已收", "Deposit received") }}</button>
                <label>{{ tx("供应商参考号", "Supplier ref") }}<input v-model="supplierRef[selectedOrder.id]" /></label>
                <button type="button" class="secondary" :disabled="busy || !supplierRef[selectedOrder.id]" @click="supplier(selectedOrder)">{{ tx("记录下单", "Record order") }}</button>
                <button type="button" class="secondary" :disabled="busy" @click="fulfil(selectedOrder, 'arrival')">{{ tx("记录本批到货", "Record arrival") }}</button>
                <button type="button" class="secondary" :disabled="busy" @click="fulfil(selectedOrder, 'delivery')">{{ tx("记录本批交付", "Record delivery") }}</button>
              </div>

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
                <label>{{ tx("调整说明", "Adjustment note") }}<input v-model="adjustNote[selectedOrder.id]" /></label>
                <button type="button" :disabled="busy" @click="adjust(selectedOrder)">{{ tx("保存员工调整", "Save adjustment") }}</button>
              </div>

              <div v-if="selectedOrder.invoices && selectedOrder.invoices.length">
                <h3>{{ tx("发票", "Invoices") }}</h3>
                <div v-for="invoice in selectedOrder.invoices" :key="invoice.id" class="invoice">
                  <label><input type="checkbox" :value="invoice.id" v-model="invoicePick" /> {{ invoice.kind }} · {{ invoice.currency }} {{ invoice.amount }} · {{ mailStatus(invoice.status) }} · {{ invoice.payment_status === "received" ? tx("已收", "Received") : tx("未收", "Unpaid") }}</label>
                  <template v-if="invoice.kind === 'balance'">
                    <input v-model="receiptNote[invoice.id]" :placeholder="tx('尾款备注', 'Balance note')" />
                    <button type="button" class="secondary" :disabled="busy" @click="markBalanceReceived(invoice)">{{ tx("尾款已收", "Balance received") }}</button>
                  </template>
                </div>
              </div>
            </article>
          </section>

          <section v-if="activeSection === 'pricing'" class="card section-card">
            <h2>{{ tx("导入计价模板", "Import pricing template") }}</h2>
            <p class="hint">{{ tx("只把选项和价格放进私有库。页面不展示整张批发价矩阵，也不把客户原文件提交到公开仓库。", "Options and prices go into the private store. This page does not show the wholesale price matrix, and the customer's original file is not committed to the public repository.") }}</p>
            <input type="file" accept=".xlsm,.xlsx" :disabled="busy" @change="importTemplate" />
            <p v-if="templateStatus">{{ templateStatus }}</p>
          </section>

          <section v-if="activeSection === 'customers'" class="card section-card">
            <h2>{{ tx("开通客户账号", "Open customer account") }}</h2>
            <p class="hint">{{ tx("一个客户只能有一个登录和一个联系人。", "A customer can have only one login and one contact.") }}</p>
            <form @submit.prevent="openAccount" class="form-grid">
              <label>{{ tx("公司", "Company") }}<input v-model="account.company" required /></label>
              <label>{{ tx("联系人", "Contact") }}<input v-model="account.contact_name" required /></label>
              <label>{{ tx("邮箱", "Email") }}<input v-model="account.email" type="email" required /></label>
              <label>{{ tx("电话", "Phone") }}<input v-model="account.phone" required /></label>
              <label>{{ tx("公司地址", "Company address") }}<input v-model="account.company_address" required /></label>
              <label>{{ tx("登录账号", "Username") }}<input v-model="account.username" required autocomplete="off" /></label>
              <label>{{ tx("初始密码", "Starting password") }}<input v-model="account.password" type="password" required autocomplete="new-password" /></label>
              <button :disabled="busy">{{ tx("开通", "Open") }}</button>
            </form>
          </section>

          <section v-if="activeSection === 'providers'" class="card section-card">
            <h2>{{ tx("供应商管理", "Provider management") }}</h2>
            
            <h3>{{ tx("创建供应商", "Create provider") }}</h3>
            <form @submit.prevent="createProvider" class="form-grid">
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
                  <button type="button" class="secondary" @click="startEditProvider(provider)">{{ tx("编辑", "Edit") }}</button>
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
            <form @submit.prevent="createTemplate" class="template-form">
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
                <h4>{{ template.name }} <span class="provider-badge">{{ providers.find(p => p.id === template.provider_id)?.name }}</span></h4>
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

          <section v-if="activeSection === 'batch'" class="card section-card">
            <h2>{{ tx("批量操作", "Batch operations") }}</h2>
            <p class="hint">{{ tx("勾选多个项目后批量标记在途或记录到货", "Select multiple projects for batch transit or arrival") }}</p>
            <div class="batch-actions">
              <button type="button" :disabled="busy" @click="transitSelected">{{ tx("批量标为在途", "Mark in transit") }}</button>
              <button type="button" :disabled="busy" @click="arriveSelected">{{ tx("批量记录到货", "Record arrival") }}</button>
            </div>
            <p v-if="transitRows.length">{{ transitRows.map((row) => `${row.order_id}: ${row.status}${row.reason ? " (" + row.reason + ")" : ""}`).join(" · ") }}</p>
            <p v-if="arrivalRows.length">{{ arrivalRows.map((row) => `${row.order_id}: ${row.status} ${row.detail}`).join(" · ") }}</p>

            <h3>{{ tx("发票发送", "Invoice sending") }}</h3>
            <p class="hint">{{ tx("勾选同一公司的发票后一起发送。跨公司会被拦住。重复发送不会再发一封。", "Select invoices from one company, then send them together. A mix of companies is blocked. Sending again does not send another copy.") }}</p>
            <button type="button" :disabled="busy" @click="sendSelectedInvoices">{{ tx("发送勾选的发票", "Send selected") }}</button>

            <h3>{{ tx("通知状态", "Notifications") }}</h3>
            <p v-if="!notices.length">{{ tx("还没有到货或发票通知。", "No notifications yet.") }}</p>
            <div v-for="item in notices" :key="item.id" class="notification-item">
              <span>{{ item.subject }} · {{ item.recipient }} · {{ mailStatus(item.status) }}</span>
              <button v-if="item.status === 'not_configured'" type="button" class="secondary" :disabled="busy" @click="retryNotice(item.id)">{{ tx("重试", "Retry") }}</button>
            </div>
          </section>

          <section v-if="activeSection === 'settlement'" class="card section-card">
            <h2>{{ tx("同公司尾款", "Balance invoice") }}</h2>
            <p class="hint">{{ tx("只对已全部交付、定金已收、同一公司的项目生成尾款草稿。部分到货会拒绝。金额用已保存的定金，不按 60% 重算旧发票。", "A balance draft is created only for fully delivered, deposit-confirmed projects of one company. Partial arrival is refused. The amount uses the stored deposit and does not recalculate an old invoice at 60%.") }}</p>
            <label>{{ tx("已确认的规则说明", "Confirmed rule evidence") }}<textarea v-model="settlementEvidence" rows="3" /></label>
            <button type="button" :disabled="busy" @click="settleSelected">{{ tx("生成尾款草稿", "Create balance") }}</button>

            <h3>{{ tx("已确认返利", "Confirmed rebates") }}</h3>
            <p class="hint">{{ tx("只记录已经确认的月度金额。没有阶梯公式，页面不算返点。同一订单不能重复计入。", "Record only a confirmed monthly amount. There is no tier formula, and this page does not calculate a rebate. An order cannot be counted twice.") }}</p>
            <p v-if="rebateStatus">{{ rebateStatus }}</p>
            <div class="form-grid">
              <label>{{ tx("年月", "Month") }}<input v-model="rebateForm.month" placeholder="2026-10" /></label>
              <label>{{ tx("金额", "Amount") }}<input v-model="rebateForm.amount" inputmode="decimal" /></label>
              <label>{{ tx("确认依据", "Evidence") }}<input v-model="rebateForm.evidence" /></label>
              <button type="button" :disabled="busy" @click="recordRebate">{{ tx("记入", "Record") }}</button>
            </div>
            <div v-for="credit in rebates" :key="credit.id" class="rebate-item">
              <span>#{{ credit.customer_id }} · {{ credit.month }} · {{ credit.currency }} {{ credit.amount }} · {{ tx("已用", "Used") }} {{ credit.used || "0.00" }} · {{ tx("余额", "Remaining") }} {{ credit.remaining || "0.00" }}</span>
            </div>
          </section>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.desk { font-size: 15px; line-height: 1.55; min-width: 0; max-width: 100%; }
.desk .card { padding: 16px; background: white; border: 1px solid #e1e6df; border-radius: 8px; }
.alert { padding: 12px 16px; background: #fae8e1; color: #842b16; border-radius: 6px; margin-bottom: 12px; }
.success { padding: 12px 16px; background: #e5efdd; color: #2d4a1e; border-radius: 6px; margin-bottom: 12px; }
.workspace-grid { display: grid; grid-template-columns: 280px 1fr; gap: 16px; min-height: calc(100vh - 180px); min-width: 0; }
.order-list { display: flex; flex-direction: column; gap: 8px; position: sticky; top: 16px; max-height: calc(100vh - 200px); min-width: 0; }
.order-list h3 { font-size: 18px; font-weight: 600; margin: 0 0 12px; }
.filter-row { font-size: 14px; margin-bottom: 8px; }
.filter-row select { width: 100%; margin-top: 4px; }
.order-scroll { overflow-y: auto; display: flex; flex-direction: column; gap: 6px; padding-right: 4px; }
.order-row { display: flex; gap: 6px; align-items: stretch; }
.pick-mark { display: flex; align-items: center; padding: 0 4px; }
.pick-mark input { width: 18px; height: 18px; margin: 0; cursor: pointer; }
.order-pick { flex: 1; display: grid; gap: 4px; text-align: left; padding: 10px 12px; border: 1px solid #d5ddd6; background: #fff; color: #1b2421; border-radius: 6px; cursor: pointer; transition: all 0.2s; min-width: 0; max-width: 100%; }
.order-pick:hover { border-color: #3d6b4f; background: #f9faf8; }
.order-pick.current { border-color: #0f6e5c; background: #f4f8f2; box-shadow: 0 0 0 2px rgba(15, 110, 92, 0.1); }
.order-pick strong { font-size: 15px; font-weight: 600; color: #1b2421; overflow-wrap: anywhere; word-break: break-word; }
.order-pick span { font-size: 14px; color: #e7eee9; overflow-wrap: anywhere; word-break: break-word; }
.order-pick.current span { color: #1b2421; }
.order-pick small { font-size: 13px; color: #b8c5be; margin-top: 2px; overflow-wrap: anywhere; word-break: break-word; }
.order-pick.current small { color: #3d4a44; }
.detail-panel { display: flex; flex-direction: column; min-height: 600px; min-width: 0; }
.section-tabs { display: flex; gap: 4px; padding: 8px; background: white; border: 1px solid #e1e6df; border-radius: 8px 8px 0 0; border-bottom: none; overflow-x: auto; -webkit-overflow-scrolling: touch; max-width: 100%; box-sizing: border-box; }
.section-tabs button { padding: 10px 16px; border: none; background: transparent; color: #3d4a44; font-size: 14px; font-weight: 500; border-radius: 6px; cursor: pointer; transition: all 0.2s; white-space: nowrap; flex-shrink: 0; }
.section-tabs button:hover { background: #f5f6f2; }
.section-tabs button.active { background: #0f6e5c; color: white; }
.section-content { flex: 1; min-width: 0; }
.section-card { border-radius: 0 0 8px 8px; overflow-y: auto; max-height: calc(100vh - 280px); min-width: 0; box-sizing: border-box; }
.order-detail h2 { font-size: 24px; margin: 0; }
.order-detail h3 { font-size: 18px; font-weight: 600; margin: 24px 0 12px; padding-bottom: 8px; border-bottom: 2px solid #e1e6df; }
.order-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 16px; padding-bottom: 16px; border-bottom: 1px solid #e1e6df; }
.company-name { font-size: 16px; color: #6d7c72; margin: 6px 0 0; }
.status-badges { display: flex; gap: 8px; flex-wrap: wrap; }
.badge { display: inline-block; padding: 6px 12px; background: #f5f6f2; color: #3d4a44; border-radius: 6px; font-size: 13px; font-weight: 500; }
.order-meta { display: grid; gap: 8px; margin-bottom: 20px; font-size: 15px; }
.order-meta p { margin: 0; }
.table-scroll { overflow-x: auto; margin: 12px 0; max-width: 100%; -webkit-overflow-scrolling: touch; }
.table-scroll table { width: 100%; min-width: 600px; border-collapse: collapse; }
@media (max-width: 390px) {
  .table-scroll table { min-width: 100%; width: max-content; }
}
th, td { text-align: left; border-bottom: 1px solid #e1e6df; padding: 12px 10px; font-size: 14px; vertical-align: top; }
th { background: #f9faf8; font-weight: 600; color: #1b2421; }
td strong { font-weight: 600; }
td small { display: block; color: #6d7c72; font-size: 13px; margin-top: 4px; line-height: 1.45; }
td input { width: 80px; padding: 6px 8px; border: 1px solid #d5ddd6; border-radius: 4px; font-size: 14px; }
.provider-section, .adjustment-section { margin-top: 20px; padding-top: 20px; border-top: 1px solid #e1e6df; }
.form-row { display: flex; gap: 12px; align-items: end; flex-wrap: wrap; margin-bottom: 12px; }
.form-row label { flex: 1; min-width: 180px; font-size: 14px; }
.form-row button { flex-shrink: 0; }
.actions { display: flex; flex-wrap: wrap; gap: 12px; align-items: end; margin-top: 12px; }
.actions label { min-width: 200px; font-size: 14px; }
.desk input, .desk select, .desk textarea { width: 100%; box-sizing: border-box; padding: 10px 12px; border: 1px solid #d5ddd6; border-radius: 6px; font-size: 14px; font-family: inherit; min-width: 0; max-width: 100%; }
.desk button { min-height: 40px; padding: 10px 18px; border: 1px solid #0f6e5c; background: #0f6e5c; color: white; border-radius: 6px; font-size: 14px; font-weight: 500; cursor: pointer; transition: all 0.2s; }
.desk button:hover:not(:disabled) { background: #0d5a4a; border-color: #0d5a4a; }
.desk button.secondary { background: white; color: #3d4a44; border-color: #d5ddd6; }
.desk button.secondary:hover:not(:disabled) { background: #f5f6f2; border-color: #c5d0c8; }
.desk button:disabled { opacity: 0.5; cursor: not-allowed; }
.desk label { display: block; font-size: 14px; font-weight: 500; color: #1b2421; }
.desk label input, .desk label select, .desk label textarea { margin-top: 6px; }
.hint { color: #6d7c72; font-size: 14px; line-height: 1.6; margin: 8px 0; }
.form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin-top: 16px; }
.form-grid button { grid-column: 1 / -1; justify-self: start; }
@media (max-width: 600px) {
  .form-grid { grid-template-columns: 1fr; }
}
.invoice { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; padding: 12px; background: #f9faf8; border-radius: 6px; margin-top: 8px; font-size: 14px; }
.invoice label { margin: 0; display: flex; align-items: center; gap: 8px; }
.provider-list, .template-list { display: grid; gap: 12px; margin-top: 16px; }
.provider-card, .template-card { padding: 16px; background: #f9faf8; border: 1px solid #e1e6df; border-radius: 6px; min-width: 0; max-width: 100%; }
.provider-card h4, .template-card h4 { font-size: 16px; margin: 0 0 12px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; overflow-wrap: anywhere; word-break: break-word; }
.provider-card p, .template-card p { overflow-wrap: anywhere; word-break: break-word; }
.status-active { color: #0f6e5c; font-size: 13px; font-weight: 500; }
.status-inactive { color: #8a3b2c; font-size: 13px; font-weight: 500; }
.provider-badge { padding: 4px 8px; background: #e1e6df; color: #3d4a44; border-radius: 4px; font-size: 12px; font-weight: 500; }
.edit-form { display: grid; gap: 12px; }
.checkbox-label { display: flex; align-items: center; gap: 8px; font-weight: normal; }
.checkbox-label input { width: auto; margin: 0; }
.button-group { display: flex; gap: 8px; }
.template-form { margin-top: 16px; padding-top: 16px; border-top: 1px solid #e1e6df; }
.template-form h4 { font-size: 16px; margin: 16px 0 8px; }
.mapping-controls { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
.mapping-controls select, .mapping-controls input { flex: 1; }
.mappings-list { display: grid; gap: 6px; margin: 12px 0; padding: 12px; background: #f9faf8; border-radius: 6px; }
.mapping-item { display: flex; justify-content: space-between; align-items: center; padding: 8px; background: white; border-radius: 4px; }
.link-button { background: none; border: none; color: #0f6e5c; padding: 4px 8px; min-height: auto; text-decoration: underline; cursor: pointer; }
.mapping-display { display: grid; gap: 4px; margin-top: 8px; font-size: 13px; }
.batch-actions { display: flex; gap: 12px; margin: 16px 0; flex-wrap: wrap; }
.notification-item, .rebate-item { padding: 12px; background: #f9faf8; border-radius: 6px; margin-top: 8px; display: flex; justify-content: space-between; align-items: center; gap: 12px; }
@media (max-width: 1199px) {
  .workspace-grid { grid-template-columns: 1fr; }
  .order-list { position: static; max-height: 320px; }
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
  .order-list { max-height: 240px; min-width: 0; width: 100%; }
  .detail-panel { min-width: 0; width: 100%; }
  .section-tabs { padding: 6px; gap: 2px; min-width: 0; }
  .section-tabs button { padding: 8px 12px; font-size: 13px; }
  .section-content { min-width: 0; width: 100%; }
  .section-card { min-width: 0; width: 100%; }
  .form-grid { grid-template-columns: 1fr; }
  .form-row, .actions, .batch-actions { flex-direction: column; align-items: stretch; min-width: 0; }
  .form-row button, .actions button { width: 100%; box-sizing: border-box; }
  .form-row label, .actions label { min-width: 0; max-width: 100%; width: 100%; box-sizing: border-box; }
  .desk input, .desk select, .desk textarea { font-size: 14px; width: 100%; box-sizing: border-box; }
  .desk button { font-size: 14px; }
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
</style>

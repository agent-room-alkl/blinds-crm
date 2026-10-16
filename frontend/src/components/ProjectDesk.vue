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

const visibleOrders = computed(() => orders.value.filter((order) => !statusFilter.value || order.status === statusFilter.value || order.payment_status === statusFilter.value));
const selectedId = ref("");
const selectedOrder = computed(() => visibleOrders.value.find((order) => order.id === selectedId.value) || visibleOrders.value[0] || null);

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
  const [listed, billed, mailed, credits] = await Promise.all([
    request<ProjectOrder[]>("operations/orders"),
    request<Invoice[]>("operations/invoices"),
    request<Notice[]>("operations/notifications"),
    request<{ calculation_status: string; credits: Rebate[] }>("operations/rebates"),
  ]);
  orders.value = listed;
  invoices.value = billed;
  notices.value = mailed;
  rebates.value = credits.credits;
  await refreshTemplate();
  rebateStatus.value = credits.calculation_status;
  for (const order of orders.value) {
    supplierRef[order.id] = order.supplier_reference || supplierRef[order.id] || "";
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
</script>

<template>
  <section class="desk">
    <div class="card intro">
      <h2>{{ tx("项目订单", "Project orders") }}</h2>
      <p>{{ tx("客户在门户提交。这里审核、定金、供应商记录和分批到货。正式工厂格式仍会拒绝；生产资料草稿和安装工作单草稿可以下载，不是已验收的工厂文件。", "Customers submit in the portal. Review, deposit, supplier reference and partial arrival happen here. Factory format is still refused. Production and job-sheet drafts can be downloaded and are not an accepted factory file.") }}</p>
      <p v-if="error" class="alert" role="alert">{{ error }}</p>
      <p v-if="notice" role="status">{{ notice }}</p>
    </div>

    <details v-if="admin" class="card fold">
      <summary>{{ tx("导入计价模板", "Import the pricing template") }}</summary>
      <h2>{{ tx("导入计价模板", "Import the pricing template") }}</h2>
      <p class="hint">{{ tx("只把选项和价格放进私有库。页面不展示整张批发价矩阵，也不把客户原文件提交到公开仓库。", "Options and prices go into the private store. This page does not show the wholesale price matrix, and the customer's original file is not committed to the public repository.") }}</p>
      <input type="file" accept=".xlsm,.xlsx" :disabled="busy" @change="importTemplate" />
      <p v-if="templateStatus">{{ templateStatus }}</p>
    </details>

    <details v-if="admin" class="card fold">
      <summary>{{ tx("开通客户账号", "Open a customer account") }}</summary>
    <form @submit.prevent="openAccount">
      <h2>{{ tx("开通客户账号", "Open a customer account") }}</h2>
      <p class="hint">{{ tx("一个客户只能有一个登录和一个联系人。", "A customer can have only one login and one contact.") }}</p>
      <div class="grid">
        <label>{{ tx("公司", "Company") }}<input v-model="account.company" required /></label>
        <label>{{ tx("联系人", "Contact") }}<input v-model="account.contact_name" required /></label>
        <label>{{ tx("邮箱", "Email") }}<input v-model="account.email" type="email" required /></label>
        <label>{{ tx("电话", "Phone") }}<input v-model="account.phone" required /></label>
        <label>{{ tx("公司地址", "Company address") }}<input v-model="account.company_address" required /></label>
        <label>{{ tx("登录账号", "Username") }}<input v-model="account.username" required autocomplete="off" /></label>
        <label>{{ tx("初始密码", "Starting password") }}<input v-model="account.password" type="password" required autocomplete="new-password" /></label>
      </div>
      <button :disabled="busy">{{ tx("开通", "Open account") }}</button>
    </form>
    </details>

    <section class="card batch-bar">
      <label>{{ tx("按状态筛选", "Filter by status") }}
        <select v-model="statusFilter">
          <option value="">{{ tx("全部", "All") }}</option>
          <option v-for="status in [...new Set(orders.flatMap((order) => [order.status, order.payment_status]))]" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button type="button" :disabled="busy" @click="transitSelected">{{ tx("批量标为在途", "Mark selected in transit") }}</button>
      <button type="button" :disabled="busy" @click="arriveSelected">{{ tx("批量记录到货", "Record arrival for selected") }}</button>
      <p v-if="transitRows.length">{{ transitRows.map((row) => `${row.order_id}: ${row.status}${row.reason ? " (" + row.reason + ")" : ""}`).join(" · ") }}</p>
      <p v-if="arrivalRows.length">{{ arrivalRows.map((row) => `${row.order_id}: ${row.status} ${row.detail}`).join(" · ") }}</p>
    </section>

    <p v-if="!visibleOrders.length" class="card">{{ tx("没有符合筛选的门户项目。", "No portal projects match this filter.") }}</p>
    <div v-else class="split">
      <aside class="card order-list">
        <div v-for="order in visibleOrders" :key="order.id" class="order-row">
          <label class="pick-mark">
            <input type="checkbox" :checked="picked.includes(order.id)" @change="toggleOrder(order.id)" />
            <span>{{ picked.includes(order.id) ? tx("已勾选", "Selected") : tx("未勾选", "Not selected") }}</span>
          </label>
          <button type="button" class="order-pick" :class="{ current: selectedOrder?.id === order.id }" @click="selectedId = order.id">
            <strong>{{ order.project_name }}</strong>
            <span>{{ order.company }} · {{ order.status }} · {{ order.total ? `${order.currency || ""} ${order.total}` : tx("待计价", "Unpriced") }}</span>
          </button>
        </div>
      </aside>
    <article v-for="order in selectedOrder ? [selectedOrder] : []" :key="order.id" class="card order">
      <header>
        <label><input type="checkbox" :checked="picked.includes(order.id)" @change="toggleOrder(order.id)" /> {{ order.project_name }}</label>
        <span>{{ order.company }}</span>
      </header>
      <p>{{ tx("施工地址", "Site address") }}：{{ order.site_address }}</p>
      <p>{{ order.status }} · {{ tx("收款", "Payment") }} {{ order.payment_status }}<template v-if="order.arrival_status"> · {{ order.arrival_status }}</template><template v-if="order.delivery_status"> · {{ order.delivery_status }}</template></p>
      <p>{{ order.total ? `${order.currency || ""} ${order.total}` : tx("合计待配置，不能审核开票", "Total is not configured, so review and invoicing stay closed") }}</p>
      <div class="table-scroll"><table>
        <thead><tr><th>{{ tx("窗户", "Window") }}</th><th>{{ tx("订购", "Ordered") }}</th><th>{{ tx("已到", "Arrived") }}</th><th>{{ tx("已交付", "Delivered") }}</th><th>{{ tx("本批到货", "This arrival") }}</th><th>{{ tx("本批交付", "This delivery") }}</th><th>{{ tx("折扣比例", "Discount ratio") }}</th><th>{{ tx("商品附加", "Product surcharge") }}</th><th>{{ tx("安装附加", "Installation surcharge") }}</th></tr></thead>
        <tbody>
          <tr v-for="line in order.lines" :key="line.id">
            <td>{{ line.window_name }}<small>{{ tx("系列", "Series") }} {{ line.product_id || "—" }} · {{ line.width_mm || "—" }}×{{ line.height_mm || "—" }} mm<span v-if="optionText(line)"> · {{ optionText(line) }}</span><span v-if="line.amount"> · {{ order.currency || "" }} {{ line.amount }}</span><span v-else> · {{ tx("行价待配置", "Line price not configured") }}</span></small></td>
            <td>{{ line.quantity }}</td>
            <td>{{ line.arrived }}</td>
            <td>{{ line.delivered }}</td>
            <td><input v-model.number="batch[`${order.id}:${line.id}:arrival`]" type="number" min="0" step="1" /></td>
            <td><input v-model.number="batch[`${order.id}:${line.id}:delivery`]" type="number" min="0" step="1" /></td>
            <td><input v-model.number="batch[`${order.id}:${line.id}:discount`]" type="number" min="0" max="1" step="0.01" :disabled="order.status !== 'pending_review'" /></td>
            <td><input v-model.number="batch[`${order.id}:${line.id}:product_surcharge`]" type="number" min="0" step="0.01" :disabled="order.status !== 'pending_review'" /></td>
            <td><input v-model.number="batch[`${order.id}:${line.id}:installation_surcharge`]" type="number" min="0" step="0.01" :disabled="order.status !== 'pending_review'" /></td>
          </tr>
        </tbody>
      </table></div>
      <div class="actions">
        <button type="button" :disabled="busy" @click="review(order.id)">{{ tx("确认接收", "Accept review") }}</button>
        <button type="button" class="secondary" :disabled="busy" @click="deposit(order.id)">{{ tx("定金已收", "Deposit received") }}</button>
        <label>{{ tx("供应商参考号", "Supplier reference") }}<input v-model="supplierRef[order.id]" /></label>
        <button type="button" class="secondary" :disabled="busy || !supplierRef[order.id]" @click="supplier(order)">{{ tx("记录下单", "Record supplier order") }}</button>
        <button type="button" class="secondary" :disabled="busy" @click="exportBlocked(order.id)">{{ tx("正式工厂格式", "Factory format") }}</button>
        <button type="button" class="secondary" :disabled="busy" @click="downloadSheet(order.id, 'production-sheet')">{{ tx("生产资料草稿", "Production draft") }}</button>
        <button type="button" class="secondary" :disabled="busy" @click="downloadSheet(order.id, 'job-sheet')">{{ tx("安装工作单草稿", "Job-sheet draft") }}</button>
        <label v-if="order.status === 'pending_review'">{{ tx("调整说明", "Adjustment note") }}<input v-model="adjustNote[order.id]" /></label>
        <button v-if="order.status === 'pending_review'" type="button" class="secondary" :disabled="busy" @click="adjust(order)">{{ tx("保存员工调整", "Save staff adjustment") }}</button>
        <button type="button" class="secondary" :disabled="busy" @click="fulfil(order, 'arrival')">{{ tx("记录本批到货", "Record this arrival") }}</button>
        <button type="button" class="secondary" :disabled="busy" @click="fulfil(order, 'delivery')">{{ tx("记录本批交付", "Record this delivery") }}</button>
      </div>
      <div v-for="invoice in order.invoices || []" :key="invoice.id" class="invoice">
        <label><input type="checkbox" :value="invoice.id" v-model="invoicePick" /> {{ invoice.kind }} · {{ invoice.currency }} {{ invoice.amount }} · {{ tx("发送", "Send") }} {{ mailStatus(invoice.status) }} · {{ tx("收款", "Receipt") }} {{ invoice.payment_status === "received" ? tx("已收", "Received") : tx("未确认收款", "Receipt not confirmed") }}</label>
        <template v-if="invoice.kind === 'balance'">
          <input v-model="receiptNote[invoice.id]" :placeholder="tx('尾款备注', 'Balance note')" />
          <button type="button" class="secondary" :disabled="busy" @click="markBalanceReceived(invoice)">{{ tx("尾款已收", "Balance received") }}</button>
        </template>
      </div>
    </article>
    </div>

    <details class="card fold">
      <summary>{{ tx("同公司尾款", "Balance for one company") }}</summary>
      <h2>{{ tx("同公司尾款", "Balance for one company") }}</h2>
      <p class="hint">{{ tx("只对已全部交付、定金已收、同一公司的项目生成尾款草稿。部分到货会拒绝。金额用已保存的定金，不按 60% 重算旧发票。", "A balance draft is created only for fully delivered, deposit-confirmed projects of one company. Partial arrival is refused. The amount uses the stored deposit and does not recalculate an old invoice at 60%.") }}</p>
      <label>{{ tx("已确认的规则说明", "Confirmed rule evidence") }}<textarea v-model="settlementEvidence" rows="2" /></label>
      <button type="button" :disabled="busy" @click="settleSelected">{{ tx("生成尾款草稿", "Create balance draft") }}</button>
    </details>

    <details class="card fold">
      <summary>{{ tx("已确认返利", "Confirmed rebates") }}</summary>
      <h2>{{ tx("已确认返利", "Confirmed rebates") }}</h2>
      <p class="hint">{{ tx("只记录已经确认的月度金额。没有阶梯公式，页面不算返点。同一订单不能重复计入。", "Record only a confirmed monthly amount. There is no tier formula, and this page does not calculate a rebate. An order cannot be counted twice.") }}</p>
      <p v-if="rebateStatus">{{ rebateStatus }}</p>
      <div class="grid">
        <label>{{ tx("年月", "Month") }}<input v-model="rebateForm.month" placeholder="2026-10" /></label>
        <label>{{ tx("金额", "Amount") }}<input v-model="rebateForm.amount" inputmode="decimal" /></label>
        <label>{{ tx("确认依据", "Evidence") }}<input v-model="rebateForm.evidence" /></label>
      </div>
      <button type="button" :disabled="busy" @click="recordRebate">{{ tx("记入勾选项目的返利", "Record a rebate for the selected projects") }}</button>
      <article v-for="credit in rebates" :key="credit.id" class="invoice">
        <span>#{{ credit.customer_id }} · {{ credit.month }} · {{ credit.currency }} {{ credit.amount }} · {{ tx("已用", "Used") }} {{ credit.used || "0.00" }} · {{ tx("余额", "Remaining") }} {{ credit.remaining || "0.00" }}</span>
      </article>
    </details>

    <details class="card fold">
      <summary>{{ tx("同公司发票", "Invoices for one company") }}</summary>
      <h2>{{ tx("同公司发票", "Invoices for one company") }}</h2>
      <p class="hint">{{ tx("勾选同一公司的发票后一起发送。跨公司会被拦住。重复发送不会再发一封。", "Select invoices from one company, then send them together. A mix of companies is blocked. Sending again does not send another copy.") }}</p>
      <button type="button" :disabled="busy" @click="sendSelectedInvoices">{{ tx("发送勾选的发票", "Send selected invoices") }}</button>
    </details>

    <details class="card fold">
      <summary>{{ tx("通知状态", "Notification status") }}</summary>
      <h2>{{ tx("通知状态", "Notification status") }}</h2>
      <p v-if="!notices.length">{{ tx("还没有到货或发票通知。", "No arrival or invoice notifications yet.") }}</p>
      <article v-for="item in notices" :key="item.id" class="invoice">
        <span>{{ item.subject }} · {{ item.recipient }} · {{ mailStatus(item.status) }}</span>
        <button v-if="item.status === 'not_configured'" type="button" class="secondary" :disabled="busy" @click="retryNotice(item.id)">{{ tx("配置好后重试", "Retry after mail is configured") }}</button>
      </article>
    </details>
  </section>
</template>

<style scoped>
.desk { display: grid; gap: 12px; font-size: 15px; line-height: 1.55; min-width: 0; max-width: 100%; overflow-x: hidden; }
.desk .card { padding: 12px 16px; }
.intro h2, .intro p { margin: 0; }
.intro p { margin-top: 8px; }
.split { display: grid; grid-template-columns: minmax(220px, 280px) minmax(0, 1fr); gap: 16px; align-items: start; min-width: 0; }
.order-list { display: grid; gap: 8px; max-height: 640px; overflow: auto; padding: 8px; }
.order-row { display: flex; gap: 8px; align-items: stretch; min-width: 0; }
.pick-mark { display: flex; flex-direction: column; justify-content: center; gap: 4px; min-width: 72px; font-size: 13px; color: #1b2421; }
.order-pick { display: grid; gap: 2px; width: 100%; text-align: left; justify-content: flex-start; padding: 8px 10px; border: 1px solid #c5d0c8; background: #fff; color: #1b2421; border-radius: 6px; cursor: pointer; min-height: 44px; }
.order-pick.current { border-color: #3d6b4f; background: #f4f8f2; color: #1b2421; }
.order-pick strong { font-size: 15px; color: #1b2421; font-weight: 650; }
.order-pick span { font-size: 13px; color: #3d4a44; line-height: 1.4; }
.fold > summary { font-size: 16px; font-weight: 600; cursor: pointer; min-height: 36px; display: flex; align-items: center; }
.fold > h2, .fold form > h2 { margin-top: 16px; }
.table-scroll { overflow-x: auto; max-width: 100%; }
.table-scroll table { width: max-content; min-width: 100%; margin: 8px 0; }
.table-scroll th, .table-scroll td { white-space: nowrap; }
.table-scroll td small { display: block; max-width: 280px; white-space: normal; }
.batch-bar { display: flex; flex-wrap: wrap; gap: 12px; align-items: end; }
.desk h2 { font-size: 20px; font-weight: 600; margin: 0 0 12px; }
.desk h3 { font-size: 18px; font-weight: 600; margin: 16px 0 8px; }
.section-label { font-size: 13px; letter-spacing: 0.08em; color: #52635a; }
.hint, .desk p, .desk li { font-size: 15px; }
.hint { color: #54645c; line-height: 1.6; }
.grid, .actions { display: flex; flex-wrap: wrap; gap: 16px; align-items: end; }
.grid label, .actions label { min-width: 180px; font-size: 14px; }
.desk input, .desk select, .desk button { min-height: 40px; font-size: 14px; }
.order header { display: flex; justify-content: space-between; gap: 16px; align-items: center; }
.order { padding: 8px 0 16px; }
table { width: 100%; border-collapse: collapse; margin: 16px 0; }
th, td { text-align: left; border-bottom: 1px solid var(--line, #dedbd5); padding: 12px 10px; font-size: 14px; }
td input { width: 96px; }
td small { display: block; color: #54645c; font-size: 13px; margin-top: 4px; line-height: 1.45; }
.invoice { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 16px; align-items: center; margin-top: 12px; font-size: 14px; }
@media (max-width: 900px) {
  .split { grid-template-columns: 1fr; }
  .order-list { max-height: 280px; }
}
.alert { color: #8a3b2c; }
</style>

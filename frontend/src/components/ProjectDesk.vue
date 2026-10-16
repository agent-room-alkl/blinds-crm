<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { request } from "../crm-api";

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
}
interface Invoice {
  id: string;
  customer_id: number;
  kind: string;
  amount: string;
  currency: string;
  status: string;
  order_ids?: string[];
}
interface Notice {
  id: string;
  status: string;
  recipient: string;
  subject: string;
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

defineProps<{ admin: boolean }>();
const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);
const orders = ref<ProjectOrder[]>([]);
const invoices = ref<Invoice[]>([]);
const notices = ref<Notice[]>([]);
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
  const [listed, billed, mailed] = await Promise.all([
    request<ProjectOrder[]>("operations/orders"),
    request<Invoice[]>("operations/invoices"),
    request<Notice[]>("operations/notifications"),
  ]);
  orders.value = listed;
  invoices.value = billed;
  notices.value = mailed;
  for (const order of orders.value) supplierRef[order.id] = order.supplier_reference || supplierRef[order.id] || "";
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
    notice.value = tx("已记录供应商参考号。正式 Excel 仍需确认模板，导出保持关闭。", "Supplier reference recorded. Formal Excel stays closed until the template is confirmed.");
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

function retryNotice(id: string) {
  return act(async () => {
    const sent = await request<Notice>(`operations/notifications/${id}/retry`, {});
    notice.value = tx(`通知状态：${mailStatus(sent.status)}`, `Notification status: ${mailStatus(sent.status)}`);
  });
}
</script>

<template>
  <section class="desk">
    <div class="card">
      <p class="section-label">{{ tx("主流程", "PRIMARY FLOW") }}</p>
      <h2>{{ tx("项目订单", "Project orders") }}</h2>
      <p>{{ tx("客户在门户提交。这里做审核、定金、供应商记录和分批到货。询价与旧报价留在历史入口。跨公司不合并成一张发票。", "Customers submit in the portal. Review, deposit, supplier reference and partial arrival happen here. Inquiries and old quotations stay in the history entries. Invoices are not combined across companies.") }}</p>
      <p class="hint">{{ tx("部分到货的开票金额、返利阶梯和供应商 Excel 模板都还没有确认规则，对应操作会拒绝，而不是套用估计值。", "Partial-arrival billing, rebate tiers and the supplier Excel template have no confirmed rules. Those actions are refused instead of using an estimate.") }}</p>
      <p v-if="error" class="alert" role="alert">{{ error }}</p>
      <p v-if="notice" role="status">{{ notice }}</p>
    </div>

    <form v-if="admin" class="card" @submit.prevent="openAccount">
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
    <article v-for="order in visibleOrders" :key="order.id" class="card order">
      <header>
        <label><input type="checkbox" :checked="picked.includes(order.id)" @change="toggleOrder(order.id)" /> {{ order.project_name }}</label>
        <span>{{ order.company }}</span>
      </header>
      <p>{{ tx("施工地址", "Site address") }}：{{ order.site_address }}</p>
      <p>{{ order.status }} · {{ tx("收款", "Payment") }} {{ order.payment_status }}<template v-if="order.arrival_status"> · {{ order.arrival_status }}</template><template v-if="order.delivery_status"> · {{ order.delivery_status }}</template></p>
      <p>{{ order.total ? `${order.currency || ""} ${order.total}` : tx("合计待配置，不能审核开票", "Total is not configured, so review and invoicing stay closed") }}</p>
      <table>
        <thead><tr><th>{{ tx("窗户", "Window") }}</th><th>{{ tx("订购", "Ordered") }}</th><th>{{ tx("已到", "Arrived") }}</th><th>{{ tx("已交付", "Delivered") }}</th><th>{{ tx("本批到货", "This arrival") }}</th><th>{{ tx("本批交付", "This delivery") }}</th></tr></thead>
        <tbody>
          <tr v-for="line in order.lines" :key="line.id">
            <td>{{ line.window_name }}<small>{{ tx("系列", "Series") }} {{ line.product_id || "—" }} · {{ line.width_mm || "—" }}×{{ line.height_mm || "—" }} mm<span v-if="optionText(line)"> · {{ optionText(line) }}</span></small></td>
            <td>{{ line.quantity }}</td>
            <td>{{ line.arrived }}</td>
            <td>{{ line.delivered }}</td>
            <td><input v-model.number="batch[`${order.id}:${line.id}:arrival`]" type="number" min="0" step="1" /></td>
            <td><input v-model.number="batch[`${order.id}:${line.id}:delivery`]" type="number" min="0" step="1" /></td>
          </tr>
        </tbody>
      </table>
      <div class="actions">
        <button type="button" :disabled="busy" @click="review(order.id)">{{ tx("确认接收", "Accept review") }}</button>
        <button type="button" class="secondary" :disabled="busy" @click="deposit(order.id)">{{ tx("定金已收", "Deposit received") }}</button>
        <label>{{ tx("供应商参考号", "Supplier reference") }}<input v-model="supplierRef[order.id]" /></label>
        <button type="button" class="secondary" :disabled="busy || !supplierRef[order.id]" @click="supplier(order)">{{ tx("记录下单", "Record supplier order") }}</button>
        <button type="button" class="secondary" :disabled="busy" @click="exportBlocked(order.id)">{{ tx("导出 Excel", "Export Excel") }}</button>
        <button type="button" class="secondary" :disabled="busy" @click="fulfil(order, 'arrival')">{{ tx("记录本批到货", "Record this arrival") }}</button>
        <button type="button" class="secondary" :disabled="busy" @click="fulfil(order, 'delivery')">{{ tx("记录本批交付", "Record this delivery") }}</button>
      </div>
      <div v-for="invoice in order.invoices || []" :key="invoice.id" class="invoice">
        <label><input type="checkbox" :value="invoice.id" v-model="invoicePick" /> {{ invoice.kind }} · {{ invoice.currency }} {{ invoice.amount }} · {{ mailStatus(invoice.status) }}</label>
      </div>
    </article>

    <section class="card">
      <h2>{{ tx("同公司发票", "Invoices for one company") }}</h2>
      <p class="hint">{{ tx("勾选同一公司的发票后一起发送。跨公司会被拦住。重复发送不会再发一封。", "Select invoices from one company, then send them together. A mix of companies is blocked. Sending again does not send another copy.") }}</p>
      <button type="button" :disabled="busy" @click="sendSelectedInvoices">{{ tx("发送勾选的发票", "Send selected invoices") }}</button>
    </section>

    <section class="card">
      <h2>{{ tx("通知状态", "Notification status") }}</h2>
      <p v-if="!notices.length">{{ tx("还没有到货或发票通知。", "No arrival or invoice notifications yet.") }}</p>
      <article v-for="item in notices" :key="item.id" class="invoice">
        <span>{{ item.subject }} · {{ item.recipient }} · {{ mailStatus(item.status) }}</span>
        <button v-if="item.status === 'not_configured'" type="button" class="secondary" :disabled="busy" @click="retryNotice(item.id)">{{ tx("配置好后重试", "Retry after mail is configured") }}</button>
      </article>
    </section>
  </section>
</template>

<style scoped>
.desk { display: grid; gap: 16px; }
.section-label { font-size: 11px; letter-spacing: 0.14em; color: #52635a; }
.hint { color: #54645c; line-height: 1.6; }
.grid, .actions { display: flex; flex-wrap: wrap; gap: 12px; align-items: end; }
.grid label, .actions label { min-width: 180px; }
.order header { display: flex; justify-content: space-between; gap: 12px; }
table { width: 100%; border-collapse: collapse; margin: 12px 0; }
th, td { text-align: left; border-bottom: 1px solid var(--line, #dedbd5); padding: 8px 6px; font-size: 14px; }
td input { width: 88px; }
td small { display: block; color: #54645c; font-size: 12px; margin-top: 4px; }
.invoice { display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-top: 8px; }
.alert { color: #8a3b2c; }
</style>

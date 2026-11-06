<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { formatDate, leadTimeLabel, normalizeStatus, paymentLabel, statusLabel } from "../../orderStatus";
import { portalRequest } from "../../portal-api";

const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);
const router = useRouter();
const route = useRoute();

const orders = ref<any[]>([]);
const loading = ref(true);
const error = ref("");

// Customer feedback, 30 Oct: filter by where the order is and when it was placed. Filters live in the URL so Back from an order keeps them.
const STATUS_GROUPS = [
  { key: "all", zh: "全部", en: "All" },
  { key: "draft", zh: "草稿", en: "Draft" },
  { key: "submitted", zh: "待审核", en: "Submitted" },
  { key: "confirmed", zh: "已确认", en: "Confirmed" },
  { key: "in_production", zh: "生产中", en: "In production" },
  { key: "in_transit", zh: "运输中", en: "In transit" },
  { key: "ready", zh: "可提货", en: "Ready" },
  { key: "complete", zh: "已完成", en: "Complete" },
];
const PAYMENT_GROUPS = [
  { key: "all", zh: "全部付款状态", en: "Any payment status" },
  { key: "deposit_unpaid", zh: "定金待付", en: "Deposit due" },
  { key: "deposit_received", zh: "定金已付", en: "Deposit paid" },
  { key: "paid", zh: "已结清", en: "Paid in full" },
];
const DATE_RANGES = [
  { key: "all", zh: "全部日期", en: "Any date" },
  { key: "30", zh: "近 30 天", en: "Last 30 days" },
  { key: "90", zh: "近 90 天", en: "Last 90 days" },
  { key: "year", zh: "今年", en: "This year" },
  { key: "custom", zh: "自定义", en: "Custom" },
];

const status = ref(String(route.query.status || "all"));
const paymentFilter = ref(String(route.query.payment || "all"));
const range = ref(String(route.query.range || "all"));
const from = ref(String(route.query.from || ""));
const to = ref(String(route.query.to || ""));
const search = ref(String(route.query.q || ""));

watch([status, paymentFilter, range, from, to, search], () => {
  const query: Record<string, string> = {};
  if (status.value !== "all") query.status = status.value;
  if (paymentFilter.value !== "all") query.payment = paymentFilter.value;
  if (range.value !== "all") query.range = range.value;
  if (range.value === "custom" && from.value) query.from = from.value;
  if (range.value === "custom" && to.value) query.to = to.value;
  if (search.value.trim()) query.q = search.value.trim();
  router.replace({ query });
});

function statusGroup(order: any): string {
  const value = normalizeStatus(order.status);
  if (value === "draft") return "draft";
  if (value === "pending_review") return "submitted";
  if (value === "accepted") return "confirmed";
  if (value === "supplier_ordered") return "in_production";
  if (["in_transit", "ready", "complete"].includes(value)) return value;
  return "confirmed";
}

function placedAt(order: any): Date | null {
  const date = order.order_date ? new Date(`${order.order_date}T00:00:00`) : null;
  return date && !Number.isNaN(date.getTime()) ? date : null;
}

function inRange(order: any): boolean {
  if (range.value === "all") return true;
  const date = placedAt(order);
  if (!date) return false;
  const now = new Date();
  if (range.value === "30" || range.value === "90") return now.getTime() - date.getTime() <= Number(range.value) * 86400000;
  if (range.value === "year") return date.getFullYear() === now.getFullYear();
  // Custom dates are whole days in the customer's own time zone.
  if (from.value && date < new Date(`${from.value}T00:00:00`)) return false;
  if (to.value && date > new Date(`${to.value}T23:59:59.999`)) return false;
  return true;
}

function matchesSearch(order: any): boolean {
  const term = search.value.trim().toLowerCase();
  if (!term) return true;
  return [order.order_number, order.project_name, order.site_address].some((value) => String(value || "").toLowerCase().includes(term));
}

const sorted = computed(() => [...orders.value].sort((a, b) => String(b.order_date || "").localeCompare(String(a.order_date || ""))));
const datedAndSearched = computed(() => sorted.value.filter((order) => inRange(order) && matchesSearch(order)));
const visible = computed(() => datedAndSearched.value.filter((order) => (status.value === "all" || statusGroup(order) === status.value) && (paymentFilter.value === "all" || order.payment_status === paymentFilter.value)));
// Counts follow the date and search filters, so each chip says how many orders it would show.
const counts = computed(() => {
  const out: Record<string, number> = { all: datedAndSearched.value.length };
  for (const order of datedAndSearched.value) out[statusGroup(order)] = (out[statusGroup(order)] || 0) + 1;
  return out;
});
const paymentCounts = computed(() => {
  const out: Record<string, number> = { all: datedAndSearched.value.length };
  for (const order of datedAndSearched.value) out[order.payment_status] = (out[order.payment_status] || 0) + 1;
  return out;
});
const filtered = computed(() => status.value !== "all" || paymentFilter.value !== "all" || range.value !== "all" || Boolean(search.value.trim()));

function clearFilters() {
  status.value = "all";
  paymentFilter.value = "all";
  range.value = "all";
  from.value = "";
  to.value = "";
  search.value = "";
}

function orderNumber(order: any): string {
  return order.order_number || (order.order_number_confirmed === false ? tx("待确认", "Pending") : "—");
}

function windowCount(order: any): number {
  return (order.lines || []).reduce((sum: number, line: any) => sum + (Number(line.quantity) || 1), 0);
}

// What the customer most wants to know about timing at this stage.
function etaText(order: any): { text: string; tone: string } {
  const value = normalizeStatus(order.status);
  if (value === "complete") return { text: tx("已完成", "Completed"), tone: "muted" };
  if (value === "ready") return { text: tx("已到货，可提取", "Arrived, ready"), tone: "ready" };
  if (order.eta) return { text: formatDate(order.eta, locale.value), tone: "date" };
  const lead = leadTimeLabel(order.lead_time, locale.value);
  if (lead) return { text: lead, tone: "muted" };
  return { text: tx("待确认", "To be confirmed"), tone: "muted" };
}

function money(order: any): string {
  return order.total ? `${order.currency || "NZD"} ${order.total}` : tx("待定价", "TBC");
}

onMounted(async () => {
  try {
    orders.value = await portalRequest<any[]>("orders");
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : tx("订单暂时无法载入。", "Orders could not be loaded.");
  } finally {
    loading.value = false;
  }
});

function viewOrder(orderId: string) {
  router.push(`/portal/orders/${orderId}`);
}

function startNewOrder() {
  router.push("/portal/order/new");
}
</script>

<template>
  <div class="orders-list">
    <div class="page-header">
      <div>
        <h1>{{ tx("我的订单", "My Orders") }}</h1>
        <p v-if="!loading && orders.length" class="subtitle">{{ tx(`共 ${orders.length} 个订单`, `${orders.length} orders`) }}</p>
      </div>
      <button type="button" class="primary" @click="startNewOrder">
        {{ tx("+ 新订单", "+ New Order") }}
      </button>
    </div>

    <div v-if="loading" class="loading">{{ tx("加载中...", "Loading...") }}</div>

    <div v-else-if="error" class="error-box" role="alert">{{ error }}</div>

    <div v-else-if="orders.length === 0" class="empty-state">
      <p>{{ tx("还没有订单", "No orders yet") }}</p>
      <button type="button" class="primary" @click="startNewOrder">
        {{ tx("开始第一个订单", "Start First Order") }}
      </button>
    </div>

    <template v-else>
      <section class="filters" :aria-label="tx('筛选订单', 'Filter orders')">
        <div class="filter-group"><strong>{{ tx("订单进度", "Order progress") }}</strong><div class="status-chips" role="group" :aria-label="tx('按订单进度', 'By order progress')">
          <button
            v-for="group in STATUS_GROUPS"
            :key="group.key"
            type="button"
            class="chip"
            :class="[`filter-${group.key}`, { active: status === group.key }]"
            :aria-pressed="status === group.key"
            @click="status = group.key"
          >
            {{ locale === "zh" ? group.zh : group.en }}<span class="chip-count">{{ counts[group.key] || 0 }}</span>
          </button>
        </div></div>
        <div class="filter-group"><strong>{{ tx("付款进度", "Payment progress") }}</strong><div class="status-chips payment-chips" role="group" :aria-label="tx('按付款进度', 'By payment progress')">
          <button v-for="group in PAYMENT_GROUPS" :key="group.key" type="button" class="chip" :class="[`pay-filter-${group.key}`,{active:paymentFilter===group.key}]" :aria-pressed="paymentFilter===group.key" @click="paymentFilter=group.key">{{locale==='zh'?group.zh:group.en}}<span class="chip-count">{{paymentCounts[group.key]||0}}</span></button>
        </div></div>
        <div class="filter-row">
          <input v-model="search" type="search" class="search" :placeholder="tx('搜索订单号或订单名称', 'Search order no. or name')" :aria-label="tx('搜索订单', 'Search orders')" />
          <label class="range">
            <span>{{ tx("下单日期", "Order date") }}</span>
            <select v-model="range">
              <option v-for="item in DATE_RANGES" :key="item.key" :value="item.key">{{ locale === "zh" ? item.zh : item.en }}</option>
            </select>
          </label>
          <template v-if="range === 'custom'">
            <label class="range"><span>{{ tx("从", "From") }}</span><input v-model="from" type="date" :max="to || undefined" /></label>
            <label class="range"><span>{{ tx("到", "To") }}</span><input v-model="to" type="date" :min="from || undefined" /></label>
          </template>
          <button v-if="filtered" type="button" class="clear" @click="clearFilters">{{ tx("清除筛选", "Clear filters") }}</button>
        </div>
      </section>

      <div v-if="visible.length === 0" class="empty-state compact">
        <p>{{ tx("没有符合筛选条件的订单。", "No orders match these filters.") }}</p>
        <button type="button" class="clear" @click="clearFilters">{{ tx("清除筛选", "Clear filters") }}</button>
      </div>

      <div v-else class="order-table" role="table" :aria-label="tx('订单列表', 'Orders')">
        <div class="order-row head" role="row">
          <span role="columnheader">{{ tx("订单号", "Order ID") }}</span>
          <span role="columnheader">{{ tx("订单名称", "Order name") }}</span>
          <span role="columnheader">{{ tx("订单日期（定金到账日）", "Order date (deposit paid)") }}</span>
          <span role="columnheader">{{ tx("状态", "Status") }}</span>
          <span role="columnheader">{{ tx("预计到货 (ETA)", "ETA") }}</span>
          <span role="columnheader" class="num">{{ tx("窗数", "Windows") }}</span>
          <span role="columnheader" class="num">{{ tx("总价", "Total") }}</span>
          <span role="columnheader">{{ tx("付款", "Payment") }}</span>
        </div>
        <div
          v-for="order in visible"
          :key="order.id"
          class="order-row"
          role="row"
          tabindex="0"
          @click="viewOrder(order.id)"
          @keydown.enter="viewOrder(order.id)"
        >
          <span role="cell" class="cell-number" :data-label="tx('订单号', 'Order ID')"><strong>{{ orderNumber(order) }}</strong></span>
          <span role="cell" class="cell-name" :data-label="tx('订单名称', 'Order name')">{{ order.project_name }}<small v-if="order.site_address">{{ order.site_address }}</small></span>
          <span role="cell" class="cell-date" :data-label="tx('订单日期（定金到账日）', 'Order date (deposit paid)')">{{ formatDate(order.order_date, locale) || "—" }}</span>
          <span role="cell" class="cell-status" :data-label="tx('状态', 'Status')"><span class="order-status" :class="`status-${normalizeStatus(order.status)}`">{{ statusLabel(order, locale) }}</span></span>
          <span role="cell" class="cell-eta" :data-label="tx('预计到货', 'ETA')"><span :class="`eta-${etaText(order).tone}`">{{ etaText(order).text }}</span><small v-if="order.batch_name && etaText(order).tone !== 'muted'">{{ order.batch_name }}</small></span>
          <span role="cell" class="cell-windows num" :data-label="tx('窗数', 'Windows')">{{ windowCount(order) }}</span>
          <span role="cell" class="cell-total num" :data-label="tx('总价', 'Total')">{{ money(order) }}</span>
          <span role="cell" class="cell-payment" :data-label="tx('付款', 'Payment')"><span class="order-payment" :class="`pay-${order.payment_status}`">{{ paymentLabel(order.payment_status, locale) }}</span></span>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.orders-list {
  max-width: 1200px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-header h1 {
  font-family: var(--font-display);
  font-size: 32px;
  font-weight: 600;
  margin: 0;
  letter-spacing: 0.01em;
}

.subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: rgba(27, 36, 33, 0.6);
}

button.primary {
  min-height: 48px;
  padding: 12px 24px;
  background: var(--cord);
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  letter-spacing: 0.02em;
}

button.primary:hover {
  background: #0c7a67;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(15, 110, 92, 0.3);
}

.loading,
.empty-state {
  text-align: center;
  padding: 60px 20px;
  font-size: 16px;
  color: rgba(27, 36, 33, 0.6);
}

.empty-state button {
  margin-top: 24px;
}

.empty-state.compact {
  padding: 32px 20px;
  border: 1px dashed var(--line);
  border-radius: 8px;
}

.empty-state.compact button {
  margin-top: 12px;
}

.error-box {
  padding: 12px 14px;
  background: #fff0ed;
  color: #8f3425;
  border-radius: 6px;
}

.filters {
  display: grid;
  gap: 12px;
  margin-bottom: 16px;
}

.filter-group{display:grid;gap:7px}.filter-group>strong{font-size:11px;letter-spacing:.06em;color:#65747d}

.status-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 36px;
  padding: 6px 12px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: white;
  color: var(--ink);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.chip:hover {
  border-color: var(--cord);
}

.chip.active {
  background: var(--cord);
  border-color: var(--cord);
  color: white;
}

.chip-count {
  min-width: 18px;
  padding: 0 6px;
  border-radius: 999px;
  background: rgba(15, 110, 92, 0.1);
  font-size: 11px;
  line-height: 18px;
  text-align: center;
}

.chip.active .chip-count {
  background: rgba(255, 255, 255, 0.22);
}

.chip.filter-draft{color:#52616a;background:#eef1f3;border-color:#d8dfe3}.chip.filter-submitted{color:#865510;background:#fff5e2;border-color:#f0ddb2}.chip.filter-confirmed{color:#5b4789;background:#f1edfa;border-color:#ded5f1}.chip.filter-in_production{color:#445192;background:#edf0fb;border-color:#d8def5}.chip.filter-in_transit{color:#286181;background:#eaf4fb;border-color:#cee3f1}.chip.filter-ready{color:#17644f;background:#e7f5f0;border-color:#c8e8dd}.chip.filter-complete{color:#42634a;background:#eaf2eb;border-color:#d2e2d4}
.chip.pay-filter-deposit_unpaid{color:#9b493b;background:#fff0ed;border-color:#f0d0c9}.chip.pay-filter-deposit_received{color:#286181;background:#eaf4fb;border-color:#cee3f1}.chip.pay-filter-paid{color:#376448;background:#eaf2eb;border-color:#d2e2d4}
.chip.active{background:var(--frame);border-color:var(--frame);color:#fff}.chip.active .chip-count{color:#fff}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 10px 14px;
}

.search {
  flex: 1 1 240px;
  min-width: 0;
  height: 38px;
  padding: 6px 12px;
  border: 1px solid var(--line);
  border-radius: 6px;
  font: inherit;
  font-size: 14px;
  background: white;
}

.range {
  display: grid;
  gap: 3px;
  font-size: 11px;
  font-weight: 600;
  color: rgba(27, 36, 33, 0.6);
}

.range select,
.range input {
  height: 38px;
  padding: 5px 9px;
  border: 1px solid var(--line);
  border-radius: 6px;
  font: inherit;
  font-size: 13px;
  color: var(--ink);
  background: white;
}

button.clear {
  height: 38px;
  padding: 0 12px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: white;
  color: #29493d;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.order-table {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: white;
  overflow: hidden;
}

.order-row {
  display: grid;
  grid-template-columns: 1.3fr 1.6fr 0.9fr 1.1fr 1.2fr 0.5fr 0.9fr 1fr;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-top: 1px solid var(--line);
  font-size: 14px;
  cursor: pointer;
}

.order-row.head {
  border-top: 0;
  background: #f3f6f3;
  color: rgba(27, 36, 33, 0.65);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  cursor: default;
}

.order-row:not(.head):hover,
.order-row:not(.head):focus-visible {
  background: #f2f7f4;
  outline: none;
}

.order-row:not(.head):focus-visible {
  box-shadow: inset 3px 0 0 var(--cord);
}

.order-row > span {
  min-width: 0;
}

.order-row small {
  display: block;
  margin-top: 2px;
  font-size: 12px;
  color: rgba(27, 36, 33, 0.55);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cell-number strong {
  overflow-wrap: anywhere;
}

.num {
  text-align: right;
}

.cell-total {
  font-weight: 600;
  white-space: nowrap;
}

.order-status {
  display: inline-block;
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  background: #e8eef0;
  color: var(--cord);
  border-radius: 12px;
  white-space: nowrap;
}

.order-status.status-draft { background:#e8ecef;color:#44545f }
.order-status.status-ready { background:#dff2ed;color:#17644f }
.order-status.status-complete { background:#e5eee6;color:#376448 }
.order-status.status-in_transit { background:#e2f0fa;color:#245b7a }
.order-status.status-supplier_ordered { background:#e7eafa;color:#3f4d90 }
.order-status.status-accepted { background:#eee8fb;color:#59428b }
.order-status.status-pending_review { background:#fff1d8;color:#82510b }

.eta-date { font-weight: 600; color: #34503f; }
.eta-ready { font-weight: 600; color: #17523a; }
.eta-muted { font-size: 13px; color: rgba(27, 36, 33, 0.6); }

.order-payment {
  font-size: 13px;
  color: rgba(27, 36, 33, 0.6);
}

.order-payment.pay-paid { color: #17523a; font-weight: 600; }
.order-payment.pay-deposit_unpaid { color: #a44034; }
.order-payment.pay-deposit_received { color:#245b7a;font-weight:650 }
.order-payment.pay-paid { color:#376448;font-weight:700 }

/* Phone and narrow tablet: each order becomes a compact card with labelled fields. */
@media (max-width: 860px) {
  .page-header {
    flex-direction: column;
    align-items: stretch;
    gap: 16px;
  }

  .page-header button {
    width: 100%;
  }

  .status-chips {
    flex-wrap: nowrap;
    overflow-x: auto;
    padding-bottom: 4px;
  }

  .chip {
    flex: 0 0 auto;
  }

  .order-table {
    border: 0;
    background: transparent;
    display: grid;
    gap: 10px;
  }

  .order-row.head {
    display: none;
  }

  .order-row {
    grid-template-columns: 1fr 1fr 1fr;
    gap: 8px 12px;
    padding: 12px 14px;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: white;
  }

  .cell-number { grid-row: 1; grid-column: 1 / 3; }
  .cell-status { grid-row: 1; grid-column: 3; text-align: right; }
  .cell-name { grid-row: 2; grid-column: 1 / -1; font-weight: 600; }
  .cell-payment { grid-column: 1 / -1; }

  .cell-date::before,
  .cell-eta::before,
  .cell-windows::before,
  .cell-total::before {
    content: attr(data-label);
    display: block;
    font-size: 11px;
    font-weight: 600;
    color: rgba(27, 36, 33, 0.55);
  }

  .cell-windows { display: none; }
  .num { text-align: left; }
}
</style>

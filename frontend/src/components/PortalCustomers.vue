<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { request } from "../crm-api";

type CustomerType = "retail" | "wholesale";

interface PortalCustomer {
  customer_id: number;
  company: string;
  contact_name: string;
  email: string;
  phone: string;
  company_address: string;
  username: string;
  customer_code?: string | null;
  customer_type?: CustomerType | null;
  created_at?: string;
}

const { locale } = useI18n();
defineProps<{ admin?: boolean }>();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);
const PAGE_SIZE = 8;

const rows = ref<PortalCustomer[]>([]);
const loading = ref(true);
const error = ref("");
const notice = ref("");

// The backend treats a profile without customer_type as wholesale (order numbering does the same).
const typeOf = (row: PortalCustomer): CustomerType => row.customer_type || "wholesale";
const missingCode = (row: PortalCustomer) => typeOf(row) === "wholesale" && !(row.customer_code || "").trim();
const typeLabel = (kind: CustomerType) => (kind === "retail" ? tx("零售", "Retail") : tx("批发", "Wholesale"));

const search = ref("");
const typeFilter = ref<"all" | CustomerType>("all");
const counts = computed(() => ({
  all: rows.value.length,
  wholesale: rows.value.filter((r) => typeOf(r) === "wholesale").length,
  retail: rows.value.filter((r) => typeOf(r) === "retail").length,
  missing: rows.value.filter(missingCode).length,
}));
const filteredRows = computed(() => {
  const term = search.value.trim().toLowerCase();
  return rows.value.filter(
    (r) =>
      (typeFilter.value === "all" || typeOf(r) === typeFilter.value) &&
      `${r.company} ${r.username} ${r.contact_name} ${r.customer_code || ""}`.toLowerCase().includes(term),
  );
});
const customerPage = ref(0);
const customerPages = computed(() => Math.max(1, Math.ceil(filteredRows.value.length / PAGE_SIZE)));
const shownRows = computed(() => filteredRows.value.slice(customerPage.value * PAGE_SIZE, customerPage.value * PAGE_SIZE + PAGE_SIZE));
watch([search, typeFilter], () => { customerPage.value = 0; });

const creating = ref(false);
const account = reactive({ company: "", contact_name: "", email: "", phone: "", company_address: "", username: "", password: "", customer_type: "wholesale" as CustomerType, customer_code: "" });
function startCreate() {
  creating.value = !creating.value;
  error.value = "";
  notice.value = "";
}
async function openAccount() {
  try {
    error.value = "";
    await request("operations/customers", { ...account, customer_code: account.customer_code.trim() || null });
    Object.assign(account, { company: "", contact_name: "", email: "", phone: "", company_address: "", username: "", password: "", customer_type: "wholesale", customer_code: "" });
    creating.value = false;
    notice.value = tx("客户与门户账号已开通", "Customer and portal account created");
    await load();
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  }
}

interface CompanyUse {
  orders: { id: string; project_name?: string; order_number?: string; total: string | null; currency?: string; status?: string }[];
  invoices: { id: string; invoice_number?: string; kind: string; amount: string; currency: string; status?: string; payment_status?: string }[];
  rebates: { id: string; month?: string; amount: string; currency: string; used?: string; remaining?: string }[];
  summary?: Record<string, { ordered?: string; invoiced?: string; received?: string; outstanding_invoiced?: string }>;
  unpriced_orders?: number;
}
const selected = ref<number | null>(null);
const current = computed(() => rows.value.find((r) => r.customer_id === selected.value) || null);
const detailTab = ref("profile");
const editing = ref(false);
const usage = ref<CompanyUse | null>(null);
const detailEl = ref<HTMLElement | null>(null);
const draft = reactive({ company: "", contact_name: "", email: "", phone: "", company_address: "", customer_type: "wholesale" as CustomerType, customer_code: "" });

async function load() {
  rows.value = await request<PortalCustomer[]>("operations/customers");
}

onMounted(async () => {
  try {
    await load();
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    loading.value = false;
  }
});

function fillDraft(row: PortalCustomer) {
  Object.assign(draft, {
    company: row.company,
    contact_name: row.contact_name,
    email: row.email,
    phone: row.phone,
    company_address: row.company_address,
    customer_type: typeOf(row),
    customer_code: row.customer_code || "",
  });
}

async function choose(row: PortalCustomer) {
  selected.value = row.customer_id;
  creating.value = false;
  editing.value = false;
  detailTab.value = "profile";
  fillDraft(row);
  error.value = "";
  notice.value = "";
  usage.value = null;
  // On a single-column layout the detail sits below the list; bring it into view.
  if (window.matchMedia("(max-width: 900px)").matches) {
    await nextTick();
    detailEl.value?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  try {
    usage.value = await request<CompanyUse>(`operations/customers/${row.customer_id}/consumption`);
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  }
}

function startEdit() {
  if (current.value) fillDraft(current.value);
  editing.value = true;
  notice.value = "";
}

async function save() {
  if (selected.value == null) return;
  error.value = "";
  notice.value = "";
  try {
    await request(`operations/customers/${selected.value}`, { ...draft, customer_code: draft.customer_code.trim() });
    notice.value = tx("客户资料已更新。", "Customer profile updated.");
    editing.value = false;
    await load();
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  }
}
</script>

<template>
  <section class="card profiles">
    <header class="profiles-head">
      <div>
        <h2>{{ tx("客户资料", "Customers") }}</h2>
        <p class="meta">
          {{ tx(`共 ${counts.all} 家 · 批发 ${counts.wholesale} · 零售 ${counts.retail}`, `${counts.all} customers · ${counts.wholesale} wholesale · ${counts.retail} retail`) }}
          <span v-if="counts.missing" class="warn-text"> · {{ tx(`${counts.missing} 家批发客户缺代码`, `${counts.missing} wholesale missing a code`) }}</span>
        </p>
      </div>
      <button v-if="admin" type="button" :class="{ secondary: creating }" @click="startCreate">{{ creating ? tx("取消新增", "Cancel") : tx("新增客户", "New customer") }}</button>
    </header>

    <form v-if="creating" class="panel create-panel" @submit.prevent="openAccount">
      <h3>{{ tx("新增客户并开通门户账号", "New customer and portal account") }}</h3>
      <fieldset>
        <legend>{{ tx("客户类型", "Customer type") }}</legend>
        <div class="segmented" role="radiogroup">
          <label v-for="kind in (['wholesale','retail'] as CustomerType[])" :key="kind" :class="{ on: account.customer_type === kind }"><input v-model="account.customer_type" type="radio" :value="kind" />{{ typeLabel(kind) }}</label>
        </div>
        <p class="hint">{{ account.customer_type === "wholesale" ? tx("批发单号 = 客户代码-工地名，必须填写客户代码。", "Wholesale order numbers are CODE-job name, so a customer code is required.") : tx("零售单号自动生成为 R+日期+当日序号+字母。", "Retail order numbers are generated as R + date + daily sequence + letter.") }}</p>
      </fieldset>
      <div class="form-grid">
        <label>{{ tx("公司", "Company") }}<input v-model="account.company" required /></label>
        <label v-if="account.customer_type === 'wholesale'">{{ tx("批发客户代码", "Wholesale customer code") }}<input v-model="account.customer_code" required maxlength="50" :placeholder="tx('如 AA、CF', 'e.g. AA, CF')" /></label>
        <label>{{ tx("联系人", "Contact") }}<input v-model="account.contact_name" required /></label>
        <label>{{ tx("电话", "Phone") }}<input v-model="account.phone" required /></label>
        <label>{{ tx("邮箱（可待补）", "Email (optional)") }}<input v-model="account.email" type="email" /></label>
        <label class="wide">{{ tx("公司地址", "Company address") }}<input v-model="account.company_address" required /></label>
      </div>
      <h4>{{ tx("门户登录", "Portal login") }}</h4>
      <div class="form-grid">
        <label>{{ tx("登录账号", "Username") }}<input v-model="account.username" required autocomplete="off" /></label>
        <label>{{ tx("初始密码（至少 8 位）", "Starting password (8+ characters)") }}<input v-model="account.password" type="password" minlength="8" required autocomplete="new-password" /></label>
      </div>
      <div class="actions"><button type="submit">{{ tx("创建客户与账号", "Create customer & account") }}</button><button type="button" class="secondary" @click="creating = false">{{ tx("取消", "Cancel") }}</button></div>
    </form>

    <p v-if="error" class="alert" role="alert">{{ error }}</p>
    <p v-if="notice" class="notice" role="status">{{ notice }}</p>

    <div class="customer-layout">
      <aside class="customer-list" :aria-label="tx('客户列表', 'Customer list')">
        <input v-model="search" type="search" :placeholder="tx('搜索公司、联系人、账号或代码', 'Search company, contact, login or code')" :aria-label="tx('搜索客户', 'Search customers')" />
        <div class="filter-row" role="tablist">
          <button v-for="item in ([['all','全部','All'],['wholesale','批发','Wholesale'],['retail','零售','Retail']] as const)" :key="item[0]" type="button" role="tab" :aria-selected="typeFilter === item[0]" :class="{ on: typeFilter === item[0] }" @click="typeFilter = item[0]">{{ tx(item[1], item[2]) }} <span>{{ counts[item[0]] }}</span></button>
        </div>
        <p v-if="loading" class="hint" role="status">{{ tx("加载客户中…", "Loading customers…") }}</p>
        <p v-else-if="!rows.length && !error" class="hint">{{ tx("还没有开通门户账号。", "No portal account has been opened yet.") }}</p>
        <p v-else-if="!filteredRows.length" class="hint">{{ tx("没有匹配的客户。", "No matching customers.") }}</p>
        <button v-for="row in shownRows" :key="row.customer_id" type="button" class="customer-row" :aria-pressed="selected === row.customer_id" @click="choose(row)">
          <span class="row-top"><strong>{{ row.company }}</strong><span class="tag" :class="typeOf(row)">{{ typeLabel(typeOf(row)) }}<template v-if="row.customer_code"> · {{ row.customer_code }}</template></span></span>
          <small>{{ row.contact_name }} · {{ row.username }}</small>
          <small v-if="missingCode(row)" class="warn-text">{{ tx("缺批发代码，无法下单", "No wholesale code — cannot order") }}</small>
        </button>
        <div v-if="customerPages > 1" class="customer-pagination">
          <button type="button" class="secondary" :disabled="customerPage === 0" :aria-label="tx('上一页', 'Previous page')" @click="customerPage--">‹</button>
          <span>{{ customerPage + 1 }} / {{ customerPages }}</span>
          <button type="button" class="secondary" :disabled="customerPage + 1 >= customerPages" :aria-label="tx('下一页', 'Next page')" @click="customerPage++">›</button>
        </div>
      </aside>

      <div ref="detailEl" class="customer-detail">
        <div v-if="!current" class="empty-detail">
          <strong>{{ tx("选择左侧的客户", "Choose a customer on the left") }}</strong>
          <p>{{ tx("可以查看资料、门户账号、订单和账款，并修改客户类型与批发代码。", "View the profile, portal account, orders and accounts, and change the customer type or wholesale code.") }}</p>
        </div>
        <template v-else>
          <header class="detail-head">
            <div>
              <h3>{{ current.company }}</h3>
              <div class="tags">
                <span class="tag" :class="typeOf(current)">{{ typeLabel(typeOf(current)) }}<template v-if="!current.customer_type"> · {{ tx("未设置，按批发处理", "not set, treated as wholesale") }}</template></span>
                <span v-if="current.customer_code" class="tag code">{{ tx("代码", "Code") }} {{ current.customer_code }}</span>
                <span class="tag portal">{{ tx("门户已开通", "Portal active") }} · {{ current.username }}</span>
              </div>
            </div>
          </header>
          <p v-if="missingCode(current)" class="banner">{{ tx("这是批发客户但还没有客户代码。批发单号 = 代码-工地名，没有代码时客户在门户下单会被拒绝。请点「编辑资料」补上代码，或把类型改成零售。", "This wholesale customer has no customer code. Wholesale order numbers are CODE-job name, so portal orders are refused until a code is added. Edit the profile to add one, or switch the type to retail.") }}</p>

          <nav class="customer-tabs" role="tablist">
            <button v-for="item in [['profile','资料','Profile'],['account','门户账号','Portal account'],['orders','订单','Orders'],['finance','账款返利','Accounts & rebates']]" :key="item[0]" type="button" role="tab" :aria-selected="detailTab === item[0]" :class="{ on: detailTab === item[0] }" @click="detailTab = item[0]!">{{ tx(item[1]!, item[2]!) }}</button>
          </nav>

          <section v-if="detailTab === 'profile' && !editing" class="panel">
            <dl class="facts">
              <div><dt>{{ tx("联系人", "Contact") }}</dt><dd>{{ current.contact_name || "—" }}</dd></div>
              <div><dt>{{ tx("电话", "Phone") }}</dt><dd>{{ current.phone || "—" }}</dd></div>
              <div><dt>{{ tx("邮箱", "Email") }}</dt><dd>{{ current.email || tx("待补", "Not provided") }}</dd></div>
              <div><dt>{{ tx("客户类型", "Customer type") }}</dt><dd>{{ typeLabel(typeOf(current)) }}</dd></div>
              <div><dt>{{ tx("批发客户代码", "Wholesale code") }}</dt><dd :class="{ 'warn-text': missingCode(current) }">{{ current.customer_code || (typeOf(current) === "wholesale" ? tx("缺失", "Missing") : "—") }}</dd></div>
              <div class="wide"><dt>{{ tx("公司地址", "Company address") }}</dt><dd>{{ current.company_address || "—" }}</dd></div>
            </dl>
            <div class="actions"><button type="button" @click="startEdit">{{ tx("编辑资料", "Edit profile") }}</button></div>
          </section>

          <form v-if="detailTab === 'profile' && editing" class="panel" @submit.prevent="save">
            <fieldset>
              <legend>{{ tx("客户类型", "Customer type") }}</legend>
              <div class="segmented" role="radiogroup">
                <label v-for="kind in (['wholesale','retail'] as CustomerType[])" :key="kind" :class="{ on: draft.customer_type === kind }"><input v-model="draft.customer_type" type="radio" :value="kind" />{{ typeLabel(kind) }}</label>
              </div>
              <p class="hint">{{ tx("只影响之后的新订单编号，已有订单号不变。", "Only affects numbers for new orders; existing order numbers stay as they are.") }}</p>
            </fieldset>
            <div class="form-grid">
              <label>{{ tx("公司", "Company") }}<input v-model="draft.company" required /></label>
              <label>{{ tx("批发客户代码", "Wholesale customer code") }}<input v-model="draft.customer_code" maxlength="50" :required="draft.customer_type === 'wholesale'" :placeholder="tx('如 AA、CF', 'e.g. AA, CF')" /></label>
              <label>{{ tx("联系人", "Contact") }}<input v-model="draft.contact_name" required /></label>
              <label>{{ tx("电话", "Phone") }}<input v-model="draft.phone" required /></label>
              <label>{{ tx("邮箱", "Email") }}<input v-model="draft.email" type="email" /></label>
              <label class="wide">{{ tx("公司地址", "Company address") }}<input v-model="draft.company_address" required /></label>
            </div>
            <div class="actions"><button type="submit">{{ tx("保存资料", "Save profile") }}</button><button type="button" class="secondary" @click="editing = false">{{ tx("取消", "Cancel") }}</button></div>
          </form>

          <section v-if="detailTab === 'account'" class="panel">
            <dl class="facts">
              <div><dt>{{ tx("登录账号", "Username") }}</dt><dd>{{ current.username }}</dd></div>
              <div><dt>{{ tx("状态", "Status") }}</dt><dd>{{ tx("已开通", "Active") }}</dd></div>
              <div v-if="current.created_at"><dt>{{ tx("开通时间", "Opened") }}</dt><dd>{{ current.created_at.slice(0, 10) }}</dd></div>
            </dl>
            <p class="hint">{{ tx("每个客户一个登录账号、一个联系人。现有密码不显示。", "One login and one contact per customer. Existing passwords are never displayed.") }}</p>
          </section>

          <section v-if="['orders','finance'].includes(detailTab)" class="panel">
            <p v-if="!usage" class="hint">{{ tx("加载中…", "Loading…") }}</p>
            <template v-else>
              <div v-if="Object.keys(usage.summary || {}).length" class="money-grid">
                <div v-for="(money, currency) in usage.summary || {}" :key="currency" class="money-card">
                  <small>{{ currency }}</small>
                  <span>{{ tx("已下单", "Ordered") }} <b>{{ money.ordered || "—" }}</b></span>
                  <span>{{ tx("已开票", "Invoiced") }} <b>{{ money.invoiced || "—" }}</b></span>
                  <span>{{ tx("已收", "Received") }} <b>{{ money.received || "—" }}</b></span>
                  <span>{{ tx("已开票未收", "Outstanding") }} <b>{{ money.outstanding_invoiced || "—" }}</b></span>
                </div>
              </div>
              <p v-if="usage.unpriced_orders" class="warn-text">{{ tx(`有 ${usage.unpriced_orders} 个订单还没有确认价格。`, `${usage.unpriced_orders} orders have no confirmed price.`) }}</p>

              <template v-if="detailTab === 'orders'">
                <p v-if="!usage.orders.length" class="hint">{{ tx("还没有订单。", "No orders yet.") }}</p>
                <ul v-else class="line-list">
                  <li v-for="order in usage.orders" :key="order.id">
                    <RouterLink :to="{ path: '/crm/projects', query: { order: order.id } }">{{ order.project_name || order.order_number || order.id }}</RouterLink>
                    <span class="muted">{{ order.status || "" }}</span>
                    <span class="amount">{{ order.total ? `${order.currency || ""} ${order.total}` : tx("合计待配置", "Total not configured") }}</span>
                  </li>
                </ul>
              </template>

              <template v-if="detailTab === 'finance'">
                <h4>{{ tx("发票", "Invoices") }}</h4>
                <p v-if="!usage.invoices.length" class="hint">{{ tx("还没有发票。", "No invoices yet.") }}</p>
                <ul v-else class="line-list">
                  <li v-for="invoice in usage.invoices" :key="invoice.id">
                    <span>{{ invoice.invoice_number || invoice.kind }}</span>
                    <span class="muted">{{ tx("发送", "Sent") }} {{ invoice.status || "—" }} · {{ invoice.payment_status === "received" ? tx("已收款", "Received") : tx("未确认收款", "Receipt not confirmed") }}</span>
                    <span class="amount">{{ invoice.currency }} {{ invoice.amount }}</span>
                  </li>
                </ul>
                <h4>{{ tx("返利", "Rebates") }}</h4>
                <p v-if="!usage.rebates.length" class="hint">{{ tx("还没有返利。", "No rebates yet.") }}</p>
                <ul v-else class="line-list">
                  <li v-for="credit in usage.rebates" :key="credit.id">
                    <span>{{ credit.month || credit.id }}</span>
                    <span class="muted">{{ tx("已用", "Used") }} {{ credit.used || "0.00" }} · {{ tx("余额", "Remaining") }} {{ credit.remaining || "0.00" }}</span>
                    <span class="amount">{{ credit.currency }} {{ credit.amount }}</span>
                  </li>
                </ul>
                <RouterLink class="ledger-link" :to="{ path: '/crm/finance', query: { customer: selected } }">{{ tx("打开客户账本 →", "Open customer ledger →") }}</RouterLink>
              </template>
            </template>
          </section>
        </template>
      </div>
    </div>
  </section>
</template>

<style scoped>
.profiles { font-size: 14px; line-height: 1.55; display: grid; gap: 16px; border-radius: 18px; box-shadow: 0 2px 10px rgba(27, 56, 43, .06); }
.profiles button { border-radius: 10px; }
.profiles h2 { font-size: 20px; margin: 0; }
.profiles h3 { font-size: 18px; margin: 0; }
.profiles h4 { font-size: 14px; margin: 16px 0 8px; }
.profiles p { margin: 0; }
.meta { color: #54645c; font-size: 13px; margin-top: 4px; }
.hint { color: #54645c; font-size: 13px; line-height: 1.6; }
.muted { color: #54645c; font-size: 13px; }
.warn-text { color: #8a3b2c; }
.alert { color: #8a3b2c; background: #fbefec; border: 1px solid #e8c9c1; border-radius: 12px; padding: 10px 14px; }
.notice { color: #17523a; background: #edf4ef; border: 1px solid #cbd8cf; border-radius: 12px; padding: 10px 14px; }

.profiles-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.panel { border: 1px solid #dce5df; border-radius: 14px; background: #fff; padding: 18px; display: grid; gap: 14px; min-width: 0; box-shadow: 0 1px 5px rgba(27, 56, 43, .035); }
.create-panel { background: #fafcfa; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 16px; }
.form-grid .wide, .facts .wide { grid-column: 1 / -1; }
.form-grid input { min-width: 0; box-sizing: border-box; }
.profiles input:not([type=radio]):not([type=checkbox]), .profiles select, .profiles textarea { min-width: 0; max-width: 100%; box-sizing: border-box; border-radius: 10px; }
fieldset { border: 0; padding: 0; margin: 0; display: grid; gap: 8px; }
legend { font-size: 13px; font-weight: 600; margin-bottom: 6px; }
.segmented { display: inline-flex; border: 1px solid #cbd8cf; border-radius: 12px; overflow: hidden; width: max-content; max-width: 100%; }
.segmented label { display: flex; align-items: center; min-height: 40px; padding: 0 18px; cursor: pointer; color: #17523a; background: #f5f8f5; font-size: 14px; }
.segmented label + label { border-left: 1px solid #cbd8cf; }
.segmented label.on { background: #17523a; color: #fff; }
.segmented input { position: absolute; opacity: 0; width: 1px; height: 1px; min-height: 0; }
.segmented label:focus-within { outline: 2px solid var(--cord, #0f6e5c); outline-offset: 2px; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }

.customer-layout { display: grid; grid-template-columns: 320px minmax(0, 1fr); gap: 20px; align-items: start; }
.customer-list { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.customer-list input[type=search] { box-sizing: border-box; }
.filter-row { display: flex; gap: 6px; margin: 2px 0 4px; }
.filter-row button { min-height: 36px; padding: 5px 13px; font-size: 13px; font-weight: 500; color: #17523a; background: #f5f8f5; border: 1px solid #cbd8cf; border-radius: 999px; }
.filter-row button span { color: #54645c; margin-left: 4px; }
.filter-row button.on { background: #17523a; border-color: #17523a; color: #fff; }
.filter-row button.on span { color: #dfeee4; }
.customer-row { display: grid; grid-template-columns: minmax(0, 1fr); justify-content: stretch; gap: 3px; justify-items: start; text-align: left; min-height: 64px; padding: 12px 14px; border: 1px solid #dce5df; border-radius: 12px; background: #fff; color: #203d30; font-weight: 400; box-shadow: 0 1px 3px rgba(27, 56, 43, .04); transition: border-color .16s, box-shadow .16s, transform .16s; }
.customer-row:hover { border-color: #9fb8a8; box-shadow: 0 4px 12px rgba(27, 56, 43, .08); transform: translateY(-1px); }
.customer-row[aria-pressed=true] { background: #edf4ef; border-color: #17523a; box-shadow: inset 3px 0 0 #17523a, 0 2px 8px rgba(27, 56, 43, .06); }
.customer-row small { font-size: 12px; color: #54645c; }
.customer-row small.warn-text { color: #8a3b2c; }
.row-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; width: 100%; }
.row-top strong { font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tag { display: inline-block; flex: none; padding: 3px 10px; font-size: 12px; line-height: 1.5; border-radius: 999px; background: #e1e6df; color: #3d4a44; white-space: nowrap; }
.tag.wholesale { background: #e3eef6; color: #1f4b6b; }
.tag.retail { background: #f6ecdf; color: #6b4a1f; }
.tag.code { background: #edf4ef; color: #17523a; }
.tag.portal { background: #f5f6f2; color: #3d4a44; }
.customer-pagination { display: flex; gap: 8px; align-items: center; justify-content: center; margin-top: 4px; }
.customer-pagination button { min-width: 44px; padding: 0 12px; }

.customer-detail { min-width: 0; display: grid; gap: 12px; }
.empty-detail { border: 1px dashed #cbd8cf; border-radius: 14px; padding: 32px 24px; text-align: center; color: #54645c; display: grid; gap: 6px; background: #fafcfa; }
.empty-detail strong { color: #203d30; font-size: 15px; }
.detail-head .tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.banner { background: #fbefec; border: 1px solid #e8c9c1; border-radius: 12px; color: #8a3b2c; padding: 12px 14px; font-size: 13px; line-height: 1.6; }
.customer-tabs { display: flex; flex-wrap: wrap; gap: 5px; border-bottom: 1px solid #dce5df; padding-bottom: 8px; }
.customer-tabs button { min-height: 40px; padding: 0 16px; background: #f5f8f5; border: 1px solid transparent; border-radius: 999px; color: #54645c; font-weight: 500; font-size: 14px; }
.customer-tabs button.on { color: #17523a; border-bottom-color: #17523a; font-weight: 600; }
.customer-tabs button.on { background: #e8f2eb; border-color: #cbd8cf; }
.facts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px 20px; margin: 0; }
.facts dt { font-size: 12px; color: #54645c; }
.facts dd { margin: 2px 0 0; font-size: 14px; overflow-wrap: anywhere; }
.money-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }
.money-card { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 12px; border: 1px solid #dce5df; border-radius: 12px; background: #fafcfa; padding: 12px 14px; font-size: 13px; }
.money-card small { grid-column: 1 / -1; color: #54645c; font-weight: 600; }
.line-list { list-style: none; margin: 0; padding: 0; }
.line-list li { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 1.4fr) auto; gap: 12px; align-items: center; padding: 10px 0; border-top: 1px solid #edf0ec; }
.line-list li:first-child { border-top: 0; }
.line-list a, .ledger-link { color: #17523a; }
.amount { font-variant-numeric: tabular-nums; text-align: right; white-space: nowrap; }

@media (max-width: 900px) {
  .customer-layout { grid-template-columns: minmax(0, 1fr); }
  .facts { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 560px) {
  .form-grid, .facts { grid-template-columns: minmax(0, 1fr); }
  .filter-row { flex-wrap: wrap; }
  .customer-tabs button { padding: 0 12px; font-size: 13px; }
  .line-list li { grid-template-columns: minmax(0, 1fr) auto; min-width: 0; }
  .line-list li > :first-child { min-width: 0; overflow-wrap: anywhere; }
  .line-list li .muted { grid-column: 1 / -1; grid-row: 2; }
}
</style>

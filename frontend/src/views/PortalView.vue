<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { portalRequest, portalSession } from "../portal-api";

interface PortalProfile {
  company: string;
  contact_name: string;
  email: string;
  phone: string;
  company_address: string;
}
interface ConfigField {
  key: string;
  label_zh: string;
  label_en: string;
  choices?: string[];
  required?: boolean;
  type?: string;
}
interface CatalogProduct {
  id: number;
  name_zh: string;
  name_en: string;
  source_code?: string;
  orderable?: boolean;
  scope?: string;
  configuration_schema?: ConfigField[];
  price_rule: { formula?: string; status?: string; version?: string; options?: Record<string, Record<string, unknown>> } | null;
}
interface WindowLine {
  window_name: string;
  product_id: number | "";
  width_mm: string;
  height_mm: string;
  quantity: number;
  panel_count: number;
  options: Record<string, string>;
}
interface PortalLine {
  id?: string;
  window_name: string;
  unit_price?: string | null;
  amount?: string | null;
  pricing_status?: string;
}
interface PortalOrder {
  id: string;
  project_name: string;
  site_address: string;
  status: string;
  payment_status: string;
  total: string | null;
  currency?: string;
  pricing_status?: string;
  lines?: PortalLine[];
  invoices?: { id: string; kind: string; amount: string; currency: string; status: string; payment_status?: string }[];
}
interface PricedQuote {
  total: string | null;
  currency: string;
  pricing_status?: string;
  subtotal?: string;
  installation?: string;
  tax?: string;
  deposit?: string;
  rule_version?: string;
  lines: PortalLine[];
}
interface MoneySummary {
  ordered?: string;
  invoiced?: string;
  received?: string;
  outstanding_invoiced?: string;
}
interface Consumption {
  invoices: { id: string; kind: string; amount: string; currency: string; status: string; payment_status?: string }[];
  rebates: { id: string; month?: string; amount: string; currency: string; used?: string; remaining?: string }[];
  statistics_status?: string;
  summary?: Record<string, MoneySummary>;
  unpriced_orders?: number;
}

const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);
const credentials = reactive({ username: "", password: "" });
const profile = ref<PortalProfile | null>(null);
const catalog = ref<CatalogProduct[]>([]);
const pricingStatus = ref("");
const orders = ref<PortalOrder[]>([]);
const busy = ref(false);
const error = ref("");
const notice = ref("");
const quote = ref("");
const priced = ref<PricedQuote | null>(null);
const consumption = ref<Consumption | null>(null);
const pricing = ref(false);
let priceTicket = 0;
let priceTimer = 0;
const submissionKey = ref(crypto.randomUUID());
const project = reactive({
  project_name: "",
  site_address: "",
  installation_required: false,
  lines: [blankLine()] as WindowLine[],
});

function blankLine(): WindowLine {
  return { window_name: "", product_id: "", width_mm: "", height_mm: "", quantity: 1, panel_count: 1, options: {} };
}
function schemaOf(line: WindowLine) {
  return productOf(line.product_id)?.configuration_schema || [];
}
const usesWorkbookFields = computed(() => catalog.value.some((item) => item.configuration_schema));
function productOf(id: number | "") {
  return catalog.value.find((item) => item.id === id);
}
function optionNames(line: WindowLine) {
  const schema = schemaOf(line);
  if (schema.length) return schema.map((field) => field.key);
  return Object.keys(productOf(line.product_id)?.price_rule?.options || {});
}
const payload = computed(() => ({
  project_name: project.project_name.trim(),
  site_address: project.site_address.trim(),
  submission_key: submissionKey.value,
  ...(usesWorkbookFields.value ? { installation_required: project.installation_required } : {}),
  lines: project.lines.map((line) => ({
    window_name: line.window_name.trim(),
    product_id: Number(line.product_id),
    width_mm: line.width_mm,
    height_mm: line.height_mm,
    quantity: line.quantity,
    ...(usesWorkbookFields.value ? { panel_count: line.panel_count } : {}),
    options: Object.fromEntries(optionNames(line).map((name) => [name, line.options[name] || ""])),
  })),
}));

onMounted(() => {
  if (portalSession.token) void refresh();
});

async function refresh() {
  profile.value = await portalRequest<PortalProfile>("me");
  const listed = await portalRequest<{ products: CatalogProduct[]; pricing_status: string }>("catalog");
  catalog.value = listed.products;
  pricingStatus.value = listed.pricing_status;
  orders.value = await portalRequest<PortalOrder[]>("orders");
  consumption.value = await portalRequest<Consumption>("consumption");
}

async function login() {
  busy.value = true;
  error.value = "";
  notice.value = "";
  try {
    const result = await portalRequest<{ token: string }>("login", { ...credentials });
    portalSession.token = result.token;
    credentials.password = "";
    await refresh();
  } catch (cause) {
    error.value = messageOf(cause);
  } finally {
    busy.value = false;
  }
}

async function logout() {
  try {
    await portalRequest("logout", {});
  } catch {
    /* local sign-out still drops the portal token */
  }
  portalSession.token = "";
  profile.value = null;
  orders.value = [];
  consumption.value = null;
  priced.value = null;
}

function addLine() {
  project.lines.push(blankLine());
}
function removeLine(index: number) {
  if (project.lines.length > 1) project.lines.splice(index, 1);
}
function onSeries(line: WindowLine) {
  line.options = {};
}

function lineReady(line: { window_name: string; product_id: number; width_mm: string; height_mm: string; quantity: number; options: Record<string, string> }) {
  const product = productOf(line.product_id);
  if (product?.orderable === false) return false;
  const names = product?.configuration_schema?.length
    ? product.configuration_schema.filter((field) => field.required !== false).map((field) => field.key)
    : Object.keys(product?.price_rule?.options || {});
  return Boolean(line.window_name && line.product_id && line.width_mm && line.height_mm && line.quantity > 0 && names.every((name) => line.options[name]));
}

watch(payload, (body) => {
  quote.value = "";
  priced.value = null;
  window.clearTimeout(priceTimer);
  const ticket = ++priceTicket;
  if (!profile.value || !body.project_name || !body.site_address || !body.lines.every(lineReady)) {
    pricing.value = false;
    return;
  }
  pricing.value = true;
  priceTimer = window.setTimeout(async () => {
    try {
      const result = await portalRequest<PricedQuote>("price", body);
      if (ticket !== priceTicket) return;
      priced.value = result;
      quote.value = result.total ? `${result.currency} ${result.total}` : "";
      if (error.value) error.value = "";
    } catch (cause) {
      if (ticket !== priceTicket) return;
      quote.value = "";
      priced.value = null;
      error.value = messageOf(cause);
    } finally {
      if (ticket === priceTicket) pricing.value = false;
    }
  }, 300);
});

async function submitOrder() {
  busy.value = true;
  error.value = "";
  notice.value = "";
  try {
    const saved = await portalRequest<PortalOrder>("orders", payload.value);
    notice.value = saved.total
      ? tx(`已提交待审核。合计 ${saved.currency || ""} ${saved.total}。提交没有生成发票。`, `Submitted for review. Total ${saved.currency || ""} ${saved.total}. Submission did not create an invoice.`)
      : tx("已保存为待审核订单。价格规则未配置，合计为空，不能当作报价，也不会生成发票。", "Saved as an order awaiting review. Pricing rules are not configured, so the total is empty. This is not a quotation and no invoice was created.");
    submissionKey.value = crypto.randomUUID();
    project.project_name = "";
    project.site_address = "";
    project.installation_required = false;
    project.lines = [blankLine()];
    quote.value = "";
    priced.value = null;
    orders.value = await portalRequest<PortalOrder[]>("orders");
    consumption.value = await portalRequest<Consumption>("consumption");
  } catch (cause) {
    error.value = messageOf(cause);
  } finally {
    busy.value = false;
  }
}

function messageOf(cause: unknown) {
  const text = cause instanceof Error ? cause.message : String(cause);
  if (text === "PORTAL_UNAVAILABLE") {
    return tx("客户门户接口尚未接通。这里不会改用员工 CRM 登录。", "The customer portal API is not connected. This page will not fall back to the employee CRM login.");
  }
  return text || tx("没有完成。", "That did not complete.");
}
</script>

<template>
  <main class="portal">
    <header class="portal-head">
      <p class="section-label">{{ tx("客户门户", "CUSTOMER PORTAL") }}</p>
      <h1>{{ tx("配置订单，提交待审核。", "Configure a project, then submit it for review.") }}</h1>
      <p>{{ tx("一个客户一个登录、一个联系人。公司地址和本单施工地址分开。没有确认价格表时可以保存订单，但合计为空，不能当作报价。", "One customer, one login, one contact. The company address and this order’s site address stay separate. A project can be saved without a confirmed price list, but its total stays empty and is not a quotation.") }}</p>
    </header>

    <section v-if="!profile" class="card login">
      <h2>{{ tx("客户登录", "Customer sign-in") }}</h2>
      <p>{{ tx("账号由后台开通。发票和到货通知只发给这一位联系人。", "Staff open the account. Invoices and arrival notices go only to this contact.") }}</p>
      <form @submit.prevent="login">
        <label>{{ tx("账号", "Account") }}<input v-model="credentials.username" autocomplete="username" required /></label>
        <label>{{ tx("密码", "Password") }}<input v-model="credentials.password" type="password" autocomplete="current-password" required /></label>
        <button :disabled="busy">{{ tx("登录", "Sign in") }}</button>
      </form>
      <p v-if="error" class="alert" role="alert">{{ error }}</p>
    </section>

    <template v-else>
      <section class="card account">
        <div>
          <p class="section-label">{{ tx("本公司", "THIS COMPANY") }}</p>
          <h2>{{ profile.company }}</h2>
          <p>{{ profile.contact_name }}</p>
          <p>{{ tx("邮箱", "Email") }}：{{ profile.email }}</p>
          <p>{{ tx("电话", "Phone") }}：{{ profile.phone }}</p>
          <p>{{ tx("公司地址", "Company address") }}：{{ profile.company_address }}</p>
        </div>
        <button type="button" class="secondary" @click="logout">{{ tx("退出", "Sign out") }}</button>
      </section>

      <p v-if="pricingStatus === 'rules_required'" class="rule-note">{{ tx("价格规则待配置。试算会拒绝，提交后的合计保持为空。", "Pricing rules are not configured. A price check is refused, and a submitted total stays empty.") }}</p>

      <form class="card project-form" @submit.prevent="submitOrder">
        <p class="section-label">{{ tx("步骤 1 · 订单信息", "STEP 1 · ORDER INFORMATION") }}</p>
        <h2>{{ tx("新订单", "New order") }}</h2>
        <div class="grid">
          <label>{{ tx("订单名称", "Order name") }}<input v-model="project.project_name" required /></label>
          <label>{{ tx("施工或安装地址", "Site or installation address") }}<input v-model="project.site_address" required /></label>
        </div>
        <label v-if="usesWorkbookFields" class="check"><input v-model="project.installation_required" type="checkbox" /> {{ tx("本订单需要安装。安装费由服务端计算，页面不填金额。", "This order needs installation. The server calculates the installation charge. This page does not type an amount.") }}</label>
        
        <p class="section-label" style="margin-top: 40px;">{{ tx("步骤 2 · 配置窗户", "STEP 2 · CONFIGURE WINDOWS") }}</p>
        <article v-for="(line, index) in project.lines" :key="index" class="window-line">
          <header>
            <h3>{{ tx("窗户", "Window") }} {{ index + 1 }}</h3>
            <button type="button" class="secondary" :disabled="project.lines.length === 1" @click="removeLine(index)">{{ tx("移除", "Remove") }}</button>
          </header>
          <div class="grid">
            <label>{{ tx("窗户名称", "Window name") }}<input v-model="line.window_name" required /></label>
            <label>{{ tx("产品系列", "Product series") }}
              <select v-model="line.product_id" required @change="onSeries(line)">
                <option disabled value="">{{ tx("选择系列", "Choose a series") }}</option>
                <option v-for="item in catalog" :key="item.id" :value="item.id" :disabled="item.orderable === false">{{ locale === "en" ? item.name_en : item.name_zh }}{{ item.source_code ? ` · ${item.source_code}` : "" }}{{ item.orderable === false ? tx("（仅展示）", " (display only)") : "" }}</option>
              </select>
            </label>
            <label>{{ tx("宽（毫米）", "Width (mm)") }}<input v-model="line.width_mm" inputmode="decimal" required /></label>
            <label>{{ tx("高（毫米）", "Height (mm)") }}<input v-model="line.height_mm" inputmode="decimal" required /></label>
            <label>{{ tx("同配置数量", "Quantity of this configuration") }}<input v-model.number="line.quantity" type="number" min="1" step="1" required /></label>
            <label v-if="usesWorkbookFields">{{ tx("每窗面板数", "Panels per window") }}<input v-model.number="line.panel_count" type="number" min="1" step="1" required /></label>
            <template v-if="schemaOf(line).length">
              <label v-for="field in schemaOf(line)" :key="field.key">{{ locale === "en" ? field.label_en : field.label_zh }}
                <select v-if="field.choices?.length" v-model="line.options[field.key]" :required="field.required !== false">
                  <option disabled value="">{{ tx("选择", "Choose") }}</option>
                  <option v-for="choice in field.choices" :key="choice" :value="choice">{{ choice }}</option>
                </select>
                <input v-else v-model="line.options[field.key]" :required="field.required !== false" />
              </label>
            </template>
            <label v-for="name in schemaOf(line).length ? [] : optionNames(line)" :key="name">{{ name }}
              <select v-model="line.options[name]" required>
                <option disabled value="">{{ tx("选择", "Choose") }}</option>
                <option v-for="choice in Object.keys(productOf(line.product_id)?.price_rule?.options?.[name] || {})" :key="choice" :value="choice">{{ choice }}</option>
              </select>
            </label>
          </div>
          <p v-if="line.product_id && !optionNames(line).length" class="hint">{{ tx("这个系列还没有确认的加价选项。页面不接受手填单价。", "This series has no confirmed surcharge options. The page does not accept a typed unit price.") }}</p>
        </article>
        <button type="button" class="secondary" @click="addLine">{{ tx("再加一扇窗户", "Add another window") }}</button>
        
        <p class="section-label" style="margin-top: 40px;">{{ tx("步骤 3 · 确认价格", "STEP 3 · CONFIRM PRICE") }}</p>
        <aside class="price-block">
          <p class="section-label">{{ tx("价格", "PRICE") }}</p>
          <strong>{{ pricing ? tx("计算中", "Calculating") : (quote || tx("待配置", "Not configured")) }}</strong>
          <ul v-if="priced">
            <li v-if="priced.subtotal">{{ tx("商品合计", "Subtotal") }} {{ priced.currency }} {{ priced.subtotal }}</li>
            <li v-if="priced.installation">{{ tx("安装", "Installation") }} {{ priced.currency }} {{ priced.installation }}</li>
            <li v-if="priced.tax">GST {{ priced.currency }} {{ priced.tax }}</li>
            <li v-if="priced.deposit">{{ tx("定金", "Deposit") }} {{ priced.currency }} {{ priced.deposit }}</li>
            <li v-if="priced.rule_version">{{ tx("规则版本", "Rule version") }} {{ priced.rule_version }}</li>
            <li v-for="(row, index) in priced.lines" :key="index">{{ row.window_name }} · {{ row.pricing_status || tx("待配置", "Not configured") }} · {{ row.amount ? `${priced.currency} ${row.amount}` : tx("行价待配置", "Line price not configured") }}</li>
          </ul>
          <p>{{ tx("行价和合计都来自服务端。尺寸或选项一变，旧金额立刻清掉。页面不自己乘面积，也不接受手填单价。", "Line prices and the total come from the server. Changing a size or option clears the previous amount at once. This page does not multiply an area or accept a typed unit price.") }}</p>
        </aside>
        
        <p class="section-label" style="margin-top: 40px;">{{ tx("步骤 4 · 提交待审核", "STEP 4 · SUBMIT FOR REVIEW") }}</p>
        <button :disabled="busy">{{ tx("提交待审核", "Submit for review") }}</button>
        <p class="hint">{{ tx("提交不生成发票。确认接收之后才有订单金额 60% 的定金发票；定金已收是后台另一步。发票金额以后端计算为准。", "Submission does not create an invoice. Acceptance creates a deposit invoice for 60% of the order. Recording the deposit received is a separate staff step. The invoice amount is calculated on the server.") }}</p>
        <p v-if="error" class="alert" role="alert">{{ error }}</p>
        <p v-if="notice" role="status">{{ notice }}</p>
      </form>

      <section class="card">
        <h2>{{ tx("本公司订单", "This company’s projects") }}</h2>
        <p v-if="!orders.length">{{ tx("还没有订单。", "No projects yet.") }}</p>
        <article v-for="order in orders" :key="order.id" class="order-row">
          <strong>{{ order.project_name }}</strong>
          <span>{{ order.site_address }}</span>
          <span>{{ order.status }} · {{ order.payment_status }}</span>
          <span>{{ order.total ? `${order.currency || ""} ${order.total}` : tx("合计待配置", "Total not configured") }}</span>
          <ul v-if="order.lines?.length">
            <li v-for="line in order.lines" :key="line.id || line.window_name">{{ line.window_name }} · {{ line.amount ? `${order.currency || ""} ${line.amount}` : tx("行价待配置", "Line price not configured") }}</li>
          </ul>
          <ul v-if="order.invoices?.length">
            <li v-for="invoice in order.invoices" :key="invoice.id">{{ invoice.kind }} · {{ invoice.currency }} {{ invoice.amount }} · {{ tx("发送", "Send") }} {{ invoice.status }} · {{ tx("收款", "Receipt") }} {{ invoice.payment_status === "received" ? tx("已收", "Received") : tx("未确认收款", "Receipt not confirmed") }}</li>
          </ul>
        </article>
      </section>

      <section class="card">
        <h2>{{ tx("购买、发票和返利", "Purchases, invoices and rebates") }}</h2>
        <p class="hint">{{ tx("这里只列出服务端返回的订单、发票和已确认返利。消费统计口径未确认，页面不把它们加总成一笔已付金额。", "This lists the orders, invoices and confirmed rebates returned by the server. The consumption basis is not confirmed, so the page does not add them into one paid total.") }}</p>
        <p v-if="consumption?.statistics_status">{{ consumption.statistics_status }}</p>
        <p v-if="consumption?.unpriced_orders">{{ tx(`还有 ${consumption.unpriced_orders} 个订单没有确认价格，不计入下面的金额。`, `${consumption.unpriced_orders} orders have no confirmed price and are excluded from the amounts below.`) }}</p>
        <article v-for="(money, currency) in consumption?.summary || {}" :key="currency" class="order-row">
          <strong>{{ currency }}</strong>
          <span>{{ tx("已下单", "Ordered") }} {{ money.ordered || "—" }}</span>
          <span>{{ tx("已开票", "Invoiced") }} {{ money.invoiced || "—" }}</span>
          <span>{{ tx("已收", "Received") }} {{ money.received || "—" }}</span>
          <span>{{ tx("已开票未收", "Invoiced outstanding") }} {{ money.outstanding_invoiced || "—" }}</span>
        </article>
        <p v-if="!consumption?.invoices.length">{{ tx("还没有发票。", "No invoices yet.") }}</p>
        <article v-for="invoice in consumption?.invoices || []" :key="invoice.id" class="order-row">
          <strong>{{ invoice.kind }}</strong>
          <span>{{ invoice.currency }} {{ invoice.amount }}</span>
          <span>{{ tx("发送", "Send") }} {{ invoice.status }}</span>
          <span>{{ tx("收款", "Receipt") }} {{ invoice.payment_status === "received" ? tx("已收", "Received") : tx("未确认收款", "Receipt not confirmed") }}</span>
        </article>
        <p v-if="!consumption?.rebates.length">{{ tx("还没有已确认的返利。", "No confirmed rebates yet.") }}</p>
        <article v-for="credit in consumption?.rebates || []" :key="credit.id" class="order-row">
          <strong>{{ credit.month || credit.id }}</strong>
          <span>{{ credit.currency }} {{ credit.amount }} · {{ tx("已用", "Used") }} {{ credit.used || "0.00" }} · {{ tx("余额", "Remaining") }} {{ credit.remaining || "0.00" }}</span>
        </article>
      </section>
    </template>
  </main>
</template>

<style scoped>
.portal { max-width: 1040px; margin: 0 auto; padding: 48px 28px 80px; font-size: 15px; line-height: 1.6; }
.portal h2 { font-family: var(--font-display); font-size: 24px; font-weight: 600; margin: 32px 0 16px; letter-spacing: 0.02em; }
.portal h3 { font-family: var(--font-display); font-size: 18px; font-weight: 600; margin: 12px 0 8px; letter-spacing: 0.01em; }
.portal p, .portal label, .portal li { font-size: 15px; line-height: 1.65; }
.portal input, .portal select, .portal button, .portal textarea { 
  min-height: 44px; 
  font-size: 15px; 
  border: 1px solid rgba(27, 36, 33, 0.3);
  border-radius: 4px;
  padding: 10px 12px;
  transition: border-color 0.2s;
}
.portal input:focus, .portal select:focus, .portal textarea:focus {
  outline: none;
  border-color: var(--cord);
  box-shadow: 0 0 0 2px rgba(15, 110, 92, 0.1);
}
.portal button { 
  min-height: 48px; 
  font-weight: 600;
  border-radius: 4px;
  letter-spacing: 0.02em;
  transition: all 0.2s;
}
.portal button:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(15, 110, 92, 0.2); }
.portal button:disabled { opacity: 0.5; cursor: not-allowed; }
.portal button.secondary { 
  min-height: 44px;
  background: transparent; 
  color: var(--ink); 
  border-color: rgba(27, 36, 33, 0.4);
}
.portal-head { margin-bottom: 40px; }
.portal-head h1 { font-family: var(--font-display); font-size: clamp(32px, 4vw, 48px); line-height: 1.15; margin: 12px 0 16px; letter-spacing: 0.01em; }
.portal-head p, .hint, .rule-note { color: rgba(27, 36, 33, 0.72); line-height: 1.7; max-width: 72ch; }
.section-label { 
  font-size: 11px; 
  letter-spacing: 0.12em; 
  text-transform: uppercase; 
  color: var(--cord); 
  font-weight: 600;
  margin-bottom: 8px;
  display: block;
}
.project-form .section-label {
  font-size: 12px;
  padding: 10px 14px;
  background: rgba(15, 110, 92, 0.08);
  border-left: 4px solid var(--cord);
  border-radius: 4px;
  margin-bottom: 16px;
}
.card { 
  margin-top: 32px; 
  padding: 28px; 
  border: 1px solid var(--line); 
  background: var(--paper); 
  border-radius: 8px;
}
.rule-note { 
  margin: 24px 0; 
  padding: 16px 20px; 
  background: rgba(15, 110, 92, 0.06); 
  border-left: 4px solid var(--cord);
  border-radius: 4px;
}
.account { display: flex; justify-content: space-between; gap: 20px; align-items: start; }
.account h2 { margin: 0 0 12px; }
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.project-form { background: linear-gradient(135deg, rgba(255, 255, 255, 0.98) 0%, rgba(247, 251, 248, 0.95) 100%); }
.project-form .grid { margin-bottom: 24px; }
.project-form label { 
  display: grid; 
  gap: 8px; 
  font-size: 14px; 
  font-weight: 500;
  color: rgba(27, 36, 33, 0.88);
}
.check { 
  display: grid;
  grid-template-columns: 22px 1fr; 
  align-items: start; 
  gap: 12px;
  padding: 14px 16px;
  background: rgba(15, 110, 92, 0.04);
  border-radius: 4px;
  margin: 20px 0;
}
.check input { 
  width: 20px; 
  min-height: 20px; 
  margin-top: 2px;
  cursor: pointer;
}
.window-line { 
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 24px;
  margin-top: 24px;
  background: white;
}
.window-line header { 
  display: flex; 
  justify-content: space-between; 
  gap: 16px; 
  align-items: center; 
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(27, 36, 33, 0.08);
}
.window-line h3 { margin: 0; color: var(--cord); }
.window-line .grid { margin-top: 0; }
.order-row { 
  border-top: 1px solid var(--line);
  margin-top: 20px; 
  padding-top: 16px; 
  display: flex; 
  justify-content: space-between; 
  gap: 16px; 
  align-items: start; 
  flex-wrap: wrap;
}
.order-row strong { color: var(--cord); }
.price-block { 
  margin: 32px 0; 
  padding: 28px; 
  background: linear-gradient(135deg, #f7fbf8 0%, #eef4f0 100%);
  border: 1px solid var(--line);
  border-radius: 8px;
}
.price-block .section-label { margin-bottom: 12px; }
.price-block strong { 
  display: block; 
  font-family: var(--font-display);
  font-size: 36px;
  font-weight: 700;
  color: var(--cord);
  margin: 4px 0 16px;
  letter-spacing: 0.01em;
}
.price-block ul { 
  margin: 16px 0; 
  padding: 0; 
  list-style: none;
  display: grid;
  gap: 8px;
}
.price-block li { 
  padding: 8px 12px; 
  background: rgba(255, 255, 255, 0.7);
  border-radius: 4px;
  font-size: 14px;
}
.price-block > p { 
  margin-top: 20px; 
  padding-top: 16px; 
  border-top: 1px solid rgba(27, 36, 33, 0.12);
  font-size: 13px; 
}
.alert { 
  color: var(--danger); 
  background: rgba(140, 47, 47, 0.08);
  padding: 14px 16px;
  border-radius: 4px;
  margin-top: 16px;
  border-left: 4px solid var(--danger);
}
@media (max-width: 700px) { 
  .grid, .account { grid-template-columns: 1fr; }
  .portal { padding: 32px 20px 60px; }
  .card { padding: 20px; }
  .window-line { padding: 20px; }
  .price-block { padding: 20px; }
  .price-block strong { font-size: 28px; }
}
@media (max-width: 390px) {
  .portal { padding: 24px 16px 48px; }
  .card { padding: 16px; }
  .window-line { padding: 16px; }
}</style>

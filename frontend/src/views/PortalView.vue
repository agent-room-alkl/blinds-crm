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
interface CatalogProduct {
  id: number;
  name_zh: string;
  name_en: string;
  price_rule: { options?: Record<string, Record<string, unknown>> } | null;
}
interface WindowLine {
  window_name: string;
  product_id: number | "";
  width_mm: string;
  height_mm: string;
  quantity: number;
  options: Record<string, string>;
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
const pricing = ref(false);
let priceTicket = 0;
let priceTimer = 0;
const submissionKey = ref(crypto.randomUUID());
const project = reactive({
  project_name: "",
  site_address: "",
  lines: [blankLine()] as WindowLine[],
});

function blankLine(): WindowLine {
  return { window_name: "", product_id: "", width_mm: "", height_mm: "", quantity: 1, options: {} };
}
function productOf(id: number | "") {
  return catalog.value.find((item) => item.id === id);
}
function optionNames(line: WindowLine) {
  return Object.keys(productOf(line.product_id)?.price_rule?.options || {});
}
const payload = computed(() => ({
  project_name: project.project_name.trim(),
  site_address: project.site_address.trim(),
  submission_key: submissionKey.value,
  lines: project.lines.map((line) => ({
    window_name: line.window_name.trim(),
    product_id: Number(line.product_id),
    width_mm: line.width_mm,
    height_mm: line.height_mm,
    quantity: line.quantity,
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
  const names = Object.keys(productOf(line.product_id)?.price_rule?.options || {});
  return line.window_name && line.product_id && line.width_mm && line.height_mm && line.quantity > 0 && names.every((name) => line.options[name]);
}

watch(payload, (body) => {
  quote.value = "";
  window.clearTimeout(priceTimer);
  const ticket = ++priceTicket;
  if (!profile.value || !body.project_name || !body.site_address || !body.lines.every(lineReady)) {
    pricing.value = false;
    return;
  }
  pricing.value = true;
  priceTimer = window.setTimeout(async () => {
    try {
      const priced = await portalRequest<{ total: string; currency: string }>("price", body);
      if (ticket !== priceTicket) return;
      quote.value = `${priced.currency} ${priced.total}`;
      if (error.value) error.value = "";
    } catch (cause) {
      if (ticket !== priceTicket) return;
      quote.value = "";
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
      : tx("已保存为待审核项目。价格规则未配置，合计为空，不能当作报价，也不会生成发票。", "Saved as a project awaiting review. Pricing rules are not configured, so the total is empty. This is not a quotation and no invoice was created.");
    submissionKey.value = crypto.randomUUID();
    project.project_name = "";
    project.site_address = "";
    project.lines = [blankLine()];
    quote.value = "";
    orders.value = await portalRequest<PortalOrder[]>("orders");
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
      <h1>{{ tx("配置项目，提交待审核。", "Configure a project, then submit it for review.") }}</h1>
      <p>{{ tx("一个客户一个登录、一个联系人。公司地址和本单施工地址分开。没有确认价格表时可以保存项目，但合计为空，不能当作报价。", "One customer, one login, one contact. The company address and this order’s site address stay separate. A project can be saved without a confirmed price list, but its total stays empty and is not a quotation.") }}</p>
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
        <h2>{{ tx("新项目", "New project") }}</h2>
        <div class="grid">
          <label>{{ tx("项目名称", "Project name") }}<input v-model="project.project_name" required /></label>
          <label>{{ tx("施工或安装地址", "Site or installation address") }}<input v-model="project.site_address" required /></label>
        </div>
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
                <option v-for="item in catalog" :key="item.id" :value="item.id">{{ locale === "en" ? item.name_en : item.name_zh }}</option>
              </select>
            </label>
            <label>{{ tx("宽（毫米）", "Width (mm)") }}<input v-model="line.width_mm" inputmode="decimal" required /></label>
            <label>{{ tx("高（毫米）", "Height (mm)") }}<input v-model="line.height_mm" inputmode="decimal" required /></label>
            <label>{{ tx("数量", "Quantity") }}<input v-model.number="line.quantity" type="number" min="1" step="1" required /></label>
            <label v-for="name in optionNames(line)" :key="name">{{ name }}
              <select v-model="line.options[name]" required>
                <option disabled value="">{{ tx("选择", "Choose") }}</option>
                <option v-for="choice in Object.keys(productOf(line.product_id)?.price_rule?.options?.[name] || {})" :key="choice" :value="choice">{{ choice }}</option>
              </select>
            </label>
          </div>
          <p v-if="line.product_id && !optionNames(line).length" class="hint">{{ tx("这个系列还没有确认的加价选项。页面不接受手填单价。", "This series has no confirmed surcharge options. The page does not accept a typed unit price.") }}</p>
        </article>
        <button type="button" class="secondary" @click="addLine">{{ tx("再加一扇窗户", "Add another window") }}</button>
        <aside class="price-block">
          <p class="section-label">{{ tx("价格", "PRICE") }}</p>
          <strong>{{ pricing ? tx("计算中", "Calculating") : (quote || tx("待配置", "Not configured")) }}</strong>
          <p>{{ tx("尺寸或选项一变，旧金额立刻清掉，再向服务端重算。没有确认价格表时不显示可付款金额。", "Changing a size or option clears the previous amount at once, then the server recalculates. Without a confirmed price list, no payable amount is shown.") }}</p>
        </aside>
        <button :disabled="busy">{{ tx("提交待审核", "Submit for review") }}</button>
        <p class="hint">{{ tx("提交不生成发票。确认接收之后才有订单金额 60% 的定金发票；定金已收是后台另一步。发票金额以后端计算为准。", "Submission does not create an invoice. Acceptance creates a deposit invoice for 60% of the order. Recording the deposit received is a separate staff step. The invoice amount is calculated on the server.") }}</p>
        <p v-if="error" class="alert" role="alert">{{ error }}</p>
        <p v-if="notice" role="status">{{ notice }}</p>
      </form>

      <section class="card">
        <h2>{{ tx("本公司项目", "This company’s projects") }}</h2>
        <p v-if="!orders.length">{{ tx("还没有项目。", "No projects yet.") }}</p>
        <article v-for="order in orders" :key="order.id" class="order-row">
          <strong>{{ order.project_name }}</strong>
          <span>{{ order.site_address }}</span>
          <span>{{ order.status }} · {{ order.payment_status }}</span>
          <span>{{ order.total ? `${order.currency || ""} ${order.total}` : tx("合计待配置", "Total not configured") }}</span>
        </article>
      </section>
    </template>
  </main>
</template>

<style scoped>
.portal { max-width: 960px; margin: 0 auto; padding: 48px 24px 72px; }
.portal-head h1 { font-family: var(--font-display); font-size: clamp(32px, 4vw, 48px); line-height: 1.15; margin: 12px 0; }
.portal-head p, .hint, .rule-note { color: #54645c; line-height: 1.7; }
.section-label { font-size: 11px; letter-spacing: 0.14em; }
.card, .rule-note { margin-top: 24px; }
.account { display: flex; justify-content: space-between; gap: 16px; align-items: start; }
.account h2, .window-line h3 { margin: 8px 0; }
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.window-line, .order-row { border-top: 1px solid var(--line, #dedbd5); margin-top: 16px; padding-top: 12px; }
.window-line header, .order-row { display: flex; justify-content: space-between; gap: 12px; align-items: center; flex-wrap: wrap; }
.price-block { margin: 20px 0; padding: 16px; background: #f5f4f0; }
.price-block strong { display: block; font-size: 28px; margin: 8px 0; }
.alert { color: #8a3b2c; }
@media (max-width: 700px) { .grid, .account { display: grid; grid-template-columns: 1fr; } }
</style>

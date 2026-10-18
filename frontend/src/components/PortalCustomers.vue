<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { request } from "../crm-api";

interface PortalCustomer {
  customer_id: number;
  company: string;
  contact_name: string;
  email: string;
  phone: string;
  company_address: string;
  username: string;
}

const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);
const rows = ref<PortalCustomer[]>([]);
const error = ref("");
const notice = ref("");
interface CompanyUse {
  orders: { id: string; project_name?: string; total: string | null; currency?: string; status?: string }[];
  invoices: { id: string; kind: string; amount: string; currency: string; status?: string; payment_status?: string }[];
  rebates: { id: string; month?: string; amount: string; currency: string; used?: string; remaining?: string }[];
  summary?: Record<string, { ordered?: string; invoiced?: string; received?: string; outstanding_invoiced?: string }>;
  unpriced_orders?: number;
}
const selected = ref<number | null>(null);
const usage = ref<CompanyUse | null>(null);
const draft = reactive({ company: "", contact_name: "", email: "", phone: "", company_address: "" });

async function load() {
  rows.value = await request<PortalCustomer[]>("operations/customers");
}

onMounted(async () => {
  try {
    await load();
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  }
});

async function choose(row: PortalCustomer) {
  selected.value = row.customer_id;
  draft.company = row.company;
  draft.contact_name = row.contact_name;
  draft.email = row.email;
  draft.phone = row.phone;
  draft.company_address = row.company_address;
  error.value = "";
  notice.value = "";
  usage.value = null;
  try {
    usage.value = await request<CompanyUse>(`operations/customers/${row.customer_id}/consumption`);
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  }
}

async function save() {
  if (selected.value == null) return;
  error.value = "";
  notice.value = "";
  try {
    await request(`operations/customers/${selected.value}`, { ...draft });
    notice.value = tx("门户档案已更新。", "Portal profile updated.");
    await load();
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  }
}
</script>

<template>
  <section class="card profiles">
    <h2>{{ tx("客户资料", "Customers") }}</h2>
    <p>{{ tx("每个客户一个登录、一个联系人。邮箱、电话和公司地址来自门户档案，不在这里加第二联系人。", "Each customer has one login and one contact. Email, phone and company address come from the portal profile. A second contact is not added here.") }}</p>
    <p class="hint">{{ tx("点一家客户后可以改公司、联系人、邮箱、电话和公司地址。", "Choose a customer, then edit the company, contact, email, phone and company address.") }}</p>
    <form v-if="selected != null" class="editor" @submit.prevent="save">
      <label>{{ tx("公司", "Company") }}<input v-model="draft.company" required /></label>
      <label>{{ tx("联系人", "Contact") }}<input v-model="draft.contact_name" required /></label>
      <label>{{ tx("邮箱", "Email") }}<input v-model="draft.email" type="email" required /></label>
      <label>{{ tx("电话", "Phone") }}<input v-model="draft.phone" required /></label>
      <label>{{ tx("公司地址", "Company address") }}<input v-model="draft.company_address" required /></label>
      <button type="submit">{{ tx("保存档案", "Save profile") }}</button>
    </form>
    <section v-if="usage">
      <h3>{{ tx("这家公司的订单、发票和返利", "This company’s orders, invoices and rebates") }}</h3>
      <p v-if="usage.unpriced_orders">{{ tx(`有 ${usage.unpriced_orders} 个订单还没有确认价格。`, `${usage.unpriced_orders} orders have no confirmed price.`) }}</p>
      <p v-for="(money, currency) in usage.summary || {}" :key="currency">{{ currency }} · {{ tx("已下单", "Ordered") }} {{ money.ordered || "—" }} · {{ tx("已开票", "Invoiced") }} {{ money.invoiced || "—" }} · {{ tx("已收", "Received") }} {{ money.received || "—" }} · {{ tx("已开票未收", "Invoiced outstanding") }} {{ money.outstanding_invoiced || "—" }}</p>
      <p v-for="order in usage.orders" :key="order.id">{{ order.project_name || order.id }} · {{ order.status || "" }} · {{ order.total ? `${order.currency || ""} ${order.total}` : tx("合计待配置", "Total not configured") }}</p>
      <p v-for="invoice in usage.invoices" :key="invoice.id">{{ invoice.kind }} · {{ invoice.currency }} {{ invoice.amount }} · {{ tx("发送", "Send") }} {{ invoice.status || "—" }} · {{ tx("收款", "Receipt") }} {{ invoice.payment_status === "received" ? tx("已收", "Received") : tx("未确认收款", "Receipt not confirmed") }}</p>
      <p v-for="credit in usage.rebates" :key="credit.id">{{ tx("返利", "Rebate") }} {{ credit.month || credit.id }} · {{ credit.currency }} {{ credit.amount }} · {{ tx("已用", "Used") }} {{ credit.used || "0.00" }} · {{ tx("余额", "Remaining") }} {{ credit.remaining || "0.00" }}</p>
    </section>
    <p v-if="error" class="alert" role="alert">{{ error }}</p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <p v-if="!rows.length && !error">{{ tx("还没有开通门户账号。", "No portal account has been opened yet.") }}</p>
    <article v-for="row in rows" :key="row.customer_id" @click="choose(row)">
      <h3>{{ row.company }}</h3>
      <p>{{ row.contact_name }} · {{ row.username }}</p>
      <p>{{ tx("邮箱", "Email") }}：{{ row.email }}</p>
      <p>{{ tx("电话", "Phone") }}：{{ row.phone }}</p>
      <p>{{ tx("公司地址", "Company address") }}：{{ row.company_address }}</p>
    </article>
  </section>
</template>

<style scoped>
.profiles { font-size: 15px; line-height: 1.55; }
.profiles h2 { font-size: 20px; margin: 0 0 12px; }
.profiles h3 { font-size: 18px; margin: 0 0 8px; }
.profiles p { font-size: 15px; margin: 8px 0; }
.profiles article { border-top: 1px solid var(--line, #dedbd5); margin-top: 20px; padding-top: 16px; cursor: pointer; }
.editor { display: grid; gap: 12px; margin: 20px 0; max-width: 640px; }
.editor label { font-size: 14px; }
.editor input, .editor button { min-height: 40px; font-size: 15px; }
.hint { color: #54645c; line-height: 1.6; }
.alert { color: #8a3b2c; }
</style>

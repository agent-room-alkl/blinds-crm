<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
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
defineProps<{ admin?: boolean }>();
const detailTab = ref('profile');
const creating = ref(false);
const account = reactive({company:'',contact_name:'',email:'',phone:'',company_address:'',username:'',password:''});
async function openAccount() {
  try { error.value=''; await request('operations/customers',{...account}); account.password=''; creating.value=false; notice.value=tx('客户与门户账号已开通','Customer and portal account created'); await load(); }
  catch(cause){error.value=cause instanceof Error?cause.message:String(cause)}
}
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);
const rows = ref<PortalCustomer[]>([]);
const loading = ref(true);
const search = ref('');
const filteredRows = computed(()=>rows.value.filter(r=>`${r.company} ${r.username}`.toLowerCase().includes(search.value.toLowerCase())));
const customerPage = ref(0);
const customerPages = computed(()=>Math.max(1,Math.ceil(filteredRows.value.length/5)));
const shownRows = computed(()=>filteredRows.value.slice(customerPage.value*5,customerPage.value*5+5));
watch(search,()=>{customerPage.value=0});
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
  } finally {
    loading.value = false;
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
    <button v-if="admin" type="button" @click="creating = !creating">{{ tx('新增客户并开通账号','Create customer & portal account') }}</button>
    <form v-if="creating" class="editor" @submit.prevent="openAccount">
      <label>{{ tx('公司','Company') }}<input v-model="account.company" required /></label><label>{{ tx('联系人','Contact') }}<input v-model="account.contact_name" required /></label>
      <label>{{ tx('邮箱（可待补）','Email (optional)') }}<input v-model="account.email" type="email" /></label><label>{{ tx('电话','Phone') }}<input v-model="account.phone" required /></label><label>{{ tx('公司地址','Company address') }}<input v-model="account.company_address" required /></label>
      <label>{{ tx('登录账号','Username') }}<input v-model="account.username" required autocomplete="off" /></label><label>{{ tx('初始密码','Starting password') }}<input v-model="account.password" type="password" minlength="8" required autocomplete="new-password" /></label><button>{{ tx('创建客户与账号','Create customer & account') }}</button>
    </form>
    <p class="hint">{{ tx("点一家客户后可以改公司、联系人、邮箱、电话和公司地址。", "Choose a customer, then edit the company, contact, email, phone and company address.") }}</p>
    <div class="customer-layout"><aside class="customer-list"><label>{{ tx('搜索客户','Search customers') }}<input v-model="search" /></label><button v-for="row in shownRows" :key="row.customer_id" type="button" :aria-pressed="selected===row.customer_id" @click="choose(row)"><strong>{{ row.company }}</strong><small>{{ row.username }}</small></button><div class="customer-pagination"><button :disabled="customerPage===0" @click="customerPage--" aria-label="Previous customers">←</button><span>{{ customerPage+1 }} / {{ customerPages }}</span><button :disabled="customerPage+1>=customerPages" @click="customerPage++" aria-label="Next customers">→</button></div></aside><div class="customer-detail"><h3 v-if="selected!=null">{{ rows.find(r=>r.customer_id===selected)?.company }}</h3><p v-else>{{ tx('选择客户查看资料与账号','Choose a customer to view profile and account') }}</p>
    <nav v-if="selected != null" class="customer-tabs"><button v-for="item in [['profile','资料','Profile'],['account','登录账号','Portal account'],['orders','订单','Orders'],['finance','账款返利','Accounts & rebates']]" :key="item[0]" :aria-pressed="detailTab === item[0]" @click="detailTab = item[0]">{{ tx(item[1]!,item[2]!) }}</button></nav>
    <section v-if="selected != null && detailTab === 'account'"><h3>{{ tx('门户账号','Portal account') }}</h3><p>{{ rows.find(r=>r.customer_id===selected)?.username }}</p><p>{{ tx('每个客户一个登录账号、一个联系人。现有密码不显示。','One login and one contact per customer. Existing passwords are never displayed.') }}</p></section>
    <form v-if="selected != null && detailTab === 'profile'" class="editor" @submit.prevent="save">
      <label>{{ tx("公司", "Company") }}<input v-model="draft.company" required /></label>
      <label>{{ tx("联系人", "Contact") }}<input v-model="draft.contact_name" required /></label>
      <label>{{ tx("邮箱", "Email") }}<input v-model="draft.email" type="email" /></label>
      <label>{{ tx("电话", "Phone") }}<input v-model="draft.phone" required /></label>
      <label>{{ tx("公司地址", "Company address") }}<input v-model="draft.company_address" required /></label>
      <button type="submit">{{ tx("保存档案", "Save profile") }}</button>
    </form>
    <section v-if="usage && ['orders','finance'].includes(detailTab)">
      <h3>{{ tx("这家公司的订单、发票和返利", "This company’s orders, invoices and rebates") }}</h3>
      <p v-if="usage.unpriced_orders">{{ tx(`有 ${usage.unpriced_orders} 个订单还没有确认价格。`, `${usage.unpriced_orders} orders have no confirmed price.`) }}</p>
      <p v-for="(money, currency) in usage.summary || {}" :key="currency">{{ currency }} · {{ tx("已下单", "Ordered") }} {{ money.ordered || "—" }} · {{ tx("已开票", "Invoiced") }} {{ money.invoiced || "—" }} · {{ tx("已收", "Received") }} {{ money.received || "—" }} · {{ tx("已开票未收", "Invoiced outstanding") }} {{ money.outstanding_invoiced || "—" }}</p>
      <p v-for="order in usage.orders" :key="order.id"><RouterLink :to="{path:'/crm/projects',query:{order:order.id}}">{{ order.project_name }}</RouterLink> · {{ order.status || "" }} · {{ order.total ? `${order.currency || ""} ${order.total}` : tx("合计待配置", "Total not configured") }}</p>
      <RouterLink v-if="detailTab === 'finance'" :to="{path:'/crm/finance',query:{customer:selected}}">{{ tx('打开客户账本','Open customer ledger') }}</RouterLink>
      <p v-for="invoice in usage.invoices" :key="invoice.id">{{ invoice.kind }} · {{ invoice.currency }} {{ invoice.amount }} · {{ tx("发送", "Send") }} {{ invoice.status || "—" }} · {{ tx("收款", "Receipt") }} {{ invoice.payment_status === "received" ? tx("已收", "Received") : tx("未确认收款", "Receipt not confirmed") }}</p>
      <p v-for="credit in usage.rebates" :key="credit.id">{{ tx("返利", "Rebate") }} {{ credit.month || credit.id }} · {{ credit.currency }} {{ credit.amount }} · {{ tx("已用", "Used") }} {{ credit.used || "0.00" }} · {{ tx("余额", "Remaining") }} {{ credit.remaining || "0.00" }}</p>
    </section>
    <p v-if="error" class="alert" role="alert">{{ error }}</p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <p v-if="loading" role="status">{{ tx('加载客户中…','Loading customers…') }}</p><p v-if="!loading && !rows.length && !error">{{ tx("还没有开通门户账号。", "No portal account has been opened yet.") }}</p>
    </div></div>
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
.editor input, .editor button,.customer-tabs button { min-height: 44px; font-size: 15px; }
.customer-tabs{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}.customer-tabs button{color:#17523a;background:#edf4ef;border:1px solid #cbd8cf}.customer-tabs button[aria-pressed=true]{background:#17523a;color:white}
.hint { color: #54645c; line-height: 1.6; }
.alert { color: #8a3b2c; }
.customer-layout{display:grid;grid-template-columns:240px minmax(0,1fr);gap:20px;margin-top:16px}.customer-list{display:flex;flex-direction:column;gap:4px;min-width:0}.customer-list button{display:flex;flex-direction:column;align-items:start;text-align:left;min-height:44px;border:1px solid #dce5df;background:#f5f8f5;color:#203d30;padding:8px}.customer-list button[aria-pressed=true]{background:#dfeee4;border-color:#17523a}.customer-list small{font-size:12px}.customer-detail{min-width:0}.customer-detail a{color:#17523a}.customer-list input{min-height:44px;width:100%;box-sizing:border-box}
@media(max-width:700px){.customer-layout{grid-template-columns:minmax(0,1fr)}.customer-list{max-height:none}.editor{grid-template-columns:minmax(0,1fr)}.editor input{min-width:0;max-width:100%;box-sizing:border-box}}
.customer-pagination{display:flex;gap:8px;align-items:center;justify-content:center}.customer-pagination button{min-width:44px;align-items:center}
</style>

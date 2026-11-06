<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { request } from '../crm-api';

interface Order {
  id: string; order_number?: string; company: string; project_name: string; status: string;
  payment_status: string; total?: string | null; deposit?: string | null; eta?: string;
  subtotal?: string | null; installation?: string | null; tax?: string | null;
  created_at?: string; accepted_at?: string; deposit_paid_at?: string; order_date?: string | null;
  history?: { action: string; created_at: string }[];
}
interface Invoice { kind: string; payment_status?: string; received_at?: string; amount: string; order_ids?: string[]; }
const router = useRouter();
const { locale } = useI18n();
const zh = computed(() => locale.value === 'zh');
const tx = (cn: string, en: string) => zh.value ? cn : en;
const orders = ref<Order[]>([]);
const invoices = ref<Invoice[]>([]);
const loading = ref(true);
const error = ref('');
const formatter = new Intl.NumberFormat('en-NZ', { style: 'currency', currency: 'NZD', minimumFractionDigits: 2, maximumFractionDigits: 2 });
const amount = (value?: string | number | null) => formatter.format(Number(value || 0));
const reviewTasks = computed(() => orders.value.filter(order => order.status === 'pending_review'));
const orderTasks = computed(() => orders.value.filter(order => order.status === 'accepted' && order.payment_status === 'deposit_received'));
const monthKey = (value?: string) => value ? value.slice(0, 7) : '';
const monthLabel = (key: string) => new Intl.DateTimeFormat(zh.value ? 'zh-NZ' : 'en-NZ', { month: 'short', year: 'numeric', timeZone: 'Pacific/Auckland' }).format(new Date(`${key}-01T12:00:00`));
const months = computed(() => {
  const result: string[] = [];
  const now = new Date();
  for (let i = 5; i >= -6; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1, 12);
    result.push(`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2, '0')}`);
  }
  return result;
});
const monthly = computed(() => months.value.map(month => {
  const bookedOrders = orders.value.filter(order => Boolean(order.order_date) && monthKey(order.order_date || undefined) === month);
  const booked = bookedOrders.reduce((sum, order) => sum + Number(order.total || 0), 0);
  const product = bookedOrders.reduce((sum, order) => sum + Number(order.subtotal || 0), 0);
  const installation = bookedOrders.reduce((sum, order) => sum + Number(order.installation || 0), 0);
  const gst = bookedOrders.reduce((sum, order) => sum + Number(order.tax || 0), 0);
  const received = invoices.value.filter(invoice => invoice.kind === 'deposit' && invoice.payment_status === 'received' && monthKey(invoice.received_at) === month).reduce((sum, invoice) => sum + Number(invoice.amount || 0), 0);
  const balance = orders.value.filter(order => order.payment_status === 'deposit_received' && order.eta && monthKey(order.eta) === month && ['accepted','supplier_ordered','in_transit','ready'].includes(order.status)).reduce((sum, order) => sum + Math.max(0, Number(order.total || 0) - Number(order.deposit || 0)), 0);
  return { month, booked, product, installation, gst, received, balance };
}));
const maxFinance = computed(() => Math.max(1, ...monthly.value.flatMap(row => [row.booked, row.product, row.installation, row.gst, row.received, row.balance])));
async function load() {
  loading.value = true;
  error.value = '';
  try {
    const [orderRows, invoiceRows] = await Promise.all([request<Order[]>('operations/orders'), request<Invoice[]>('operations/invoices')]);
    orders.value = orderRows;
    invoices.value = invoiceRows;
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally { loading.value = false; }
}
function openOrders(status: string, payment?: string) {
  const query: Record<string, string> = {};
  if (status) query.status = status;
  if (payment) query.payment = payment;
  void router.push({ path: '/crm/projects', query });
}
onMounted(() => void load());
</script>

<template>
  <main class="dashboard-live">
    <header class="dashboard-title"><div><p>{{ tx('业务概览','BUSINESS OVERVIEW') }}</p><h1>{{ tx('Dashboard','Dashboard') }}</h1></div><button type="button" @click="load">{{ tx('刷新','Refresh') }}</button></header>
    <p v-if="error" class="dashboard-error" role="alert">{{ error }}</p>
    <section class="task-area"><h2>{{ tx('需要处理的工作','Action required') }}</h2><p>{{ tx('任务根据订单进度自动更新。点击卡片打开对应订单列表。','Tasks update automatically from order progress. Select a card to open its order list.') }}</p>
      <div class="task-cards">
        <button type="button" class="task-card" @click="openOrders('pending_review')"><span>{{ tx('待审阅','Pending review') }}</span><strong>{{ reviewTasks.length }}</strong><small>{{ tx('客户已提交，等待审核','Submitted by customers and awaiting review') }}</small></button>
        <button type="button" class="task-card" @click="openOrders('accepted', 'deposit_received')"><span>{{ tx('待下单','Ready to order') }}</span><strong>{{ orderTasks.length }}</strong><small>{{ tx('已确认且定金已收，等待向工厂下单','Confirmed and deposit received; awaiting supplier order') }}</small></button>
      </div>
    </section>
    <section class="finance-area"><div class="section-title"><div><h2>{{ tx('财务概览','Financial overview') }}</h2><p>{{ tx('营业额按定金到账后的正式订单日期归月；已收款按实际到账日；尾款按 ETA 预测。','Revenue is grouped by the formal order date after deposit receipt; payments use the actual receipt date, and balances are forecast by ETA.') }}</p></div></div>
      <p v-if="loading" class="muted">{{ tx('正在读取真实订单…','Loading live order data…') }}</p>
      <div v-else class="finance-table-wrap"><table><thead><tr><th>{{ tx('月份','Month') }}</th><th>{{ tx('订单金额（营业额）','Order total (revenue)') }}</th><th>{{ tx('产品金额','Product') }}</th><th>{{ tx('安装','Installation') }}</th><th>GST</th><th>{{ tx('已收定金','Deposits received') }}</th><th>{{ tx('预计尾款（ETA）','Forecast balance (ETA)') }}</th></tr></thead><tbody><tr v-for="row in monthly" :key="row.month"><th>{{ monthLabel(row.month) }}</th><td><div class="metric-cell"><span>{{ amount(row.booked) }}</span><i :style="{width:`${row.booked/maxFinance*100}%`}" /></div></td><td>{{ amount(row.product) }}</td><td>{{ amount(row.installation) }}</td><td>{{ amount(row.gst) }}</td><td><div class="metric-cell"><span>{{ amount(row.received) }}</span><i class="received" :style="{width:`${row.received/maxFinance*100}%`}" /></div></td><td><div class="metric-cell"><span>{{ amount(row.balance) }}</span><i class="forecast" :style="{width:`${row.balance/maxFinance*100}%`}" /></div></td></tr></tbody></table></div>
      <div class="finance-legend"><span><i />{{ tx('营业额','Revenue') }}</span><span><i class="received" />{{ tx('已收款','Received') }}</span><span><i class="forecast" />{{ tx('预计尾款','Forecast balance') }}</span></div>
    </section>
    <section class="profit-area"><div><h2>{{ tx('每单利润','Profit per order') }}</h2><p>{{ tx('接入真实工厂成本、运费与关税后显示。','Will appear when real factory costs, freight and duties are available.') }}</p></div><span>{{ tx('等待成本数据','Awaiting cost data') }}</span></section>
  </main>
</template>

<style scoped>
.dashboard-live{display:grid;gap:20px;color:#20352b}.dashboard-title,.section-title{display:flex;justify-content:space-between;align-items:center;gap:16px}.dashboard-title{padding:6px 0 16px;border-bottom:1px solid #dce5df}.dashboard-title p{margin:0;color:#65756b;font-size:11px;letter-spacing:.12em}.dashboard-title h1{margin:4px 0 0;font-size:25px}.dashboard-title button{border:1px solid #cbd8ce;border-radius:7px;background:white;padding:10px 14px;color:#234b37}.task-area,.finance-area,.profit-area{padding:20px;background:white;border:1px solid #e1e8e2;border-radius:12px}.task-area h2,.finance-area h2,.profit-area h2{margin:0;font-size:17px}.task-area>p,.section-title p,.profit-area p{color:#63736a;margin:5px 0 0}.task-cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin-top:16px}.task-card{display:grid;gap:8px;text-align:left;padding:18px;border:1px solid #dce7df;border-radius:10px;background:#f8fbf8;color:#20382c;cursor:pointer}.task-card:hover{border-color:#65927b;background:#f0f7f2}.task-card span{font-weight:600}.task-card strong{font-size:32px;line-height:1.1;color:#17603e}.task-card small{color:#65756b}.finance-table-wrap{overflow-x:auto;margin-top:12px}.finance-area table{width:100%;min-width:670px;border-collapse:collapse}.finance-area th,.finance-area td{text-align:left;padding:10px;border-bottom:1px solid #edf1ee}.finance-area thead th{font-size:12px;color:#617168}.metric-cell{display:grid;gap:6px;min-width:125px}.metric-cell i,.finance-legend i{height:5px;display:block;border-radius:5px;background:#376e50}.metric-cell i.received,.finance-legend i.received{background:#76a587}.metric-cell i.forecast,.finance-legend i.forecast{background:#d2a84c}.finance-legend{display:flex;gap:18px;flex-wrap:wrap;margin-top:12px;color:#617168;font-size:12px}.finance-legend span{display:flex;align-items:center;gap:6px}.finance-legend i{width:12px;height:12px}.profit-area{display:flex;align-items:center;justify-content:space-between;gap:16px;background:#f8faf8}.profit-area>span{border:1px solid #d9e3dc;border-radius:999px;padding:7px 11px;font-size:12px;color:#64746a}.dashboard-error{padding:12px;background:#fae8e1;border-radius:8px;color:#842b16}.muted{color:#65756b}@media(max-width:680px){.task-cards{grid-template-columns:1fr}.task-area,.finance-area,.profit-area{padding:15px}.profit-area{align-items:flex-start;flex-direction:column}}
</style>

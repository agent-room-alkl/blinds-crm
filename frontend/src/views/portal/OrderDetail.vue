<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import { describeAddons } from "../../addons";
import { ORDER_FLOW, formatDate, leadTimeLabel, normalizeStatus } from "../../orderStatus";
import { portalRequest } from "../../portal-api";

const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);
const route = useRoute();
const order = ref<any>(null);
const loading = ref(true);
const error = ref("");

const FLOW = ORDER_FLOW;
const normalizedStatus = computed(() => normalizeStatus(order.value?.status));
const currentFlowIndex = computed(() => {
  if (!order.value) return -1;
  if (normalizedStatus.value === "pending_review") return 0;
  if (normalizedStatus.value === "accepted" || normalizedStatus.value === "deposit_unpaid") return 1;
  const found = FLOW.findIndex((step) => step.key === normalizedStatus.value);
  return found >= 0 ? found : Math.max(0, FLOW.findIndex((step) => step.key === "accepted"));
});
const friendlyStatus = computed(() => FLOW.find((step) => step.key === normalizedStatus.value)?.[locale.value === "zh" ? "zh" : "en"] || tx("处理中", "In progress"));

function lineAddons(line: any): string[] {
  const values = describeAddons(line.options, locale.value);
  if (line.options?.custom_frame === "yes") values.push(tx("定制边框", "Customised frame"));
  return values;
}
function option(line: any, key: string): string { return line.options?.[key] || "—"; }

onMounted(async () => {
  try {
    const orders = await portalRequest<any[]>("orders");
    order.value = orders.find((item) => item.id === route.params.id) || null;
    if (!order.value) error.value = tx("找不到这张订单。", "This order could not be found.");
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : tx("订单暂时无法载入。", "The order could not be loaded.");
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="order-detail">
    <div v-if="loading" class="notice">{{ tx("加载中…", "Loading…") }}</div>
    <div v-else-if="error" class="notice error" role="alert">{{ error }}</div>
    <template v-else-if="order">
      <header class="page-heading">
        <div><p class="eyebrow">{{ tx("订单详情", "ORDER DETAILS") }}</p><h1>{{ order.project_name }}</h1><p v-if="order.order_number" class="order-number">{{ order.order_number }}</p></div>
        <span class="status-pill" :class="`status-${normalizedStatus}`">{{ friendlyStatus }}</span>
      </header>

      <section class="panel status-panel">
        <div class="section-heading"><div><h2>{{ tx("订单进度", "Order progress") }}</h2><p v-if="order.eta">{{ tx("预计到货", "Estimated arrival") }}: <strong>{{ formatDate(order.eta, locale) }}</strong><span v-if="order.batch_name"> · {{ order.batch_name }}</span></p></div><span v-if="leadTimeLabel(order.lead_time, locale)" class="lead-time">{{ leadTimeLabel(order.lead_time, locale) }}</span></div>
        <ol class="status-flow">
          <li v-for="(step,index) in FLOW" :key="step.key" :class="{ done:index<currentFlowIndex, current:index===currentFlowIndex }"><span class="dot"></span><span>{{ locale==='zh'?step.zh:step.en }}</span></li>
        </ol>
      </section>

      <section class="panel">
        <h2>{{ tx("订单信息", "Order information") }}</h2>
        <dl class="facts">
          <dt>{{ tx("订单号", "Order number") }}</dt><dd>{{ order.order_number || (order.order_number_confirmed===false ? tx("待确认", "Awaiting confirmation") : "—") }}</dd>
          <dt>{{ tx("状态", "Status") }}</dt><dd>{{ friendlyStatus }}</dd>
          <dt>{{ tx("定金状态", "Deposit") }}</dt><dd>{{ order.payment_status==='deposit_received' || order.payment_status==='paid' ? tx("已到账", "Received") : tx("处理中", "Pending") }}<span v-if="order.deposit_paid_at"> · {{ order.deposit_paid_at.slice(0,10) }}</span></dd>
          <dt>{{ tx("安装", "Installation") }}</dt><dd>{{ order.installation_required ? tx("需要", "Required") : tx("不需要", "Not required") }}</dd>
          <template v-if="order.site_address"><dt>{{ tx("施工地址", "Site address") }}</dt><dd>{{ order.site_address }}</dd></template>
          <dt>{{ tx("订单总额", "Order total") }}</dt><dd>{{ order.total ? `${order.currency || "NZD"} ${order.total}` : tx("待定价", "To be confirmed") }}</dd>
        </dl>
      </section>

      <section v-if="order.lines?.length" class="panel">
        <div class="section-heading"><h2>{{ tx("窗户明细", "Window details") }}</h2><span>{{ order.lines.length }} {{ tx("行", "lines") }}</span></div>
        <div class="line-table-wrap" tabindex="0" :aria-label="tx('窗户明细表，可横向滚动','Window detail table, scroll horizontally')">
          <table class="line-table">
            <thead><tr><th>#</th><th>{{ tx("位置 / 名称", "Location / name") }}</th><th>{{ tx("宽 (mm)", "Width (mm)") }}</th><th>{{ tx("高 (mm)", "Height (mm)") }}</th><th>{{ tx("产品系列", "Product series") }}</th><th>{{ tx("开合方式", "Opening style") }}</th><th>{{ tx("扇数", "Panels") }}</th><th>{{ tx("布局代码", "Layout code") }}</th><th>{{ tx("竖柱", "VT post") }}</th><th>{{ tx("横柱", "HT post") }}</th><th>{{ tx("中横档", "Midrail") }}</th><th>{{ tx("框型", "Frame") }}</th><th>{{ tx("叶片尺寸", "Louver size") }}</th><th>{{ tx("颜色", "Colour") }}</th><th>{{ tx("控制杆", "Control rod") }}</th><th>{{ tx("安装尺寸", "Fitting") }}</th><th>{{ tx("数量", "Quantity") }}</th><th>{{ tx("附加项 / 特殊要求", "Add-ons / special request") }}</th><th>{{ tx("金额", "Amount") }}</th></tr></thead>
            <tbody>
              <tr v-for="(line,index) in order.lines" :key="line.id || index">
                <td>{{ index+1 }}</td><td><strong>{{ line.window_name }}</strong></td><td>{{ line.width_mm }}</td><td>{{ line.height_mm }}</td><td>{{ line.product_name || line.source_code || "—" }}</td><td>{{ option(line,"opening_style") }}</td><td>{{ line.panel_count || 1 }}</td><td>{{ option(line,"layout_code") }}</td><td>{{ option(line,"vt_post") }}</td><td>{{ option(line,"ht_post") }}</td><td>{{ option(line,"midrail") }}</td><td>{{ option(line,"frame") }}</td><td>{{ option(line,"louver_size") }}</td><td>{{ option(line,"colour") }}</td><td>{{ option(line,"control_rod") }}</td><td>{{ option(line,"fitting") }}</td><td>{{ line.quantity }}</td>
                <td><div class="line-extras"><span v-for="fact in lineAddons(line)" :key="fact" class="extra-chip">{{ fact }}</span><span v-if="line.options?.special_request" class="special-request">{{ line.options.special_request }}</span><span v-if="!lineAddons(line).length && !line.options?.special_request">—</span></div></td>
                <td>{{ line.amount ? `${order.currency || "NZD"} ${line.amount}` : "—" }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section v-if="order.invoices?.length" class="panel">
        <h2>{{ tx("相关发票", "Related invoices") }}</h2>
        <ul class="invoice-links"><li v-for="invoice in order.invoices" :key="invoice.id"><strong>{{ invoice.invoice_number || invoice.kind }}</strong><span>{{ invoice.currency }} {{ invoice.amount }}</span></li></ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
.order-detail{max-width:1400px;margin:auto;color:var(--ink,#1b2421)}.page-heading,.section-heading{display:flex;align-items:center;justify-content:space-between;gap:16px}.page-heading{margin:4px 0 20px}.eyebrow{margin:0 0 5px;color:var(--cord);font-size:11px;font-weight:750;letter-spacing:.12em}.page-heading h1{margin:0;font:600 28px var(--font-display)}.order-number{margin:5px 0 0;color:#66746c;font-size:13px}.status-pill{padding:8px 13px;border-radius:999px;background:#e7f0eb;color:#17523a;font-size:13px;font-weight:700;white-space:nowrap}.panel{margin:0 0 16px;padding:20px;background:#fff;border:1px solid #dbe4dd;border-radius:8px}.panel h2{margin:0;font:600 18px var(--font-display)}.section-heading p{margin:6px 0 0;color:#62716b;font-size:13px}.lead-time{color:#62716b;font-size:12px;text-align:right}.status-flow{display:grid;grid-template-columns:repeat(7,minmax(90px,1fr));gap:8px;padding:0;margin:22px 0 0;list-style:none}.status-flow li{display:flex;align-items:flex-start;gap:7px;color:#6a776f;font-size:11px;line-height:1.35}.status-flow .dot{width:11px;height:11px;flex:none;border:2px solid #c8d3cb;border-radius:50%;background:#fff}.status-flow li.done,.status-flow li.current{color:#17523a;font-weight:650}.status-flow li.done .dot,.status-flow li.current .dot{border-color:var(--cord,#0f6e5c);background:var(--cord,#0f6e5c)}.facts{display:grid;grid-template-columns:180px minmax(0,1fr);gap:10px 16px;margin:16px 0 0}.facts dt{color:#64736b;font-size:13px;font-weight:650}.facts dd{margin:0;overflow-wrap:anywhere;font-size:14px}.line-table-wrap{overflow:auto;margin-top:14px;border:1px solid #dbe4dd;border-radius:6px}.line-table{width:100%;min-width:2020px;border-collapse:collapse;font-size:12px}.line-table th,.line-table td{padding:10px 9px;border-bottom:1px solid #e5ebe6;text-align:left;vertical-align:top}.line-table th{position:sticky;top:0;background:#edf2ee;color:#33473c;font-size:11px;white-space:nowrap}.line-table tr:last-child td{border-bottom:0}.line-extras{display:flex;flex-wrap:wrap;gap:4px}.extra-chip{padding:3px 7px;border-radius:999px;background:#e8f1eb;color:#2c5942}.special-request{display:block;width:100%;color:#58675f;white-space:pre-wrap}.invoice-links{display:grid;gap:8px;margin:14px 0 0;padding:0;list-style:none}.invoice-links li{display:flex;justify-content:space-between;gap:12px;padding:11px;background:#f5f7f5;border-radius:5px}.notice{padding:40px;text-align:center;color:#617068}.notice.error{color:#8f3425;background:#fff0ed;border-radius:6px}@media(max-width:760px){.page-heading{align-items:flex-start}.page-heading h1{font-size:23px}.panel{padding:14px}.status-flow{grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.facts{grid-template-columns:1fr;gap:4px}.facts dd{margin-bottom:9px}.section-heading{align-items:flex-start;flex-direction:column}.lead-time{text-align:left}}
</style>

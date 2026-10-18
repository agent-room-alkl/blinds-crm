<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { portalRequest } from "../../portal-api";

const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);

const consumption = ref<any>(null);
const loading = ref(true);

onMounted(async () => {
  try {
    consumption.value = await portalRequest<any>("consumption");
  } catch {
    // error
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="invoices-page">
    <h1>{{ tx("发票与付款", "Invoices & Payments") }}</h1>
    
    <div v-if="loading" class="loading">{{ tx("加载中...", "Loading...") }}</div>
    
    <div v-else-if="consumption">
      <div v-if="consumption.invoices && consumption.invoices.length" class="invoices-list">
        <div v-for="invoice in consumption.invoices" :key="invoice.id" class="invoice-card">
          <div class="invoice-header">
            <strong>{{ invoice.kind }}</strong>
            <span class="invoice-status">{{ invoice.status }}</span>
          </div>
          <div class="invoice-details">
            <p><strong>{{ tx("金额", "Amount") }}:</strong> {{ invoice.currency }} {{ invoice.amount }}</p>
            <p><strong>{{ tx("收款状态", "Payment") }}:</strong> {{ invoice.payment_status === "received" ? tx("已收", "Received") : tx("未确认", "Pending") }}</p>
          </div>
        </div>
      </div>
      <div v-else class="empty">{{ tx("还没有发票", "No invoices yet") }}</div>

      <div v-if="consumption.rebates && consumption.rebates.length" class="rebates-section">
        <h2>{{ tx("返利", "Rebates") }}</h2>
        <div class="rebates-list">
          <div v-for="rebate in consumption.rebates" :key="rebate.id" class="rebate-card">
            <strong>{{ rebate.month || rebate.id }}</strong>
            <p>{{ rebate.currency }} {{ rebate.amount }}</p>
            <p><small>{{ tx("已用", "Used") }}: {{ rebate.used || "0.00" }} · {{ tx("余额", "Remaining") }}: {{ rebate.remaining || "0.00" }}</small></p>
          </div>
        </div>
      </div>
    </div>
    
    <div v-else class="empty">{{ tx("暂无数据", "No data available") }}</div>
  </div>
</template>

<style scoped>
.invoices-page {
  max-width: 1200px;
}

.invoices-page h1 {
  font-family: var(--font-display);
  font-size: 32px;
  font-weight: 600;
  margin: 0 0 32px;
}

.invoices-page h2 {
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 600;
  margin: 40px 0 20px;
}

.loading,
.empty {
  text-align: center;
  padding: 60px 20px;
  font-size: 16px;
  color: rgba(27, 36, 33, 0.6);
}

.invoices-list,
.rebates-list {
  display: grid;
  gap: 16px;
}

.invoice-card,
.rebate-card {
  padding: 20px 24px;
  background: white;
  border: 1px solid var(--line);
  border-radius: 8px;
}

.invoice-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--line);
}

.invoice-header strong {
  font-size: 18px;
  color: var(--ink);
}

.invoice-status {
  font-size: 13px;
  font-weight: 600;
  padding: 4px 12px;
  background: rgba(15, 110, 92, 0.1);
  color: var(--cord);
  border-radius: 12px;
}

.invoice-details p {
  margin: 8px 0;
  font-size: 15px;
  line-height: 1.6;
}

.rebate-card strong {
  display: block;
  font-size: 16px;
  margin-bottom: 8px;
  color: var(--cord);
}

.rebate-card p {
  margin: 4px 0;
  font-size: 14px;
}
</style>

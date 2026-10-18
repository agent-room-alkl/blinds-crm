<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import { portalRequest } from "../../portal-api";

const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);
const route = useRoute();

const order = ref<any>(null);
const loading = ref(true);

const STATUS_TIMELINE = [
  { key: 'draft', label_zh: '草稿', label_en: 'Draft' },
  { key: 'pending_review', label_zh: '已提交待审核', label_en: 'Submitted' },
  { key: 'confirmed', label_zh: '已审核并冻结', label_en: 'Confirmed' },
  { key: 'deposit_invoiced', label_zh: '定金发票已开', label_en: '60% Deposit Invoiced' },
  { key: 'deposit_paid', label_zh: '定金已付', label_en: 'Deposit Paid' },
  { key: 'ordered', label_zh: '已向供应商下单', label_en: 'Ordered' },
  { key: 'in_transit', label_zh: '运输中', label_en: 'In Transit' },
  { key: 'delivered', label_zh: '已交付', label_en: 'Delivered' },
  { key: 'balance_invoiced', label_zh: '尾款发票已开', label_en: 'Balance Invoiced' },
  { key: 'paid', label_zh: '已结清', label_en: 'Paid in Full' },
];

const currentStatusIndex = computed(() => {
  if (!order.value) return -1;
  return STATUS_TIMELINE.findIndex(s => s.key === order.value.status);
});

onMounted(async () => {
  const orderId = route.params.id as string;
  try {
    const orders = await portalRequest<any[]>("orders");
    order.value = orders.find((o: any) => o.id === orderId) || orders[0];
  } catch {
    // error
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="order-detail">
    <div v-if="loading" class="loading">{{ tx("加载中...", "Loading...") }}</div>
    
    <div v-else-if="order" class="detail-content">
      <div class="detail-header">
        <h1>{{ order.project_name }}</h1>
        <span class="order-status">{{ order.status }}</span>
      </div>

      <div class="status-timeline">
        <h2>{{ tx("订单状态", "Order Status") }}</h2>
        <div class="timeline">
          <div
            v-for="(status, index) in STATUS_TIMELINE"
            :key="status.key"
            class="timeline-item"
            :class="{
              active: index === currentStatusIndex,
              completed: index < currentStatusIndex,
              pending: index > currentStatusIndex
            }"
          >
            <div class="timeline-marker"></div>
            <div class="timeline-content">
              <strong>{{ locale === "zh" ? status.label_zh : status.label_en }}</strong>
            </div>
          </div>
        </div>
      </div>

      <div class="detail-section">
        <h2>{{ tx("订单信息", "Order Information") }}</h2>
        <dl>
          <dt>{{ tx("订单号", "Order ID") }}</dt>
          <dd>{{ order.id }}</dd>
          <dt>{{ tx("施工地址", "Site Address") }}</dt>
          <dd>{{ order.site_address }}</dd>
          <dt>{{ tx("状态", "Status") }}</dt>
          <dd>{{ order.status }}</dd>
          <dt>{{ tx("付款状态", "Payment Status") }}</dt>
          <dd>{{ order.payment_status }}</dd>
          <dt>{{ tx("合计", "Total") }}</dt>
          <dd>{{ order.total ? `${order.currency || ""} ${order.total}` : tx("待定价", "TBC") }}</dd>
        </dl>
      </div>

      <div v-if="order.lines && order.lines.length" class="detail-section">
        <h2>{{ tx("窗户明细", "Window Details") }}</h2>
        <div class="lines-list">
          <div v-for="line in order.lines" :key="line.id" class="line-item">
            <strong>{{ line.window_name }}</strong>
            <p>{{ line.amount ? `${order.currency || ""} ${line.amount}` : tx("待定价", "TBC") }}</p>
          </div>
        </div>
      </div>

      <div v-if="order.invoices && order.invoices.length" class="detail-section">
        <h2>{{ tx("相关发票", "Related Invoices") }}</h2>
        <div class="invoices-list">
          <div v-for="invoice in order.invoices" :key="invoice.id" class="invoice-item">
            <strong>{{ invoice.kind }}</strong>
            <span>{{ invoice.currency }} {{ invoice.amount }}</span>
            <span>{{ invoice.status }}</span>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="empty">{{ tx("订单未找到", "Order not found") }}</div>
  </div>
</template>

<style scoped>
.order-detail {
  max-width: 1200px;
}

.loading,
.empty {
  text-align: center;
  padding: 60px 20px;
  font-size: 16px;
  color: rgba(27, 36, 33, 0.6);
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--line);
}

.detail-header h1 {
  font-family: var(--font-display);
  font-size: 32px;
  font-weight: 600;
  margin: 0;
}

.order-status {
  font-size: 14px;
  font-weight: 600;
  padding: 6px 16px;
  background: rgba(15, 110, 92, 0.1);
  color: var(--cord);
  border-radius: 12px;
}

.status-timeline {
  margin-bottom: 40px;
  padding: 24px;
  background: white;
  border: 1px solid var(--line);
  border-radius: 8px;
}

.status-timeline h2 {
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 600;
  margin: 0 0 24px;
}

.timeline {
  position: relative;
}

.timeline::before {
  content: '';
  position: absolute;
  left: 15px;
  top: 0;
  bottom: 0;
  width: 2px;
  background: var(--line);
}

.timeline-item {
  position: relative;
  padding-left: 48px;
  padding-bottom: 24px;
}

.timeline-item:last-child {
  padding-bottom: 0;
}

.timeline-marker {
  position: absolute;
  left: 8px;
  top: 4px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: rgba(27, 36, 33, 0.2);
  border: 2px solid white;
  box-shadow: 0 0 0 2px var(--line);
}

.timeline-item.completed .timeline-marker {
  background: var(--cord);
  box-shadow: 0 0 0 2px var(--cord);
}

.timeline-item.active .timeline-marker {
  background: var(--cord);
  box-shadow: 0 0 0 2px var(--cord), 0 0 0 4px rgba(15, 110, 92, 0.2);
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.1); }
}

.timeline-content strong {
  font-size: 15px;
  color: rgba(27, 36, 33, 0.88);
}

.timeline-item.completed .timeline-content strong {
  color: var(--cord);
}

.detail-section {
  margin-bottom: 32px;
  padding: 24px;
  background: white;
  border: 1px solid var(--line);
  border-radius: 8px;
}

.detail-section h2 {
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 600;
  margin: 0 0 20px;
}

.detail-section dl {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 16px;
  margin: 0;
}

.detail-section dt {
  font-weight: 600;
  font-size: 14px;
  color: rgba(27, 36, 33, 0.6);
}

.detail-section dd {
  margin: 0;
  font-size: 15px;
  color: var(--ink);
}

.lines-list,
.invoices-list {
  display: grid;
  gap: 12px;
}

.line-item,
.invoice-item {
  padding: 16px;
  background: rgba(15, 110, 92, 0.04);
  border-radius: 4px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.line-item strong,
.invoice-item strong {
  font-size: 15px;
  color: var(--ink);
}

@media (max-width: 700px) {
  .detail-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .detail-section dl {
    grid-template-columns: 1fr;
    gap: 8px;
  }

  .detail-section dd {
    margin-bottom: 16px;
  }
}
</style>

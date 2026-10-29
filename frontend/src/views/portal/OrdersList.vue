<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { formatDate, leadTimeLabel, normalizeStatus, paymentLabel, statusLabel } from "../../orderStatus";
import { portalRequest } from "../../portal-api";

const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);
const router = useRouter();

const orders = ref<any[]>([]);
const loading = ref(true);

onMounted(async () => {
  try {
    orders.value = await portalRequest<any[]>("orders");
  } catch {
    // handle error
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
      <h1>{{ tx("我的订单", "My Orders") }}</h1>
      <button type="button" class="primary" @click="startNewOrder">
        {{ tx("+ 新订单", "+ New Order") }}
      </button>
    </div>

    <div v-if="loading" class="loading">{{ tx("加载中...", "Loading...") }}</div>

    <div v-else-if="orders.length === 0" class="empty-state">
      <p>{{ tx("还没有订单", "No orders yet") }}</p>
      <button type="button" class="primary" @click="startNewOrder">
        {{ tx("开始第一个订单", "Start First Order") }}
      </button>
    </div>

    <div v-else class="orders-grid">
      <div
        v-for="order in orders"
        :key="order.id"
        class="order-card"
        @click="viewOrder(order.id)"
      >
        <div class="order-header">
          <strong>{{ order.project_name }}</strong>
          <span class="order-status" :class="`status-${normalizeStatus(order.status)}`">{{ statusLabel(order, locale) }}</span>
        </div>
        <p>{{ tx('订单号', 'Order no.') }} {{ order.order_number || (order.order_number_confirmed === false ? tx('待管理员确认', 'Pending admin confirmation') : '—') }}</p>
        <p v-if="order.eta && !['ready', 'complete'].includes(normalizeStatus(order.status))" class="order-eta">{{ tx('预计到货', 'Estimated arrival') }} <strong>{{ formatDate(order.eta, locale) }}</strong><span v-if="order.batch_name"> · {{ order.batch_name }}</span></p>
        <p v-else-if="normalizeStatus(order.status) === 'ready'" class="order-eta ready">{{ tx('已到货，可以提取', 'Arrived. Ready for collection') }}<span v-if="order.batch_name"> · {{ order.batch_name }}</span></p>
        <p v-else-if="leadTimeLabel(order.lead_time, locale) && normalizeStatus(order.status) !== 'complete'">{{ tx('预计交期', 'Lead time') }} {{ leadTimeLabel(order.lead_time, locale) }}</p>
        <p class="order-address">{{ order.site_address }}</p>
        <div class="order-footer">
          <span>{{ order.total ? `${order.currency || ""} ${order.total}` : tx("待定价", "TBC") }}</span>
          <span class="order-payment" :class="`pay-${order.payment_status}`">{{ paymentLabel(order.payment_status, locale) }}</span>
        </div>
      </div>
    </div>
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
  margin-bottom: 32px;
}

.page-header h1 {
  font-family: var(--font-display);
  font-size: 32px;
  font-weight: 600;
  margin: 0;
  letter-spacing: 0.01em;
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

.orders-grid {
  display: grid;
  gap: 16px;
}

.order-card {
  padding: 20px 24px;
  background: white;
  border: 1px solid var(--line);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.order-card:hover {
  border-color: var(--cord);
  box-shadow: 0 2px 8px rgba(15, 110, 92, 0.1);
  transform: translateY(-1px);
}

.order-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.order-header strong {
  font-size: 18px;
  color: var(--ink);
}

.order-status {
  font-size: 13px;
  font-weight: 600;
  padding: 4px 12px;
  background: rgba(15, 110, 92, 0.1);
  color: var(--cord);
  border-radius: 12px;
}

.order-address {
  font-size: 14px;
  color: rgba(27, 36, 33, 0.6);
  margin: 0 0 12px;
}

.order-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 12px;
  border-top: 1px solid var(--line);
  font-size: 15px;
}

.order-payment {
  font-size: 13px;
  color: rgba(27, 36, 33, 0.6);
  text-align: right;
}

.order-payment.pay-paid { color: #17523a; font-weight: 600; }

.order-status.status-ready { background: #0f6e5c; color: #fff; }
.order-status.status-complete { background: #e8e8e4; color: #4b5650; }
.order-status.status-in_transit { background: #e6eef7; color: #24527a; }

.order-eta { color: #34503f; }
.order-eta.ready { color: #17523a; font-weight: 600; }

@media (max-width: 700px) {
  .page-header {
    flex-direction: column;
    align-items: stretch;
    gap: 16px;
  }

  .page-header button {
    width: 100%;
  }
}
</style>

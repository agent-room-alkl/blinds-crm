<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";

const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);

const props = defineProps<{
  draft: any;
  catalog: any[];
  saving: boolean;
  error: string;
}>();

const emit = defineEmits<{
  (e: "submit"): void;
  (e: "prev"): void;
}>();

const allConfigured = computed(() => {
  return props.draft.windows.every((w: any) => w.configured);
});

const canSubmit = computed(() => {
  return (
    props.draft.project_name.trim() &&
    props.draft.site_address.trim() &&
    props.draft.windows.length > 0 &&
    allConfigured.value &&
    !props.saving
  );
});

const missingItems = computed(() => {
  const items: string[] = [];
  if (!props.draft.project_name.trim()) items.push(tx("订单名称", "Order name"));
  if (!props.draft.site_address.trim()) items.push(tx("施工地址", "Site address"));
  if (props.draft.windows.length === 0) items.push(tx("至少一扇窗", "At least one window"));
  const unconfigured = props.draft.windows.filter((w: any) => !w.configured).length;
  if (unconfigured > 0) items.push(tx(`${unconfigured} 扇窗未配置`, `${unconfigured} windows not configured`));
  return items;
});

function getProductName(productId: number) {
  const product = props.catalog.find((p) => p.id === productId);
  if (!product) return "";
  return locale.value === "zh" ? product.name_zh : product.name_en;
}
</script>

<template>
  <div class="review-step">
    <div class="step-intro">
      <p class="section-label">{{ tx("步骤 4 · 核对并提交", "STEP 4 · REVIEW & SUBMIT") }}</p>
      <h2>{{ tx("核对订单", "Review Order") }}</h2>
      <p>{{ tx("请仔细核对所有信息。提交后订单将进入待审核状态。", "Please review all information carefully. After submission, the order will enter review status.") }}</p>
    </div>

    <div class="review-sections">
      <div class="review-card">
        <h3>{{ tx("订单信息", "Order Information") }}</h3>
        <dl>
          <dt>{{ tx("订单名称", "Order Name") }}</dt>
          <dd><input v-model="draft.project_name" :aria-label="tx('订单名称', 'Order Name')" required /></dd>
          <dt>{{ tx("施工地址", "Site Address") }}</dt>
          <dd><input v-model="draft.site_address" :aria-label="tx('施工地址', 'Site Address')" required /></dd>
          <dt>{{ tx("需要安装", "Installation Required") }}</dt>
          <dd>{{ draft.installation_required ? tx("是", "Yes") : tx("否", "No") }}</dd>
        </dl>
      </div>

      <div class="review-card">
        <h3>{{ tx("窗户明细", "Window Details") }}</h3>
        <div class="window-summary">
          <div v-for="(window, index) in draft.windows" :key="window.id" class="window-item">
            <strong>{{ index + 1 }}. {{ window.window_name }}</strong>
            <p>{{ getProductName(window.product_id) }}</p>
            <p>{{ window.width_mm }} × {{ window.height_mm }} mm · {{ tx("数量", "Qty") }} {{ window.quantity }} · {{ window.panel_count }} {{ tx("扇", "panels") }}</p>
            <p v-if="window.options.colour"><strong>{{ tx("颜色", "Colour") }}:</strong> {{ window.options.colour }}</p>
            <p v-if="window.options.louver_size"><strong>{{ tx("叶片", "Louver") }}:</strong> {{ window.options.louver_size }}</p>
          </div>
        </div>
      </div>

      <div class="review-card">
        <h3>{{ tx("提交确认", "Submission Confirmation") }}</h3>
        <p class="terms-text">
          {{ tx(
            "我已核对尺寸，提交后由 VERA 审核并开 60% 定金发票。",
            "I have verified the dimensions. After submission, VERA will review and issue a 60% deposit invoice."
          ) }}
        </p>
      </div>
    </div>

    <div v-if="!canSubmit" class="validation-alert">
      <p><strong>{{ tx("提交前请完成以下项目：", "Complete the following before submission:") }}</strong></p>
      <ul>
        <li v-for="(item, i) in missingItems" :key="i">{{ item }}</li>
      </ul>
    </div>

    <p v-if="error" class="alert" role="alert">{{ error }}</p>

    <div class="step-actions">
      <button type="button" class="secondary" @click="emit('prev')">
        {{ tx("上一步", "Previous") }}
      </button>
      <button type="button" class="primary" :disabled="!canSubmit" @click="emit('submit')">
        {{ saving ? tx("提交中...", "Submitting...") : tx("提交待审核", "Submit for Review") }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.review-step {
  padding: 24px 0;
}

.step-intro {
  margin-bottom: 32px;
}

.step-intro h2 {
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 600;
  margin: 12px 0 16px;
  letter-spacing: 0.01em;
}

.step-intro p {
  font-size: 15px;
  line-height: 1.65;
  color: rgba(27, 36, 33, 0.72);
  max-width: 72ch;
}

.section-label {
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--cord);
  font-weight: 600;
  margin-bottom: 8px;
  display: block;
}

.review-sections {
  display: grid;
  gap: 24px;
  margin-bottom: 32px;
}

.review-card {
  padding: 24px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: white;
}

.review-card h3 {
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 600;
  margin: 0 0 16px;
  letter-spacing: 0.01em;
}

.review-card dl {
  display: grid;
  gap: 12px;
}

.review-card dt {
  font-size: 13px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: rgba(27, 36, 33, 0.6);
  margin: 0;
}

.review-card dd {
  font-size: 15px;
  color: var(--ink);
  margin: 0 0 8px 0;
}

.window-summary {
  display: grid;
  gap: 16px;
}

.window-item {
  padding: 16px;
  background: rgba(15, 110, 92, 0.04);
  border-radius: 4px;
}

.window-item strong {
  display: block;
  font-size: 15px;
  margin-bottom: 8px;
  color: var(--cord);
}

.window-item p {
  margin: 4px 0;
  font-size: 14px;
  line-height: 1.6;
  color: rgba(27, 36, 33, 0.72);
}

.terms-text {
  font-size: 15px;
  line-height: 1.7;
  color: rgba(27, 36, 33, 0.72);
  padding: 16px;
  background: rgba(15, 110, 92, 0.04);
  border-radius: 4px;
  margin: 0;
}

.validation-alert {
  padding: 16px 20px;
  background: rgba(245, 158, 11, 0.1);
  border-left: 4px solid #f59e0b;
  border-radius: 4px;
  margin-bottom: 24px;
}

.validation-alert p {
  margin: 0 0 12px;
  font-size: 15px;
  color: rgba(27, 36, 33, 0.88);
}

.validation-alert ul {
  margin: 0;
  padding-left: 20px;
  list-style: disc;
}

.validation-alert li {
  margin: 4px 0;
  font-size: 14px;
  color: rgba(27, 36, 33, 0.72);
}

.alert {
  color: var(--danger);
  background: rgba(140, 47, 47, 0.08);
  padding: 14px 16px;
  border-radius: 4px;
  margin-bottom: 16px;
  border-left: 4px solid var(--danger);
}

.step-actions {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding-top: 24px;
  border-top: 1px solid var(--line);
}

button.primary,
button.secondary {
  min-height: 48px;
  padding: 12px 32px;
  border-radius: 4px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  letter-spacing: 0.02em;
  border: none;
}

button.primary {
  background: var(--cord);
  color: white;
}

button.primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

button.primary:hover:not(:disabled) {
  background: #0c7a67;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(15, 110, 92, 0.3);
}

button.secondary {
  background: transparent;
  color: var(--ink);
  border: 1px solid rgba(27, 36, 33, 0.4);
  min-height: 44px;
}

button.secondary:hover {
  background: rgba(27, 36, 33, 0.04);
  border-color: var(--cord);
}

@media (max-width: 700px) {
  .step-actions {
    flex-direction: column;
  }

  .step-actions button {
    width: 100%;
  }
}
</style>

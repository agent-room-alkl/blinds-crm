<script setup lang="ts">
import { computed, reactive, ref, watch, onMounted } from "vue";
import { useRouter, useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import { portalRequest, portalSession } from "../../portal-api";
import SeriesCards from "./wizard/SeriesCards.vue";
import WindowList from "./wizard/WindowList.vue";
import WindowConfig from "./wizard/WindowConfig.vue";
import OrderReview from "./wizard/OrderReview.vue";

const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);
const router = useRouter();
const route = useRoute();

const step = ref(1);
const saving = ref(false);
const error = ref("");
const catalog = ref<any[]>([]);
const lastSaved = ref<string | null>(null);

interface WindowDraft {
  id: string;
  window_name: string;
  product_id: number | "";
  width_mm: string;
  height_mm: string;
  quantity: number;
  panel_count: number;
  options: Record<string, string>;
  configured: boolean;
}

const draft = reactive({
  project_name: "",
  site_address: "",
  installation_required: false,
  default_series: null as number | null,
  windows: [] as WindowDraft[],
});

const STEPS = [
  { num: 1, label_zh: "选系列", label_en: "Series" },
  { num: 2, label_zh: "窗户列表", label_en: "Windows" },
  { num: 3, label_zh: "尺寸与配置", label_en: "Size & Config" },
  { num: 4, label_zh: "核对并提交", label_en: "Review" },
];

async function loadCatalog() {
  try {
    const result = await portalRequest<{ products: any[] }>("catalog");
    catalog.value = result.products;
    // Load draft from localStorage
    const saved = localStorage.getItem("vera-order-draft");
    if (saved) {
      const parsed = JSON.parse(saved);
      Object.assign(draft, parsed);
      lastSaved.value = new Date(parsed.saved_at || Date.now()).toLocaleTimeString();
    }
    // Sync step from URL query param
    const urlStep = parseInt(String(route.query.step || "1"));
    if (urlStep >= 1 && urlStep <= 4) {
      step.value = urlStep;
    }
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  }
}

// Watch route changes to update step
watch(() => route.query.step, (newStep) => {
  const num = parseInt(String(newStep || "1"));
  if (num >= 1 && num <= 4) {
    step.value = num;
  }
});

// Watch step changes to update URL
watch(step, (newStep) => {
  if (parseInt(String(route.query.step || "1")) !== newStep) {
    router.replace({ query: { ...route.query, step: String(newStep) } });
  }
});

function saveDraft() {
  const data = { ...draft, saved_at: Date.now() };
  localStorage.setItem("vera-order-draft", JSON.stringify(data));
  lastSaved.value = new Date().toLocaleTimeString();
}

watch(draft, () => {
  saveDraft();
}, { deep: true });

function goToStep(num: number) {
  if (num <= step.value || canProgress(num - 1)) {
    router.push({ query: { step: String(num) } });
  }
}

function canProgress(fromStep: number): boolean {
  if (fromStep === 1) return draft.default_series !== null;
  if (fromStep === 2) return draft.windows.length > 0;
  if (fromStep === 3) return draft.windows.every((w) => w.configured);
  return false;
}

function nextStep() {
  if (step.value < 4 && canProgress(step.value)) {
    router.push({ query: { step: String(step.value + 1) } });
  }
}

function prevStep() {
  if (step.value > 1) {
    router.push({ query: { step: String(step.value - 1) } });
  }
}

async function submitOrder() {
  saving.value = true;
  error.value = "";
  try {
    const payload = {
      project_name: draft.project_name.trim(),
      site_address: draft.site_address.trim(),
      installation_required: draft.installation_required,
      submission_key: crypto.randomUUID(),
      lines: draft.windows.map((w) => ({
        window_name: w.window_name.trim(),
        product_id: Number(w.product_id),
        width_mm: w.width_mm,
        height_mm: w.height_mm,
        quantity: w.quantity,
        panel_count: w.panel_count,
        options: w.options,
      })),
    };
    const saved = await portalRequest<any>("orders", payload);
    localStorage.removeItem("vera-order-draft");
    router.push(`/portal/orders/${saved.id}`);
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    saving.value = false;
  }
}

if (portalSession.token) {
  loadCatalog();
} else {
  router.push("/portal");
}
</script>

<template>
  <div class="wizard">
    <div class="wizard-header">
      <div class="wizard-steps">
        <button
          v-for="s in STEPS"
          :key="s.num"
          type="button"
          class="step-btn"
          :class="{ active: step === s.num, done: step > s.num }"
          :disabled="s.num > step && !canProgress(s.num - 1)"
          @click="goToStep(s.num)"
        >
          <span class="step-num">{{ s.num }}</span>
          <span class="step-label">{{ locale === "zh" ? s.label_zh : s.label_en }}</span>
        </button>
      </div>
      <p v-if="lastSaved" class="save-indicator">{{ tx("已保存", "Saved") }} {{ lastSaved }}</p>
    </div>

    <div class="wizard-body">
      <SeriesCards v-if="step === 1" v-model="draft.default_series" :catalog="catalog" @next="nextStep" />
      <WindowList v-else-if="step === 2" v-model="draft.windows" :catalog="catalog" :default-series="draft.default_series" @next="nextStep" @prev="prevStep" />
      <WindowConfig v-else-if="step === 3" v-model="draft.windows" :catalog="catalog" @next="nextStep" @prev="prevStep" />
      <OrderReview
        v-else-if="step === 4"
        :draft="draft"
        :catalog="catalog"
        :saving="saving"
        :error="error"
        @submit="submitOrder"
        @prev="prevStep"
      />
    </div>
  </div>
</template>

<style scoped>
.wizard {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px 16px 80px;
}

.wizard-header {
  margin-bottom: 32px;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--line);
}

.wizard-steps {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}

.step-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: white;
  cursor: pointer;
  transition: all 0.2s;
  min-height: 44px;
}

.step-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.step-btn.active {
  border-color: var(--cord);
  background: rgba(15, 110, 92, 0.06);
}

.step-btn.done .step-num {
  background: var(--cord);
  color: white;
}

.step-num {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: rgba(27, 36, 33, 0.1);
  font-weight: 600;
  font-size: 14px;
}

.step-label {
  font-size: 15px;
  font-weight: 500;
}

.save-indicator {
  font-size: 13px;
  color: rgba(27, 36, 33, 0.6);
}

@media (max-width: 700px) {
  .wizard-steps {
    flex-direction: column;
  }

  .step-btn {
    width: 100%;
  }
}
</style>

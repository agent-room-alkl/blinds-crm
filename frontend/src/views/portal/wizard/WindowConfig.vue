<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { portalRequest } from "../../../portal-api";

const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);

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

const props = defineProps<{
  modelValue: WindowDraft[];
  catalog: any[];
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: WindowDraft[]): void;
  (e: "next"): void;
  (e: "prev"): void;
}>();

const currentIndex = ref(0);
const pricing = ref(false);
const priceData = ref<any>(null);
const priceError = ref("");

const currentWindow = computed(() => props.modelValue[currentIndex.value]);
const currentProduct = computed(() => {
  if (!currentWindow.value) return null;
  return props.catalog.find((p) => p.id === currentWindow.value.product_id);
});

// Color mapping from spec
const COLOR_MAP: Record<string, string[]> = {
  Shutters_PVC_Eco: ["White 01"],
  Shutters_PVC: ["White 01", "Dusk 02", "Soft Glow 03", "Old Moon 04", "Oyster 05", "Sea Pearl 06", "Picaso 07", "Chalk 08"],
  Shutters_Pinewood: ["White 01", "Dusk 02", "Soft Glow 03", "Old Moon 04", "Oyster 05", "Sea Pearl 06", "Picaso 07", "Chalk 08"],
  Shutters_Basswood: [
    "White 01",
    "Dusk 02",
    "Soft Glow 03",
    "Old Moon 04",
    "Oyster 05",
    "Sea Pearl 06",
    "Picaso 07",
    "Chalk 08",
    "Golden Oak 61",
    "Fruitwood 62",
    "Old Mahogany 63",
    "Coffee Bean 64",
    "BlackWalnut 65",
    "Light Ash 66",
    "Limed 67",
    "Natural 68",
    "Rustic Gray 69",
    "Provence Blue 70",
  ],
  VERA_Ashwood_provisional: [
    "Golden Oak 61",
    "Fruitwood 62",
    "Old Mahogany 63",
    "Coffee Bean 64",
    "BlackWalnut 65",
    "Light Ash 66",
    "Limed 67",
    "Natural 68",
    "Rustic Gray 69",
    "Provence Blue 70",
  ],
  // Old demo DB code - same colors as provisional
  VERA_Ashwood_display: [
    "Golden Oak 61",
    "Fruitwood 62",
    "Old Mahogany 63",
    "Coffee Bean 64",
    "BlackWalnut 65",
    "Light Ash 66",
    "Limed 67",
    "Natural 68",
    "Rustic Gray 69",
    "Provence Blue 70",
  ],
};

const LOUVER_SIZES = ["63", "76", "89", "114"];

const availableColors = computed(() => {
  const sourceCode = currentProduct.value?.source_code;
  if (!sourceCode || !(sourceCode in COLOR_MAP)) return [];
  return COLOR_MAP[sourceCode];
});

function updateWindow(updates: Partial<WindowDraft>) {
  const updated = [...props.modelValue];
  updated[currentIndex.value] = { ...currentWindow.value, ...updates };
  emit("update:modelValue", updated);
}

function markConfigured() {
  if (!currentWindow.value) return;
  const w = currentWindow.value;
  const isValid = Boolean(
    w.window_name.trim() &&
    w.product_id &&
    Number(w.width_mm) > 0 &&
    Number(w.height_mm) > 0 &&
    w.quantity > 0 &&
    w.panel_count > 0 &&
    w.options.colour &&
    w.options.louver_size
  );

  updateWindow({ configured: isValid });
}

watch(currentWindow, markConfigured, { deep: true });

function nextWindow() {
  if (currentIndex.value < props.modelValue.length - 1) {
    currentIndex.value++;
  } else {
    emit("next");
  }
}

function prevWindow() {
  if (currentIndex.value > 0) {
    currentIndex.value--;
  } else {
    emit("prev");
  }
}

// Price calculation
let priceTicket = 0;
watch(
  currentWindow,
  async () => {
    if (!currentWindow.value || !currentWindow.value.configured) {
      priceData.value = null;
      return;
    }

    pricing.value = true;
    priceError.value = "";
    const ticket = ++priceTicket;

    try {
      const result = await portalRequest<any>("price", {
        project_name: "Preview",
        site_address: "Preview",
        submission_key: "preview",
        installation_required: false,
        lines: [
          {
            window_name: currentWindow.value.window_name,
            product_id: Number(currentWindow.value.product_id),
            width_mm: currentWindow.value.width_mm,
            height_mm: currentWindow.value.height_mm,
            quantity: currentWindow.value.quantity,
            panel_count: currentWindow.value.panel_count,
            options: currentWindow.value.options,
          },
        ],
      });
      if (ticket === priceTicket) {
        priceData.value = result;
      }
    } catch (cause) {
      if (ticket === priceTicket) {
        priceError.value = cause instanceof Error ? cause.message : String(cause);
        priceData.value = null;
      }
    } finally {
      if (ticket === priceTicket) {
        pricing.value = false;
      }
    }
  },
  { deep: true }
);
</script>

<template>
  <div class="window-config-step">
    <div class="step-intro">
      <p class="section-label">{{ tx("步骤 3 · 尺寸与配置", "STEP 3 · SIZE & CONFIG") }}</p>
      <h2>
        {{ tx("窗户", "Window") }} {{ currentIndex + 1 }} / {{ modelValue.length }}
      </h2>
    </div>

    <div v-if="currentWindow" class="config-layout">
      <div class="config-form">
        <div class="form-group">
          <h3>{{ tx("基本信息", "Basic") }}</h3>
          <label>
            {{ tx("窗户名称", "Window Name") }} *
            <input v-model="currentWindow.window_name" type="text" required />
          </label>
          <label>
            {{ tx("系列", "Series") }}
            <select v-model="currentWindow.product_id" required>
              <option v-for="p in catalog" :key="p.id" :value="p.id">
                {{ locale === "zh" ? p.name_zh : p.name_en }}
              </option>
            </select>
          </label>
          <div class="row">
            <label>
              <span class="price-indicator">$ {{ tx("影响价格", "Affects Price") }}</span>
              {{ tx("宽（毫米）", "Width (mm)") }} *
              <input v-model="currentWindow.width_mm" type="number" inputmode="decimal" min="1" required />
            </label>
            <label>
              <span class="price-indicator">$ {{ tx("影响价格", "Affects Price") }}</span>
              {{ tx("高（毫米）", "Height (mm)") }} *
              <input v-model="currentWindow.height_mm" type="number" inputmode="decimal" min="1" required />
            </label>
          </div>
          <div class="row">
            <label>
              {{ tx("数量", "Quantity") }} *
              <input v-model.number="currentWindow.quantity" type="number" min="1" required />
            </label>
            <label>
              {{ tx("扇数", "Panels") }} *
              <input v-model.number="currentWindow.panel_count" type="number" min="1" required />
            </label>
          </div>
        </div>

        <div class="form-group">
          <h3>{{ tx("外观", "Appearance") }}</h3>
          <label>
            {{ tx("颜色", "Colour") }} *
            <div class="color-grid">
              <button
                v-for="color in availableColors"
                :key="color"
                type="button"
                class="color-btn"
                :class="{ selected: currentWindow.options.colour === color }"
                @click="updateWindow({ options: { ...currentWindow.options, colour: color } })"
              >
                {{ color }}
              </button>
            </div>
          </label>
          <label>
            {{ tx("叶片尺寸 (mm)", "Louver Size (mm)") }} *
            <div class="louver-grid">
              <button
                v-for="size in LOUVER_SIZES"
                :key="size"
                type="button"
                class="louver-btn"
                :class="{ selected: currentWindow.options.louver_size === size }"
                @click="updateWindow({ options: { ...currentWindow.options, louver_size: size } })"
              >
                {{ size }}mm
              </button>
            </div>
          </label>
        </div>

        <div class="form-group">
          <h3>{{ tx("结构（不影响价格）", "Structure (no price impact)") }}</h3>
          <label>
            {{ tx("框型", "Frame Type") }}
            <input v-model="currentWindow.options.frame_type" type="text" :placeholder="tx('如：L/Z', 'e.g. L/Z')" />
          </label>
          <label>
            {{ tx("控制杆", "Control Rod") }}
            <input v-model="currentWindow.options.control_rod" type="text" />
          </label>
          <label>
            {{ tx("开启方式", "Opening Style") }}
            <input v-model="currentWindow.options.opening_style" type="text" :placeholder="tx('如：Hinged', 'e.g. Hinged')" />
          </label>
        </div>

        <div class="form-group">
          <h3>{{ tx("安装", "Installation") }}</h3>
          <label>
            {{ tx("安装方式", "Install Method") }}
            <select v-model="currentWindow.options.install_method">
              <option value="">{{ tx("选择", "Choose") }}</option>
              <option value="In Fit">In Fit</option>
              <option value="Out Fit">Out Fit</option>
              <option value="Make Size">Make Size</option>
            </select>
          </label>
        </div>
      </div>

      <div class="price-panel">
        <p class="section-label">{{ tx("价格预览", "PRICE PREVIEW") }}</p>
        <div v-if="pricing" class="price-loading">{{ tx("计算中...", "Calculating...") }}</div>
        <div v-else-if="priceError" class="price-error">
          <p>{{ tx("暂时无法计算价格", "Unable to calculate price") }}</p>
          <small>{{ priceError }}</small>
        </div>
        <div v-else-if="priceData && priceData.lines && priceData.lines[0]" class="price-display">
          <strong v-if="priceData.lines[0].amount && Number(priceData.lines[0].amount) > 0" class="price-amount">
            {{ priceData.currency }} {{ priceData.lines[0].amount }}
          </strong>
          <div v-else class="price-error">
            <p>{{ tx("价格计算错误", "Price calculation error") }}</p>
            <small>{{ tx("价格为 0 可能表示配置超出范围或数据错误", "A price of 0 may indicate configuration out of range or data error") }}</small>
          </div>
          <ul class="price-details">
            <li v-if="priceData.lines[0].pricing_status">{{ priceData.lines[0].pricing_status }}</li>
            <li v-if="priceData.subtotal">{{ tx("小计", "Subtotal") }}: {{ priceData.currency }} {{ priceData.subtotal }}</li>
            <li v-if="priceData.tax">GST: {{ priceData.currency }} {{ priceData.tax }}</li>
          </ul>
          <p class="price-note">{{ tx("仅此窗预览，最终价格在提交时计算。配置选项（颜色、框型、叶片等）不影响价格。", "Preview for this window only. Final price calculated on submission. Configuration options (colour, frame, louver, etc.) do not affect price.") }}</p>
        </div>
        <div v-else class="price-incomplete">
          <p>{{ tx("待完整配置", "Incomplete configuration") }}</p>
        </div>
      </div>
    </div>

    <div class="step-actions">
      <button type="button" class="secondary" @click="prevWindow">
        {{ currentIndex === 0 ? tx("上一步", "Previous") : tx("上一扇", "Previous Window") }}
      </button>
      <button type="button" class="primary" @click="nextWindow">
        {{ currentIndex === modelValue.length - 1 ? tx("完成，下一步", "Done, Next") : tx("保存并下一扇", "Save & Next") }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.window-config-step {
  padding: 24px 0;
}

.step-intro {
  margin-bottom: 32px;
}

.step-intro h2 {
  font-family: var(--font-display);
  font-size: 28px;
  font-weight: 600;
  margin: 12px 0 16px;
  letter-spacing: 0.01em;
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

.config-layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: 24px;
  margin-bottom: 32px;
}

.config-form {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.form-group {
  padding: 24px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: white;
}

.form-group h3 {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 16px;
  letter-spacing: 0.01em;
}

.form-group label {
  display: grid;
  gap: 8px;
  margin-bottom: 16px;
  font-size: 14px;
  font-weight: 500;
  color: rgba(27, 36, 33, 0.88);
}

.form-group label:last-child {
  margin-bottom: 0;
}

.price-indicator {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 600;
  color: #f59e0b;
  background: rgba(245, 158, 11, 0.1);
  padding: 2px 8px;
  border-radius: 4px;
  margin-left: 8px;
}

.row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.form-group input,
.form-group select {
  min-height: 44px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 4px;
  font-size: 15px;
  transition: border-color 0.2s;
}

.form-group input:focus,
.form-group select:focus {
  outline: none;
  border-color: var(--cord);
  box-shadow: 0 0 0 2px rgba(15, 110, 92, 0.1);
}

.color-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 8px;
}

.color-btn {
  min-height: 44px;
  padding: 10px 12px;
  border: 2px solid var(--line);
  border-radius: 4px;
  background: white;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  text-align: center;
}

.color-btn:hover {
  border-color: var(--cord);
  background: rgba(15, 110, 92, 0.04);
}

.color-btn.selected {
  border-color: var(--cord);
  background: rgba(15, 110, 92, 0.1);
  font-weight: 600;
}

.louver-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.louver-btn {
  min-height: 48px;
  padding: 12px;
  border: 2px solid var(--line);
  border-radius: 4px;
  background: white;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.louver-btn:hover {
  border-color: var(--cord);
  background: rgba(15, 110, 92, 0.04);
}

.louver-btn.selected {
  border-color: var(--cord);
  background: var(--cord);
  color: white;
}

.price-panel {
  padding: 24px;
  background: linear-gradient(135deg, #f7fbf8 0%, #eef4f0 100%);
  border: 1px solid var(--line);
  border-radius: 8px;
  position: sticky;
  top: 24px;
  align-self: start;
}

.price-display {
  margin-top: 16px;
}

.price-amount {
  display: block;
  font-family: var(--font-display);
  font-size: 36px;
  font-weight: 700;
  color: var(--cord);
  margin-bottom: 16px;
  letter-spacing: 0.01em;
}

.price-details {
  list-style: none;
  padding: 0;
  margin: 0 0 16px;
  display: grid;
  gap: 8px;
}

.price-details li {
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 4px;
  font-size: 14px;
}

.price-note,
.price-incomplete p,
.price-error p {
  font-size: 13px;
  line-height: 1.6;
  color: rgba(27, 36, 33, 0.6);
  margin: 0;
}

.price-loading,
.price-incomplete,
.price-error {
  margin-top: 16px;
  padding: 20px;
  text-align: center;
  border-radius: 4px;
}

.price-loading {
  background: rgba(15, 110, 92, 0.06);
  color: var(--cord);
  font-weight: 600;
}

.price-incomplete {
  background: rgba(245, 158, 11, 0.06);
}

.price-error {
  background: rgba(140, 47, 47, 0.06);
}

.price-error small {
  display: block;
  margin-top: 8px;
  font-size: 12px;
  color: rgba(140, 47, 47, 0.7);
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

button.primary:hover {
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

@media (min-width: 1024px) {
  .config-layout {
    grid-template-columns: 2fr 1fr;
  }
}

@media (max-width: 700px) {
  .row {
    grid-template-columns: 1fr;
  }

  .color-grid {
    grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  }

  .louver-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .step-actions {
    flex-direction: column;
  }

  .step-actions button {
    width: 100%;
  }

  .price-panel {
    position: relative;
    top: auto;
  }
}
</style>

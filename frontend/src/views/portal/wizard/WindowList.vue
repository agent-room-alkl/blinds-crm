<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";

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
  defaultSeries: number | null;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: WindowDraft[]): void;
  (e: "next"): void;
  (e: "prev"): void;
}>();

const deleteConfirm = ref<string | null>(null);
const undoTimeout = ref<number | null>(null);

function addWindow() {
  const newWindow: WindowDraft = {
    id: crypto.randomUUID(),
    window_name: "",
    product_id: props.defaultSeries || "",
    width_mm: "",
    height_mm: "",
    quantity: 1,
    panel_count: 1,
    options: {},
    configured: false,
  };
  emit("update:modelValue", [...props.modelValue, newWindow]);
}

function copyLastWindow() {
  if (props.modelValue.length === 0) {
    addWindow();
    return;
  }
  const last = props.modelValue[props.modelValue.length - 1];
  const copy: WindowDraft = {
    id: crypto.randomUUID(),
    window_name: "",
    product_id: last.product_id,
    width_mm: last.width_mm,
    height_mm: last.height_mm,
    quantity: last.quantity,
    panel_count: last.panel_count,
    options: { ...last.options },
    configured: false,
  };
  emit("update:modelValue", [...props.modelValue, copy]);
}

function deleteWindow(id: string) {
  if (deleteConfirm.value === id) {
    // Already confirmed, delete immediately
    const updated = props.modelValue.filter((w) => w.id !== id);
    emit("update:modelValue", updated);
    deleteConfirm.value = null;
  } else {
    // Show undo toast
    deleteConfirm.value = id;
    if (undoTimeout.value) {
      clearTimeout(undoTimeout.value);
    }
    undoTimeout.value = window.setTimeout(() => {
      if (deleteConfirm.value === id) {
        const updated = props.modelValue.filter((w) => w.id !== id);
        emit("update:modelValue", updated);
        deleteConfirm.value = null;
      }
    }, 5000);
  }
}

function cancelDelete() {
  deleteConfirm.value = null;
  if (undoTimeout.value) {
    clearTimeout(undoTimeout.value);
    undoTimeout.value = null;
  }
}

function getProductName(productId: number | "") {
  const product = props.catalog.find((p) => p.id === productId);
  if (!product) return "";
  return locale.value === "zh" ? product.name_zh : product.name_en;
}

function nextStep() {
  if (props.modelValue.length > 0) {
    emit("next");
  }
}
</script>

<template>
  <div class="window-list-step">
    <div class="step-intro">
      <p class="section-label">{{ tx("步骤 2 · 窗户列表", "STEP 2 · WINDOWS") }}</p>
      <h2>{{ tx("添加窗户", "Add Windows") }}</h2>
      <p>{{ tx("添加订单中的所有窗户。每扇窗可以在下一步配置尺寸和选项。", "Add all windows in the order. Each window will be configured with size and options in the next step.") }}</p>
    </div>

    <div v-if="modelValue.length === 0" class="empty-state">
      <p>{{ tx("还没有窗户，先添加第一扇", "No windows yet. Add the first window to begin.") }}</p>
      <button type="button" class="primary" @click="addWindow">
        {{ tx("+ 添加第一扇窗户", "+ Add First Window") }}
      </button>
    </div>

    <div v-else>
      <!-- Desktop table view -->
      <div class="window-table">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>{{ tx("窗户名称", "Window Name") }}</th>
              <th>{{ tx("系列", "Series") }}</th>
              <th>{{ tx("尺寸 (mm)", "Size (mm)") }}</th>
              <th>{{ tx("扇数", "Panels") }}</th>
              <th>{{ tx("数量", "Qty") }}</th>
              <th>{{ tx("状态", "Status") }}</th>
              <th>{{ tx("操作", "Actions") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(window, index) in modelValue" :key="window.id">
              <td>{{ index + 1 }}</td>
              <td>
                <input
                  v-model="window.window_name"
                  type="text"
                  :placeholder="tx('例如：Bedroom 1', 'e.g. Bedroom 1')"
                  required
                />
              </td>
              <td>{{ getProductName(window.product_id) }}</td>
              <td>
                {{ window.width_mm && window.height_mm ? `${window.width_mm} × ${window.height_mm}` : tx("待配置", "TBC") }}
              </td>
              <td>{{ window.panel_count || 1 }}</td>
              <td>{{ window.quantity || 1 }}</td>
              <td>
                <span v-if="window.configured" class="status-ok">✓ {{ tx("已配置", "Done") }}</span>
                <span v-else class="status-pending">! {{ tx("未完成", "Pending") }}</span>
              </td>
              <td>
                <div class="actions">
                  <button type="button" class="icon-btn" :title="tx('删除', 'Delete')" @click="deleteWindow(window.id)">
                    🗑️
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Mobile card view -->
      <div class="window-cards">
        <div v-for="(window, index) in modelValue" :key="window.id" class="window-card">
          <div class="window-card-header">
            <strong>{{ index + 1 }}. {{ window.window_name || tx("未命名", "Unnamed") }}</strong>
            <button type="button" class="icon-btn" @click="deleteWindow(window.id)">🗑️</button>
          </div>
          <div class="window-card-body">
            <p><strong>{{ tx("系列", "Series") }}:</strong> {{ getProductName(window.product_id) }}</p>
            <p><strong>{{ tx("尺寸", "Size") }}:</strong> {{ window.width_mm && window.height_mm ? `${window.width_mm} × ${window.height_mm} mm` : tx("待配置", "TBC") }}</p>
            <p>
              <span v-if="window.configured" class="status-ok">✓ {{ tx("已配置", "Done") }}</span>
              <span v-else class="status-pending">! {{ tx("未完成", "Pending") }}</span>
            </p>
          </div>
        </div>
      </div>

      <div class="action-row">
        <button type="button" class="secondary" @click="addWindow">
          {{ tx("+ 添加窗户", "+ Add Window") }}
        </button>
        <button type="button" class="secondary" @click="copyLastWindow">
          {{ tx("复制上一扇", "Copy Last") }}
        </button>
      </div>
    </div>

    <div v-if="deleteConfirm" class="undo-toast">
      <p>{{ tx("窗户将被删除", "Window will be deleted") }}</p>
      <button type="button" @click="cancelDelete">{{ tx("撤销", "Undo") }}</button>
    </div>

    <div class="step-actions">
      <button type="button" class="secondary" @click="emit('prev')">
        {{ tx("上一步", "Previous") }}
      </button>
      <button type="button" class="primary" :disabled="modelValue.length === 0" @click="nextStep">
        {{ tx("下一步 · 配置", "Next · Configure") }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.window-list-step {
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

.empty-state {
  text-align: center;
  padding: 60px 20px;
  background: rgba(15, 110, 92, 0.04);
  border-radius: 8px;
  margin-bottom: 32px;
}

.empty-state p {
  font-size: 16px;
  color: rgba(27, 36, 33, 0.6);
  margin-bottom: 24px;
}

.window-table {
  display: none;
  overflow-x: auto;
  margin-bottom: 24px;
}

.window-table table {
  width: 100%;
  border-collapse: collapse;
  background: white;
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
}

.window-table th,
.window-table td {
  padding: 12px 16px;
  text-align: left;
  font-size: 14px;
  border-bottom: 1px solid var(--line);
}

.window-table th {
  background: rgba(27, 36, 33, 0.04);
  font-weight: 600;
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.window-table tbody tr:last-child td {
  border-bottom: none;
}

.window-table input {
  width: 100%;
  min-height: 44px;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 4px;
  font-size: 14px;
}

.window-cards {
  display: grid;
  gap: 16px;
  margin-bottom: 24px;
}

.window-card {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: white;
  overflow: hidden;
}

.window-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: rgba(27, 36, 33, 0.04);
  border-bottom: 1px solid var(--line);
}

.window-card-body {
  padding: 16px;
}

.window-card-body p {
  margin: 8px 0;
  font-size: 14px;
  line-height: 1.6;
}

.status-ok {
  color: var(--cord);
  font-weight: 600;
}

.status-pending {
  color: #f59e0b;
  font-weight: 600;
}

.actions {
  display: flex;
  gap: 8px;
}

.icon-btn {
  min-width: 44px;
  min-height: 44px;
  padding: 8px 10px;
  background: transparent;
  border: 1px solid var(--line);
  border-radius: 4px;
  cursor: pointer;
  font-size: 16px;
  transition: all 0.2s;
}

.icon-btn:hover {
  background: rgba(27, 36, 33, 0.04);
  border-color: var(--cord);
}

.action-row {
  display: flex;
  gap: 12px;
  margin-bottom: 32px;
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

.undo-toast {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 100;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 24px;
  background: var(--ink);
  color: white;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.undo-toast p {
  margin: 0;
  font-size: 15px;
}

.undo-toast button {
  min-height: 44px;
  padding: 10px 20px;
  background: white;
  color: var(--ink);
  border: none;
  border-radius: 4px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

@media (min-width: 1024px) {
  .window-table {
    display: block;
  }

  .window-cards {
    display: none;
  }
}

@media (max-width: 700px) {
  .action-row {
    flex-direction: column;
  }

  .step-actions {
    flex-direction: column;
  }

  .step-actions button {
    width: 100%;
  }
}
</style>

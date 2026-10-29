<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { Plus, Trash2 } from "lucide-vue-next";
import { request } from "../crm-api";

const props = defineProps<{ customers: { customer_id: number; company: string; customer_code?: string }[]; locale: string }>();
const emit = defineEmits<{ (event: "created", invoice: any): void }>();
const tx = (zh: string, en: string) => (props.locale === "zh" ? zh : en);

// Charges outside an order balance (installation, air freight, credits). Amounts include GST; a credit is a negative line.
const GST_RATE = 0.15;
const customerId = ref<number | "">("");
const items = reactive<{ description: string; amount: string }[]>([{ description: "", amount: "" }]);
const busy = ref(false);
const error = ref("");
const notice = ref("");
let operationKey = crypto.randomUUID();
// An edited form is a different request; an untouched retry keeps its key so it can never create a second invoice.
watch([customerId, items], () => { operationKey = crypto.randomUUID(); }, { deep: true });

const cents = (text: string) => {
  const value = text.trim();
  return /^-?\d+(\.\d{1,2})?$/.test(value) ? Math.round(Number(value) * 100) : null;
};
const lineIssue = (line: { description: string; amount: string }) => {
  if (!line.description.trim() && !line.amount.trim()) return "";
  if (!line.description.trim()) return tx("请填写项目说明", "Enter a description");
  const amount = cents(line.amount);
  if (amount === null) return tx("金额最多两位小数，负数表示抵扣", "Amount with up to 2 decimals; negative is a credit");
  return amount === 0 ? tx("金额不能为 0", "Amount cannot be zero") : "";
};
const filled = computed(() => items.filter((line) => line.description.trim() || line.amount.trim()));
const totalCents = computed(() => filled.value.reduce((sum, line) => sum + (cents(line.amount) ?? 0), 0));
const gstCents = computed(() => Math.round(totalCents.value * GST_RATE / (1 + GST_RATE)));
const money = (value: number) => (value / 100).toLocaleString("en-NZ", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const blocker = computed(() => {
  if (!customerId.value) return tx("先选择公司", "Choose a company first");
  if (!filled.value.length) return tx("至少填一行", "Add at least one line");
  if (filled.value.some((line) => lineIssue(line))) return tx("请先修正标红的行", "Fix the highlighted lines first");
  if (totalCents.value <= 0) return tx("合计必须大于 0；抵扣请写成负数行并配正数项目", "The total must be above 0; enter credits as negative lines next to charges");
  return "";
});

function addLine() { items.push({ description: "", amount: "" }); }
function removeLine(index: number) { items.splice(index, 1); if (!items.length) addLine(); }

async function submit() {
  error.value = ""; notice.value = "";
  if (blocker.value) { error.value = blocker.value; return; }
  busy.value = true;
  try {
    const invoice = await request<any>("operations/invoices/manual", {
      customer_id: Number(customerId.value),
      items: filled.value.map((line) => ({ description: line.description.trim(), amount: line.amount.trim() })),
      operation_key: operationKey,
    });
    notice.value = tx(`已创建账单草稿 ${invoice.invoice_number}，可在发票列表预览并发送。`, `Draft invoice ${invoice.invoice_number} created. Preview and send it from the invoice list.`);
    items.splice(0, items.length, { description: "", amount: "" });
    emit("created", invoice);
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally { busy.value = false; }
}
</script>

<template>
  <section class="manual-invoice">
    <header>
      <h3>{{ tx("手动账单", "Manual invoice") }}</h3>
      <p>{{ tx("用于订单尾款以外的费用，如安装、空运运费、抵扣。金额含 GST，抵扣写成负数。它是单独的一张账单，不并入订单尾款。", "For charges outside the order balance, such as installation, air freight or credits. Amounts include GST; enter a credit as a negative line. It is its own invoice, separate from the order balance.") }}</p>
    </header>
    <label class="company">{{ tx("公司", "Company") }}
      <select v-model.number="customerId">
        <option value="">{{ tx("选择公司", "Choose a company") }}</option>
        <option v-for="customer in customers" :key="customer.customer_id" :value="customer.customer_id">{{ customer.company }}{{ customer.customer_code ? ` (${customer.customer_code})` : "" }}</option>
      </select>
    </label>
    <div class="lines">
      <div class="line head" aria-hidden="true"><span>{{ tx("项目说明", "Description") }}</span><span>{{ tx("金额（含 GST）", "Amount (incl. GST)") }}</span><span></span></div>
      <div v-for="(line, index) in items" :key="index" class="line" :class="{ bad: lineIssue(line) }">
        <input v-model="line.description" maxlength="200" :placeholder="tx('例如：Sterling House 安装', 'e.g. Sterling House installation')" :aria-label="tx('项目说明', 'Description')" />
        <input v-model="line.amount" inputmode="decimal" :placeholder="tx('460.00 或 -75.00', '460.00 or -75.00')" :aria-label="tx('金额', 'Amount')" />
        <button type="button" class="icon" :title="tx('删除此行', 'Remove line')" @click="removeLine(index)"><Trash2 :size="14" aria-hidden="true" /></button>
        <small v-if="lineIssue(line)" class="issue">{{ lineIssue(line) }}</small>
      </div>
      <button type="button" class="add" @click="addLine"><Plus :size="14" aria-hidden="true" />{{ tx("添加一行", "Add line") }}</button>
    </div>
    <dl class="totals">
      <div><dt>{{ tx("合计（含 GST）", "Total (incl. GST)") }}</dt><dd>NZD {{ money(totalCents) }}</dd></div>
      <div class="gst"><dt>{{ tx("其中 GST (15%)", "Of which GST (15%)") }}</dt><dd>NZD {{ money(gstCents) }}</dd></div>
    </dl>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="notice" class="ok" role="status">{{ notice }}</p>
    <footer>
      <button type="button" class="primary" :disabled="busy || !!blocker" :title="blocker || undefined" @click="submit">{{ busy ? tx("创建中…", "Creating…") : tx("创建账单草稿", "Create draft invoice") }}</button>
      <span v-if="blocker && (customerId || filled.length)" class="hint">{{ blocker }}</span>
    </footer>
  </section>
</template>

<style scoped>
.manual-invoice{padding:16px;border:1px solid #e0e8d9;background:#fff;border-radius:6px;max-width:760px}
.manual-invoice h3{margin:0 0 6px;font-size:18px;font-weight:600}
.manual-invoice header p{margin:0 0 14px;font-size:13px;line-height:1.6;color:#54645c}
.company{display:grid;gap:6px;font-size:12px;font-weight:650;margin-bottom:14px}
.manual-invoice select,.manual-invoice input{width:100%;min-height:0;height:38px;box-sizing:border-box;padding:6px 9px;border:1px solid #ccd7cf;border-radius:4px;background:#fff;font:inherit;font-weight:400}
.lines{display:grid;gap:8px}
.line{display:grid;grid-template-columns:minmax(0,1fr) 170px 34px;gap:8px;align-items:center}
.line.head{font-size:11px;font-weight:650;color:#64766b;letter-spacing:.04em}
.line.bad input{border-color:#c4655c;background:#fff8f6}
.issue{grid-column:1/-1;color:#8f3425;font-size:12px;margin-top:-4px}
.icon{display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;padding:0;border:1px solid #c5d0c8;border-radius:4px;background:#fff;color:#9b3a32;cursor:pointer}
.icon:hover{border-color:#c4655c;background:#fbf1ef}
.add{justify-self:start;display:inline-flex;align-items:center;gap:6px;min-height:34px;padding:0 12px;border:1px dashed #a9b8ad;border-radius:4px;background:#fff;color:#29493d;font-size:12px;font-weight:600;cursor:pointer}
.add:hover{border-color:#0f6e5c;background:#f2f7f4}
.totals{display:grid;gap:4px;margin:16px 0 0;padding:12px 14px;background:#f3f6f3;border-radius:6px}
.totals div{display:flex;justify-content:space-between;gap:12px}
.totals dt{font-size:13px;color:#34503f}.totals dd{margin:0;font-weight:700;white-space:nowrap}
.totals .gst dt,.totals .gst dd{font-size:12px;font-weight:500;color:#64766b}
.error{margin:12px 0 0;padding:10px 12px;border-radius:6px;background:#fff0ed;color:#8f3425;font-size:13px;white-space:pre-line}
.ok{margin:12px 0 0;padding:10px 12px;border-radius:6px;background:#edf5ef;color:#17523a;font-size:13px}
footer{display:flex;align-items:center;gap:12px;margin-top:14px;flex-wrap:wrap}
.primary{min-height:40px;padding:0 16px;border:0;border-radius:5px;background:#0f6e5c;color:#fff;font-weight:650;cursor:pointer}
.primary:disabled{opacity:.5;cursor:not-allowed}
.hint{font-size:12px;color:#64766b}
@media(max-width:560px){.line{grid-template-columns:minmax(0,1fr) 34px}.line.head{display:none}.line input:nth-of-type(2){grid-column:1}.line .icon{grid-row:1;grid-column:2}}
</style>

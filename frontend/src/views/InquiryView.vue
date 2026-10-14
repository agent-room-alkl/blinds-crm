<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute } from "vue-router";
import { createInquiry, listProducts, type ApiProduct } from "../api";

const { t, tm, locale } = useI18n();
const customerTypes = computed(() => tm("inquiry.types") as string[]);
const route = useRoute();
const lang = computed(() => (locale.value === "en" ? "en" : "zh"));
const products = ref<ApiProduct[]>([]);
const sending = ref(false);
const error = ref("");
const reference = ref("");
const submissionKey = crypto.randomUUID();

const form = reactive({
  contactName: "",
  company: "",
  customerType: "other",
  phone: "",
  email: "",
  wechat: "",
  productId: typeof route.query.product === "string" ? route.query.product : "",
  quantity: "",
  width: "",
  height: "",
  unit: "mm",
  sizeUnknown: true,
  dueUnknown: true,
  dueText: "",
  notes: "",
});

onMounted(async () => {
  products.value = await listProducts();
});

const nextSteps = computed(() => tm("inquiry.nextSteps") as string[]);
const brief = computed(() => {
  const rows: { label: string; value: string }[] = [];
  const name = form.contactName.trim();
  const company = form.company.trim();
  const channel = [form.phone, form.email, form.wechat].map((item) => item.trim()).filter(Boolean).join(" / ");
  if (name) rows.push({ label: t("inquiry.contact"), value: name });
  if (company) rows.push({ label: t("inquiry.company"), value: company });
  if (channel) rows.push({ label: t("inquiry.reply"), value: channel });
  const product = products.value.find((item) => String(item.id) === form.productId);
  if (product) rows.push({ label: t("inquiry.product"), value: lang.value === "en" ? product.name_en : product.name_zh });
  if (form.quantity.trim()) rows.push({ label: t("inquiry.quantity"), value: form.quantity.trim() });
  if (!form.sizeUnknown && form.width.trim() && form.height.trim()) {
    rows.push({ label: t("inquiry.size"), value: `${form.width.trim()} × ${form.height.trim()} ${form.unit}` });
  }
  if (!form.dueUnknown && form.dueText.trim()) rows.push({ label: t("inquiry.due"), value: form.dueText.trim() });
  return rows;
});

function numberOrNull(value: string) {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

async function submit() {
  error.value = "";
  reference.value = "";
  if (!form.contactName.trim() || (!form.phone && !form.email && !form.wechat)) {
    error.value = t("inquiry.channelHint");
    return;
  }
  sending.value = true;
  try {
    const channel = [form.phone, form.email, form.wechat].map((item) => item.trim()).filter(Boolean).join(" / ");
    const productId = Number(form.productId);
    const result = await createInquiry({
      company: form.company.trim() || (lang.value === "en" ? "Other / individual" : "其他/个人"),
      contact_name: form.contactName.trim(),
      channel,
      locale: lang.value,
      product_id: Number.isInteger(productId) && productId > 0 ? productId : null,
      quantity: numberOrNull(form.quantity),
      width: form.sizeUnknown ? null : numberOrNull(form.width),
      height: form.sizeUnknown ? null : numberOrNull(form.height),
      unit: form.sizeUnknown ? null : form.unit === "inch" ? "inch" : "mm",
      expected_date: form.dueUnknown ? "" : form.dueText.trim(),
      notes: [form.customerType, form.sizeUnknown ? t("inquiry.sizeUnknown") : "", form.notes.trim()].filter(Boolean).join("\n"),
      submission_key: submissionKey,
      source: "website",
    });
    reference.value = result.reference ?? String(result.id ?? "ok");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("inquiry.fail");
  } finally {
    sending.value = false;
  }
}
</script>

<template>
  <main class="inquiry-page">
    <header>
      <p class="kicker">VERA</p>
      <h1>{{ t("inquiry.title") }}</h1>
    </header>
    <div class="sheet">
    <form @submit.prevent="submit">
      <fieldset>
        <legend>{{ t("inquiry.who") }}</legend>
        <div class="pair">
          <label>{{ t("inquiry.contact") }}<input v-model="form.contactName" required /></label>
          <label>{{ t("inquiry.company") }}<input v-model="form.company" /></label>
        </div>
        <label>
          {{ t("inquiry.type") }}
          <select v-model="form.customerType">
            <option value="retailer">{{ customerTypes[0] }}</option>
            <option value="fitout">{{ customerTypes[1] }}</option>
            <option value="architect">{{ customerTypes[2] }}</option>
            <option value="other">{{ customerTypes[3] }}</option>
          </select>
        </label>
        <p class="hint">{{ t("inquiry.companyHint") }}</p>
      </fieldset>
      <fieldset>
        <legend>{{ t("inquiry.reply") }}</legend>
        <div class="pair">
          <label>{{ t("inquiry.phone") }}<input v-model="form.phone" /></label>
          <label>{{ t("inquiry.email") }}<input v-model="form.email" type="email" /></label>
        </div>
        <label>{{ t("inquiry.wechat") }}<input v-model="form.wechat" /></label>
        <p class="hint">{{ t("inquiry.channelHint") }}</p>
      </fieldset>
      <fieldset>
        <legend>{{ t("inquiry.project") }}</legend>
        <div class="pair">
          <label>
            {{ t("inquiry.product") }}
            <select v-model="form.productId">
              <option value="">{{ t("inquiry.unknownProduct") }}</option>
              <option v-for="product in products" :key="product.id" :value="String(product.id)">
                {{ lang === "en" ? product.name_en : product.name_zh }} — {{ t("sample") }}
              </option>
            </select>
          </label>
          <label>{{ t("inquiry.quantity") }}<input v-model="form.quantity" inputmode="numeric" /></label>
        </div>
        <label class="check">
          <input v-model="form.sizeUnknown" type="checkbox" />
          <span>{{ t("inquiry.sizeUnknown") }}</span>
        </label>
        <div v-if="!form.sizeUnknown" class="row">
          <label>{{ t("inquiry.width") }}<input v-model="form.width" inputmode="decimal" /></label>
          <label>{{ t("inquiry.height") }}<input v-model="form.height" inputmode="decimal" /></label>
          <label>
            {{ t("inquiry.unit") }}
            <select v-model="form.unit">
              <option value="mm">mm</option>
              <option value="inch">inch</option>
            </select>
          </label>
        </div>
        <label class="check">
          <input v-model="form.dueUnknown" type="checkbox" />
          <span>{{ t("inquiry.dueUnknown") }}</span>
        </label>
        <label v-if="!form.dueUnknown">{{ t("inquiry.due") }}<input v-model="form.dueText" /></label>
        <label>{{ t("inquiry.notes") }}<textarea v-model="form.notes" /></label>
      </fieldset>
      <p v-if="error" class="error">{{ error }}</p>
      <p v-if="reference" class="ok">{{ t("inquiry.success") }} {{ reference }}</p>
      <button type="submit" :disabled="sending">
        {{ sending ? t("inquiry.sending") : t("inquiry.submit") }}
      </button>
    </form>
    <aside class="summary">
      <p class="kicker">{{ t("inquiry.nextKicker") }}</p>
      <strong>{{ t("inquiry.nextTitle") }}</strong>
      <ol>
        <li v-for="(step, index) in nextSteps" :key="step"><span>0{{ index + 1 }}</span>{{ step }}</li>
      </ol>
      <dl v-if="brief.length">
        <div v-for="row in brief" :key="row.label">
          <dt>{{ row.label }}</dt>
          <dd>{{ row.value }}</dd>
        </div>
      </dl>
      <p v-else class="hint">{{ t("inquiry.nextHint") }}</p>
    </aside>
    </div>
  </main>
</template>
<style scoped>
.inquiry-page{max-width:1080px;margin:auto;padding:28px 48px 56px;background:#faf9f6}
.inquiry-page h1{font-size:clamp(32px,4vw,44px);font-weight:600;letter-spacing:-.03em;line-height:1.1;max-width:none;margin:8px 0 20px}
.inquiry-page .kicker{margin:0}
.inquiry-page form{gap:18px}
.inquiry-page fieldset{border:1px solid rgba(27,36,33,.14);background:white;padding:16px 18px 18px;display:grid;gap:12px}
.inquiry-page legend{padding:0 6px;font-size:12px;letter-spacing:.12em;color:#54645c}
.inquiry-page .pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.inquiry-page .hint{margin:0;font-size:12px;line-height:1.5;color:#617168}
.inquiry-page input,.inquiry-page select,.inquiry-page textarea{background:white;border-color:rgba(27,36,33,.22)}
.inquiry-page button{justify-self:start;padding:10px 22px}
.inquiry-page .summary{background:white;border:1px solid rgba(27,36,33,.14);padding:18px 18px 20px;display:grid;gap:12px;align-content:start}
.inquiry-page .summary strong{font-size:20px;font-weight:600;letter-spacing:-.02em;line-height:1.25}
.inquiry-page .summary ol{list-style:none;margin:0;padding:0;display:grid;gap:10px}
.inquiry-page .summary li{display:grid;grid-template-columns:28px 1fr;gap:8px;align-items:baseline;font-size:14px;line-height:1.45}
.inquiry-page .summary li span{font-size:12px;letter-spacing:.08em;color:#54645c}
.inquiry-page .summary dl{margin:4px 0 0;padding-top:12px;border-top:1px solid rgba(27,36,33,.14);display:grid;gap:10px}
.inquiry-page .summary dt{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#54645c}
.inquiry-page .summary dd{margin:2px 0 0;font-size:15px}
@media(max-width:700px){.inquiry-page{padding:20px 24px 40px}.inquiry-page .pair,.inquiry-page .row{grid-template-columns:1fr}}
</style>

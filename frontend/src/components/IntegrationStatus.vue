<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { request } from "../crm-api";

const props = defineProps<{ locale: string }>();
const tx = (zh: string, en: string) => (props.locale === "zh" ? zh : en);
const notice = ref("");
type PaymentDetails = { account_name: string; bank_name: string; account_number: string; reference_note: string; configured?: boolean };
const settings = ref<{ email?: { configured?: boolean; sender?: string; mode?:string }; storage?: string; database?: string; payment_details?: PaymentDetails } | null>(null);
const payment = reactive<PaymentDetails>({ account_name: "", bank_name: "", account_number: "", reference_note: "" });
const paymentBusy = ref(false);
const paymentError = ref("");
const paymentSaved = ref("");

function fillPayment(details?: PaymentDetails) {
  for (const key of ["account_name", "bank_name", "account_number", "reference_note"] as const) payment[key] = details?.[key] ?? "";
}

async function savePayment() {
  paymentError.value = ""; paymentSaved.value = "";
  paymentBusy.value = true;
  try {
    const result = await request<{ payment_details: PaymentDetails }>("operations/settings", {
      payment_details: { account_name: payment.account_name.trim(), bank_name: payment.bank_name.trim(), account_number: payment.account_number.trim(), reference_note: payment.reference_note.trim() },
    });
    fillPayment(result.payment_details);
    if (settings.value) settings.value.payment_details = result.payment_details;
    paymentSaved.value = result.payment_details.configured
      ? tx("已保存，之后发出的账单邮件和 PDF 都会带上这些收款信息。", "Saved. Invoice emails and PDFs sent from now on carry these payment details.")
      : tx("已保存为空，账单将只提示联系 VERA 付款。", "Saved empty. Invoices will only ask the customer to contact VERA.");
  } catch (cause) {
    paymentError.value = cause instanceof Error ? cause.message : String(cause);
  } finally { paymentBusy.value = false; }
}

onMounted(async () => {
  try {
    settings.value = await request("operations/settings");
    fillPayment(settings.value?.payment_details);
  } catch {
    notice.value = tx("暂时无法读取服务配置", "Could not load service settings");
  }
});
</script>

<template>
  <section class="ops-settings">
    <h2>{{ tx("服务配置", "Service settings") }}</h2>
    <p>{{ tx("只显示发件是否就绪、存储方式和数据库类型。密钥不出现在页面上。", "This shows whether outgoing mail is ready, plus the storage mode and database type. Secrets are not shown.") }}</p>
    <p v-if="notice" role="alert">{{ notice }}</p>
    <div v-else-if="settings" class="ops-grid">
      <article>
        <span>{{ tx("发件", "Outgoing mail") }}</span>
        <h3>{{ settings.email?.mode==='demo' ? (settings.email?.configured ? tx('演示发件就绪 · 仅自己','Demo mail ready · owner only') : tx('演示发件未就绪','Demo mail not ready')) : settings.email?.configured ? tx("已配置", "Configured") : tx("未配置", "Not configured") }}</h3>
        <p>{{ settings.email?.mode==='demo' ? tx('客户不会收到邮件；发件人与收件人均限定为管理员测试邮箱。','Customers receive no email; sender and recipient are limited to the owner test mailbox.') : settings.email?.sender || tx("没有可显示的发件地址", "No sender address to show") }}</p>
      </article>
      <article>
        <span>{{ tx("存储", "Storage") }}</span>
        <h3>{{ settings.storage || "—" }}</h3>
      </article>
      <article>
        <span>{{ tx("数据库", "Database") }}</span>
        <h3>{{ settings.database || "—" }}</h3>
      </article>
    </div>
    <form v-if="settings?.payment_details" class="payment-form" @submit.prevent="savePayment">
      <h3>{{ tx("收款信息", "Payment details") }}</h3>
      <p>{{ tx("显示在每张账单的邮件和 PDF 上。没有填写时，账单只提示客户联系 VERA。", "Shown on every invoice email and PDF. Until filled in, invoices only ask the customer to contact VERA.") }}</p>
      <div class="payment-grid">
        <label>{{ tx("账户名称", "Account name") }}<input v-model="payment.account_name" maxlength="200" autocomplete="off" /></label>
        <label>{{ tx("银行", "Bank") }}<input v-model="payment.bank_name" maxlength="200" autocomplete="off" /></label>
        <label>{{ tx("账号", "Account number") }}<input v-model="payment.account_number" maxlength="100" inputmode="numeric" autocomplete="off" /></label>
        <label class="wide">{{ tx("备注（可选）", "Note (optional)") }}<textarea v-model="payment.reference_note" maxlength="500" rows="2" :placeholder="tx('例如：付款时请写账单号作为参考', 'e.g. Please use the invoice number as the payment reference')"></textarea></label>
      </div>
      <p v-if="paymentError" class="payment-error" role="alert">{{ paymentError }}</p>
      <p v-if="paymentSaved" class="payment-ok" role="status">{{ paymentSaved }}</p>
      <button type="submit" :disabled="paymentBusy">{{ paymentBusy ? tx("保存中…", "Saving…") : tx("保存收款信息", "Save payment details") }}</button>
    </form>
  </section>
</template>

<style scoped>
.ops-settings { padding: 8px 0 28px; }
.ops-settings h2 { font-size: 20px; font-weight: 600; margin: 0 0 12px; }
.ops-settings > p { font-size: 15px; line-height: 1.6; color: #54645c; max-width: 640px; }
.ops-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin-top: 16px; }
.ops-grid article { padding: 16px; border: 1px solid #e0e8d9; background: #fff; border-radius: 6px; min-width: 0; }
.ops-grid span { font-size: 13px; letter-spacing: 0.04em; color: #52635a; }
.ops-grid h3 { font-size: 18px; font-weight: 600; margin: 10px 0 0; overflow-wrap: anywhere; }
.ops-grid p { font-size: 14px; line-height: 1.5; color: #54645c; margin: 8px 0 0; overflow-wrap: anywhere; }
.payment-form { margin-top: 28px; padding: 16px; border: 1px solid #e0e8d9; background: #fff; border-radius: 6px; max-width: 760px; }
.payment-form h3 { font-size: 18px; font-weight: 600; margin: 0 0 6px; }
.payment-form > p { font-size: 13px; line-height: 1.6; color: #54645c; margin: 0 0 14px; }
.payment-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.payment-grid label { display: grid; gap: 6px; font-size: 12px; font-weight: 650; }
.payment-grid .wide { grid-column: 1 / -1; }
.payment-grid input, .payment-grid textarea { width: 100%; box-sizing: border-box; padding: 8px 10px; border: 1px solid #ccd7cf; border-radius: 4px; font: inherit; font-weight: 400; background: #fff; }
.payment-grid input { height: 38px; min-height: 0; }
.payment-form button { margin-top: 14px; min-height: 40px; padding: 0 16px; border: 0; border-radius: 5px; background: #0f6e5c; color: #fff; font-weight: 650; cursor: pointer; }
.payment-form button:disabled { opacity: .55; cursor: not-allowed; }
.payment-error { margin: 12px 0 0; padding: 10px 12px; border-radius: 6px; background: #fff0ed; color: #8f3425; font-size: 13px; }
.payment-ok { margin: 12px 0 0; padding: 10px 12px; border-radius: 6px; background: #edf5ef; color: #17523a; font-size: 13px; }
@media (max-width: 800px) { .ops-grid { grid-template-columns: 1fr; } .payment-grid { grid-template-columns: 1fr; } }
</style>

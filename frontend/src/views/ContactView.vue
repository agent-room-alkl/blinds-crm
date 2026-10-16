<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { siteProfile } from "../site-profile";

const { t, tm } = useI18n();
const windows = computed(() => tm("contact.windows") as string[]);
const sending = ref(false);
const error = ref("");
const reference = ref("");
const form = reactive({
  contactName: "",
  company: "",
  channel: "phone",
  channelValue: "",
  weekdayWindow: "morning",
  notes: "",
});

function submit() {
  error.value = "";
  reference.value = "";
  const email = siteProfile.email.trim();
  if (!email) {
    error.value = t("contact.fail");
    return;
  }
  const windowLabel = windows.value[["morning", "afternoon", "any"].indexOf(form.weekdayWindow)] || form.weekdayWindow;
  const body = [
    `${t("contact.name")}: ${form.contactName.trim()}`,
    `${t("contact.company")}: ${form.company.trim()}`,
    `${t("contact.channel")}: ${form.channel} ${form.channelValue.trim()}`,
    `${t("contact.window")}: ${windowLabel}`,
    form.notes.trim(),
  ].filter(Boolean).join("\n");
  window.location.href = `mailto:${email}?subject=${encodeURIComponent("VERA contact")}&body=${encodeURIComponent(body)}`;
  reference.value = email;
}
</script>

<template>
  <main class="page contact-page">
    <div class="contact-form-panel">
    <h1>{{ t("contact.title") }}</h1>
    <p class="lead">{{ t("contact.lead") }} <router-link to="/portal">{{ t("nav.portal") }}</router-link></p>
    <form @submit.prevent="submit">
      <label>{{ t("contact.name") }}<input v-model="form.contactName" required /></label>
      <label>{{ t("contact.company") }}<input v-model="form.company" required /></label>
      <label>
        {{ t("contact.channel") }}
        <select v-model="form.channel">
          <option value="phone">{{ t("inquiry.phone") }}</option>
          <option value="wechat">{{ t("inquiry.wechat") }}</option>
          <option value="email">{{ t("inquiry.email") }}</option>
        </select>
      </label>
      <label>{{ t("contact.channelValue") }}<input v-model="form.channelValue" required /></label>
      <fieldset class="slots">
        <legend>{{ t("contact.window") }}</legend>
        <label>
          <input v-model="form.weekdayWindow" type="radio" value="morning" required />
          <span>{{ windows[0] }}</span>
        </label>
        <label>
          <input v-model="form.weekdayWindow" type="radio" value="afternoon" />
          <span>{{ windows[1] }}</span>
        </label>
        <label>
          <input v-model="form.weekdayWindow" type="radio" value="any" />
          <span>{{ windows[2] }}</span>
        </label>
      </fieldset>
      <label>{{ t("contact.notes") }}<textarea v-model="form.notes" /></label>
      <p v-if="error" class="error">{{ error }}</p>
      <p v-if="reference" class="ok">{{ t("contact.success") }} {{ reference }}</p>
      <button type="submit" :disabled="sending">
        {{ sending ? t("contact.sending") : t("contact.submit") }}
      </button>
    </form>
    </div>
  </main>
</template>

<style scoped>
.contact-page{max-width:920px;margin:auto;padding:28px 48px 40px;background:#faf9f6}.contact-form-panel h1{font-size:32px!important;font-weight:500;line-height:1.15;max-width:none;margin:0}.contact-form-panel .lead{font-size:15px;color:#617168;line-height:1.6;margin:12px 0 20px}.contact-form-panel form{display:grid;grid-template-columns:1fr 1fr;gap:12px 16px;align-items:end}.contact-form-panel label{font-size:13px;margin:0}.contact-form-panel input,.contact-form-panel textarea,.contact-form-panel select{border:1px solid var(--line);background:white;padding:10px 12px;font-size:14px;border-radius:2px}.contact-form-panel .slots{grid-column:1/-1;margin:0;display:flex;flex-wrap:wrap;gap:8px 16px;border:0;padding:0}.contact-form-panel .slots legend{width:100%;font-size:13px;margin-bottom:4px}.contact-form-panel textarea{min-height:72px}.contact-form-panel form>label:has(textarea),.contact-form-panel .error,.contact-form-panel .ok,.contact-form-panel button{grid-column:1/-1}.contact-form-panel button{justify-self:start;padding:10px 20px;font-size:13px}@media(max-width:640px){.contact-page{padding:20px 24px 36px}.contact-form-panel form{grid-template-columns:1fr}.contact-form-panel h1{font-size:28px!important}}
</style>

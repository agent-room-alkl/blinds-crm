<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { request } from "../crm-api";

interface PortalCustomer {
  customer_id: number;
  company: string;
  contact_name: string;
  email: string;
  phone: string;
  company_address: string;
  username: string;
}

const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);
const rows = ref<PortalCustomer[]>([]);
const error = ref("");

onMounted(async () => {
  try {
    rows.value = await request<PortalCustomer[]>("operations/customers");
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  }
});
</script>

<template>
  <section class="card profiles">
    <h2>{{ tx("客户资料", "Customers") }}</h2>
    <p>{{ tx("每个客户一个登录、一个联系人。邮箱、电话和公司地址来自门户档案。旧的多联系人记录在「辅助历史 / 旧客户资料」，不在这里维护第二联系人。", "Each customer has one login and one contact. Email, phone and company address come from the portal profile. Older multi-contact rows stay under History / Old records. A second contact is not added here.") }}</p>
    <p class="hint">{{ tx("门户档案目前只能在开通时写入，没有修改接口。这里不把旧的「联系渠道」当成邮箱或电话。", "A portal profile is written when the account is opened. There is no update API yet, so the old channel field is not treated as the email or phone.") }}</p>
    <p v-if="error" class="alert" role="alert">{{ error }}</p>
    <p v-else-if="!rows.length">{{ tx("还没有开通门户账号。", "No portal account has been opened yet.") }}</p>
    <article v-for="row in rows" :key="row.customer_id">
      <h3>{{ row.company }}</h3>
      <p>{{ row.contact_name }} · {{ row.username }}</p>
      <p>{{ tx("邮箱", "Email") }}：{{ row.email }}</p>
      <p>{{ tx("电话", "Phone") }}：{{ row.phone }}</p>
      <p>{{ tx("公司地址", "Company address") }}：{{ row.company_address }}</p>
    </article>
  </section>
</template>

<style scoped>
.profiles article { border-top: 1px solid var(--line, #dedbd5); margin-top: 16px; padding-top: 12px; }
.hint { color: #54645c; line-height: 1.6; }
.alert { color: #8a3b2c; }
h3 { margin: 0 0 6px; }
</style>

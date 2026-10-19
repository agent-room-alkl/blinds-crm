<script setup lang="ts">
import { onMounted, ref } from "vue";
import { request } from "../crm-api";

const props = defineProps<{ locale: string }>();
const tx = (zh: string, en: string) => (props.locale === "zh" ? zh : en);
const notice = ref("");
const settings = ref<{ email?: { configured?: boolean; sender?: string; mode?:string }; storage?: string; database?: string } | null>(null);

onMounted(async () => {
  try {
    settings.value = await request("operations/settings");
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
@media (max-width: 800px) { .ops-grid { grid-template-columns: 1fr; } }
</style>

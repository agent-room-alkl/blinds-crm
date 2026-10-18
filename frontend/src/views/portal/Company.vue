<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { portalRequest } from "../../portal-api";

const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);

const profile = ref<any>(null);
const loading = ref(true);

onMounted(async () => {
  try {
    profile.value = await portalRequest<any>("me");
  } catch {
    // error
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="company-page">
    <h1>{{ tx("公司资料", "Company Profile") }}</h1>
    
    <div v-if="loading" class="loading">{{ tx("加载中...", "Loading...") }}</div>
    
    <div v-else-if="profile" class="company-card">
      <div class="info-section">
        <h2>{{ profile.company }}</h2>
        <dl>
          <dt>{{ tx("联系人", "Contact Name") }}</dt>
          <dd>{{ profile.contact_name }}</dd>
          <dt>{{ tx("邮箱", "Email") }}</dt>
          <dd>{{ profile.email }}</dd>
          <dt>{{ tx("电话", "Phone") }}</dt>
          <dd>{{ profile.phone }}</dd>
          <dt>{{ tx("公司地址", "Company Address") }}</dt>
          <dd>{{ profile.company_address }}</dd>
        </dl>
      </div>
      
      <p class="hint">{{ tx("如需修改资料，请联系管理员", "To update company information, please contact the administrator") }}</p>
    </div>
    
    <div v-else class="empty">{{ tx("无法加载公司资料", "Unable to load company profile") }}</div>
  </div>
</template>

<style scoped>
.company-page {
  max-width: 800px;
}

.company-page h1 {
  font-family: var(--font-display);
  font-size: 32px;
  font-weight: 600;
  margin: 0 0 32px;
}

.loading,
.empty {
  text-align: center;
  padding: 60px 20px;
  font-size: 16px;
  color: rgba(27, 36, 33, 0.6);
}

.company-card {
  padding: 32px;
  background: white;
  border: 1px solid var(--line);
  border-radius: 8px;
}

.info-section h2 {
  font-family: var(--font-display);
  font-size: 28px;
  font-weight: 600;
  margin: 0 0 24px;
  color: var(--cord);
}

.info-section dl {
  display: grid;
  grid-template-columns: 180px 1fr;
  gap: 20px;
  margin-bottom: 32px;
}

.info-section dt {
  font-weight: 600;
  font-size: 14px;
  color: rgba(27, 36, 33, 0.6);
}

.info-section dd {
  margin: 0;
  font-size: 15px;
  color: var(--ink);
}

.hint {
  font-size: 14px;
  color: rgba(27, 36, 33, 0.6);
  margin: 0;
  padding-top: 24px;
  border-top: 1px solid var(--line);
}

@media (max-width: 700px) {
  .info-section dl {
    grid-template-columns: 1fr;
    gap: 8px;
  }

  .info-section dd {
    margin-bottom: 16px;
  }
}
</style>

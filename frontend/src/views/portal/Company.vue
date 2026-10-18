<script setup lang="ts">
import { useI18n } from "vue-i18n";
const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);
</script>

<template>
  <div class="page-placeholder">
    <h1>{{ tx("公司资料", "Company Profile") }}</h1>
    <p>{{ tx("公司资料页面开发中", "Company page under development") }}</p>
  </div>
</template>

<style scoped>
.page-placeholder {
  max-width: 1200px;
}
.page-placeholder h1 {
  font-family: var(--font-display);
  font-size: 32px;
  font-weight: 600;
  margin: 0 0 16px;
}
</style>

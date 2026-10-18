<script setup lang="ts">
import { useI18n } from "vue-i18n";
const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);
</script>

<template>
  <div class="page-placeholder">
    <h1>{{ tx("发票与付款", "Invoices & Payments") }}</h1>
    <p>{{ tx("发票与付款页面开发中", "Invoices page under development") }}</p>
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

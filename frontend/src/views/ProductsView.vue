<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { listProducts, materialPhoto, type ApiProduct } from "../api";

const { t, locale } = useI18n();
const products = ref<ApiProduct[]>([]);
const lang = computed(() => (locale.value === "en" ? "en" : "zh"));

onMounted(async () => {
  products.value = await listProducts();
});
</script>

<template>
  <main class="page">
    <h1 :class="{ 'title-zh': lang === 'zh' }">{{ t("products.title") }}</h1>
    <p class="lead">{{ t("products.lead") }}</p>
    <div class="gallery">
      <router-link
        v-for="product in products"
        :key="product.id"
        class="photo-panel"
        :to="`/products/${product.id}`"
      >
        <img :src="materialPhoto(product)" :alt="lang === 'en' ? product.name_en : product.name_zh" />
        <div class="photo-copy">
          <p v-if="product.sample" class="badge">{{ t("sample") }}</p>
          <h2>{{ lang === "en" ? product.name_en : product.name_zh }}</h2>
          <p>{{ lang === "en" ? product.description_en : product.description_zh }}</p>
        </div>
      </router-link>
    </div>
  </main>
</template>

<style scoped>
.page h1 {
  font-weight: 600;
  font-size: clamp(34px, 3.2vw, 46px);
  line-height: 1.25;
  letter-spacing: 0;
  margin: 20px 0 10px;
}
.page h1.title-zh { letter-spacing: 0.08em; }
</style>

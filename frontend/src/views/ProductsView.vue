<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { listProducts, type ApiProduct } from "../api";
import CatalogueGallery from '../components/CatalogueGallery.vue';

const { t, locale } = useI18n();
const products = ref<ApiProduct[]>([]);
const lang = computed(() => (locale.value === "en" ? "en" : "zh"));

onMounted(async () => {
  products.value = await listProducts();
});
</script>

<template>
  <main class="page">
    <header class="catalogue-intro">
      <p class="catalogue-label">VERA / {{ lang === 'zh' ? '材料与选型' : 'MATERIALS & OPTIONS' }}</p>
      <h1>{{ t("products.title") }}</h1>
      <p class="lead">{{ t("products.lead") }}</p>
    </header>
    <div class="gallery">
      <article
        v-for="product in products"
        :key="product.id"
        class="photo-panel"
      >
        <CatalogueGallery :product="product" :lang="lang" />
        <div class="photo-copy">
          <p v-if="product.sample" class="badge">{{ t("sample") }}</p>
          <h2>{{ lang === "en" ? product.name_en : product.name_zh }}</h2>
          <p>{{ lang === "en" ? product.description_en : product.description_zh }}</p>
          <router-link class="detail-link" :to="`/products/${product.id}`">{{ lang === 'zh' ? '查看规格与详情' : 'View specifications & details' }} ↗</router-link>
        </div>
      </article>
    </div>
  </main>
</template>

<style scoped>
.page{background:#faf9f6}.catalogue-intro{padding:32px 0 30px}.catalogue-label{font-size:11px;letter-spacing:.12em;color:#64766b;margin:0 0 12px}.page h1 {
  font-weight: 600;
  font-size: clamp(28px, 2.6vw, 38px);
  line-height: 1.25;
  letter-spacing: 0;
  margin: 0 0 10px;
}
.lead{font-size:15px;line-height:1.7;margin:0;color:#5d6d63}.detail-link{display:inline-block;border-bottom:1px solid var(--ink);padding:8px 0;margin-top:16px;font-size:14px}.photo-panel:nth-child(even) .catalogue-gallery{order:2}@media(max-width:900px){.photo-panel:nth-child(even) .catalogue-gallery{order:0}}@media(max-width:640px){.catalogue-intro{padding:24px 0}.page h1{font-size:28px}}
</style>

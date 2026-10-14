<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute } from "vue-router";
import { listProducts, materialPhoto, type ApiProduct } from "../api";

const { t, locale } = useI18n();
const route = useRoute();
const product = ref<ApiProduct | null>(null);
const missing = ref(false);
const lang = computed(() => (locale.value === "en" ? "en" : "zh"));
const photo = computed(() => (product.value ? materialPhoto(product.value) : ""));

async function load() {
  missing.value = false;
  product.value = null;
  const id = Number(route.params.id);
  if (!Number.isInteger(id)) {
    missing.value = true;
    return;
  }
  const items = await listProducts();
  product.value = items.find((item) => item.id === id) ?? null;
  missing.value = !product.value;
}

watch(() => route.params.id, load, { immediate: true });
</script>

<template>
  <main class="page">
    <template v-if="product">
      <img class="detail-photo" :src="photo" :alt="lang === 'en' ? product.name_en : product.name_zh" />
      <p class="badge">{{ t("sample") }}</p>
      <h1>{{ lang === "en" ? product.name_en : product.name_zh }}</h1>
      <div class="ticket">
        <div>
          <p>{{ t("placeholderArt") }}</p>
          <dl class="card">
            <div>
              <dt>{{ t("products.material") }}</dt>
              <dd>{{ lang === "en" ? product.material_en : product.material_zh }}</dd>
            </div>
            <div>
              <dt>{{ t("products.scene") }}</dt>
              <dd>{{ lang === "en" ? product.description_en : product.description_zh }}</dd>
            </div>
            <div>
              <dt>{{ t("products.size") }}</dt>
              <dd v-if="product.width_min||product.width_max||product.height_min||product.height_max">{{lang==='zh'?'宽度':'Width'}} {{product.width_min ?? '—'}}–{{product.width_max ?? '—'}} {{product.unit||'mm'}} · {{lang==='zh'?'高度':'Height'}} {{product.height_min ?? '—'}}–{{product.height_max ?? '—'}} {{product.unit||'mm'}}</dd><dd v-else>{{lang==='zh'?'按项目确认规格':'Specifications confirmed for each project'}}</dd>
            </div>
          <div v-if="product.colors?.length"><dt>{{lang==='zh'?'颜色选项':'Colour options'}}</dt><dd>{{product.colors.join(' / ')}}</dd></div><div v-if="product.controls?.length"><dt>{{lang==='zh'?'控制方式':'Controls'}}</dt><dd>{{product.controls.join(' / ')}}</dd></div></dl>
          <div class="actions">
            <router-link class="button" :to="`/inquiry?product=${product.id}`">
              {{ t("products.detail") }}
            </router-link>
          </div>
        </div>
      </div>
    </template>
    <template v-else-if="missing">
      <h1>{{ t("products.missing") }}</h1>
      <router-link to="/products">{{ t("nav.products") }}</router-link>
    </template>
  </main>
</template>

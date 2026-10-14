<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { materialPhoto, type ApiProduct } from '../api';
const props = defineProps<{ product: ApiProduct; lang: 'zh' | 'en' }>();
const images = computed(() => props.product.image_urls?.length ? props.product.image_urls : [materialPhoto(props.product)]);
const selected = ref(0);
const name = computed(() => props.lang === 'zh' ? props.product.name_zh : props.product.name_en);
watch(images, () => { selected.value = 0; });
</script>

<template>
  <figure class="catalogue-gallery">
    <router-link class="image-link" :to="`/products/${product.id}`" :aria-label="lang === 'zh' ? `查看${name}详情` : `View ${name} details`">
      <img class="main-image" :src="images[selected] || images[0]" :alt="`${name} — ${selected + 1}`" loading="lazy" />
    </router-link>
    <div v-if="images.length > 1" class="thumbnails" :aria-label="lang === 'zh' ? '产品图片' : 'Product images'">
      <button v-for="(url, index) in images" :key="url" type="button" :aria-pressed="selected === index" :aria-label="lang === 'zh' ? `查看${name}第${index + 1}张图片` : `View ${name} image ${index + 1}`" @click="selected = index">
        <img :src="url" alt="" loading="lazy" />
      </button>
      <span class="image-count">{{ selected + 1 }} / {{ images.length }}</span>
    </div>
  </figure>
</template>

<style scoped>
.catalogue-gallery{margin:0;min-width:0;background:#fff}.image-link{display:block}.main-image{display:block;width:100%;height:auto;aspect-ratio:4/3;object-fit:cover}.thumbnails{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:16px 20px 18px}.thumbnails button{background:transparent;padding:0 0 7px;border:0;border-bottom:2px solid transparent;min-height:0;width:76px;height:64px;opacity:.7;transition:opacity .15s}.thumbnails button:hover,.thumbnails button[aria-pressed=true]{opacity:1}.thumbnails button[aria-pressed=true]{border-bottom-color:var(--ink)}.thumbnails img{min-height:0;display:block;width:100%;height:100%;object-fit:cover}.image-count{font-size:11px;color:#7b837e;margin-left:auto;font-variant-numeric:tabular-nums}@media(max-width:640px){.thumbnails{gap:10px;padding:14px 16px}.thumbnails button{width:64px;height:56px}}
</style>

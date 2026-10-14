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
.catalogue-gallery{margin:0;min-width:0;background:#f1f0eb}.image-link{display:block}.main-image{display:block;width:100%;height:auto;aspect-ratio:4/3;object-fit:cover}.thumbnails{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:12px 16px}.thumbnails button{background:transparent;padding:3px;border:1px solid transparent;min-height:0;width:64px;height:48px}.thumbnails button[aria-pressed=true]{border-color:var(--ink)}.thumbnails img{min-height:0;display:block;width:100%;height:100%;object-fit:cover}.image-count{font-size:12px;color:#59655f;margin-left:auto;font-variant-numeric:tabular-nums}@media(max-width:640px){.thumbnails{gap:6px;padding:10px 16px}.thumbnails button{width:56px;height:42px}}
</style>

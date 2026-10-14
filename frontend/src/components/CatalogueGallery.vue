<script setup lang="ts">
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue';
import { materialPhoto, type ApiProduct } from '../api';
const props = defineProps<{ product: ApiProduct; lang: 'zh' | 'en' }>();
const images = computed(() => props.product.image_urls?.length ? props.product.image_urls : [materialPhoto(props.product)]);
const selected = ref(0);
const hovered = ref(false);
const focused = ref(false);
const paused = ref(false);
let timer: ReturnType<typeof setInterval> | undefined;
let motion: MediaQueryList | undefined;
function motionChanged() { if (motion?.matches) paused.value = true; }
function leaveFocus(event: FocusEvent) {
  focused.value = (event.currentTarget as HTMLElement).contains(event.relatedTarget as Node | null);
}
onMounted(() => {
  motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  motionChanged();
  motion.addEventListener('change', motionChanged);
  timer = setInterval(() => {
    if (images.value.length > 1 && !paused.value && !hovered.value && !focused.value && !document.hidden) selected.value = (selected.value + 1) % images.value.length;
  }, 5000);
});
onBeforeUnmount(() => { clearInterval(timer); motion?.removeEventListener('change', motionChanged); });
const name = computed(() => props.lang === 'zh' ? props.product.name_zh : props.product.name_en);
watch(images, () => { selected.value = 0; });
</script>

<template>
  <figure class="catalogue-gallery" @mouseenter="hovered = true" @mouseleave="hovered = false" @focusin="focused = true" @focusout="leaveFocus">
    <router-link class="image-link" :to="`/products/${product.id}`" :aria-label="lang === 'zh' ? `查看${name}详情` : `View ${name} details`">
      <img class="main-image" :src="images[selected] || images[0]" :alt="`${name} — ${selected + 1}`" loading="lazy" />
    </router-link>
    <div v-if="images.length > 1" class="thumbnails" :aria-label="lang === 'zh' ? '产品图片' : 'Product images'">
      <button v-for="(url, index) in images" :key="url" type="button" :aria-pressed="selected === index" :aria-label="lang === 'zh' ? `查看${name}第${index + 1}张图片` : `View ${name} image ${index + 1}`" @click="selected = index">
        <img :src="url" alt="" loading="lazy" />
      </button>
      <div class="playback"><span class="image-count">{{ selected + 1 }} / {{ images.length }}</span><button class="playback-button" type="button" :aria-label="paused ? (lang === 'zh' ? '播放图片轮播' : 'Play image slideshow') : (lang === 'zh' ? '暂停图片轮播' : 'Pause image slideshow')" :aria-pressed="paused" @click="paused = !paused">{{ paused ? (lang === 'zh' ? '播放' : 'Play') : (lang === 'zh' ? '暂停' : 'Pause') }}</button></div>
    </div>
  </figure>
</template>

<style scoped>
.catalogue-gallery{margin:0;min-width:0;background:#fff}.image-link{display:block}.main-image{display:block;width:100%;height:auto;aspect-ratio:4/3;object-fit:cover}.thumbnails{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:16px 20px 18px}.thumbnails button{background:transparent;padding:0 0 7px;border:0;border-bottom:2px solid transparent;min-height:0;width:76px;height:64px;opacity:.7;transition:opacity .15s}.thumbnails button:hover,.thumbnails button[aria-pressed=true]{opacity:1}.thumbnails button[aria-pressed=true]{border-bottom-color:var(--ink)}.thumbnails img{min-height:0;display:block;width:100%;height:100%;object-fit:cover}.playback{margin-left:auto;display:flex;gap:12px;align-items:center}.thumbnails .playback-button{width:auto;height:auto;min-height:44px;padding:0 4px;border:0;opacity:1;font-size:11px;font-weight:400;color:#59655f}.image-count{font-size:11px;color:#7b837e;font-variant-numeric:tabular-nums}@media(max-width:640px){.thumbnails{gap:10px;padding:14px 16px}.thumbnails button{width:64px;height:56px}}
</style>

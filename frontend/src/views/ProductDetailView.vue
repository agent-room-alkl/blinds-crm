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
const activeImage=ref(0);
const gallery=computed(()=>product.value?(product.value.image_urls?.length?product.value.image_urls:[materialPhoto(product.value)]):[]);
const photo=computed(()=>gallery.value[activeImage.value]||gallery.value[0]||'');

async function load() {
  activeImage.value=0;
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
      <div class="product-gallery"><img class="detail-photo" :src="photo" :alt="`${lang==='en'?product.name_en:product.name_zh} — ${activeImage+1}`"/><div v-if="gallery.length>1" class="product-thumbnails"><button v-for="(url,index) in gallery" :key="url" type="button" :class="{active:index===activeImage}" :aria-pressed="index===activeImage" :aria-label="lang==='zh'?`查看第${index+1}张产品图`:`View product image ${index+1}`" @click="activeImage=index"><img :src="url" alt="" loading="lazy"/></button></div><p class="gallery-caption">{{product.sample?(lang==='zh'?'原创产品示意图 · 实际材质与规格以确认样品为准':'Original product illustrations · Confirm materials and specifications against actual samples'):(lang==='zh'?'产品图片 · 以实际确认样品为准':'Product images · Refer to the approved samples')}}</p></div>
      <p v-if="product.sample" class="badge">{{ t("sample") }}</p>
      <h1>{{ lang === "en" ? product.name_en : product.name_zh }}</h1>
      <div class="ticket">
        <div>
          <p v-if="product.sample">{{ t("placeholderArt") }}</p>
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
            <router-link class="button" to="/portal">
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

<style scoped>.product-gallery{margin:0 0 24px}.product-gallery .detail-photo{width:100%;height:clamp(280px,48vw,600px);object-fit:cover;display:block}.product-thumbnails{display:flex;flex-wrap:wrap;gap:12px;margin-top:14px}.product-thumbnails button{background:white;border:1px solid #dfe3df;padding:3px;width:110px;height:76px;min-height:0}.product-thumbnails button.active{border:2px solid #0f6e5c}.product-thumbnails img{width:100%;height:100%;object-fit:cover;display:block}.gallery-caption{font-size:11px;color:#65736a;line-height:1.7;margin-top:10px}@media(max-width:640px){.product-thumbnails button{width:84px;height:60px}.product-gallery .detail-photo{height:300px}}</style>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { listProducts, materialPhoto, type ApiProduct } from '../api';
const { locale } = useI18n();
const zh = computed(() => locale.value === 'zh');
const products = ref<ApiProduct[]>([]);
onMounted(async () => { products.value = await listProducts(); });
</script>
<template>
  <main class="page catalogue-page">
    <header class="catalogue-intro"><p class="eyebrow">VERA / {{zh?'批发产品目录':'WHOLESALE PRODUCT CATALOGUE'}}</p><h1>{{zh?'产品系列与规格':'Product ranges & specifications'}}</h1><p>{{zh?'按材料查看系列参数、饰面选项和质保年限。':'Compare material ranges, finish options and warranty periods.'}}</p></header>
    <nav class="range-tabs" :aria-label="zh?'产品系列':'Product ranges'"><router-link v-for="(product,index) in products" :key="product.id" :to="`/products/${product.id}`"><span>0{{index+1}}</span>{{zh?product.name_zh:product.name_en}}</router-link></nav>
    <section class="range-list"><article v-for="(product,index) in products" :key="product.id" class="range-row"><router-link :to="`/products/${product.id}`" class="range-image"><img :src="materialPhoto(product)" :alt="zh?product.name_zh:product.name_en" loading="lazy"></router-link><div class="range-detail"><p class="eyebrow">RANGE 0{{index+1}} / {{zh?product.material_zh:product.material_en}}</p><h2>{{zh?product.name_zh:product.name_en}}</h2><p>{{zh?product.description_zh:product.description_en}}</p><dl><div><dt>{{zh?'材料':'Material'}}</dt><dd>{{zh?product.material_zh:product.material_en}}</dd></div><div><dt>{{zh?'叶片规格':'Louvre widths'}}</dt><dd>63 · 76 · 89 · 114 mm</dd></div></dl><router-link class="detail-link" :to="`/products/${product.id}`">{{zh?'打开产品规格':'View product specifications'}} ↗</router-link></div></article></section>
  </main>
</template>
<style scoped>
.catalogue-page{padding:0 0 60px;background:var(--paper)}.catalogue-intro{padding:clamp(44px,7vw,80px) clamp(24px,7vw,96px) 32px;background:#edf1f2}.eyebrow{font-size:10px;letter-spacing:.14em;color:#586b77;font-weight:700;margin:0 0 12px}.catalogue-intro h1{font:600 clamp(34px,4.5vw,56px)/1.12 var(--font-display);margin:0 0 12px}.catalogue-intro>p:last-child{color:#5a6870;margin:0;font-size:14px}.range-tabs{position:sticky;top:0;z-index:10;display:flex;overflow-x:auto;background:#fff;border-bottom:1px solid var(--line);padding:0 clamp(18px,5vw,72px)}.range-tabs a{flex:1;min-width:max-content;gap:9px;padding:14px 18px;border-bottom:2px solid transparent;font-size:12px}.range-tabs a span{font-size:10px;color:#78858c}.range-tabs a:hover,.range-tabs a.router-link-active{background:#edf1f2;border-bottom-color:var(--frame)}.range-list{max-width:1440px;margin:auto;padding:22px clamp(20px,5vw,72px)}.range-row{display:grid;grid-template-columns:minmax(260px,.9fr) 1.1fr;gap:clamp(24px,5vw,72px);padding:28px 0;border-bottom:1px solid var(--line)}.range-image img{display:block;width:100%;height:100%;min-height:280px;max-height:390px;object-fit:cover}.range-detail{align-self:center}.range-detail h2{font:600 clamp(27px,3vw,38px)/1.15 var(--font-display);margin:0 0 12px}.range-detail>p:not(.eyebrow){font-size:13px;line-height:1.75;color:#5b6971;max-width:590px}.range-detail dl{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:22px 0}.range-detail dl div{padding-top:10px;border-top:1px solid var(--line)}dt{font-size:10px;color:#67757d}dd{font-size:13px;margin:4px 0 0}.detail-link{display:inline-flex;border-bottom:1px solid;padding:8px 0;font-size:12px}.detail-link:hover{color:#526b7b}@media(max-width:700px){.range-row{grid-template-columns:1fr;gap:18px;padding:20px 0}.range-image img{height:240px;min-height:0}.range-tabs{padding:0 10px}.range-tabs a{padding:12px 10px}.range-detail dl{gap:8px}}
</style>

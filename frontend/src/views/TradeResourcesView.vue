<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { listProducts, type ApiProduct } from '../api';
const { locale } = useI18n();
const zh = computed(() => locale.value === 'zh');
const products = ref<ApiProduct[]>([]);
onMounted(async()=>{try{products.value=await listProducts()}catch{/* Keep the resource page readable if the catalogue API is offline. */}});
</script>
<template>
  <main class="page resources-page">
    <header class="resources-head"><p class="eyebrow">VERA / TRADE RESOURCES</p><h1>{{zh?'批发客户资料':'Trade resources'}}</h1><p>{{zh?'产品规格与正式文件集中查看。':'Product specifications and approved trade documents.'}}</p></header>
    <section class="resource-section"><h2>{{zh?'产品资料':'Product documents'}}</h2><p class="intro">{{zh?'每个系列的页面均列出画册与质保文件位置。正式 PDF 文件尚未提供，确认文件后即可在这里下载。':'Each range has a place for its brochure and warranty PDF. The final approved PDFs have not yet been supplied; download links will be enabled when they are available.'}}</p>
      <div class="resource-list"><article v-for="(product,index) in products" :key="product.id"><div><span class="index">0{{index+1}}</span><h3>{{zh?product.name_zh:product.name_en}}</h3><small>{{zh?product.material_zh:product.material_en}}</small></div><div class="resource-actions"><span>{{zh?'产品画册 · 待提供':'Brochure · Awaiting file'}}</span><span>{{zh?'质保文件 · 待提供':'Warranty · Awaiting file'}}</span><router-link :to="`/products/${product.id}`">{{zh?'查看产品页':'Open product page'}} ↗</router-link></div></article></div>
    </section>
    <section class="resource-note"><h2>{{zh?'正式文件':'Approved documents'}}</h2><p>{{zh?'为确保客户获得有效的产品与质保信息，此处只发布已确认的正式 PDF。':''}}{{!zh?'Only confirmed, final PDF files will be published here so trade customers receive valid product and warranty information.':''}}</p></section>
  </main>
</template>
<style scoped>
.resources-page{padding:0 0 64px;background:var(--paper)}.resources-head{padding:clamp(46px,7vw,84px) clamp(24px,7vw,96px) 40px;background:#edf1f2}.eyebrow{font-size:10px;letter-spacing:.15em;font-weight:700;color:#586b77}.resources-head h1{font:600 clamp(36px,5vw,58px)/1.12 var(--font-display);margin:12px 0}.resources-head>p:last-child{margin:0;color:#5c6a72;font-size:14px}.resource-section{max-width:1180px;margin:auto;padding:48px clamp(24px,5vw,64px)}.resource-section h2,.resource-note h2{font:600 28px var(--font-display);margin:0}.intro{max-width:720px;color:#5b6971;font-size:13px;line-height:1.8}.resource-list{border-top:1px solid var(--line);margin-top:22px}.resource-list article{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:18px 0;border-bottom:1px solid var(--line)}.resource-list article>div:first-child{display:grid;grid-template-columns:34px 1fr;align-items:baseline;min-width:180px}.index{grid-row:span 2;font-size:10px;color:#718089}.resource-list h3{font-size:15px;margin:0}.resource-list small{grid-column:2;color:#69767d;margin-top:4px}.resource-actions{display:flex;align-items:center;gap:12px;flex-wrap:wrap;justify-content:end}.resource-actions span{font-size:10px;color:#64727a;border:1px solid var(--line);padding:6px 8px}.resource-actions a{font-size:11px;border-bottom:1px solid;padding:6px 0}.resource-note{margin:0 clamp(24px,7vw,96px);padding:26px 30px;background:#e8eef0}.resource-note p{font-size:12px;line-height:1.7;color:#56656d;margin-bottom:0}@media(max-width:700px){.resource-section{padding-top:36px}.resource-list article{align-items:flex-start;flex-direction:column}.resource-actions{justify-content:start}.resource-note{padding:22px}}
</style>

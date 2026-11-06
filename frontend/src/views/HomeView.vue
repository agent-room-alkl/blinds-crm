<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { listProducts, materialPhoto, type ApiProduct } from '../api';
const { locale } = useI18n();
const zh = computed(() => locale.value === 'zh');
const products = ref<ApiProduct[]>([]);
const error = ref(false);
onMounted(async () => { try { products.value = await listProducts(); } catch { error.value = true; } });
</script>

<template>
  <main class="trade-home">
    <section class="trade-intro">
      <p class="eyebrow">VERA / {{ zh ? '批发产品目录' : 'WHOLESALE PRODUCT CATALOGUE' }}</p>
      <h1>{{ zh ? '产品参数与项目资料' : 'Product specifications\n& trade information' }}</h1>
      <p>{{ zh ? '面向百叶窗批发客户。查看材质、叶片规格、饰面与质保年限；项目尺寸和供货条件由团队确认。' : 'For wholesale blind partners. Review materials, louvre sizes, finishes and warranty periods. Project dimensions and supply terms are confirmed by our team.' }}</p>
      <div class="intro-actions"><router-link class="button" to="/portal">{{ zh ? 'Trade Login' : 'Trade Login' }} ↗</router-link><router-link class="outline-button" to="/products">{{ zh ? '查看全部产品' : 'Browse all products' }}</router-link></div>
      <div class="catalogue-meta"><span>{{ zh ? '5 个产品系列' : '5 product ranges' }}</span><span>{{ zh ? 'PVC · 松木 · 椴木 · 白蜡木' : 'PVC · Pine · Basswood · Ashwood' }}</span><span>{{ zh ? '批发供货' : 'Wholesale supply' }}</span></div>
    </section>
    <section class="trade-products">
      <header><div><p class="eyebrow">01 / {{ zh ? '产品系列' : 'PRODUCT RANGES' }}</p><h2>{{ zh ? '按材质选择系列' : 'Select a range by material' }}</h2></div><router-link to="/products">{{ zh ? '产品总览' : 'Product overview' }} ↗</router-link></header>
      <p v-if="error" role="alert">{{ zh ? '暂时无法加载产品目录。' : 'The product catalogue is temporarily unavailable.' }}</p>
      <div class="range-grid"><router-link v-for="(product,index) in products" :key="product.id" :to="`/products/${product.id}`" class="range-card"><img :src="materialPhoto(product)" :alt="zh ? product.name_zh : product.name_en" loading="lazy"><div class="range-label"><span>0{{ index + 1 }}</span><h3>{{ zh ? product.name_zh : product.name_en }}</h3><b>↗</b></div><p>{{ zh ? product.material_zh : product.material_en }}</p></router-link></div>
    </section>
    <section class="trade-notes"><div><p class="eyebrow">02 / {{ zh ? '供货资料' : 'TRADE SUPPORT' }}</p><h2>{{ zh ? '规格、订单与文件' : 'Specifications, ordering & documents' }}</h2></div><div class="notes-copy"><p>{{ zh ? '产品页面列出当前可确认的规格。项目尺寸、可用配置和供货条件请通过 Trade Login 提交订单，或联系团队核实。' : 'Each product page lists currently confirmed specifications. Use Trade Login to submit project requirements, or contact the team to confirm dimensions, configurations and supply terms.' }}</p><router-link class="outline-button" to="/trade-resources">{{ zh ? '打开 Trade Resources' : 'Open Trade Resources' }} ↗</router-link></div></section>
  </main>
</template>

<style scoped>
.trade-home{background:var(--paper);color:var(--ink)}.trade-intro{padding:clamp(56px,9vw,120px) clamp(24px,8vw,120px) 34px;background:linear-gradient(115deg,#edf1f2,#f4f6f5 70%);border-bottom:1px solid var(--line)}.eyebrow{font-size:10px;font-weight:700;letter-spacing:.16em;color:#536674;margin:0 0 18px}.trade-intro h1,.trade-products h2,.trade-notes h2{font-family:var(--font-display);font-weight:600;letter-spacing:-.02em}.trade-intro h1{font-size:clamp(38px,5.4vw,68px);line-height:1.08;white-space:pre-line;margin:0;max-width:850px}.trade-intro>p:not(.eyebrow){font-size:15px;line-height:1.8;max-width:680px;color:#52616a;margin:22px 0}.intro-actions{display:flex;gap:12px;flex-wrap:wrap;margin:26px 0 56px}.outline-button{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:10px 18px;border:1px solid var(--frame);font-size:13px;font-weight:650}.outline-button:hover{background:var(--frame);color:white}.catalogue-meta{display:flex;gap:0;flex-wrap:wrap;border-top:1px solid var(--line);padding-top:18px;color:#53616a;font-size:11px;letter-spacing:.04em}.catalogue-meta span{padding:0 22px;border-right:1px solid var(--line)}.catalogue-meta span:first-child{padding-left:0}.catalogue-meta span:last-child{border:0}.trade-products{max-width:1440px;margin:auto;padding:64px clamp(24px,5vw,72px) 78px}.trade-products header{display:flex;align-items:end;justify-content:space-between;gap:24px;margin-bottom:26px}.trade-products h2,.trade-notes h2{font-size:clamp(28px,3.5vw,42px);margin:0}.trade-products header>a{font-size:12px;border-bottom:1px solid;padding:8px 0}.range-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:14px}.range-card{display:block;min-width:0;border:1px solid var(--line);background:#fff}.range-card img{display:block;width:100%;aspect-ratio:4/3;object-fit:cover;background:#e5e9e9}.range-label{display:flex;align-items:baseline;gap:8px;padding:14px 14px 0}.range-label span{font-size:10px;color:#687781}.range-label h3{margin:0;flex:1;font-size:16px;font-weight:650}.range-label b{font-weight:400;color:#687781}.range-card>p{font-size:12px;color:#64727a;margin:8px 14px 16px}.range-card:hover{border-color:#354552;box-shadow:0 8px 24px rgba(40,52,58,.1)}.range-card:hover .range-label b{transform:translate(2px,-2px)}.trade-notes{display:grid;grid-template-columns:1fr 1fr;gap:64px;padding:54px clamp(24px,8vw,120px);background:#e8eef0;border-top:1px solid var(--line)}.notes-copy p{max-width:620px;color:#53616a;line-height:1.8;margin:0 0 20px}.notes-copy .outline-button{background:transparent}@media(max-width:900px){.range-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.trade-notes{gap:32px}}@media(max-width:600px){.trade-intro{padding-top:52px}.intro-actions{margin-bottom:36px}.catalogue-meta{gap:10px}.catalogue-meta span{padding:0 10px 0 0;border:0}.trade-products{padding-top:42px}.trade-products header{align-items:start;flex-direction:column}.range-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.range-label{padding:10px 10px 0}.range-label h3{font-size:14px}.range-card>p{margin:6px 10px 12px}.trade-notes{grid-template-columns:1fr;gap:16px;padding-top:38px;padding-bottom:42px}}
</style>

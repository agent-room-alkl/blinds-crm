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
const verifiedSpecs = computed(() => {
  const id = product.value?.id;
  const ranges:Record<number,{warranty:string;finishes:string;use:string}> = {
    5:{warranty:'5 years',finishes:'White 01',use:'Moisture resistant; suitable for kitchens and bathrooms.'},
    4:{warranty:'20 years',finishes:'White 01 · Dusk 02 · Soft Glow 03 · Old Moon 04 · Oyster 05 · Sea Pearl 06 · Picaso 07 · Chalk 08',use:'Moisture resistant; suitable for kitchens and bathrooms.'},
    6:{warranty:'5 years',finishes:'White 01 · Dusk 02 · Soft Glow 03 · Old Moon 04 · Oyster 05 · Sea Pearl 06 · Picaso 07 · Chalk 08',use:'Light pine grain; keep dry and dust regularly.'},
    7:{warranty:'10 years',finishes:'White 01 · Dusk 02 · Soft Glow 03 · Old Moon 04 · Oyster 05 · Sea Pearl 06 · Picaso 07 · Chalk 08 · Golden Oak 61 · Fruitwood 62 · Old Mahogany 63 · Coffee Bean 64 · BlackWalnut 65 · Light Ash 66 · Limed 67 · Natural 68 · Rustic Gray 69 · Provence Blue 70',use:'Smooth painted basswood surface.'},
    8:{warranty:'10 years',finishes:'Golden Oak 61 · Fruitwood 62 · Old Mahogany 63 · Coffee Bean 64 · BlackWalnut 65 · Light Ash 66 · Limed 67 · Natural 68 · Rustic Gray 69 · Provence Blue 70',use:'Premium ashwood with natural, stained or oiled finishes.'}
  };
  return id ? ranges[id] : undefined;
});

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
          <dl v-if="verifiedSpecs" class="verified-specs">
            <div><dt>{{lang==='zh'?'叶片宽度':'Louvre widths'}}</dt><dd>63 · 76 · 89 · 114 mm</dd></div>
            <div><dt>{{lang==='zh'?'饰面选项':'Finish options'}}</dt><dd>{{verifiedSpecs.finishes}}</dd></div>
            <div><dt>{{lang==='zh'?'质保年限':'Warranty period'}}</dt><dd>{{verifiedSpecs.warranty}}</dd></div>
            <div><dt>{{lang==='zh'?'使用与维护':'Use & care'}}</dt><dd>{{verifiedSpecs.use}}</dd></div>
          </dl>
          <section class="document-panel" aria-labelledby="product-documents-title">
            <p class="eyebrow">{{lang==='zh'?'产品资料':'PRODUCT DOCUMENTS'}}</p>
            <h2 id="product-documents-title">{{lang==='zh'?'下载与文件':'Downloads & documents'}}</h2>
            <div class="document-row"><span><strong>{{lang==='zh'?'产品画册':'Product brochure'}}</strong><small>{{lang==='zh'?'PDF · 正式文件待提供':'PDF · Approved file to be supplied'}}</small></span><span class="file-pending">{{lang==='zh'?'待发布':'Coming soon'}}</span></div>
            <div class="document-row"><span><strong>{{lang==='zh'?'质保文件':'Warranty document'}}</strong><small>{{lang==='zh'?'PDF · 正式文件待提供':'PDF · Approved file to be supplied'}}</small></span><span class="file-pending">{{lang==='zh'?'待发布':'Coming soon'}}</span></div>
            <p class="document-note">{{lang==='zh'?'此处仅会提供经确认的正式文件。':'Only approved, final documents will be published here.'}}</p>
          </section>
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

<style scoped>.product-gallery{margin:0 0 24px}.product-gallery .detail-photo{width:100%;height:clamp(280px,48vw,600px);object-fit:cover;display:block}.product-thumbnails{display:flex;flex-wrap:wrap;gap:12px;margin-top:14px}.product-thumbnails button{background:white;border:1px solid #dfe3df;padding:3px;width:110px;height:76px;min-height:0}.product-thumbnails button.active{border:2px solid var(--frame)}.product-thumbnails img{width:100%;height:100%;object-fit:cover;display:block}.gallery-caption{font-size:11px;color:#65736a;line-height:1.7;margin-top:10px}.verified-specs{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 24px;border-top:1px solid var(--line);margin-top:22px}.verified-specs>div{padding:14px 0;border-bottom:1px solid var(--line)}.verified-specs dt{font-size:11px;color:#65747d;font-weight:700;letter-spacing:.04em}.verified-specs dd{margin:5px 0 0;font-size:13px;line-height:1.7}.document-panel{margin:28px 0;padding:22px;border:1px solid var(--line);background:#f0f3f3}.document-panel .eyebrow{margin:0 0 6px;font-size:10px;letter-spacing:.12em;color:#5f707a}.document-panel h2{font:600 22px var(--font-display);margin:0 0 12px}.document-row{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:13px 0;border-top:1px solid var(--line)}.document-row strong,.document-row small{display:block}.document-row strong{font-size:13px}.document-row small{font-size:11px;color:#66757d;margin-top:4px}.file-pending{font-size:10px;color:#66757d;border:1px solid #c5ced2;padding:5px 8px;white-space:nowrap}.document-note{font-size:11px;line-height:1.6;color:#66757d;margin:12px 0 0}@media(max-width:640px){.product-thumbnails button{width:84px;height:60px}.product-gallery .detail-photo{height:300px}.verified-specs{grid-template-columns:1fr}.document-panel{padding:16px}}</style>

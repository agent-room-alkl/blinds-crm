<script setup lang="ts">
import {ref,reactive,computed,onMounted,onBeforeUnmount,nextTick} from 'vue';
import {useI18n} from 'vue-i18n';
import {request} from '../crm-api';
import ProductPicture from './ProductPicture.vue';
import {materialPhoto,type ApiProduct} from '../api';
const props=defineProps<{admin:boolean}>();const emit=defineEmits<{updated:[]}>();
const {locale}=useI18n();const tx=(z:string,e:string)=>locale.value==='zh'?z:e;
type Product=ApiProduct&{published:boolean;image_url:string;image_urls:string[];unit:string;width_min:number|null;width_max:number|null;height_min:number|null;height_max:number|null;colors:string[];controls:string[]};
const products=ref<Product[]>([]),query=ref(''),chosen=ref<number|null>(null),busy=ref(false),error=ref(''),notice=ref(''),adding=ref(false);
const blank=()=>({name_zh:'',name_en:'',material_zh:'',material_en:'',description_zh:'',description_en:'',category:'aluminium',image_url:'',image_urls:[] as string[],sample:true,published:false,unit:'mm',width_min:null as number|null,width_max:null as number|null,height_min:null as number|null,height_max:null as number|null});
const form=reactive(blank()),colors=ref(''),controls=ref(''),maxImageBytes=ref(5*1024*1024);
const filtered=computed(()=>products.value.filter(p=>[p.name_en,p.name_zh,p.category].join(' ').toLowerCase().includes(query.value.toLowerCase())));
const previewIndex=ref(0);
const preview=computed(()=>form.image_urls[previewIndex.value]||form.image_urls[0]||form.image_url||'');
function cover(index:number){const [url]=form.image_urls.splice(index,1);form.image_urls.unshift(url);form.image_url=url;previewIndex.value=0}
function removeImage(index:number){form.image_urls.splice(index,1);form.image_url=form.image_urls[0]||'';previewIndex.value=0}
function choose(p:Product){previewIndex.value=0;chosen.value=p.id;adding.value=false;Object.assign(form,blank(),p,{image_urls:[...(p.image_urls||[])]});colors.value=p.colors.join(', ');controls.value=p.controls.join(', ');error.value='';notice.value=''}
function add(){previewIndex.value=0;chosen.value=null;adding.value=true;Object.assign(form,blank());colors.value='';controls.value='';notice.value='';error.value=''}
async function load(){const [items,config]=await Promise.all([request<Product[]>('admin/products'),request<{max_bytes:number}>('admin/image-upload-config')]);products.value=items;maxImageBytes.value=config.max_bytes;if(!adding.value&&chosen.value!=null){const p=products.value.find(p=>p.id===chosen.value);if(p)choose(p);else chosen.value=null}}
async function save(){busy.value=true;error.value='';try{const values={...form,image_url:form.image_urls[0]||'',width_min:form.width_min==null||String(form.width_min)===''?null:Number(form.width_min),width_max:form.width_max==null||String(form.width_max)===''?null:Number(form.width_max),height_min:form.height_min==null||String(form.height_min)===''?null:Number(form.height_min),height_max:form.height_max==null||String(form.height_max)===''?null:Number(form.height_max),colors:colors.value.split(/[,，\n]/).map(s=>s.trim()).filter(Boolean),controls:controls.value.split(/[,，\n]/).map(s=>s.trim()).filter(Boolean)};const p=await request<Product>(chosen.value?`admin/products/${chosen.value}`:'admin/products',values);chosen.value=p.id;adding.value=false;await load();notice.value=tx('已保存。官网重新加载后显示同一产品资料。','Saved. Reload the website to see the same product details.');emit('updated')}catch(e){error.value=e instanceof Error?e.message:String(e)}finally{busy.value=false}}
async function upload(event:Event){const input=event.target as HTMLInputElement,files=Array.from(input.files||[]);if(!files.length)return;if(form.image_urls.length+files.length>12){error.value=tx('最多12张图片。','Up to 12 images.');input.value='';return}if(files.some(file=>file.size>maxImageBytes.value||!['image/png','image/jpeg','image/webp'].includes(file.type))){error.value=tx(`每张请选择${maxImageBytes.value/1024/1024}MB以内PNG、JPEG或WebP。`,`Each image must be PNG, JPEG or WebP, up to ${maxImageBytes.value/1024/1024} MB.`);input.value='';return}busy.value=true;error.value='';try{for(const file of files){const data=await new Promise<string>((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(String(r.result).split(',')[1]);r.onerror=()=>reject(new Error('Image could not be read'));r.readAsDataURL(file)});const result=await request<{image_url:string}>('admin/product-images',{data,content_type:file.type});form.image_urls.push(result.image_url);form.image_url=form.image_urls[0]}notice.value=tx('图片已加入图集，保存产品后应用。','Images added to the gallery. Save the product to apply them.')}catch(e){error.value=e instanceof Error?e.message:String(e)}finally{busy.value=false;input.value=''}}

const open=computed(()=>chosen.value!=null||adding.value);
const drawer=ref<HTMLElement|null>(null);
function close(){chosen.value=null;adding.value=false;error.value='';notice.value=''}
function pick(p:Product){choose(p);nextTick(()=>drawer.value?.focus())}
function create(){add();nextTick(()=>drawer.value?.focus())}
function range(p:Product,min:number|null,max:number|null){if(min==null&&max==null)return '—';return `${min??'?'} – ${max??'?'}`}
const stats=computed(()=>({total:products.value.length,live:products.value.filter(p=>p.published).length}));
function onKey(e:KeyboardEvent){if(e.key==='Escape'&&open.value&&!busy.value)close()}
onMounted(async()=>{window.addEventListener('keydown',onKey);try{await load()}catch(e){error.value=e instanceof Error?e.message:String(e)}});
onBeforeUnmount(()=>window.removeEventListener('keydown',onKey));
</script>
<template>
<div class="pm">
<header class="pm-head">
  <div><p class="pm-eyebrow">VERA · {{tx('产品目录','CATALOGUE')}}</p><h2>{{tx('产品目录','Product catalogue')}}</h2><p class="pm-sub">{{tx('官网与报价共用同一份资料；修改展示信息不会改动已保存订单的价格。','The website and quotes share these records. Editing display details never changes saved order prices.')}}</p></div>
  <div class="pm-tools"><div class="pm-count" aria-live="polite"><strong>{{stats.total}}</strong><span>{{tx('个产品','products')}}</span><i></i><strong>{{stats.live}}</strong><span>{{tx('官网展示中','live')}}</span></div>
  <label class="pm-search"><span class="sr">{{tx('搜索产品','Search products')}}</span><input v-model="query" type="search" :placeholder="tx('搜索名称或分类','Search name or category')"/></label>
  <button v-if="admin" type="button" class="pm-primary" :disabled="busy" @click="create">＋ {{tx('新增产品','Add product')}}</button></div>
</header>
<p v-if="error&&!open" class="alert" role="alert">{{error}}</p>

<ul class="pm-grid" v-if="filtered.length">
  <li v-for="p in filtered" :key="p.id">
    <button type="button" class="pm-card" :class="{current:chosen===p.id}" @click="pick(p)" :aria-label="tx(`编辑 ${p.name_zh}`,`Edit ${p.name_en}`)">
      <span class="pm-cover"><ProductPicture :src="materialPhoto(p)" :alt="locale==='zh'?p.name_zh:p.name_en"/><span class="pm-chip" :class="p.published?'on':'off'">{{p.published?tx('官网展示','Live'):tx('未展示','Hidden')}}</span><span v-if="p.sample" class="pm-chip sample">{{tx('示例','Sample')}}</span></span>
      <span class="pm-body">
        <strong>{{locale==='zh'?p.name_zh:p.name_en}}</strong>
        <small>{{locale==='zh'?p.material_zh:p.material_en}} · #{{p.id}}</small>
        <span class="pm-specs"><span><em>{{tx('宽','W')}}</em>{{range(p,p.width_min,p.width_max)}}</span><span><em>{{tx('高','H')}}</em>{{range(p,p.height_min,p.height_max)}}</span><span class="unit">{{p.unit||'mm'}}</span></span>
        <span class="pm-tags"><span v-for="c in (p.colors||[]).slice(0,3)" :key="c">{{c}}</span><span v-if="(p.colors||[]).length>3" class="more">+{{p.colors.length-3}}</span><span v-if="!(p.colors||[]).length" class="none">{{tx('未设置颜色','No colours set')}}</span></span>
      </span>
    </button>
  </li>
</ul>
<p v-else class="pm-empty">{{tx('没有匹配的产品','No matching products')}}</p>

<div v-if="open" class="pm-backdrop" @click="close" aria-hidden="true"></div>
<aside v-if="open" ref="drawer" class="pm-drawer" role="dialog" aria-modal="true" :aria-label="adding?tx('新增产品','Add product'):tx('编辑产品','Edit product')" tabindex="-1">
  <header class="pm-drawer-head"><div><p class="pm-eyebrow">{{adding?tx('新产品','NEW PRODUCT'):`PRODUCT #${chosen}`}} · {{admin?tx('管理员可编辑','Administrator access'):tx('销售只读','Read-only for sales')}}</p><h3>{{adding?tx('新增产品','Add product'):(locale==='zh'?form.name_zh:form.name_en)}}</h3></div><button type="button" class="pm-close" @click="close" :aria-label="tx('关闭','Close')">✕</button></header>
  <p v-if="error" class="alert" role="alert">{{error}}</p><p v-if="notice" class="success" role="status">{{notice}}</p>
  <form @submit.prevent="save" class="pm-form">
    <section class="pm-sec"><h4><b>1</b>{{tx('图片','Images')}}</h4>
      <div class="pm-stage"><ProductPicture v-if="preview" :src="preview" :alt="locale==='zh'?form.name_zh:form.name_en"/><span v-else class="pm-noimg">{{tx('还没有图片','No image yet')}}</span></div>
      <div class="pm-thumbs"><article v-for="(url,index) in form.image_urls" :key="url" :class="{active:previewIndex===index}"><button type="button" class="pm-thumb" :aria-label="tx(`预览第${index+1}张产品图`,`Preview product image ${index+1}`)" :aria-pressed="previewIndex===index" @click="previewIndex=index"><ProductPicture :src="url" alt=""/></button><small>{{index===0?tx('封面','Cover'):index+1}}</small><div v-if="admin"><button v-if="index>0" type="button" class="pm-mini" @click="cover(index)">{{tx('设为封面','Set cover')}}</button><button type="button" class="pm-mini danger" @click="removeImage(index)" :aria-label="tx(`移除第${index+1}张图片`,`Remove image ${index+1}`)">{{tx('移除','Remove')}}</button></div></article></div>
      <label v-if="admin" class="pm-upload"><span>＋ {{tx('添加产品图片','Add product images')}}</span><small>{{tx(`PNG / JPEG / WebP · 最大${maxImageBytes/1024/1024}MB · 最多12张`,`PNG / JPEG / WebP · up to ${maxImageBytes/1024/1024} MB · max 12`)}}</small><input type="file" multiple accept="image/png,image/jpeg,image/webp" @change="upload" :disabled="busy"/></label>
    </section>
    <section class="pm-sec"><h4><b>2</b>{{tx('基本资料','Details')}}</h4>
      <div class="pm-pair"><label>{{tx('中文名称','Chinese name')}}<input v-model="form.name_zh" required maxlength="160" :readonly="!admin"/></label><label>{{tx('英文名称','English name')}}<input v-model="form.name_en" required maxlength="160" :readonly="!admin"/></label></div>
      <div class="pm-pair"><label>{{tx('中文材质','Material in Chinese')}}<input v-model="form.material_zh" required maxlength="100" :readonly="!admin"/></label><label>{{tx('英文材质','Material in English')}}<input v-model="form.material_en" required maxlength="100" :readonly="!admin"/></label></div>
      <label>{{tx('分类','Category')}}<select v-model="form.category" :disabled="!admin"><option value="aluminium">{{tx('铝百叶','Aluminium blinds')}}</option><option value="timber">{{tx('木百叶','Timber blinds')}}</option><option value="composite">{{tx('复合百叶','Composite blinds')}}</option><option value="other">{{tx('其他','Other')}}</option></select></label>
      <div class="pm-toggles"><label class="pm-toggle"><input type="checkbox" v-model="form.published" :disabled="!admin"/><span>{{tx('在官网展示','Show on website')}}</span></label><label class="pm-toggle"><input type="checkbox" v-model="form.sample" :disabled="!admin"/><span>{{tx('示例产品','Sample product')}}</span></label></div>
    </section>
    <section class="pm-sec"><h4><b>3</b>{{tx('描述','Description')}}</h4>
      <div class="pm-pair"><label>{{tx('中文描述','Chinese description')}}<textarea v-model="form.description_zh" maxlength="3000" :readonly="!admin"/></label><label>{{tx('英文描述','English description')}}<textarea v-model="form.description_en" maxlength="3000" :readonly="!admin"/></label></div>
    </section>
    <section class="pm-sec"><h4><b>4</b>{{tx('规格范围','Size range')}}</h4>
      <div class="pm-dims"><label>{{tx('单位','Unit')}}<select v-model="form.unit" :disabled="!admin"><option>mm</option><option>inch</option></select></label><label>{{tx('最小宽度','Minimum width')}}<input v-model.number="form.width_min" type="number" min="0.01" step="any" :readonly="!admin"/></label><label>{{tx('最大宽度','Maximum width')}}<input v-model.number="form.width_max" type="number" min="0.01" step="any" :readonly="!admin"/></label><label>{{tx('最小高度','Minimum height')}}<input v-model.number="form.height_min" type="number" min="0.01" step="any" :readonly="!admin"/></label><label>{{tx('最大高度','Maximum height')}}<input v-model.number="form.height_max" type="number" min="0.01" step="any" :readonly="!admin"/></label></div>
      <div class="pm-pair"><label>{{tx('可选颜色 · 用逗号分隔','Colour options · separate with commas')}}<input v-model="colors" :readonly="!admin"/></label><label>{{tx('控制方式 · 用逗号分隔','Controls · separate with commas')}}<input v-model="controls" :readonly="!admin"/></label></div>
      <p class="pm-hint">{{tx('范围可留空，实际项目规格与单价在报价中确认。修改目录不改变历史报价和订单。','Ranges may be left blank. Confirm project specifications and pricing in the quote. Catalogue changes do not alter past quotes or orders.')}}</p>
    </section>
    <footer class="pm-save"><button v-if="admin" type="submit" class="pm-primary" :disabled="busy">{{busy?tx('保存中…','Saving…'):tx('保存产品','Save product')}}</button><button type="button" class="pm-ghost" @click="close" :disabled="busy">{{admin?tx('取消','Cancel'):tx('关闭','Close')}}</button><span v-if="admin">{{form.published?tx('保存后供官网展示','Will be visible on the website'):tx('保存为未展示产品','Will remain hidden from the website')}}</span></footer>
  </form>
</aside>
</div>
</template>
<style scoped>
.pm{display:block;color:#1b2421}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.pm-eyebrow{margin:0 0 4px;font-size:11px;letter-spacing:.12em;color:#64766b;text-transform:uppercase}
.pm-head{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;flex-wrap:wrap;padding:4px 0 20px}
.pm-head h2{margin:0!important;font-size:26px!important;line-height:1.2}
.pm-sub{margin:6px 0 0;max-width:520px;font-size:13px;line-height:1.6;color:#5d6d63}
.pm-tools{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.pm-count{white-space:nowrap;display:flex;align-items:baseline;gap:6px;padding:0 14px;height:44px;border-radius:999px;background:#fff;border:1px solid #dfe7e1;font-size:12px;color:#64766b}
.pm-count strong{font-size:18px;color:#0f6e5c;font-variant-numeric:tabular-nums}.pm-count i{width:1px;height:16px;background:#dfe7e1;align-self:center;margin:0 4px}
.pm-search input{width:230px;height:44px;border-radius:999px;border:1px solid #dfe7e1;background:#fff;padding:0 16px}
.pm-primary{min-height:44px;border-radius:999px;padding:0 22px;background:#0f6e5c;border:1px solid #0f6e5c;color:#fff;font-weight:600;cursor:pointer}
.pm-primary:disabled{opacity:.5;cursor:default}
.pm-ghost{min-height:44px;border-radius:999px;padding:0 20px;background:#fff;border:1px solid #cddbd1;color:#1b2421;cursor:pointer}

.pm-grid{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:20px}
.pm-card{width:100%;height:100%;display:flex;flex-direction:column;align-items:stretch;justify-content:flex-start;font-weight:400;padding:0;text-align:left;background:#fff;color:inherit;border:1px solid #e1e8e3;border-radius:16px;overflow:hidden;cursor:pointer;box-shadow:0 1px 2px rgba(27,36,33,.04);transition:transform .18s,box-shadow .18s,border-color .18s}
.pm-card:hover{transform:translateY(-3px);box-shadow:0 14px 32px rgba(27,36,33,.12);border-color:#b9cfc2}
.pm-card:focus-visible{outline:3px solid #7fb7a3;outline-offset:2px}.pm-card.current{border-color:#0f6e5c;box-shadow:0 0 0 2px #0f6e5c}
.pm-cover{position:relative;display:block;aspect-ratio:4/3;background:#edf1ed;overflow:hidden}
.pm-cover :deep(img){width:100%;height:100%;object-fit:cover;display:block;transition:transform .5s}.pm-card:hover .pm-cover :deep(img){transform:scale(1.04)}
.pm-cover :deep(.product-picture-placeholder){width:100%;height:100%}
.pm-chip{position:absolute;top:12px;left:12px;padding:4px 10px;border-radius:999px;font-size:11px;font-weight:600;background:rgba(255,255,255,.92);color:#34503f;backdrop-filter:blur(4px)}
.pm-chip.on{background:#0f6e5c;color:#fff}.pm-chip.off{background:rgba(27,36,33,.78);color:#fff}.pm-chip.sample{left:auto;right:12px;background:#f2e7d3;color:#7a5a24}
.pm-body{display:flex;flex-direction:column;gap:6px;padding:16px 18px 18px}
.pm-body strong{font-size:17px;line-height:1.3}.pm-body small{font-size:12px;color:#64766b}
.pm-specs{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:6px;padding-top:12px;border-top:1px dashed #dfe7e1;font-size:12.5px;color:#34503f;font-variant-numeric:tabular-nums}
.pm-specs em{font-style:normal;color:#8a998f;margin-right:6px;font-size:11px}.pm-specs .unit{margin-left:auto;color:#8a998f}
.pm-tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:2px}
.pm-tags span{padding:3px 9px;border-radius:999px;background:#eef4f0;color:#34503f;font-size:11.5px}.pm-tags .more{background:transparent;color:#64766b}.pm-tags .none{background:transparent;color:#9aa89f;padding-left:0}
.pm-empty{padding:48px 0;text-align:center;color:#64766b}

.pm-backdrop{position:fixed;inset:0;background:rgba(16,28,22,.42);z-index:50;animation:pm-fade .2s}
.pm-drawer{position:fixed;top:0;right:0;bottom:0;width:min(760px,100vw);z-index:51;display:flex;flex-direction:column;background:#f7f9f8;box-shadow:-20px 0 60px rgba(16,28,22,.25);animation:pm-slide .26s cubic-bezier(.2,.8,.2,1);outline:none}
@keyframes pm-fade{from{opacity:0}}@keyframes pm-slide{from{transform:translateX(40px);opacity:0}}
.pm-drawer-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;padding:22px 28px 16px;background:#fff;border-bottom:1px solid #e1e8e3}
.pm-drawer-head h3{margin:0;font-size:22px;line-height:1.25}
.pm-close{min-width:44px;min-height:44px;border-radius:50%;border:1px solid #dfe7e1;background:#fff;color:#1b2421;cursor:pointer;padding:0}
.pm-drawer>.alert,.pm-drawer>.success{margin:12px 28px 0}
.pm-form{display:flex;flex-direction:column;flex:1;min-height:0;overflow:auto}
.pm-sec{margin:16px 28px 0;padding:20px 22px;background:#fff;border:1px solid #e1e8e3;border-radius:14px}
.pm-sec h4{display:flex;align-items:center;gap:10px;margin:0 0 14px;font-size:15px}
.pm-sec h4 b{display:grid;place-items:center;width:24px;height:24px;border-radius:50%;background:#0f6e5c;color:#fff;font-size:12px}
.pm-sec label{display:grid;gap:6px;font-size:13px;color:#34503f;margin-bottom:12px}
.pm-pair{display:grid;grid-template-columns:1fr 1fr;gap:0 16px}
.pm-dims{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:0 12px}
.pm-sec input,.pm-sec select,.pm-sec textarea{width:100%;min-height:44px;border-radius:10px;border:1px solid #d3ddd6;background:#fff;padding:8px 12px;font:inherit}
.pm-sec textarea{min-height:120px;resize:vertical}
.pm-sec input:read-only,.pm-sec textarea:read-only{background:#f3f6f4;color:#4d6256}
.pm-stage{aspect-ratio:16/9;border-radius:12px;overflow:hidden;background:#edf1ed;display:grid;place-items:center}
.pm-stage :deep(img){width:100%;height:100%;object-fit:cover;display:block}.pm-noimg{color:#8a998f;font-size:13px}
.pm-thumbs{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}
.pm-thumbs article{width:104px;padding:5px;border:2px solid transparent;border-radius:12px;background:#f3f6f4}.pm-thumbs article.active{border-color:#0f6e5c;background:#fff}
.pm-thumb{display:block;width:100%;aspect-ratio:4/3;padding:0;min-height:0;border:0;border-radius:8px;overflow:hidden;background:#edf1ed;cursor:pointer}
.pm-thumb :deep(img){width:100%;height:100%;object-fit:cover;display:block}
.pm-thumbs small{display:block;margin:4px 2px;font-size:11px;color:#64766b}.pm-thumbs article>div{display:flex;flex-wrap:wrap;gap:4px}
.pm-mini{min-height:32px;padding:0 8px;border-radius:8px;border:1px solid #cddbd1;background:#fff;color:#1b2421;font-size:11px;cursor:pointer}.pm-mini.danger{color:#8c2f2f}
.pm-upload{position:relative;display:grid!important;gap:2px!important;place-items:center;padding:18px;border:2px dashed #b9cfc2;border-radius:12px;background:#f7faf8;cursor:pointer;text-align:center}
.pm-upload span{font-weight:600;color:#0f6e5c;font-size:14px}.pm-upload small{color:#64766b;font-size:12px}.pm-upload input{position:absolute;inset:0;opacity:0;cursor:pointer;min-height:0;padding:0}
.pm-toggles{display:flex;gap:12px;flex-wrap:wrap}
.pm-toggle{display:flex!important;align-items:center;grid-template-columns:none;gap:10px!important;padding:0 16px;min-height:44px;border:1px solid #d3ddd6;border-radius:999px;background:#fff;cursor:pointer;margin:0!important}
.pm-toggle input{width:18px;height:18px;min-height:18px;margin:0;accent-color:#0f6e5c}
.pm-hint{margin:0;font-size:12px;line-height:1.6;color:#64766b}
.pm-save{position:sticky;bottom:0;margin-top:20px;padding:14px 28px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;background:#fff;border-top:1px solid #e1e8e3;box-shadow:0 -8px 24px rgba(16,28,22,.06)}
.pm-save span{font-size:12px;color:#64766b}

@media(max-width:800px){
  .pm-head{align-items:stretch}.pm-tools{width:100%}.pm-search{flex:1 1 100%}.pm-search input{width:100%}.pm-count{order:2}.pm-tools .pm-primary{order:3;flex:1}
  .pm-grid{grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px}
  .pm-drawer{width:100vw}.pm-drawer-head{padding:16px}.pm-drawer>.alert,.pm-drawer>.success{margin:12px 16px 0}
  .pm-sec{margin:12px 12px 0;padding:16px}.pm-pair{grid-template-columns:1fr}.pm-dims{grid-template-columns:1fr 1fr}.pm-save{padding:12px 16px}
}
@media(prefers-reduced-motion:reduce){.pm-card,.pm-card:hover,.pm-cover :deep(img),.pm-drawer,.pm-backdrop{transition:none;animation:none;transform:none}}
</style>

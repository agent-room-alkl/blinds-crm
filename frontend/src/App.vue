<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount, watch } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import SiteFooter from "./components/SiteFooter.vue";
import { listProducts, type ApiProduct } from "./api";

const { t, locale } = useI18n();
const route = useRoute();
const workbench = computed(() => route.path.startsWith("/crm"));
const portalWorkspace = computed(() => route.path.startsWith("/portal"));
const menuOpen = ref(false);
const home = computed(() => route.path === '/');
const scrolled = ref(false);
const products = ref<ApiProduct[]>([]);
onMounted(async()=>{try{products.value=await listProducts()}catch{/* Navigation remains usable if the catalogue is offline. */}});
function updateScroll(){scrolled.value=window.scrollY>24}
onMounted(()=>{updateScroll();window.addEventListener('scroll',updateScroll,{passive:true})});
onBeforeUnmount(()=>window.removeEventListener('scroll',updateScroll));
watch(()=>route.path,()=>{menuOpen.value=false;updateScroll()});

function toggleLocale() {
  const next = locale.value === "zh" ? "en" : "zh";
  locale.value = next;
  localStorage.setItem("vera-locale", next);
  document.documentElement.lang = next === "zh" ? "zh" : "en";
}
</script>

<template>
  <div class="frame" :class="{ 'frame-work': workbench, 'frame-portal': portalWorkspace }">
    <header v-if="!workbench" class="rail" :class="{'rail-home':home,'rail-solid':scrolled||menuOpen}" >
      <router-link to="/" class="mark">
        <img class="brand-logo" src="/images/vera-logo.png" alt="VERA Shading Solutions" />
      </router-link>
      <button type="button" class="secondary menu" :aria-expanded="menuOpen" aria-controls="site-navigation" @click="menuOpen = !menuOpen">
        {{ t("nav.menu") }}
      </button>
      <nav id="site-navigation" class="nav" :class="{ open: menuOpen }">
        <router-link to="/">{{ t("nav.home") }}</router-link>
        <div class="product-nav-group">
          <router-link to="/products">{{ t("nav.products") }} <span aria-hidden="true">⌄</span></router-link>
          <div class="product-subnav">
            <router-link v-for="product in products" :key="product.id" :to="`/products/${product.id}`">{{ locale === 'zh' ? product.name_zh : product.name_en }}</router-link>
          </div>
        </div>
        <router-link to="/about">{{ t("nav.about") }}</router-link>
        <router-link to="/portal" class="nav-quote">Trade Login</router-link>
        <router-link to="/contact">{{ t("nav.contact") }}</router-link>
        <router-link to="/trade-resources">Trade Resources</router-link>
      </nav>
      <button type="button" class="secondary" @click="toggleLocale">
        {{ t("switchTo") }}
      </button>
    </header>
    <router-view />
    <SiteFooter v-if="!workbench && !portalWorkspace" />

  </div>
</template>

<style scoped>
.rail{min-height:76px}
.rail:not(.rail-home){background:#faf9f6}
@media(max-width:700px){.rail{min-height:72px;padding-top:12px;padding-bottom:12px}}
.rail-home{position:fixed;left:0;right:0;top:0;z-index:50;background:rgba(250,249,246,.97);color:var(--ink);border-bottom:1px solid var(--line)}
.brand-logo{display:block;width:170px;height:auto;max-height:58px;object-fit:contain}
.nav a.router-link-active:not(.button){box-shadow:none}.nav-quote{background:transparent;border:0;color:inherit}
.product-nav-group{position:relative}.product-nav-group>a{gap:6px}.product-subnav{display:none;position:absolute;z-index:70;top:100%;left:0;min-width:205px;padding:7px;background:#fff;border:1px solid var(--line);box-shadow:0 12px 28px rgba(40,52,58,.14)}.product-subnav a{display:flex!important;width:100%;padding:9px 12px!important;font-size:12px;white-space:nowrap}.product-nav-group:hover .product-subnav,.product-nav-group:focus-within .product-subnav{display:block}.product-subnav a:hover{background:#e8eef0;color:#28343a}
@media(max-width:700px){.brand-logo{width:148px;max-height:50px}}
@media(max-width:700px){.product-nav-group{width:100%}.product-nav-group>a{width:100%}.product-subnav{position:static;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));box-shadow:none;border:0;background:transparent;padding:0 0 0 10px}.product-nav-group .product-subnav{display:grid}.product-subnav a{white-space:normal}.rail .nav:not(.open) .product-subnav{display:none}}

.frame-portal .rail{min-height:64px;padding:8px 24px;border-bottom:1px solid var(--line)}
.frame-portal .brand-logo{width:150px;max-height:52px}
@media(max-width:700px){.frame-portal .rail{min-height:60px;padding:6px 12px}}

.frame-portal{padding:0;display:flex;flex-direction:column;min-height:100dvh}.frame-portal .rail{flex:none}
.frame-work{margin:0;padding:0}
</style>

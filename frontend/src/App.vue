<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount, watch } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import SiteFooter from "./components/SiteFooter.vue";

const { t, locale } = useI18n();
const route = useRoute();
const workbench = computed(() => route.path.startsWith("/crm"));
const menuOpen = ref(false);
const home = computed(() => route.path === '/');
const scrolled = ref(false);
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
  <div class="frame" :class="{ 'frame-work': workbench }">
    <header v-if="!workbench" class="rail" :class="{'rail-home':home,'rail-solid':scrolled||menuOpen}" >
      <router-link to="/" class="mark">
        <span class="oval">{{ t("brand") }}</span>
        <small>{{ t("tagline") }}</small>
      </router-link>
      <button type="button" class="secondary menu" :aria-expanded="menuOpen" aria-controls="site-navigation" @click="menuOpen = !menuOpen">
        {{ t("nav.menu") }}
      </button>
      <nav id="site-navigation" class="nav" :class="{ open: menuOpen }">
        <router-link to="/">{{ t("nav.home") }}</router-link>
        <router-link to="/products">{{ t("nav.products") }}</router-link>
        <router-link to="/about">{{ t("nav.about") }}</router-link>
        <router-link to="/inquiry" class="nav-quote">{{ t("nav.quote") }}</router-link>
      </nav>
      <button type="button" class="secondary" @click="toggleLocale">
        {{ t("switchTo") }}
      </button>
    </header>
    <router-view />
    <SiteFooter v-if="!workbench" />

  </div>
</template>

<style scoped>
.rail-home{position:fixed;left:0;right:0;top:0;z-index:50;background:transparent;border-bottom-color:rgba(255,255,255,.2);color:white;transition:background .2s,color .2s}
.rail:not(.rail-home) .oval{background:transparent;color:var(--ink);border-radius:0}
.rail-home .oval{background:white;color:var(--frame)}.rail-home button.secondary{color:white;border-color:rgba(255,255,255,.5)}
.rail-home:hover,.rail-home:has(:focus-visible),.rail-home.rail-solid{background:rgba(250,249,246,.98);color:var(--ink);border-bottom-color:var(--line)}
.rail-home:hover .oval,.rail-home:has(:focus-visible) .oval,.rail-home.rail-solid .oval{background:var(--frame);color:white}
.rail-home:hover button.secondary,.rail-home:has(:focus-visible) button.secondary,.rail-home.rail-solid button.secondary{color:var(--ink);border-color:var(--ink)}
@media(prefers-reduced-motion:reduce){.rail-home{transition:none}}
.rail,.rail-home,.rail-home:hover,.rail-home:has(:focus-visible),.rail-home.rail-solid{border-bottom:0}.nav a.router-link-active:not(.button){box-shadow:none}.nav-quote{background:transparent;border:0;color:inherit}
.rail-home .oval{background:transparent;color:white;border-radius:0}.rail-home:hover .oval,.rail-home:has(:focus-visible) .oval,.rail-home.rail-solid .oval{background:transparent;color:var(--ink)}
.rail-home:not(.rail-solid) .nav a,.rail-home:not(.rail-solid) .mark{text-shadow:0 1px 3px rgba(0,0,0,.6)}.rail-home:hover .nav a,.rail-home:has(:focus-visible) .nav a,.rail-home:hover .mark,.rail-home:has(:focus-visible) .mark{text-shadow:none}
</style>

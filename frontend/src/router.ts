import { createRouter, createWebHistory } from "vue-router";
import HomeView from "./views/HomeView.vue";
import ProductsView from "./views/ProductsView.vue";
import ProductDetailView from "./views/ProductDetailView.vue";
import InquiryView from "./views/InquiryView.vue";
import AboutView from "./views/AboutView.vue";
import CrmView from "./views/CrmView.vue";
import PortalView from "./views/PortalView.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "home", component: HomeView },
    { path: "/products", name: "products", component: ProductsView },
    { path: "/products/:id", name: "product", component: ProductDetailView },
    { path: "/inquiry", name: "inquiry", component: InquiryView },
    { path: "/portal", name: "portal", component: PortalView },
    { path: "/about", name: "about", component: AboutView },
    { path: "/contact", redirect: "/inquiry" },
    { path: "/crm/:section?", name: "crm", component: CrmView },
  ],
});

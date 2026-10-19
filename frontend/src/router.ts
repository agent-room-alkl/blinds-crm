import { createRouter, createWebHistory } from "vue-router";
import HomeView from "./views/HomeView.vue";
import ProductsView from "./views/ProductsView.vue";
import ProductDetailView from "./views/ProductDetailView.vue";
import AboutView from "./views/AboutView.vue";
import ContactView from "./views/ContactView.vue";
import CrmView from "./views/CrmView.vue";
import PortalView from "./views/PortalView.vue";
import PortalLayout from "./views/PortalLayout.vue";
import OrderWizard from "./views/portal/OrderWizard.vue";
import OrdersList from "./views/portal/OrdersList.vue";
import OrderDetail from "./views/portal/OrderDetail.vue";
import Invoices from "./views/portal/Invoices.vue";
import Company from "./views/portal/Company.vue";
import Help from "./views/portal/Help.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "home", component: HomeView },
    { path: "/products", name: "products", component: ProductsView },
    { path: "/products/:id", name: "product", component: ProductDetailView },
    { path: "/inquiry", redirect: "/contact" },
    { path: "/portal-old", name: "portal-old", component: PortalView },
    {
      path: "/portal",
      component: PortalLayout,
      children: [
        { path: "", redirect: "/portal/orders" },
        { path: "order/new", name: "new-order", component: OrderWizard },
        { path: "orders", name: "orders", component: OrdersList },
        { path: "orders/:id", name: "order-detail", component: OrderDetail },
        { path: "invoices", name: "invoices", component: Invoices },
        { path: "company", name: "company", component: Company },
        { path: "help", name: "help", component: Help },
      ],
    },
    { path: "/about", name: "about", component: AboutView },
    { path: "/contact", name: "contact", component: ContactView },
    { path: "/crm/:section?", name: "crm", component: CrmView },
  ],
});

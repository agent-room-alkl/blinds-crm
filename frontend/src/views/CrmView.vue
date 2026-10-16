<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { request, session } from "../crm-api";
import ProductManager from "../components/ProductManager.vue";
import IntegrationStatus from "../components/IntegrationStatus.vue";
import ProjectDesk from "../components/ProjectDesk.vue";
import SampleDashboard from "../components/SampleDashboard.vue";
import PortalCustomers from "../components/PortalCustomers.vue";
import type { ApiProduct } from "../api";

const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);
const signed = ref(!!session.token);
const busy = ref(false);
const error = ref("");
const message = ref("");
const tab = ref("projects");
const credentials = reactive({ username: "", password: "" });
const products = ref<ApiProduct[]>([]);
const me = ref({ username: "", name: "", role: "staff" });
const passwordOpen = ref(false);
const passwordForm = reactive({ current: "", next: "", confirm: "" });
const users = ref<{ username: string; name: string; role: string; active: number }[]>([]);
const newUser = reactive({ username: "", name: "", password: "", role: "staff" });
const nav = computed(() => [
  { key: "projects", label: tx("项目订单", "Project orders") },
  { key: "customers", label: tx("客户资料", "Customers") },
  { key: "dashboard", label: tx("分析看板", "Dashboard") },
  { key: "products", label: tx("产品目录", "Product catalogue") },
]);
const pageTitle = computed(() => nav.value.find((item) => item.key === tab.value)?.label || tx("系统设置", "Settings"));

async function act(fn: () => Promise<void>) {
  busy.value = true;
  error.value = "";
  message.value = "";
  try {
    await fn();
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
    if (!session.token) signed.value = false;
  } finally {
    busy.value = false;
  }
}

async function load() {
  const [catalogue, who] = await Promise.all([
    request<ApiProduct[]>("admin/products"),
    request<{ username: string; name: string; role: string }>("auth/me"),
  ]);
  products.value = catalogue;
  me.value = who;
  if (who.role === "admin") users.value = await request("users");
}

function toggleLocale() {
  const next = locale.value === "zh" ? "en" : "zh";
  locale.value = next;
  localStorage.setItem("vera-locale", next);
  document.documentElement.lang = next === "zh" ? "zh" : "en";
}

async function changePassword() {
  if (passwordForm.next !== passwordForm.confirm) {
    error.value = tx("两次新密码不一致", "The new passwords do not match");
    return;
  }
  await act(async () => {
    await request("auth/password", { current: passwordForm.current, new: passwordForm.next });
    session.token = "";
    signed.value = false;
    passwordForm.current = "";
    passwordForm.next = "";
    passwordForm.confirm = "";
    passwordOpen.value = false;
    message.value = tx("密码已更新，请用新密码重新登录", "Password updated. Sign in again with the new password");
  });
}

async function addUser() {
  await act(async () => {
    await request("users", { ...newUser });
    newUser.username = "";
    newUser.name = "";
    newUser.password = "";
    await load();
    message.value = tx("用户已添加", "User added");
  });
}

async function setRole(username: string, role: string) {
  await act(async () => {
    await request(`users/${username}/role`, { role });
    await load();
    message.value = tx("权限已更新", "Access updated");
  });
}

function onRole(username: string, event: Event) {
  void setRole(username, (event.target as HTMLSelectElement).value);
}

async function login() {
  await act(async () => {
    const result = await request<{ token: string }>("auth/login", credentials);
    session.token = result.token;
    signed.value = true;
    credentials.password = "";
    await load();
  });
}

async function logout() {
  await act(async () => {
    await request("auth/logout", {});
    session.token = "";
    signed.value = false;
  });
}

function openTab(key: string) {
  tab.value = key;
  window.scrollTo({ top: 0 });
}

onMounted(() => {
  if (signed.value) void act(load);
});
</script>

<template>
  <main class="page crm" :class="{ 'is-signed': signed }">
    <aside v-if="signed" class="desk-rail">
      <div class="rail-brand">VERA</div>
      <button v-for="item in nav" :key="item.key" type="button" :class="{ current: tab === item.key }" @click="openTab(item.key)">
        {{ item.label }}
      </button>
      <button v-if="me.role === 'admin'" type="button" :class="{ current: tab === 'users' }" @click="openTab('users')">
        {{ tx("系统设置", "Settings") }}
      </button>
      <div class="rail-bottom">
        <span class="user-avatar">{{ (me.name || "V").slice(0, 1) }}</span>
        <div class="user-meta">
          <strong>{{ me.name }}</strong>
          <small>{{ me.role === "admin" ? tx("管理员", "Admin") : tx("销售", "Sales") }}</small>
        </div>
      </div>
    </aside>

    <p v-if="error" class="alert" role="alert">{{ error }}</p>
    <p v-if="message" class="success" role="status">{{ message }}</p>

    <form v-if="!signed" class="card login" @submit.prevent="login">
      <h1>{{ tx("内部登录", "Internal sign in") }}</h1>
      <p>{{ tx("客户资料仅对已登录用户开放", "Customer information requires sign in") }}</p>
      <label>{{ tx("用户名", "Username") }}<input v-model="credentials.username" autocomplete="username" required /></label>
      <label>{{ tx("密码", "Password") }}<input v-model="credentials.password" type="password" autocomplete="current-password" required /></label>
      <button :disabled="busy">{{ tx("登录", "Sign in") }}</button>
    </form>

    <template v-else>
      <header class="crm-bar">
        <div class="page-context">
          <span>VERA / CRM</span>
          <h1>{{ pageTitle }}</h1>
        </div>
        <button type="button" class="secondary" @click="toggleLocale">{{ locale === "zh" ? "English" : "中文" }}</button>
        <button type="button" class="secondary" @click="passwordOpen = !passwordOpen">{{ tx("修改密码", "Change password") }}</button>
        <button type="button" class="secondary" @click="logout">{{ tx("退出", "Sign out") }}</button>
      </header>
      <form v-if="passwordOpen" class="password-form" @submit.prevent="changePassword">
        <label>{{ tx("当前密码", "Current password") }}<input v-model="passwordForm.current" type="password" autocomplete="current-password" required /></label>
        <label>{{ tx("新密码", "New password") }}<input v-model="passwordForm.next" type="password" autocomplete="new-password" minlength="8" required /></label>
        <label>{{ tx("再输入一次", "Repeat the new password") }}<input v-model="passwordForm.confirm" type="password" autocomplete="new-password" minlength="8" required /></label>
        <button :disabled="busy">{{ tx("保存密码", "Save password") }}</button>
      </form>
      <ProjectDesk v-if="tab === 'projects'" :admin="me.role === 'admin'" />
      <PortalCustomers v-if="tab === 'customers'" />
      <SampleDashboard v-if="tab === 'dashboard'" />
      <ProductManager v-if="tab === 'products'" :admin="me.role === 'admin'" @updated="act(load)" />
      <div v-if="tab === 'users' && me.role === 'admin'" class="settings-layout">
        <IntegrationStatus :locale="locale" />
        <section class="card">
          <h2>{{ tx("用户与权限", "Users & access") }}</h2>
          <form class="user-form" @submit.prevent="addUser">
            <label>{{ tx("用户名", "Username") }}<input v-model="newUser.username" required pattern="[a-z0-9._-]{2,40}" autocomplete="off" /></label>
            <label>{{ tx("姓名", "Name") }}<input v-model="newUser.name" required autocomplete="off" /></label>
            <label>{{ tx("初始密码", "Starting password") }}<input v-model="newUser.password" type="password" minlength="8" required autocomplete="new-password" /></label>
            <label>{{ tx("权限", "Access") }}
              <select v-model="newUser.role">
                <option value="staff">{{ tx("销售", "Sales") }}</option>
                <option value="admin">{{ tx("管理员", "Admin") }}</option>
              </select>
            </label>
            <button :disabled="busy">{{ tx("添加用户", "Add user") }}</button>
          </form>
          <div class="table-wrap">
            <table>
              <thead><tr><th>{{ tx("用户名", "Username") }}</th><th>{{ tx("姓名", "Name") }}</th><th>{{ tx("权限", "Access") }}</th></tr></thead>
              <tbody>
                <tr v-for="person in users" :key="person.username">
                  <td>{{ person.username }}</td>
                  <td>{{ person.name }}</td>
                  <td>
                    <select :value="person.role" @change="onRole(person.username, $event)">
                      <option value="admin">{{ tx("管理员", "Admin") }}</option>
                      <option value="staff">{{ tx("销售", "Sales") }}</option>
                    </select>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </template>
  </main>
</template>

<style scoped>
.crm { font-family: var(--font-body, "Figtree", "Noto Sans SC", sans-serif); color: #1b2421; background: #f5f6f2; min-height: 100vh; padding: 32px 28px 48px; overflow-x: hidden; }
.crm.is-signed { padding-left: 268px; }
.desk-rail { position: fixed; inset: 0 auto 0 0; width: 236px; background: #1a2823; color: #e7eee9; padding: 28px 16px; display: flex; flex-direction: column; gap: 4px; }
.rail-brand { font-size: 22px; letter-spacing: 0.16em; padding: 4px 12px 20px; }
.desk-rail button { display: flex; align-items: center; min-height: 44px; border: 0; background: transparent; color: #e7eee9; padding: 10px 14px; text-align: left; font-size: 15px; border-radius: 6px; }
.desk-rail button.current { background: #0f6e5c; color: white; }
.rail-bottom { margin-top: auto; display: flex; gap: 10px; align-items: center; padding: 16px 12px; border-top: 1px solid rgba(231, 238, 233, 0.16); }
.user-avatar { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 50%; background: #8e9a94; color: #1a2823; font-size: 14px; }
.user-meta strong { display: block; font-size: 14px; }
.user-meta small { display: block; font-size: 12px; opacity: 0.75; margin-top: 2px; }
.crm-bar { display: flex; align-items: flex-end; gap: 12px; min-height: 72px; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid #e1e6df; }
.page-context { margin-right: auto; }
.page-context span { font-size: 12px; letter-spacing: 0.14em; color: #6d7c72; }
.page-context h1 { font-size: 28px; line-height: 1.25; font-weight: 600; margin: 6px 0 0; }
.crm-bar button, .login button, .password-form button, .user-form button { min-height: 40px; font-size: 14px; padding: 8px 14px; border-radius: 6px; border: 1px solid #0f6e5c; background: #0f6e5c; color: white; }
.crm-bar button.secondary { background: white; color: #24342c; border-color: #d5ddd6; }
.card, .login { background: white; border: 1px solid #e1e6df; border-radius: 8px; padding: 24px; }
.login { max-width: 440px; margin: 48px auto; }
.login h1 { font-size: 28px; margin: 0 0 8px; }
.login p, .card p { font-size: 15px; line-height: 1.6; }
.crm label { display: block; margin: 14px 0; font-size: 14px; }
.crm input, .crm select { width: 100%; box-sizing: border-box; min-height: 40px; margin-top: 6px; padding: 8px 12px; font-size: 15px; border: 1px solid #d5ddd6; border-radius: 6px; }
.password-form, .user-form { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)) auto; gap: 12px; align-items: end; margin-bottom: 16px; }
.password-form label, .user-form label { margin: 0; }
.settings-layout { display: grid; gap: 24px; }
.card h2 { font-size: 20px; margin: 0 0 16px; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; font-size: 14px; padding: 12px 10px; border-bottom: 1px solid #e1e6df; }
.alert { padding: 12px 16px; background: #fae8e1; color: #842b16; }
.success { padding: 12px 16px; background: #e5efdd; }
@media (max-width: 800px) {
  .crm, .crm.is-signed { padding: 16px; }
  .desk-rail { position: static; width: auto; margin: -16px -16px 20px; display: grid; grid-template-columns: 1fr 1fr; }
  .rail-brand, .rail-bottom { display: none; }
  .password-form, .user-form { grid-template-columns: 1fr; }
  .crm-bar { flex-wrap: wrap; }
  .page-context { flex-basis: 100%; }
}
</style>

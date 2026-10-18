<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { request, session } from "../crm-api";
import ProductManager from "../components/ProductManager.vue";
import IntegrationStatus from "../components/IntegrationStatus.vue";
import ProjectDesk from "../components/ProjectDesk.vue";
import SampleDashboard from "../components/SampleDashboard.vue";
import PortalCustomers from "../components/PortalCustomers.vue";
import { FolderKanban, Users, BarChart3, Package, Settings } from "lucide-vue-next";
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
const accountMenu = ref<HTMLDetailsElement>();
function closeAccountMenu() { 
  if (accountMenu.value) {
    accountMenu.value.open = false;
    const summary = accountMenu.value.querySelector('summary');
    if (summary && document.activeElement && accountMenu.value.contains(document.activeElement)) {
      summary.focus();
    }
  }
}
function dismissAccountMenu(event: PointerEvent) {
  if (event.target instanceof Node && !accountMenu.value?.contains(event.target)) closeAccountMenu();
}
onMounted(() => document.addEventListener("pointerdown", dismissAccountMenu));
onUnmounted(() => document.removeEventListener("pointerdown", dismissAccountMenu));
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
      <button type="button" :class="{ current: tab === 'projects' }" @click="openTab('projects')">
        <FolderKanban :size="20" aria-hidden="true" />
        {{ tx("项目订单", "Project orders") }}
      </button>
      <button type="button" :class="{ current: tab === 'customers' }" @click="openTab('customers')">
        <Users :size="20" aria-hidden="true" />
        {{ tx("客户资料", "Customers") }}
      </button>
      <button type="button" :class="{ current: tab === 'dashboard' }" @click="openTab('dashboard')">
        <BarChart3 :size="20" aria-hidden="true" />
        {{ tx("分析看板", "Dashboard") }}
      </button>
      <button type="button" :class="{ current: tab === 'products' }" @click="openTab('products')">
        <Package :size="20" aria-hidden="true" />
        {{ tx("产品目录", "Product catalogue") }}
      </button>
      <button v-if="me.role === 'admin'" type="button" :class="{ current: tab === 'users' }" @click="openTab('users')">
        <Settings :size="20" aria-hidden="true" />
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
        <nav class="page-context" :aria-label="tx('当前位置', 'Breadcrumb')">
          <span>VERA</span><span aria-hidden="true">/</span><span>CRM</span><span aria-hidden="true">/</span><strong aria-current="page">{{ pageTitle }}</strong>
        </nav>
        <details ref="accountMenu" class="account-menu" @keydown.esc="closeAccountMenu">
          <summary :aria-label="tx('账户菜单', 'Account menu')" :title="me.name"><span>{{ (me.name || 'V').slice(0, 1) }}</span></summary>
          <div class="account-dropdown">
            <div class="account-identity"><strong>{{ me.name }}</strong><small>{{ me.role === 'admin' ? tx('管理员', 'Admin') : tx('员工', 'Staff') }}</small></div>
            <button type="button" @click="toggleLocale(); closeAccountMenu()">{{ locale === 'zh' ? 'English' : '中文' }}</button>
            <button type="button" @click="passwordOpen = !passwordOpen; closeAccountMenu()">{{ tx('修改密码', 'Change password') }}</button>
            <button type="button" @click="logout(); closeAccountMenu()">{{ tx('退出', 'Sign out') }}</button>
          </div>
        </details>
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
.crm {
  --fs-page-title: 20px; --lh-page-title: 1.35;
  --fs-title: 15px; --lh-title: 1.5;
  --fs-heading: 14px; --lh-heading: 1.5;
  --fs-body: 13px; --lh-body: 1.55;
  --fs-meta: 12px; --lh-meta: 1.5;
  --fw-body: 400;
  --fw-emphasis: 600;
  font-family: var(--font-body, "Figtree", "Noto Sans SC", sans-serif); color: #1b2421; background: #f5f6f2; min-height: 100vh; padding: 24px 20px 36px; overflow: visible;
}
.crm.is-signed { padding-left: 252px; }
.desk-rail { position: fixed; inset: 0 auto 0 0; width: 228px; background: #1a2823; color: #e7eee9; padding: 24px 12px; display: flex; flex-direction: column; gap: 4px; }
.rail-brand { font-size: var(--fs-page-title); line-height: var(--lh-page-title); font-weight: var(--fw-emphasis); letter-spacing: 0.16em; padding: 4px 12px 16px; }
.desk-rail button { display: flex; align-items: center; gap: 10px; min-height: 44px; border: 0; background: transparent; color: #e7eee9; padding: 10px 12px; text-align: left; font-size: var(--fs-heading); line-height: var(--lh-heading); font-weight: var(--fw-body); border-radius: 6px; transition: background 0.2s; }
.desk-rail button:hover { background: rgba(255,255,255,0.08); }
.desk-rail button:focus-visible { outline: 2px solid #0f6e5c; outline-offset: 2px; }
.desk-rail button.current { background: #0f6e5c; color: white; }
.rail-bottom { margin-top: auto; display: flex; gap: 10px; align-items: center; padding: 16px 12px; border-top: 1px solid rgba(231, 238, 233, 0.16); }
.user-avatar { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 50%; background: #8e9a94; color: #1a2823; font-size: var(--fs-heading); line-height: 1; }
.user-meta strong { display: block; font-size: var(--fs-heading); line-height: var(--lh-heading); }
.user-meta small { display: block; font-size: var(--fs-meta); line-height: var(--lh-meta); opacity: 0.75; margin-top: 2px; }
.crm-bar { display: flex; align-items: flex-end; gap: 12px; min-height: 72px; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid #e1e6df; }
.page-context { margin-right: auto; }
.page-context span { font-size: var(--fs-meta); line-height: var(--lh-meta); letter-spacing: 0.14em; color: #6d7c72; }
.page-context h1 { font-size: var(--fs-page-title); line-height: var(--lh-page-title); font-weight: var(--fw-emphasis); margin: 6px 0 0; }
.crm-bar button, .login button, .password-form button, .user-form button { min-height: 44px; font-size: var(--fs-body); line-height: var(--lh-body); padding: 8px 14px; border-radius: 6px; border: 1px solid #0f6e5c; background: #0f6e5c; color: white; font-weight: var(--fw-body); }
.crm-bar button.secondary { background: white; color: #24342c; border-color: #d5ddd6; }
.card, .login { background: white; border: 1px solid #e1e6df; border-radius: 8px; padding: 24px; }
.login { max-width: 440px; margin: 48px auto; }
.login h1 { font-size: var(--fs-page-title); line-height: var(--lh-page-title); font-weight: var(--fw-emphasis); margin: 0 0 8px; }
.login p, .card p { font-size: var(--fs-body); line-height: var(--lh-body); }
.crm label { display: block; margin: 14px 0; font-size: var(--fs-body); line-height: var(--lh-body); }
.crm input, .crm select { width: 100%; box-sizing: border-box; min-height: 44px; margin-top: 6px; padding: 8px 12px; font-size: var(--fs-body); line-height: var(--lh-body); border: 1px solid #d5ddd6; border-radius: 6px; }
.password-form, .user-form { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)) auto; gap: 12px; align-items: end; margin-bottom: 16px; }
.password-form label, .user-form label { margin: 0; }
.settings-layout { display: grid; gap: 24px; }
.card h2 { font-size: var(--fs-page-title); line-height: var(--lh-page-title); font-weight: var(--fw-emphasis); margin: 0 0 16px; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; font-size: var(--fs-body); line-height: var(--lh-body); padding: 12px 10px; border-bottom: 1px solid #e1e6df; }
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
@media (max-width: 390px) {
  .crm, .crm.is-signed { padding: 12px; }
  .desk-rail { grid-template-columns: 1fr 1fr; gap: 2px; margin: -12px -12px 16px; }
  .crm-bar { min-height: 60px; margin-bottom: 16px; }
  .page-context h1 { font-size: var(--fs-title); line-height: var(--lh-title); }
}

.crm { font-family: Inter, "Segoe UI", "Microsoft YaHei", sans-serif; background: #f3f6f4; }
.crm :deep(*) { box-sizing: border-box; }
.crm :deep(h1), .crm :deep(h2), .crm :deep(h3), .crm :deep(h4) { font-family: inherit; letter-spacing: -.015em; }
.crm :deep(button), .crm :deep(input), .crm :deep(select), .crm :deep(textarea) { font-family: inherit; }
.crm-bar { min-height: 64px; align-items: center; margin-bottom: 24px; }
.page-context h1 { font-size: var(--fs-page-title); line-height: var(--lh-page-title); font-weight: var(--fw-emphasis); }
.desk-rail { width: 220px; padding: 28px 14px; background: #19392d; box-sizing: border-box; }
.crm.is-signed { padding-left: 248px; }
.desk-rail button { font-size: var(--fs-heading); line-height: var(--lh-heading); padding: 10px 12px; border-radius: 8px; }
.desk-rail button.current { background: #315844; }
.crm-bar button.secondary { font-size: var(--fs-body); line-height: var(--lh-body); min-height: 44px; padding: 8px 12px; font-weight: var(--fw-body); }
@media(max-width:800px) { .crm.is-signed { padding: 16px; } .desk-rail { width: auto; padding: 12px; gap: 4px; } .crm-bar { gap: 8px; } }
@media(max-width:390px) { .crm.is-signed { padding: 12px; } .desk-rail button { font-size: var(--fs-meta); line-height: var(--lh-meta); min-height: 44px; font-weight: var(--fw-body); } }

.crm .crm-bar { min-height: 44px; padding: 0 0 10px; margin-bottom: 16px; display: flex; align-items: center; flex-wrap: nowrap; }
.crm .page-context { display: flex; align-items: center; gap: 9px; min-width: 0; margin-right: auto; flex-basis: auto; }
.crm .page-context span { font-size: var(--fs-meta); line-height: var(--lh-meta); letter-spacing: 0; color: #5d6b64; }
.crm .page-context strong { font-size: var(--fs-heading); line-height: var(--lh-heading); font-weight: var(--fw-emphasis); color: #203c30; }
.account-menu { position: relative; flex-shrink: 0; }
.account-menu summary { list-style: none; cursor: pointer; border-radius: 50%; }
.account-menu summary::-webkit-details-marker { display: none; }
.account-menu summary > span { display: grid; place-items: center; width: 44px; height: 44px; border-radius: 50%; background: #e4eee7; color: #234b37; border: 1px solid #cadbce; font-size: var(--fs-body); line-height: 1; font-weight: var(--fw-emphasis); }
.account-menu summary:focus-visible { outline: 2px solid #237356; outline-offset: 3px; }
.account-dropdown { position: absolute; right: 0; top: 53px; z-index: 30; width: 196px; border: 1px solid #dce5df; border-radius: 10px; padding: 6px; background: white; box-shadow: 0 8px 32px #17382b1a; }
.account-identity { padding: 9px 10px; margin-bottom: 4px; border-bottom: 1px solid #edf1ee; }
.account-identity strong, .account-identity small { display: block; font-size: var(--fs-body); line-height: var(--lh-body); }
.account-identity small { color: #5d6b64; font-size: var(--fs-meta); line-height: var(--lh-meta); }
.crm .account-dropdown button { width: 100%; display: block; text-align: left; background: white; color: #31483b; border: 0; border-radius: 6px; font-size: var(--fs-body); line-height: var(--lh-body); padding: 10px 10px; min-height: 44px; font-weight: var(--fw-body); }
.crm .account-dropdown button:hover { background: #edf5f1; }
@media(max-width:600px) { .crm .crm-bar { margin-bottom: 12px; } }
</style>

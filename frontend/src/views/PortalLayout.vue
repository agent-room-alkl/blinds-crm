<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { portalRequest, portalSession } from "../portal-api";

const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);

const route = useRoute();
const router = useRouter();

const profile = ref<any>(null);
const loading = ref(true);
const loginError = ref("");
const credentials = ref({ username: "", password: "" });

const NAV_ITEMS = [
  { path: "/portal/order/new", label_zh: "下单", label_en: "New Order", icon: "➕" },
  { path: "/portal/orders", label_zh: "我的订单", label_en: "My Orders", icon: "📋" },
  { path: "/portal/invoices", label_zh: "发票与付款", label_en: "Invoices", icon: "💰" },
  { path: "/portal/company", label_zh: "公司资料", label_en: "Company", icon: "🏢" },
  { path: "/portal/help", label_zh: "帮助", label_en: "Help", icon: "❓" },
];

const currentNav = computed(() => {
  return NAV_ITEMS.find((item) => route.path.startsWith(item.path));
});

onMounted(async () => {
  if (portalSession.token) {
    try {
      profile.value = await portalRequest<any>("me");
    } catch {
      portalSession.token = "";
    }
  }
  loading.value = false;
});

async function login() {
  loginError.value = "";
  try {
    const result = await portalRequest<{ token: string }>("login", credentials.value);
    portalSession.token = result.token;
    profile.value = await portalRequest<any>("me");
    credentials.value = { username: "", password: "" };
    router.push("/portal/orders");
  } catch (cause) {
    loginError.value = cause instanceof Error ? cause.message : String(cause);
  }
}

async function logout() {
  try {
    await portalRequest("logout", {});
  } catch {
    // ignore
  }
  portalSession.token = "";
  profile.value = null;
  router.push("/portal");
}
</script>

<template>
  <div class="portal-layout">
    <div v-if="!profile && !loading" class="login-view">
      <div class="login-card">
        <h1>{{ tx("客户门户", "Customer Portal") }}</h1>
        <p>{{ tx("配置订单，提交待审核。", "Configure orders and submit for review.") }}</p>
        <form @submit.prevent="login">
          <label>
            {{ tx("账号", "Account") }}
            <input v-model="credentials.username" autocomplete="username" required />
          </label>
          <label>
            {{ tx("密码", "Password") }}
            <input v-model="credentials.password" type="password" autocomplete="current-password" required />
          </label>
          <button type="submit" class="primary">
            {{ tx("登录", "Sign in") }}
          </button>
        </form>
        <p v-if="loginError" class="alert" role="alert">{{ loginError }}</p>
      </div>
    </div>

    <div v-else-if="profile" class="portal-main">
      <!-- Desktop sidebar -->
      <aside class="portal-sidebar">
        <div class="sidebar-header">
          <h2>{{ tx("客户门户", "Portal") }}</h2>
          <p class="company-name">{{ profile.company }}</p>
        </div>
        <nav class="sidebar-nav">
          <router-link
            v-for="item in NAV_ITEMS"
            :key="item.path"
            :to="item.path"
            class="nav-item"
            :class="{ active: route.path.startsWith(item.path) }"
          >
            <span class="nav-icon">{{ item.icon }}</span>
            <span class="nav-label">{{ locale === "zh" ? item.label_zh : item.label_en }}</span>
          </router-link>
        </nav>
        <button type="button" class="logout-btn" @click="logout">
          {{ tx("退出", "Sign out") }}
        </button>
      </aside>

      <!-- Main content -->
      <main class="portal-content">
        <router-view />
      </main>

      <!-- Mobile bottom nav -->
      <nav class="portal-bottom-nav">
        <router-link
          v-for="item in NAV_ITEMS"
          :key="item.path"
          :to="item.path"
          class="bottom-nav-item"
          :class="{ active: route.path.startsWith(item.path) }"
        >
          <span class="nav-icon">{{ item.icon }}</span>
          <span class="nav-label">{{ locale === "zh" ? item.label_zh : item.label_en }}</span>
        </router-link>
      </nav>
    </div>

    <div v-else class="loading-view">
      <p>{{ tx("加载中...", "Loading...") }}</p>
    </div>
  </div>
</template>

<style scoped>
.portal-layout {
  min-height: 100vh;
  background: #faf9f6;
}

.login-view {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 24px;
}

.login-card {
  width: 100%;
  max-width: 420px;
  padding: 40px 32px;
  background: white;
  border: 1px solid var(--line);
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.login-card h1 {
  font-family: var(--font-display);
  font-size: 32px;
  font-weight: 600;
  margin: 0 0 12px;
  letter-spacing: 0.01em;
}

.login-card > p {
  font-size: 15px;
  line-height: 1.6;
  color: rgba(27, 36, 33, 0.72);
  margin: 0 0 32px;
}

.login-card form {
  display: grid;
  gap: 20px;
}

.login-card label {
  display: grid;
  gap: 8px;
  font-size: 14px;
  font-weight: 500;
  color: rgba(27, 36, 33, 0.88);
}

.login-card input {
  min-height: 48px;
  padding: 12px 16px;
  border: 1px solid var(--line);
  border-radius: 4px;
  font-size: 15px;
  transition: border-color 0.2s;
}

.login-card input:focus {
  outline: none;
  border-color: var(--cord);
  box-shadow: 0 0 0 2px rgba(15, 110, 92, 0.1);
}

.alert {
  color: var(--danger);
  background: rgba(140, 47, 47, 0.08);
  padding: 14px 16px;
  border-radius: 4px;
  margin-top: 16px;
  border-left: 4px solid var(--danger);
}

button.primary {
  min-height: 48px;
  padding: 12px 32px;
  background: var(--cord);
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  letter-spacing: 0.02em;
}

button.primary:hover {
  background: #0c7a67;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(15, 110, 92, 0.3);
}

.portal-main {
  display: grid;
  grid-template-columns: 1fr;
  min-height: 100vh;
}

.portal-sidebar {
  display: none;
}

.portal-content {
  padding: 24px 16px 100px;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
}

.portal-bottom-nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  background: white;
  border-top: 1px solid var(--line);
  z-index: 50;
  box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.05);
}

.bottom-nav-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 68px;
  padding: 8px 4px;
  text-decoration: none;
  color: rgba(27, 36, 33, 0.6);
  transition: all 0.2s;
  border-top: 3px solid transparent;
}

.bottom-nav-item.active {
  color: var(--cord);
  border-top-color: var(--cord);
  background: rgba(15, 110, 92, 0.04);
}

.bottom-nav-item .nav-icon {
  font-size: 24px;
  margin-bottom: 4px;
}

.bottom-nav-item .nav-label {
  font-size: 11px;
  font-weight: 500;
  text-align: center;
}

.loading-view {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  font-size: 18px;
  color: rgba(27, 36, 33, 0.6);
}

@media (min-width: 1024px) {
  .portal-main {
    grid-template-columns: 280px 1fr;
  }

  .portal-sidebar {
    display: flex;
    flex-direction: column;
    background: white;
    border-right: 1px solid var(--line);
    padding: 32px 0;
    position: sticky;
    top: 0;
    height: 100vh;
    overflow-y: auto;
  }

  .sidebar-header {
    padding: 0 24px 24px;
    border-bottom: 1px solid var(--line);
    margin-bottom: 16px;
  }

  .sidebar-header h2 {
    font-family: var(--font-display);
    font-size: 24px;
    font-weight: 600;
    margin: 0 0 8px;
    letter-spacing: 0.01em;
  }

  .company-name {
    font-size: 14px;
    color: rgba(27, 36, 33, 0.6);
    margin: 0;
  }

  .sidebar-nav {
    flex: 1;
    display: flex;
    flex-direction: column;
    padding: 0 12px;
  }

  .nav-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    margin-bottom: 4px;
    text-decoration: none;
    color: rgba(27, 36, 33, 0.72);
    border-radius: 6px;
    transition: all 0.2s;
    min-height: 48px;
  }

  .nav-item:hover {
    background: rgba(15, 110, 92, 0.04);
    color: var(--ink);
  }

  .nav-item.active {
    background: rgba(15, 110, 92, 0.1);
    color: var(--cord);
    font-weight: 600;
  }

  .nav-item .nav-icon {
    font-size: 20px;
    width: 24px;
    text-align: center;
  }

  .nav-item .nav-label {
    font-size: 15px;
  }

  .logout-btn {
    margin: 16px 24px 0;
    min-height: 44px;
    padding: 10px 20px;
    background: transparent;
    color: rgba(27, 36, 33, 0.72);
    border: 1px solid rgba(27, 36, 33, 0.3);
    border-radius: 4px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }

  .logout-btn:hover {
    background: rgba(27, 36, 33, 0.04);
    border-color: var(--cord);
    color: var(--cord);
  }

  .portal-content {
    padding: 48px 40px;
  }

  .portal-bottom-nav {
    display: none;
  }
}
</style>

import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig(({ mode }) => ({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      "/api": loadEnv(mode, ".", "VERA_DEV_").VERA_DEV_API_URL || "http://127.0.0.1:8000",
    },
  },
}));

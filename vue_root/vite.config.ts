import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue({ template: { transformAssetUrls: { includeAbsolute: false }, compilerOptions: { isCustomElement: tag => tag === "math-field" } } })],
  root: ".",
  // Static assets are served by FastAPI in both development and production.
  // Never copy the backend directory (including .env and source) into dist.
  publicDir: false,
  build: {
    outDir: "dist",
    rollupOptions: {
      input: "index.html"
    }
  },
  server: {
    port: 5173,
    proxy: Object.fromEntries(["/api", "/static", "/videos", "/assets", "/css", "/js", "/docs"].map(path => [path, { target: "http://127.0.0.1:8000", changeOrigin: true, ws: path==='/api' }]))
  }
});


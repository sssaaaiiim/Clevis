import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import viteConfig from "./vite.config";
export default defineConfig({ plugins: [react()], resolve: viteConfig.resolve, test: { environment: "jsdom", maxWorkers: 1 } });

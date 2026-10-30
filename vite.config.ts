import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig(({mode})=>{const env=loadEnv(mode,process.cwd(),'APP_');return { plugins: [react()], root: 'frontend', build: { outDir: '../dist', emptyOutDir: true }, server: { proxy: { '/api': `http://127.0.0.1:${env.APP_PORT||8876}` } } };});

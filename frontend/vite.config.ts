import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({ plugins: [react()], build: { rollupOptions: { output: { manualChunks: { 'react-vendor': ['react', 'react-dom', 'react-router-dom'], 'query-vendor': ['@tanstack/react-query'], 'antd-vendor': ['antd', '@ant-design/icons'] } } } }, server: { port: 5173, proxy: { '/api': 'http://127.0.0.1:8000' } } })

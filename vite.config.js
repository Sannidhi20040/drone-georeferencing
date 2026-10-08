import { defineConfig } from 'vite'

export default defineConfig({
  base: '/drone-georeferencing/',
  optimizeDeps: {
    exclude: ['onnxruntime-web'],
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  }
})

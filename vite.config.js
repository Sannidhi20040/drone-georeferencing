import { defineConfig } from 'vite'

export default defineConfig({
  base: '/drone-georeferencing/',
  optimizeDeps: {
    exclude: ['onnxruntime-web'],
  },
  test: {
    include: ['src/**/*.test.js', 'scripts/**/*.test.js'],
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  }
})

import { defineConfig } from 'vite'

export default defineConfig({
  base: '/drone-georeferencing/',
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  }
})

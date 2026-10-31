import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// The page is built into dist/ and served by the FastAPI server (app/main.py) at "/".
// `npm run dev` runs it on 5173 with the API, the takes and the frames taken from the server on 8810.
const SERVER = process.env.RV_SERVER || 'http://127.0.0.1:8810'   // RV_SERVER: another server, e.g. a test one on 8821

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: { '/api': SERVER, '/outputs': SERVER, '/frames': SERVER },
  },
})

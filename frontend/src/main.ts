import { createApp } from 'vue'
import './styles/studio.css'
import './styles/lab.css'
import './styles/help-modal.css'
import App from './App.vue'
import router from './router'
import { i18n } from './i18n'

createApp(App).use(router).use(i18n).mount('#app')

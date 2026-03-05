import { createApp, } from 'vue'
import { createPinia } from 'pinia'
import { mdi } from 'vuetify/iconsets/mdi'
import App from './App.vue'

import { usePipelineStore } from './store'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@mdi/font/css/materialdesignicons.css'
import './style.css'

// Vuetify
import "vuetify/dist/vuetify.css"
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

const vuetify = createVuetify({
  theme: {
    defaultTheme: 'workflowLight',
    themes: {
      workflowLight: {
        dark: false,
        colors: {
          // Core surfaces
          background: '#efefef',
          surface: '#2d3748cf',
          surfaceVariant: '#0a7652bf',

          // Brand
          primary: '#2563eb',
          primarySoft:  '#5e88e3',

          // Semantic
          success: '#16a34a',
          warning: '#f59e0b',
          error: '#dc2626',

          // Graph domain (separate from semantic!)
          nodeDefaultBorder: '#925819',
          nodeNfCoreBorder: '#1a9655',

          // Text
          onSurface: '#cbd5e1',
          onPrimary: '#303030',
        }
      }
    }
  },
  icons: {
    defaultSet: "mdi",
    sets: { mdi }
  },
  components,
  directives,
})

const pinia = createPinia()
const app = createApp(App)
app.use(pinia)
app.use(vuetify)
app.mount("#app")

// Prepopulate data in the pipeline store
const pipelineStore = usePipelineStore()
pipelineStore.initialize()

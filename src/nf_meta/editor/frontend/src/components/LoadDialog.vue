<script setup lang="ts">
import { ref, watch } from 'vue'
import { useEditorStore, useGraphStore } from '../store'
import FileBrowser from './FileBrowser.vue'

const editorStore = useEditorStore()
const graphStore = useGraphStore()

const path = ref('')
const problem = ref<string>()
const loading = ref(false)
// a new key re-creates the browser, so it starts afresh each time the dialog opens
const browserKey = ref(0)

// Each time the dialog opens: start from the config being edited
watch(() => editorStore.loadDialogOpen, (open) => {
  if (!open) return
  path.value = graphStore.filename ?? ''
  problem.value = undefined
  browserKey.value++
})

function openFile(file: string) {
  path.value = file
  load()
}

async function load() {
  const target = path.value.trim()
  if (!target) {
    problem.value = 'Enter the path of a config file'
    return
  }
  loading.value = true
  try {
    problem.value = await graphStore.loadConfig(target)
    if (!problem.value) editorStore.closeLoadDialog()
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <v-dialog v-model="editorStore.loadDialogOpen" width="640" persistent>
    <v-card>
      <v-card-title>Open config</v-card-title>
      <v-form @submit.prevent="load">
        <v-card-text class="d-flex flex-column ga-3">
          <!-- the folders of the machine running the editor, not the browser's file picker,
               which only tells a picked file's name -->
          <FileBrowser
            :key="browserKey" :start="graphStore.filename" :selected="path"
            @select="(file) => path = file" @open="openFile" />
          <v-text-field
            v-model="path"
            label="Config file"
            placeholder="path/to/metapipeline.yaml"
            hint="Relative to the machine running 'nf-meta editor'"
            persistent-hint
            prepend-inner-icon="mdi-file-document-outline"
            autofocus
            variant="outlined"
            :error-messages="problem" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn :disabled="loading" @click="editorStore.closeLoadDialog()">Cancel</v-btn>
          <v-btn type="submit" color="primary" variant="flat" :loading="loading">Open</v-btn>
        </v-card-actions>
      </v-form>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useEditorStore, useGraphStore } from '../store'

const editorStore = useEditorStore()
const graphStore = useGraphStore()

const path = ref('')
const problem = ref<string>()
const loading = ref(false)

// Each time the dialog opens: start from the config being edited
watch(() => editorStore.loadDialogOpen, (open) => {
  if (!open) return
  path.value = graphStore.filename ?? ''
  problem.value = undefined
})

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
  <v-dialog v-model="editorStore.loadDialogOpen" width="560" persistent>
    <v-card>
      <v-card-title>Open config</v-card-title>
      <v-form @submit.prevent="load">
        <v-card-text>
          <!-- a path, not a file picker: the browser only tells the name of a picked file -->
          <v-text-field
            v-model="path"
            label="Config file"
            placeholder="path/to/metapipeline.yaml"
            hint="On the machine running nf-meta; relative paths start where 'nf-meta editor' was started"
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

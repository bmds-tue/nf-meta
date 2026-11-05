<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useEditorStore, useGraphStore } from '../store'
import { baseName, isUrl, joinPath } from '../utils'
import FileBrowser from './FileBrowser.vue'

const editorStore = useEditorStore()
const graphStore = useGraphStore()

const path = ref('')
const problem = ref<string>()
const saving = ref(false)
// a new key re-creates the browser, so it starts afresh each time the dialog opens
const browserKey = ref(0)

// A config loaded from a URL: saved as a local copy, browsing starts where the editor runs
const fromUrl = computed(() => isUrl(graphStore.filename))
const start = computed(() => (fromUrl.value ? undefined : graphStore.filename))

// Each time the dialog opens: start from the config being edited
watch(() => editorStore.saveDialogOpen, (open) => {
  if (!open) return
  path.value = fromUrl.value ? baseName(graphStore.filename ?? '') : graphStore.filename ?? ''
  problem.value = undefined
  browserKey.value++
})

// Browsing to a folder keeps the file name: the config is saved there under that name
function inFolder(folder: string) {
  path.value = joinPath(folder, baseName(path.value) || 'metapipeline.yaml')
}

async function save() {
  const target = path.value.trim()
  if (!target) {
    problem.value = 'Enter a file name'
    return
  }
  if (!/\.ya?ml$/i.test(target)) {
    problem.value = 'The file needs a .yaml or .yml extension'
    return
  }
  saving.value = true
  try {
    problem.value = await graphStore.saveAs(target)
    if (!problem.value) editorStore.closeSaveDialog(true)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <v-dialog v-model="editorStore.saveDialogOpen" width="640" persistent>
    <v-card>
      <v-card-title>{{ editorStore.saveDialogReason ? 'Save the config first' : 'Save config as' }}</v-card-title>
      <v-card-subtitle v-if="editorStore.saveDialogReason === 'new'" class="reason">
        Changes are saved to a file as you edit. Choose where this config goes.
      </v-card-subtitle>
      <v-card-subtitle v-else-if="editorStore.saveDialogReason === 'url'" class="reason">
        This config was loaded from {{ graphStore.filename }}. Choose where to save your copy.
      </v-card-subtitle>
      <v-form @submit.prevent="save">
        <v-card-text class="d-flex flex-column ga-3">
          <FileBrowser
            :key="browserKey" :start="start" :selected="path"
            @select="(file) => path = file" @open="(file) => { path = file; save() }" @folder="inFolder" />
          <v-text-field
            v-model="path"
            label="Config file"
            placeholder="path/to/metapipeline.yaml"
            hint="Relative to the machine running 'nf-meta editor'"
            persistent-hint
            prepend-inner-icon="mdi-content-save-outline"
            autofocus
            variant="outlined"
            :error-messages="problem" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn :disabled="saving" @click="editorStore.closeSaveDialog()">Cancel</v-btn>
          <v-btn type="submit" color="primary" variant="flat" :loading="saving">Save</v-btn>
        </v-card-actions>
      </v-form>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.reason {
  white-space: normal;
}
</style>

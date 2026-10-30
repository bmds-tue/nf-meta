<script setup lang="ts">
import { ref, watch } from 'vue'
import { useEditorStore, useGraphStore } from '../store'

const editorStore = useEditorStore()
const graphStore = useGraphStore()

const path = ref('')
const problem = ref<string>()
const saving = ref(false)

// Each time the dialog opens: start from the config being edited
watch(() => editorStore.saveDialogOpen, (open) => {
  if (!open) return
  path.value = graphStore.filename ?? ''
  problem.value = undefined
})

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
    if (!problem.value) editorStore.closeSaveDialog()
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <v-dialog v-model="editorStore.saveDialogOpen" width="560" persistent>
    <v-card>
      <v-card-title>Save config as</v-card-title>
      <v-form @submit.prevent="save">
        <v-card-text>
          <v-text-field
            v-model="path"
            label="Config file"
            placeholder="path/to/metapipeline.yaml"
            hint="On the machine running nf-meta; relative paths start where 'nf-meta editor' was started"
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

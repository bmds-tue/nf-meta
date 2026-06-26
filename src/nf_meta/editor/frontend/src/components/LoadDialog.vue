<script setup lang="ts">
import { useEditorStore } from '../store'
import { useGraphStore } from '../store'
import { ref } from 'vue'

const editorStore = useEditorStore()
const graphStore = useGraphStore()

const filename = ref<File>()
const errorMessages = ref<string[]>([])
const loading = ref(false)

function cleanup() {
    errorMessages.value = []
    editorStore.closeLoadDialog()
}

async function load() {
    if (!filename.value) {
        errorMessages.value.push("No file selected")
        return
    }
    loading.value = true
    try {
        await graphStore.loadConfig(filename.value.name)
        cleanup()
    } finally {
        loading.value = false
    }
}

function cancel() {
    cleanup()
}

</script>

<template>
  <v-dialog
    v-model="editorStore.loadDialogOpen"
    width="500"
    persistent
  >
    <v-card>
        <v-card-title>Load Config</v-card-title>
        <v-card-text>
            <v-file-input 
                label="File input" 
                variant="outlined"
                v-model="filename"
                :multiple="false"
                :error-messages=errorMessages
                clearable>
            </v-file-input>
        </v-card-text>

        <v-card-actions>
        <v-spacer />
        <v-btn @click="cancel" :disabled="loading">Cancel</v-btn>
        <v-btn @click="load" :loading="loading">Load selected file</v-btn>
        </v-card-actions>
    </v-card>
  </v-dialog>
</template>
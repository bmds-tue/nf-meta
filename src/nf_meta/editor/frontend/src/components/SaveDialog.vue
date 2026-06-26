<script setup lang="ts">
import { useEditorStore } from '../store'
import { useGraphStore } from '../store'
import { ref } from 'vue'

const editorStore = useEditorStore()
const graphStore = useGraphStore()

const filename = ref<string>(graphStore.filename || "")
const errorMessages = ref<string[]>([])
const saving = ref(false)

function resetDialog() {
    errorMessages.value = []
    filename.value = graphStore.filename || ""
}

async function save() {
    if (!filename.value) {
        errorMessages.value.push("Filename Required")
        return
    }
    if (!filename.value.endsWith(".yaml") && !filename.value.endsWith(".yml")) {
        errorMessages.value.push("File must have a .yaml or .yml extension")
        return
    }
    saving.value = true
    try {
        await graphStore.saveAs(filename.value)
        resetDialog()
        editorStore.closeSaveDialog()
    } finally {
        saving.value = false
    }
}

function cancel() {
    resetDialog()
    editorStore.closeSaveDialog()
}

</script>

<template>
  <v-dialog
    v-model="editorStore.saveDialogOpen"
    width="500"
    persistent
  >
    <v-card>
        <v-card-title>Save Project</v-card-title>
        <v-card-text>
            <v-text-field
                label="Filename"
                v-model="filename"
                :error-messages="errorMessages"
                autofocus
                variant="outlined"/>
        </v-card-text>

        <v-card-actions>
        <v-spacer />
        <v-btn @click="cancel" :disabled="saving">Cancel</v-btn>
        <v-btn @click="save" :loading="saving">Save</v-btn>
        </v-card-actions>
    </v-card>
  </v-dialog>
</template>
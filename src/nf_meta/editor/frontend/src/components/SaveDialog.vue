<script setup lang="ts">
import { useEditorStore } from '../store.ts'
import { useGraphStore } from '../store.ts'
import { ref } from 'vue'

const editorStore = useEditorStore()
const graphStore = useGraphStore()

const filename = ref<string>(graphStore.filename || "")
const errorMessages = ref<string[]>([])

function resetDialog() {
    errorMessages.value = []
    filename.value = graphStore.filename || ""
}

function save() {
    if (filename.value){
        if (!filename.value.endsWith(".yaml") &&
            !filename.value.endsWith(".yml")) {
                errorMessages.value.push("File must have a .yaml or .yml extension")
                return
        }
        graphStore.saveAs(filename.value).then(() => {
            resetDialog()
            editorStore.closeSaveDialog()
        })
    } else {
        errorMessages.value.push("Filename Required")
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
            />
        </v-card-text>

        <v-card-actions>
        <v-spacer />
        <v-btn @click="cancel">Cancel</v-btn>
        <v-btn @click="save">Save</v-btn>
        </v-card-actions>
    </v-card>
  </v-dialog>
</template>
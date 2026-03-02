<script setup lang="ts">
import { useEditorStore } from '../store.ts'
import { useGraphStore } from '../store.ts'
import { ref } from 'vue'

const editorStore = useEditorStore()
const graphStore = useGraphStore()

const filename = ref<File>()
const errorMessages = ref<string[]>([])

function cleanup() {
    errorMessages.value = []
    editorStore.closeLoadDialog()
}

function load() {
    console.log(filename)
    console.log(filename.value)
    if (filename.value){
        graphStore.loadConfig(filename.value.name).then(() => {
            cleanup()
        })
    } else {
        errorMessages.value.push("Unable to load File")
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
        <v-btn @click="cancel">Cancel</v-btn>
        <v-btn @click="load">Load selected file</v-btn>
        </v-card-actions>
    </v-card>
  </v-dialog>
</template>
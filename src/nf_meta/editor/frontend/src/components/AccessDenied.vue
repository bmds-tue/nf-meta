<script setup lang="ts">
import { useEditorStore } from '../store'

const editorStore = useEditorStore()
</script>

<template>
  <v-dialog :model-value="editorStore.accessDenied" width="520" persistent>
    <v-card prepend-icon="mdi-lock-outline" title="Cannot reach the editor backend">
      <v-card-text>
        Open the link printed by <code>nf-meta editor</code> in your terminal.
        On each restart, link and token changes.
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

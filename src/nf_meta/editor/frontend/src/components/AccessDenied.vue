<script setup lang="ts">
import { useEditorStore } from '../store'

const editorStore = useEditorStore()
</script>

<template>
  <v-dialog :model-value="editorStore.accessDenied" width="520" persistent>
    <v-card prepend-icon="mdi-lock-outline" title="This page can't reach the editor">
      <v-card-text>
        Open the link printed by <code>nf-meta editor</code> in your terminal; it carries this
        session's access token. A restarted editor prints a new link.
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

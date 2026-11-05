<script setup lang="ts">
import { computed } from 'vue'
import { useEditorStore } from '../store'

const editorStore = useEditorStore()
const shown = computed(() => editorStore.backendState !== 'ok')
</script>

<template>
  <v-dialog :model-value="shown" width="520" persistent>
    <v-card v-if="editorStore.backendState === 'refused'" prepend-icon="mdi-lock-outline" title="Cannot reach the editor backend">
      <v-card-text>
        Open the link printed by <code class="text-no-wrap">nf-meta editor</code> in your terminal.
        On each restart, link and token changes.
      </v-card-text>
    </v-card>
    <v-card v-else-if="editorStore.quitHere" prepend-icon="mdi-power" title="The editor is stopped">
      <v-card-text>
        Your changes are saved. You can close this tab now. To continue editing, run
        <code class="text-no-wrap">nf-meta editor</code> again and open the link printed in your terminal.
      </v-card-text>
    </v-card>
    <v-card v-else prepend-icon="mdi-power" title="The editor backend is not running">
      <v-card-text>
        It was stopped, or the connection to it is lost. Run <code class="text-no-wrap">nf-meta editor</code> again
        and open the link printed in your terminal.
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

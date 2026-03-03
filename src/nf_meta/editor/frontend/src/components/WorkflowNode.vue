<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'
import { computed } from 'vue'
import type { NodeProps } from '@vue-flow/core'
import type { APINodeData } from '../types.ts'

const props = defineProps<NodeProps<APINodeData>>()
    
const horizLayout = computed(() => {
    return props.targetPosition == Position.Left && 
        props.sourcePosition == Position.Right
}) 

</script>

<template>
  <v-container :class="['workflow-node', data.is_nfcore && 'workflow-node-nfcore']">
    <Handle class="workflow-node-handle" 
            :class="{'handle-horiz' : horizLayout }"
            type="target" 
            :position="targetPosition"
            />
        <strong>{{ data.name }}</strong> <v-chip v-if="data.version">{{ data.version }}</v-chip>
    <Handle class="workflow-node-handle"
            :class="{'handle-horiz' : horizLayout}"
            type="source" 
            :position="sourcePosition"
            /> 
  </v-container>

</template>

<style scoped>
.workflow-node-handle {
    background: #2d3f46;
    width: 20px;
    height: 10px;
    border-radius: 10px;
}
.handle-horiz {
    width: 10px;
    height: 20px;
}
</style>
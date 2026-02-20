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
  <div 
        class="workflow-node"
        :class="{'workflow-node-nfcore' : data.is_nfcore} ">
    <Handle class="workflow-node-handle" 
            :class="{'handle-horiz' : horizLayout }"
            type="target" 
            :position="targetPosition"
            />
    <div>{{ data.name }}</div>
    <div> {{ data.pipeline_location }} </div>
    <Handle class="workflow-node-handle"
            :class="{'handle-horiz' : horizLayout}"
            type="source" 
            :position="sourcePosition"
            /> 
  </div>

</template>

<style scoped>
.workflow-node-handle {
    background: #2d3f46;
    width: 35px;
    height: 7px;
    border-radius: 10px;
}
.handle-horiz {
    width: 7px;
    height: 35px;
}
</style>
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
:global(.workflow-node) {
    padding: 10px;
    color: #303030;
    background: #efefef;
    border-width: 2px;
    border-style: solid;
    border-radius: 10px;
    border-color: #925819;
}
:global(.workflow-node:hover) {
    box-shadow:0 0 0 2px #6c6c6c80;
    transition:box-shadow .2s;
}
:global(.workflow-node-nfcore) {
    border-color: #1a9655;
}
:global(.workflow-node-handle) {
    background: #2d3f46;
    width: 35px;
    height: 7px;
    border-radius: 10px;
}
:global(.handle-horiz) {
    width: 7px;
    height: 35px;
}
</style>
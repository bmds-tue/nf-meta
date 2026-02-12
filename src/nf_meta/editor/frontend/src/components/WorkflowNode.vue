<script setup>
import { Position, Handle } from '@vue-flow/core'
import { computed } from 'vue'
import { useLayout } from '../LayoutGraph.vue'

const { layoutOptions } = useLayout()
const props = defineProps(["label", "layout", "data"])
const horizLayout = computed(() => {
    console.log("props.layout", props.layout)
    console.log("Layouts.horizontal", layoutOptions.horizontal)
    return props.layout == layoutOptions.horizontal
})
</script>

<template>
  <div 
        class="workflow-node"
        :class="{'workflow-node-nfcore' : data?.is_nfcore} ">
    <Handle class="workflow-node-handle" 
            :class="{'handle-horiz' : horizLayout}"
            type="target" 
            :position="horizLayout ? Position.Left : Position.Top"
            />
    <div class="workflow-node-label">{{ label }}</div>
    <div> {{ data.pipeline_location }} </div>
    <Handle class="workflow-node-handle"
            :class="{'handle-horiz' : horizLayout}"
            type="source" 
            :position="horizLayout ? Position.Right : Position.Bottom"
            />
  </div>
</template>

<style scoped>
:global(.workflow-node) {
    padding: 10px;
    color: #fff;
    background: #9CA8B3;
    border-width: 2px;
    border-style: solid;
    border-radius: 4px;
    border-color: #ca7820;
}
:global(.workflow-node:hover) {
    box-shadow:0 0 0 2px #2563eb;
    transition:box-shadow .2s
}
:global(.workflow-node-nfcore) {
    border-color: #1a9655;
}
:global(.workflow-node-handle) {
    background: #2d3f46;
    width: 20px;
    height: 3px;
    border-radius: 1px;
}
:global(.handle-horiz) {
    width: 3px;
    height: 10px;
}

:global(.workflow-node-label) {
    width: 100%;
    justify-content: center
}
</style>
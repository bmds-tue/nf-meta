<script setup lang="ts">
import { Position, Handle } from '@vue-flow/core'
import { computed } from 'vue'
import { useLayout } from '../layout_graph.ts'

const props = defineProps({
        label: String,
        layout: String,
        data: Object
    })

const { layoutOptions } = useLayout()

const horizLayout = computed(() => {
    console.log("props.layout", props.layout)
    console.log("Layouts.horizontal", layoutOptions.horizontal)
    return props.layout == layoutOptions.horizontal
})
</script>

<template>
  <div 
        class="workflow-node"
        :class="{'workflow-node-nfcore' : props.data?.is_nfcore} ">
    <Handle class="workflow-node-handle" 
            :class="{'handle-horiz' : horizLayout}"
            type="target" 
            :position="horizLayout ? Position.Left : Position.Top"
            />
    <div>{{ props.label }}</div>
    <div> {{ props.data?.pipeline_location }} </div>
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
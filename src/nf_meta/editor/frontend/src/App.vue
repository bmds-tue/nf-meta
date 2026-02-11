<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { VueFlow, useVueFlow, MarkerType, ConnectionMode, type Node, type Edge } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { Layouts, useLayout } from './LayoutGraph.vue'
import WorkflowNode from './components/WorkflowNode.vue'


const { onConnect, addEdges } = useVueFlow()
const nodes = ref([])
const edges = ref([])
const { layout } = useLayout()
const { fitView } = useVueFlow()
const layoutDirection = Layouts.horizontal
            
onMounted(async () => {
  const res = await fetch('/api/graph/')
  const graph = await res.json()

  const direction = layoutDirection
  console.log(graph)
  edges.value = graph.transitions.map(t => ({
    ...t,
    markerEnd: MarkerType.ArrowClosed,
  }))
  nodes.value = layout(graph.nodes, graph.transitions, direction).map(n => ({
    ...n,
    layout: "vertical",
    type: "workflow-node"
  }))

  console.log(">>>NODES", nodes.value)
  console.log(">>>EDGES", edges.value)
})
</script>

<template>
  <div style="width: 100vw; height: 100vh;">
    <VueFlow 
      :nodes="nodes" 
      :edges="edges" 
      :connection-mode="ConnectionMode.Loose"
      fit-view-on-init>
      <Background />
      
      <template #node-workflow-node="props">
        <WorkflowNode v-bind="props" :layout="layoutDirection"/>
      </template>
    </VueFlow>
  </div>
</template>
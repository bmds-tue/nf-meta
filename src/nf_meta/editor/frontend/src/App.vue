<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { Node, Edge, Connection } from '@vue-flow/core'
import { VueFlow, useVueFlow, MarkerType, ConnectionMode} from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { useLayout } from './layout_graph.ts'
import WorkflowNode from './components/WorkflowNode.vue'
import type { APIEdgeData, APINodeData, APIGraph } from './types.ts'

const { addEdges } = useVueFlow()
const { fitView } = useVueFlow()
const { layout, layoutOptions } = useLayout()

const layoutDirection = layoutOptions.horizontal
const edges = ref<Edge<APIEdgeData>[]>()
const nodes = ref<Node<APINodeData>[]>()

const updateEdges = (newEdges: Edge[]) => {
  edges.value = newEdges.map(t => ({
    ...t,
    data: t.data ?? {},
    animated: true,
    markerEnd: MarkerType.Arrow,
    
  }))
}

const updateNodes = (newNodes: Node[]) => {
  nodes.value = newNodes.map(n => ({
    ...n,
    data: n.data ?? {},
    type: "workflow-node",
  }))
}

const onConnected = (conn: Connection) => {
  const edge = {
    ...conn,
    animated: true,
    markerEnd: MarkerType.Arrow
  }
  addEdges([edge])
}

onMounted(async () => {
  const res = await fetch('/api/graph/')
  const graph: APIGraph = await res.json()

  console.log(graph)
  updateEdges(graph.transitions)
  if (graph.nodes.length > 0) {
    updateNodes(layout(graph.nodes, graph.transitions, layoutDirection))
  }

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
      @connect=onConnected
      fit-view-on-init>
      <Background />
      
      <Controls></Controls>
      <template #node-workflow-node="nodeProps">
        <WorkflowNode 
          v-bind="nodeProps"/>
      </template>
    </VueFlow>
  </div>
</template>
<script setup lang="ts">
import { nextTick, ref, onMounted } from 'vue'
import type { Node, Edge, Connection } from '@vue-flow/core'
import { VueFlow, useVueFlow, MarkerType, ConnectionMode, Panel} from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { useLayout } from './layout_graph.ts'
import WorkflowNode from './components/WorkflowNode.vue'
import Icon from './components/Icon.vue'
import type { APIEdgeData, APINodeData, APIGraph } from './types.ts'

const { addEdges } = useVueFlow()
const { fitView } = useVueFlow()
const { layout, layoutOptions } = useLayout()

const layoutDirection = ref(layoutOptions.vertical)
const edges = ref<Edge<APIEdgeData>[]>([])
const nodes = ref<Node<APINodeData>[]>([])

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


const layoutGraph = async function(direction: string) {
  updateNodes(layout(nodes.value, edges.value, direction))
  layoutDirection.value = direction
  nextTick(() => {
    fitView()
  })
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
  updateNodes(layout(graph.nodes, graph.transitions, layoutDirection.value))

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
      <Panel class="process-panel" position="top-right">
        <div class="layout-panel">
          <button title="set horizontal layout" @click="layoutGraph(layoutOptions.horizontal)">
            <Icon name="horizontal" />
          </button>

          <button title="set vertical layout" @click="layoutGraph(layoutOptions.vertical)">
            <Icon name="vertical" />
          </button>
        </div>
      </Panel>
      
      <Controls></Controls>
      <template #node-workflow-node="nodeProps">
        <WorkflowNode 
          v-bind="nodeProps"/>
      </template>
    </VueFlow>
  </div>
</template>


<style>
.layout-flow {
  background-color: #1a192b;
  height: 100%;
  width: 100%;
}

.process-panel,
.layout-panel {
  display: flex;
  gap: 10px;
}

.process-panel {
  background-color: #2d3748;
  padding: 10px;
  border-radius: 8px;
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.5);
  display: flex;
  flex-direction: column;
}

.process-panel button {
  border: none;
  cursor: pointer;
  background-color: #4a5568;
  border-radius: 8px;
  color: white;
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.5);
}

.process-panel button {
  font-size: 16px;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.checkbox-panel {
  display: flex;
  align-items: center;
  gap: 10px;
}

.process-panel button:hover,
.layout-panel button:hover {
  background-color: #2563eb;
  transition: background-color 0.2s;
}

.process-panel label {
  color: white;
  font-size: 12px;
}

.stop-btn svg {
  display: none;
}

.stop-btn:hover svg {
  display: block;
}

.stop-btn:hover .spinner {
  display: none;
}

.spinner {
  border: 3px solid #f3f3f3;
  border-top: 3px solid #2563eb;
  border-radius: 50%;
  width: 10px;
  height: 10px;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}
</style>
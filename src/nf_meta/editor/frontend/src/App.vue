<script setup lang="ts">
import { nextTick, ref, onMounted } from 'vue'
import type { Node, Edge, Connection } from '@vue-flow/core'
import { VueFlow, useVueFlow, MarkerType, ConnectionMode, Panel} from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { useLayout } from './layout_graph.ts'
import WorkflowNode from './components/WorkflowNode.vue'
import Icon from './components/Icon.vue'
import Sidebar from './components/Sidebar.vue'
import Footer from './components/Footer.vue'
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


const switchLayout = async function() {
  layoutDirection.value = layoutDirection.value == layoutOptions.vertical ? 
      layoutOptions.horizontal : 
      layoutOptions.vertical

  updateNodes(layout(nodes.value, edges.value, layoutDirection.value))

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
  <div class="editor">
  
    <Panel class="process-panel" position="top-left">
      <div class="layout-panel">
        <div class="title"> 
          <h1>MetaFlow_2</h1>
        </div>
        <button title="add a workflow node">
          <Icon name="add" />
        </button>
        
        <button title="save to file">
          <Icon name="save" />
        </button>

        <button title="undo last operation">
          <Icon name="undo" />
        </button>

        <button title="redo last operations">
          <Icon name="redo" />
        </button>

        <button v-if="layoutDirection == layoutOptions.vertical" title="set horizontal layout" @click="switchLayout()">
          <Icon name="horizontal" />
        </button>

        <button v-else title="set vertical layout" @click="switchLayout()">
          <Icon name="vertical" />
        </button>

        <button title="editor options">
          <Icon name="split" />
        </button>

        <button title="editor options">
          <Icon name="options" />
        </button>
      </div>
    </Panel>
    <VueFlow 
      class="vueflow-graph"
      :nodes="nodes" 
      :edges="edges" 
      :connection-mode="ConnectionMode.Loose"
      @connect=onConnected
      fit-view-on-init>
      <Background />
      
      <template #node-workflow-node="nodeProps">
        <WorkflowNode 
          v-bind="nodeProps"/>
      </template>
    </VueFlow>

    <Footer class="footer"></Footer>
  </div>
</template>


<style scoped>
.editor {
  /* This fixes the scrollbar and no size for VueFlow issues: */
  position: fixed;
  inset: 0;
  
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
}

.editor * {
  outline: 1px solid red;
}

/* 
.editor aside {
  display: flex;
  flex-direction:column;
  gap:5px;
  color:#fff;
  font-weight:700;
  border-right:1px solid #eee;
  padding:10px;
  font-size:12px;
  background:#10b981bf;
  -webkit-box-shadow:0px 5px 10px 0px rgba(0,0,0,.3);
  box-shadow:0 5px 10px #0000004d
} */

.vueflow-graph {
  flex: 1;
  min-height: 0;
  min-width: 0;
}

.footer {
  flex-grow: 0;
  flex-shrink: 0;
}

.process-panel {
  flex: 0;
  padding: 10px;
  background-color: #2d3748cf;
  backdrop-filter: blur(6px);

  box-shadow: 0 0 10px rgba(0, 0, 0, 0.5);
  border-radius: 8px;
}

.layout-panel {
  display: flex;
  flex-direction: row;
  gap: 10px;
}

.title {
  margin-left: 50px;
  margin-right: 50px;

  h1 {
    color: white;
    margin: 0;
  }
}

.process-panel button {
  border: none;
  cursor: pointer;
  background-color: #4a5568;
  border-radius: 8px;
  color: white;
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.5);
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
/* 
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
} */
</style>
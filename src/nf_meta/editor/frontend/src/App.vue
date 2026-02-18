<script setup lang="ts">
import { watch, nextTick, ref, onMounted, computed } from 'vue'
import type { Node, Edge, Connection } from '@vue-flow/core'
import { VueFlow, useVueFlow, MarkerType, ConnectionMode, Panel} from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { useLayout } from './layout_graph.ts'
import WorkflowNode from './components/WorkflowNode.vue'
import Icon from './components/Icon.vue'
import Sidebar from './components/Sidebar.vue'
import Footer from './components/Footer.vue'
import type { APIEdgeData, APINodeData, APIGraph } from './types.ts'
import { useEditorStore, useGraphStore } from './store'

const editorStore = useEditorStore()
const graphStore = useGraphStore()

const { addEdges } = useVueFlow()
const { fitView } = useVueFlow()
const { layout } = useLayout()

const toggleSidebarAndfitView = async function() {
  editorStore.toggleSidebar()
  nextTick(() => {
    // TODO: Wait for component to be ready PROPERLY!
    setTimeout(fitView, 10)
  })
}

const toggleLayoutAndFitView = async function() {
  graphStore.switchLayout()
  nextTick(() => {
    // TODO: Wait for component to be ready PROPERLY!
    setTimeout(fitView, 10)  
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
  console.log("[INFO] Updating graph")
  graphStore.updateGraph()
})

</script>

<template>
  <div class="editor">
  
    <Panel class="process-panel" position="top-left">
      <div class="layout-panel">
        <div class="title"> 
          <h1>MetaFlow v2</h1>
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

        <button title="redo last operations" :disabled="true">
          <Icon name="redo" />
        </button>

        <button v-if="graphStore.isHorizontalLayout" title="set horizontal layout" @click="toggleLayoutAndFitView">
          <Icon name="horizontal" />
        </button>

        <button v-else title="set vertical layout" @click="toggleLayoutAndFitView">
          <Icon name="vertical" />
        </button>

        <button title="toggle sidebar" :class="{'btn-active': editorStore.showSidebar}" @click="toggleSidebarAndfitView" >
          <Icon name="split"/>
        </button>

        <button title="editor options">
          <Icon name="options" />
        </button>
      </div>
    </Panel>

    <div class="split-view">
      <VueFlow 
        class="vueflow-graph"
        :nodes="graphStore.nodes" 
        :edges="graphStore.edges" 
        :connection-mode="ConnectionMode.Loose"
        @connect=onConnected
        fit-view-on-init>
        <Background />
        
        <template #node-workflow-node="nodeProps">
          <WorkflowNode 
            v-bind="nodeProps"/>
        </template>
      </VueFlow>
  
      <Sidebar v-if="editorStore.showSidebar"></Sidebar>
    </div>
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
/* 
.editor * {
  outline: 1px solid red;
} */

.footer {
  flex-grow: 0;
  flex-shrink: 0;
}

.split-view {
  flex: 1;
  min-height: 0;
  min-width: 0;

  display: flex;
  flex-direction: row;
}
/* 
.split-view .vueflow-graph {
} */

.split-view aside {
  flex-shrink: 0;
}

.process-panel {
  flex: 0;
  padding: 10px;
  background-color: #2d3748cf;
  backdrop-filter: blur(6px);

  box-shadow: 0 0 10px rgba(0, 0, 0, 0.5);
  border-radius: 8px;

  .layout-panel {
    display: flex;
    flex-direction: row;
    gap: 10px;
  }

  .title {
    margin-left: 25px;
    margin-right: 25px;

    h1 {
      color: white;
      margin: 0;
    }
  }

 button {
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

  button:hover {
    background-color: #2563eb;
    transition: background-color 0.2s;
  }
}

button.btn-active {
    background-color: #5e88e3;
  }

button:disabled {
  background-color: #18233a;
  transition: none !important;
  cursor: not-allowed;
  /* This prevents :hover from triggering at all */
  pointer-events: none;
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
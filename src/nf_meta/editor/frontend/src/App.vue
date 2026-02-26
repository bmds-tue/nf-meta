<script setup lang="ts">
import { nextTick, onMounted } from 'vue'
import type { Node, Connection, NodeMouseEvent } from '@vue-flow/core'
import { VueFlow, useVueFlow, ConnectionMode, Panel} from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import WorkflowNode from './components/WorkflowNode.vue'
import Sidebar from './components/Sidebar.vue'
import Footer from './components/Footer.vue'
import Snackbar from './components/Snackbar.vue'
import { useEditorStore, useGraphStore } from './store'
import type { APINodeData } from './types'

const editorStore = useEditorStore()
const graphStore = useGraphStore()

const { fitView } = useVueFlow()

const toggleSidebarAndfitView = async function() {
  editorStore.toggleSidebar()
  nextTick(() => {
    setTimeout(fitView, 1)
  })
}

const toggleLayoutAndFitView = async function() {
  graphStore.switchLayout()
  nextTick(fitView)
}

const openNodeDetail = function (node: Node<APINodeData> | null | undefined = null) {
  if (!!node && !node.data) {
    console.warn("[WARN] Node from Graph view has no APINodeData: ", node)
    return
  }
  
  if (!editorStore.sideBarOpen) { editorStore.toggleSidebar() }
  editorStore.addNodeToSideBar(node?.data ?? {})
}

const onNodeDbClick = function (event: NodeMouseEvent) {
  openNodeDetail(event.node)
}

const onAddNodeClick = function (_: any) {
  openNodeDetail()
}

const onConnected = (conn: Connection) => {
  graphStore.saveEdge(conn)
}

onMounted(async () => {
  console.log("[INFO] Updating graph")
  graphStore.getAndUpdateGraph()
})

</script>

<template>
<v-app class="editor">
    <Panel class="process-panel" position="top-left">
      <v-container class="layout-panel">
          <h1>MetaFlow v2</h1>
        <v-btn 
          title="add a workflow node" 
          @click=onAddNodeClick
          icon="add"
          >
        </v-btn>
        
        <v-btn 
          title="save to file"
          icon="save">
        </v-btn>

        <v-btn
          title="undo last operation"
          icon="undo">
        </v-btn>

        <v-btn 
          title="redo last operations"
          :disabled="true" 
          icon="redo">
        </v-btn>

        <v-btn
          :title="graphStore.isHorizontalLayout ? 'set vertical layout' : 'set horizontal layout'" 
          @click="toggleLayoutAndFitView"
          :icon="graphStore.isHorizontalLayout ? 'vertical' : 'horizontal'">
        </v-btn>

        <v-btn 
          title="toggle sidebar" 
          :active="editorStore.sideBarOpen"
          active-color="primarySoft"
          @click="toggleSidebarAndfitView"
          icon="split">
        </v-btn>

        <v-btn 
          title="editor options"
          icon="options">
        </v-btn>
      </v-container>
    </Panel>

    <div class="split-view">
      <VueFlow 
        class="vueflow-graph"
        :nodes="graphStore.nodes" 
        :edges="graphStore.edges" 
        :connection-mode="ConnectionMode.Loose"
        @connect=onConnected
        @node-double-click=onNodeDbClick
        fit-view-on-init>
        <Background />
        
        <template #node-workflow-node="nodeProps">
          <WorkflowNode 
            v-bind="nodeProps"/>
        </template>
      </VueFlow>
  
      <Sidebar v-if="editorStore.sideBarOpen"></Sidebar>
    </div>
    <Snackbar></Snackbar>
    <Footer class="footer"></Footer>
</v-app>
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
  color: rgb(var(--v-theme-onSurface));
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

.split-view aside {
  flex-shrink: 0;
}

.process-panel {
  background-color: rgb(var(--v-theme-surface));
  backdrop-filter: blur(6px);
  border-radius: 8px;

  .layout-panel {
    display: flex;
    flex-direction: row;
    gap: 5px;
  }
  
  h1 {
    color: white;
    margin: 0;
    margin-right: 25px;
  }
}

</style>
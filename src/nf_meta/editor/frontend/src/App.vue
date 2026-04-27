<script setup lang="ts">
import { nextTick, onMounted, watch } from 'vue'
import type { Node, Connection, NodeMouseEvent } from '@vue-flow/core'
import { VueFlow, useVueFlow, ConnectionMode, Panel} from '@vue-flow/core'
import { storeToRefs } from 'pinia'
import { Background } from '@vue-flow/background'
import WorkflowNode from './components/WorkflowNode.vue'
import Sidebar from './components/Sidebar.vue'
import Footer from './components/Footer.vue'
import Snackbar from './components/Snackbar.vue'
import { useEditorStore, useGraphStore } from './store'
import type { APINodeData } from './types'
import SaveDialog from './components/SaveDialog.vue'
import LoadDialog from './components/LoadDialog.vue'
import { useLayout } from './layout_graph'

const editorStore = useEditorStore()
const graphStore = useGraphStore()

const { sideBarTab, sideBarOpen } = storeToRefs(editorStore)
const { setNodes, getNodes, getEdges, onNodesInitialized, fitView } = useVueFlow({id: "main-flow"})
const { layout } = useLayout()

const toggleLayoutAndFitView = async function() {
  graphStore.switchLayout()
  applyLayout()
  nextTick(fitView)
}

const openNodeDetail = function (node: Node<APINodeData> | null | undefined = null) {
  if (!!node && !node.data) {
    console.warn("[WARN] Node from Graph view has no APINodeData: ", node)
    return
  }
  
  if (!editorStore.sideBarOpen) { 
    editorStore.toggleSidebar() 
  }
  if (!node || !["nodes", "params"].includes(sideBarTab.value)) {
    sideBarTab.value = "nodes" 
  }
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

const onSave = () => {
  if (!graphStore.filename) {
    editorStore.openSaveDialog()
  } else {
    graphStore.save()
  }
}

const onOpen = () => {
  editorStore.openLoadDialog()
}

const onUndo = () => {
  graphStore.undo()
}

const onRedo = () => {
  graphStore.redo()
}


function applyLayout() {
    setNodes(layout(getNodes.value, getEdges.value, graphStore.layoutDirection))
}

// First Render
onNodesInitialized(() => {
    // Real dimensions now available — refine positions without re-fetching from backend
    applyLayout()
    nextTick(fitView)
})

// Subsequent backend-driven changes — watch the store refs
// nextTick ensures VueFlow has processed the new nodes before we read dimensions
watch(
    [() => graphStore.nodes, () => graphStore.edges],
    async () => {
        await nextTick()
        applyLayout()
    }
)

watch(
  sideBarOpen,
  async () => {
    nextTick(() => {
      setTimeout(fitView, 1)
    })
  }
)

onMounted(async () => {
  console.log("[INFO] Updating graph")
  graphStore.getAndUpdateGraph()
})

</script>

<template>
<v-app class="editor">
    <Panel class="process-panel" position="top-left">
      <v-container class="layout-panel">
          <h1>nf-meta</h1>
        <v-btn 
          title="add a workflow node" 
          icon="mdi-plus"
          @click=onAddNodeClick>
        </v-btn>
        
        <v-btn 
          title="save to file"
          icon="mdi-content-save"
          @click="onSave">
        </v-btn>

        <v-btn
          title="open from file"
          icon="mdi-upload"
          @click="onOpen">
        </v-btn>

        <v-btn
          title="undo last operation"
          :disabled="!graphStore.undoable"
          icon="mdi-undo"
          @click="onUndo">
        </v-btn>

        <v-btn 
          title="redo last operations"
          :disabled="!graphStore.redoable" 
          icon="mdi-redo"
          @click="onRedo">
        </v-btn>

        <v-btn
          :title="graphStore.isHorizontalLayout ? 'set vertical layout' : 'set horizontal layout'" 
          @click="toggleLayoutAndFitView"
          :icon="graphStore.isHorizontalLayout ? 'mdi-arrow-up-down' : 'mdi-arrow-left-right'">
        </v-btn>

        <v-btn 
          title="toggle sidebar" 
          :active="editorStore.sideBarOpen"
          active-color="primarySoft"
          @click="editorStore.toggleSidebar"
          icon="mdi-view-split-vertical">
        </v-btn>

        <v-btn 
          title="editor options"
          icon="mdi-dots-horizontal">
        </v-btn>
      </v-container>
    </Panel>

    <div class="split-view">
      <VueFlow 
        id="main-flow"
        class="vueflow-graph"
        :nodes="graphStore.nodes" 
        :edges="graphStore.edges" 
        :connection-mode="ConnectionMode.Strict"
        @connect=onConnected
        @node-double-click=onNodeDbClick
        :delete-key-code="null"
        fit-view-on-init>
        <Background />
        
        <template #node-workflow-node="nodeProps">
          <WorkflowNode 
            v-bind="nodeProps"/>
        </template>
      </VueFlow>
  
      <Sidebar v-if="editorStore.sideBarOpen"></Sidebar>
    </div>
    <LoadDialog></LoadDialog>
    <SaveDialog></SaveDialog>
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
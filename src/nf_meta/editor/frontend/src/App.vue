<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import type { Node, Connection, NodeMouseEvent } from '@vue-flow/core'
import { VueFlow, useVueFlow, ConnectionMode } from '@vue-flow/core'
import { storeToRefs } from 'pinia'
import { Background } from '@vue-flow/background'
import WorkflowNode from './components/WorkflowNode.vue'
import InputsNode from './components/InputsNode.vue'
import Sidebar from './components/Sidebar.vue'
import Footer from './components/Footer.vue'
import Snackbar from './components/Snackbar.vue'
import { useEditorStore, useGraphStore } from './store'
import type { APINodeData } from './types'
import SaveDialog from './components/SaveDialog.vue'
import LoadDialog from './components/LoadDialog.vue'
import { useLayout } from './layout_graph'
import { useTheme } from 'vuetify'
import { THEME_CHOICES, storeTheme, type ThemeName } from './themes'
// Inlined so the logo takes the text color (it is drawn in currentColor)
import logoSvg from './assets/nf-meta-octo.svg?raw'
import { DOCS_URL } from './links'

const editorStore = useEditorStore()
const graphStore = useGraphStore()

const theme = useTheme()
const themeName = computed(() => theme.global.name.value)
// The canvas dots are an SVG attribute, so they need the color itself, not a CSS variable
const gridColor = computed(() => theme.current.value.colors.grid as string)

function setTheme(name: ThemeName) {
  theme.change(name)
  storeTheme(name)
}

const { sideBarTab, sideBarOpen } = storeToRefs(editorStore)
const { setNodes, getNodes, getEdges, onNodesInitialized, fitView, findNode, addSelectedNodes, removeSelectedNodes } = useVueFlow({id: "main-flow"})
const { layout } = useLayout()

const fitGraph = () => fitView({ padding: 0.15 })

const toggleLayoutAndFitView = async function() {
  graphStore.switchLayout()
  applyLayout()
  nextTick(fitGraph)
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
  if (event.node.type === 'inputs-node') {
    editorStore.showInputs([])
    return
  }
  openNodeDetail(event.node)
}

const onAddNodeClick = function (_: any) {
  openNodeDetail()
}

const onConnected = (conn: Connection) => {
  graphStore.saveEdge(conn)
}

const onNodeHoverEnter = (e: NodeMouseEvent) => editorStore.setHoveredNodeId(e.node.id)
const onNodeHoverLeave = () => editorStore.setHoveredNodeId(undefined)

const saving = ref(false)
const undoing = ref(false)
const redoing = ref(false)

const onSave = async () => {
  if (!graphStore.filename) {
    editorStore.openSaveDialog()
    return
  }
  saving.value = true
  try { await graphStore.save() } finally { saving.value = false }
}

const onOpen = () => {
  editorStore.openLoadDialog()
}

const onUndo = async () => {
  undoing.value = true
  try { await graphStore.undo() } finally { undoing.value = false }
}

const onRedo = async () => {
  redoing.value = true
  try { await graphStore.redo() } finally { redoing.value = false }
}


function applyLayout() {
    setNodes(layout(getNodes.value, getEdges.value, graphStore.layoutDirection))
}

// First Render
onNodesInitialized(() => {
    // Real dimensions now available — refine positions without re-fetching from backend
    applyLayout()
    nextTick(fitGraph)
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
      setTimeout(fitGraph, 300)
    })
  }
)

watch(
  () => editorStore.sideBarActiveDetailId,
  (activeId) => {
    if (!activeId) return
    const detail = editorStore.sideBarNodes.find(d => d.id === activeId)
    const nodeId = detail && 'id' in detail.detailData ? detail.detailData.id : undefined
    removeSelectedNodes(getNodes.value.filter(n => n.selected))
    if (nodeId) {
      const node = findNode(nodeId)
      if (node) addSelectedNodes([node])
    }
  }
)

onMounted(async () => {
  console.log("[INFO] Updating graph")
  graphStore.getAndUpdateGraph()
})

</script>

<template>
<v-app class="editor">
    <header class="app-bar">
      <a class="logo" :href="DOCS_URL" target="_blank" title="nf-meta: open the documentation" v-html="logoSvg"></a>

      <!-- config file -->
      <v-menu location="bottom start">
        <template #activator="{ props: menuProps }">
          <v-btn v-bind="menuProps" title="Config file" variant="text" :loading="saving" class="file-btn">
            <v-icon icon="mdi-folder-outline" />
            <v-icon icon="mdi-menu-down" size="16" class="ml-n1" />
          </v-btn>
        </template>
        <v-list density="compact">
          <v-list-item prepend-icon="mdi-folder-open-outline" title="Open config…" subtitle="Ctrl/⌘+O" @click="onOpen" />
          <v-list-item prepend-icon="mdi-content-save-outline" title="Save" subtitle="Ctrl/⌘+S" @click="onSave" />
          <v-list-item prepend-icon="mdi-content-save-edit-outline" title="Save as…" subtitle="Ctrl/⌘+Shift+S" @click="editorStore.openSaveDialog" />
          <v-list-item prepend-icon="mdi-web" title="Load from URL" subtitle="Coming soon" disabled />
        </v-list>
      </v-menu>
      <v-divider vertical inset class="mx-1" />
      <!-- graph -->
      <div class="bar-group" aria-label="Graph">
        <v-btn title="Add a workflow" icon="mdi-plus" variant="text" @click="onAddNodeClick" />
        <v-btn title="Undo" icon="mdi-undo" variant="text" :disabled="!graphStore.undoable" :loading="undoing" @click="onUndo" />
        <v-btn title="Redo" icon="mdi-redo" variant="text" :disabled="!graphStore.redoable" :loading="redoing" @click="onRedo" />
        <v-btn
          :title="graphStore.showInputsNode ? 'Hide the inputs node' : 'Show the inputs node'"
          icon="mdi-import" variant="text"
          :active="graphStore.showInputsNode" active-color="primary"
          @click="graphStore.toggleInputsNode" />
        <v-btn
          :title="graphStore.isHorizontalLayout ? 'Vertical layout' : 'Horizontal layout'"
          :icon="graphStore.isHorizontalLayout ? 'mdi-arrow-up-down' : 'mdi-arrow-left-right'" variant="text"
          @click="toggleLayoutAndFitView" />
      </div>

      <v-spacer />

      <!-- editor -->
      <div class="bar-group" aria-label="Editor">
        <v-btn
          title="Show or hide the sidebar"
          icon="mdi-dock-right" variant="text"
          :active="editorStore.sideBarOpen" active-color="primary"
          @click="editorStore.toggleSidebar" />
        <v-menu location="bottom end">
          <template #activator="{ props: menuProps }">
            <v-btn v-bind="menuProps" title="Theme" icon="mdi-theme-light-dark" variant="text" class="mr-1" />
          </template>
          <v-list density="compact" :selected="[themeName]" @update:selected="(names: unknown[]) => names[0] && setTheme(names[0] as ThemeName)">
            <v-list-item
              v-for="choice in THEME_CHOICES" :key="choice.name" :value="choice.name"
              :title="choice.title" :subtitle="choice.subtitle" color="primary" />
          </v-list>
        </v-menu>
      </div>
    </header>

    <div class="split-view">
      <VueFlow 
        id="main-flow"
        class="vueflow-graph"
        :nodes="graphStore.nodes" 
        :edges="graphStore.edges" 
        :connection-mode="ConnectionMode.Strict"
        @connect=onConnected
        @node-double-click=onNodeDbClick
        @node-mouse-enter="onNodeHoverEnter"
        @node-mouse-leave="onNodeHoverLeave"
        :delete-key-code="null"
        fit-view-on-init>
        <Background :pattern-color="gridColor" :gap="20" />
        
        <template #node-workflow-node="nodeProps">
          <WorkflowNode 
            v-bind="nodeProps"/>
        </template>
        <template #node-inputs-node="nodeProps">
          <InputsNode v-bind="nodeProps" />
        </template>
      </VueFlow>
  
      <v-expand-x-transition>
        <Sidebar v-if="editorStore.sideBarOpen"></Sidebar>
      </v-expand-x-transition>
    </div>
    <LoadDialog></LoadDialog>
    <SaveDialog></SaveDialog>
    <Snackbar></Snackbar>
    <Footer></Footer>
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

.app-bar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 4px;
  height: 52px;
  padding: 0 8px;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  z-index: 5;
}

.file-btn {
  min-width: 0;
  padding: 0 8px;
}

.bar-group {
  display: flex;
  align-items: center;
  gap: 2px;
}

.logo {
  display: flex;
  align-items: center;
  color: rgb(var(--v-theme-on-surface));
  margin: 0 10px 0 4px;
  transition: opacity 0.15s;
}

.logo:hover {
  opacity: 0.8;
}

.logo :deep(svg) {
  width: 34px;
  height: 34px;
}

</style>
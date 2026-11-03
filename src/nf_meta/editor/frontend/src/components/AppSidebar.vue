<script setup lang="ts">
import NodeDetail from "./SidebarNodeDetail.vue"
import { nextTick, onBeforeUnmount, ref, watch } from "vue"
import { useVueFlow } from '@vue-flow/core'
import { storeToRefs } from 'pinia'
import { useEditorStore } from "../store"
import GlobalConfig from "./GlobalConfig.vue"
import InputsPanel from "./InputsPanel.vue"
import { useGraphStore } from "../store"

const editorStore = useEditorStore()
const graphStore = useGraphStore()

watch(() => graphStore.nodeData, (nodes) => editorStore.syncSidebarNodes(nodes), { immediate: true })

const { fitView } = useVueFlow()
const { sideBarTab } = storeToRefs(editorStore)



const vw = Math.max(document.documentElement.clientWidth || 0, window.innerWidth || 0)

const MIN = 0.15*vw
const MAX = 0.6*vw

const isDragging = ref(false)

const width = ref(
  Number(localStorage.getItem("pane-width")) || MIN
)

watch(width, v =>
  localStorage.setItem("pane-width", String(v))
)

let startX = 0
let startWidth = 0

const onMove = (e: MouseEvent) => {
  const delta = startX - e.clientX
  let next = startWidth + delta

  next = Math.max(MIN, Math.min(MAX, next))

  width.value = next
}

const stopDrag = () => {
    isDragging.value = false
    window.removeEventListener("pointermove", onMove)
    window.removeEventListener("pointerup", stopDrag)

    document.body.style.userSelect = ""
    document.body.style.cursor = ""

    nextTick(() => {
        fitView({ padding: 0.15 })
    })
}

const startDrag = (e: MouseEvent) => {
    isDragging.value = true

    startX = e.clientX
    startWidth = width.value

    document.body.style.userSelect = "none"
    document.body.style.cursor = "col-resize"

    window.addEventListener("pointermove", onMove)
    window.addEventListener("pointerup", stopDrag)
}

onBeforeUnmount(stopDrag)
</script>

<template>
  <aside class="split-pane" :class="{'dragging': isDragging}" :style="{ width: width + 'px' }">
    <v-tabs v-model="sideBarTab" density="compact" grow class="pane-tabs">
      <v-tab value="nodes">Steps</v-tab>
      <v-tab value="inputs">
        Inputs
        <v-badge
          v-if="graphStore.inputs.length"
          :content="graphStore.inputs.length"
          :color="graphStore.inputs.some(i => i.diagnostics.length) ? 'warning' : 'primary'"
          inline />
      </v-tab>
      <v-tab value="globals">Globals</v-tab>
    </v-tabs>

    <v-tabs-window v-model="sideBarTab" class="pane-body">
      <v-tabs-window-item value="nodes">
        <div class="pane-content">
          <div class="pane-actions">
            <v-btn size="small" variant="tonal" prepend-icon="mdi-plus" @click="editorStore.addNodeToSideBar({})">Add step</v-btn>
          </div>
          <TransitionGroup name="detail-fade">
            <NodeDetail
              v-for="sbDetail in editorStore.sideBarNodes"
              :key="sbDetail.id"
              :id="sbDetail.id"
              :detail-data="sbDetail.detailData">
            </NodeDetail>
          </TransitionGroup>
          <v-card v-if="editorStore.sideBarNodes.length == 0" text="No steps yet."></v-card>
        </div>
      </v-tabs-window-item>

      <v-tabs-window-item value="inputs">
        <div class="pane-content">
          <InputsPanel></InputsPanel>
        </div>
      </v-tabs-window-item>

      <v-tabs-window-item value="globals">
        <div class="pane-content">
          <GlobalConfig></GlobalConfig>
        </div>
      </v-tabs-window-item>
    </v-tabs-window>

    <div
      class="resize-handle"
      :class="{'dragging': isDragging}"
      title="Drag to resize"
      @pointerdown="startDrag">
    </div>
  </aside>
</template>

<style scoped>
/* docked below the app bar, full height, separated from the graph by a border */
.split-pane {
  position: relative;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: rgb(var(--v-theme-panel));
  border-left: 1px solid rgba(var(--v-theme-on-surface), 0.12);
}

.pane-tabs {
  /* Vuetify's tab bar is flexible by default; it must not grow in the column */
  flex: 0 0 auto;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
}

.pane-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

/* the same padding and spacing in every tab */
.pane-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
}

.pane-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 4px;
}

/* the left edge: drag to resize */
.resize-handle {
  position: absolute;
  top: 0;
  bottom: 0;
  left: -3px;
  width: 6px;
  cursor: col-resize;
  z-index: 2;
  transition: background 0.15s;
}

.resize-handle:hover,
.resize-handle.dragging {
  background: rgba(var(--v-theme-primary), 0.5);
}

.detail-fade-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease;
}
.detail-fade-leave-to {
  opacity: 0;
  transform: translateX(12px);
}
</style>
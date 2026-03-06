<script setup lang="ts">
import NodeDetail from "./SidebarNodeDetail.vue"
import { nextTick, onBeforeUnmount, ref, watch } from "vue"
import { useVueFlow } from '@vue-flow/core'
import { useEditorStore, useGraphStore } from "../store"
import YamlEditor from "./YamlEditor.vue"

const graphStore = useGraphStore()
const editorStore = useEditorStore()

const { fitView } = useVueFlow()

const props = defineProps(["resized"])

const tab = ref('nodes')

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
        fitView()
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

const closeDetail = (detailId: number) => {
  editorStore.removeSidebarDetail(detailId)
}

onBeforeUnmount(stopDrag)
</script>

<template>
  <v-container class="split-pane" :class="{'dragging': isDragging}" :style="{ width: width + 'px' }">
    <v-container class="pa-0 mb-1">
      <v-tabs v-model="tab">
        <v-tab value="nodes">Node Details</v-tab>
        <v-tab value="params">Params</v-tab>
      </v-tabs>
    </v-container>
    <v-tabs-window v-model="tab" class="d-flex flex-column fill-height">
      <v-tabs-window-item value="nodes">
        <v-container v-if="editorStore.sideBarNodes.length > 0" class="content">
          <NodeDetail 
            v-for="sbDetail in editorStore.sideBarNodes" 
            :id="sbDetail.id" 
            :detail-data="sbDetail.detailData"> 
          </NodeDetail>
        </v-container>
        <v-container v-if="editorStore.sideBarNodes.length == 0" class="content">
          <v-card
            text="Double click nodes to show detail"
          ></v-card>
        </v-container>
      </v-tabs-window-item>

      <v-tabs-window-item value="params" class="d-flex flex-column fill-height" transition="none">
        <v-container v-if="editorStore.sideBarNodes.length > 0 " class="d-flex flex-column flex-grow-1 pa-1">
          <v-card class="pa-0 mb-1 mt-0 flex-grow-1 d-flex flex-column">
            <v-card-title>
              <v-tabs v-model="editorStore.sideBarActiveDetailId" class="flex-grow-0" show-arrows>
                <v-tab v-for="detail of editorStore.sideBarNodes" :value="detail.id">
                  {{ detail.detailData.name ?? "New Workflow" }}
                  <template v-slot:append props="{{ detail }}">
                    <v-btn
                      title="close params detail"
                      icon="mdi-close"
                      size="small"
                      density="compact"
                      variant="plain"
                      rounded="circle"
                      @click.stop="closeDetail(detail.id)">
                    </v-btn>
                  </template>
                </v-tab>
              </v-tabs>
            </v-card-title>
            <v-card-text>

              <v-tabs-window v-model="editorStore.sideBarActiveDetailId" class="flex-grow-1 d-flex flex-column  mt-1" style="height: 100%;">
                <v-tabs-window-item v-for="detail of editorStore.sideBarNodes" :value="detail.id" class="flex-grow-1 d-flex flex-column min-h-0" style="height:100%">
                  <YamlEditor 
                    v-model="detail.detailData.params"
                    @save="graphStore.saveNode(detail.detailData)"
                  ></YamlEditor>
                </v-tabs-window-item>
              </v-tabs-window>
            </v-card-text>
            <!-- <v-card-actions class="flex-grow-0">
              <v-btn>
                Save changes
              </v-btn>
            </v-card-actions> -->
          </v-card> 
        </v-container>
        <v-container v-else class="content">
          <v-card
            text="Double click nodes to show detail"
          ></v-card>
        </v-container>
      </v-tabs-window-item>
    </v-tabs-window>

    <div
      class="resize-handle"
      :class="{'dragging': isDragging}"
      @pointerdown="startDrag">
    </div>
    
  </v-container>
</template>

<style scoped>

.split-pane {
    position: relative;
    flex-shrink: 0;

    display: flex;
    flex-direction:column;
    gap:5px;

    padding:10px;
    margin-top: 16px;

    -webkit-box-shadow:0px 5px 10px 0px rgba(0,0,0,.3);
    box-shadow:0 5px 10px #0000004d;

    border-radius: 8px;
    border: 2px solid rgb(var(--v-theme-surfaceVariant));
    background: rgb(var(--v-theme-surfaceVariant));
}

/* critical flex rule */
.content {
  flex: 1;
  min-width: 0;
  overflow: auto;
}

/* the draggable bar */
.resize-handle {
    position: absolute;
    left: -4px;
    top: 50%;
    transform: translateY(-50%);

    width: 8px;
    height: 120px;

    cursor: col-resize;
    border-radius: 6px;
    border-width: 2px;
    border-color:rgb(var(--v-theme-surface));;

    background: rgb(var(--v-theme-onSurface));
}

.resize-handle:hover {
    background: rgb(var(--v-theme-onSurface));
    transition: background 0.1s;
}

.resize-handle.dragging {
    background: rgba(235,235,235,0.9);
}

.split-pane.dragging {
    border-left: 2px solid #4a5568;
}
</style>
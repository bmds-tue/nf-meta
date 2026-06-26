<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'
import { computed, ref } from 'vue'
import type { NodeProps } from '@vue-flow/core'
import type { APINodeData } from '../types.ts'
import { WorkflowType } from '../types.ts'
import { useEditorStore } from '../store'

const editorStore = useEditorStore()

const copyIcon = ref("mdi-content-copy")

const props = defineProps<NodeProps<APINodeData>>()

const horizLayout = computed(() => {
    return props.targetPosition == Position.Left &&
        props.sourcePosition == Position.Right
})

const isModule = computed(() => props.data.type === WorkflowType.NF_MODULE)
const isNfCorePipeline = computed(() =>
    props.data.type === WorkflowType.NF_PIPELINE && props.data.is_nfcore
)
const isHovered = computed(() => editorStore.hoveredNodeId === props.id)

async function copyToClipboard() {
    try {
        await navigator.clipboard.writeText(props.id)
        copyIcon.value = 'mdi-check'
        setTimeout(() => (copyIcon.value = 'mdi-content-copy'), 2000)
    } catch (e) {
        console.error('Clipboard write failed:', e)
    }
}

</script>

<template>
  <v-container :class="['workflow-node', (isNfCorePipeline || isModule) && 'workflow-node-nfcore', isHovered && 'workflow-node-hovered']">
    <Handle class="workflow-node-handle"
            :class="{'handle-horiz' : horizLayout }"
            type="target"
            :position="targetPosition"
            />
    <div class="d-flex flex-column">
        <div class="d-flex flex-row align-center">
            <strong>
                {{ data.name }}
            </strong>
            <v-chip
                v-if="data.version"
                class="ml-2">
                {{ data.version }}
            </v-chip>
            <v-chip
                v-if="isModule"
                color="success"
                class="ml-1">
                module
            </v-chip>
        </div>
        <div class="d-flex flex-row align-center">
            <small> {{ data.id }} </small>
            <v-btn
                :icon="copyIcon"
                @click="copyToClipboard"
                @dbclick.stop
                size="x-small"
                variant="text"
                :ripple="false"
                flat>
            </v-btn>
        </div>
    </div>
    <!-- No source (output) handles for nf-module type. There is no stable mechanism for connection yet -->
    <Handle 
            v-if="!isModule"
            class="workflow-node-handle"
            :class="{'handle-horiz' : horizLayout}"
            type="source"
            :position="sourcePosition"
            />
  </v-container>

</template>

<style scoped>
.workflow-node-handle {
    background: #2d3f46;
    width: 20px;
    height: 10px;
    border-radius: 10px;
}
.handle-horiz {
    width: 10px;
    height: 20px;
}
</style>
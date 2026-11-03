<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'
import { computed, ref } from 'vue'
import type { NodeProps } from '@vue-flow/core'
import type { APINodeData } from '../types.ts'
import { WorkflowType } from '../types.ts'
import { useEditorStore, useGraphStore } from '../store'
import { inputFillsStep, inputsOfStep, shortVersion } from '../utils'

const editorStore = useEditorStore()
const graphStore = useGraphStore()

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
const hoveredInput = computed(() => graphStore.inputs.find(i => i.name === editorStore.hoveredInputName))
const isHovered = computed(() =>
    editorStore.hoveredNodeId === props.id || inputFillsStep(hoveredInput.value, props.id)
)
const filledBy = computed(() => inputsOfStep(graphStore.inputs, props.id))

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
                class="ml-2"
                size="small"
                :title="data.version">
                {{ shortVersion(data.version) }}
            </v-chip>
            <v-chip
                v-if="'path' in data && data.path"
                color="warning"
                size="small"
                class="ml-1"
                prepend-icon="mdi-folder-alert-outline"
                :title="`Local pipeline: ${data.path}. This config can't be reproduced elsewhere until the pipeline is published and used with a URL and version.`">
                local
            </v-chip>
            <v-chip
                v-if="isModule"
                color="success"
                size="small"
                class="ml-1">
                module
            </v-chip>
            <v-chip
                v-if="filledBy.length"
                class="ml-1 nodrag"
                size="small"
                prepend-icon="mdi-import"
                :title="filledBy.map(f => `${f.param} ← ${f.input.name}`).join('\n') + '\n\nClick to show in Inputs'"
                @click.stop="editorStore.showInputs(filledBy.map(f => f.input.name))"
                @dblclick.stop>
                {{ filledBy.length }}
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
    background: rgb(var(--v-theme-handle));
    width: 20px;
    height: 10px;
    border-radius: 10px;
}
.handle-horiz {
    width: 10px;
    height: 20px;
}
</style>
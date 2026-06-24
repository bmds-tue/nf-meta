<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useActivityStore } from '../store'
import type { APIEvent } from '../types'

const activityStore = useActivityStore()
const { log } = storeToRefs(activityStore)

function label(event: APIEvent): string {
    switch (event.type) {
        case 'WorkflowAdded': {
            const wf = event.workflow as { name?: string }
            return `Added '${wf?.name ?? '?'}'`
        }
        case 'WorkflowRemoved': {
            const wf = event.workflow as { name?: string }
            return `Removed '${wf?.name ?? '?'}'`
        }
        case 'WorkflowUpdated': {
            const wf = event.new_workflow as { name?: string }
            return `Updated '${wf?.name ?? '?'}'`
        }
        case 'TransitionAdded': {
            const tr = event.transition as { source?: string; target?: string }
            return `Added edge '${tr?.source ?? '?'} → ${tr?.target ?? '?'}'`
        }
        case 'TransitionRemoved': {
            const tr = event.transition as { source?: string; target?: string }
            return `Removed edge '${tr?.source ?? '?'} → ${tr?.target ?? '?'}'`
        }
        case 'GlobalOptionsUpdated':
            return 'Updated global options'
        default:
            return event.type
    }
}

function chipColor(eventType: string): string {
    if (eventType.endsWith('Added')) return 'success'
    if (eventType.endsWith('Removed')) return 'error'
    return 'warning'
}

function formatTime(date: Date): string {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
}
</script>

<template>
    <div class="log-wrapper">
        <v-list density="compact" class="pa-0">
            <v-list-item v-if="!log.length">
                No changes in history yet
            </v-list-item>
            <v-list-item
                v-for="(entry, i) in log"
                :key="i"
                class="px-1 py-0"
            >
                <div class="row-grid">
                    <div class="chip-cell">
                        <v-chip
                            :color="chipColor(entry.event.type)"
                            size="small"
                            label
                        >{{ entry.event.type }}</v-chip>
                    </div>
                    <span class="text-caption">{{ label(entry.event) }}</span>
                    <span class="text-caption timestamp">{{ formatTime(entry.timestamp) }}</span>
                </div>
            </v-list-item>
        </v-list>
    </div>
</template>

<style scoped>
.log-wrapper {
    width: 100%;
    overflow-y: auto;
}

.row-grid {
    display: flex;
    align-items: center;
    gap: 12px;
    width: 100%;
}

.chip-cell {
    flex: 0 0 160px;
}

.timestamp {
    margin-left: auto;
    white-space: nowrap;
}
</style>
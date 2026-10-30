<script setup lang="ts">
import { computed } from 'vue'
import { REF_COLOR } from '../store'
import type { ReferenceTarget } from '../utils'

const props = defineProps<{
  param: string
  references: ReferenceTarget[]
  size: number | string
  location?: 'bottom start' | 'end'
}>()

const emit = defineEmits<{
  pick: [stepId: string, key: string],
}>()

// Steps with params to offer: connected ones, then the others (saving adds their edge)
const connected = computed(() => props.references.filter(t => t.connected && t.params.length))
const unconnected = computed(() => props.references.filter(t => !t.connected && t.params.length))
const empty = computed(() => !connected.value.length && !unconnected.value.length)
</script>

<template>
  <!-- a wrapper element, so spacing classes from the parent apply -->
  <span class="d-inline-flex">
  <v-menu :location="location ?? 'bottom start'">
    <template #activator="{ props: menuProps }">
      <v-btn
        v-bind="menuProps"
        icon="mdi-transit-connection-variant" :size="size" variant="flat" class="pill-btn"
        :color="REF_COLOR" :title="`Fill '${param}' with a param of another step`"
        @click.stop />
    </template>
    <v-list density="compact" class="reference-list">
      <v-list-item v-if="empty" disabled title="No other step with params to reference yet" />
      <template v-if="connected.length">
        <v-list-subheader>Connected</v-list-subheader>
        <template v-for="target in connected" :key="target.stepId">
          <v-list-item
            v-for="p in target.params" :key="`${target.stepId}.${p.key}`"
            :title="`${target.stepName.split('/').pop()} · ${p.key}`" :subtitle="p.value"
            @click="emit('pick', target.stepId, p.key)" />
        </template>
      </template>
      <template v-if="unconnected.length">
        <v-list-subheader>Not connected yet: saving adds an edge</v-list-subheader>
        <template v-for="target in unconnected" :key="target.stepId">
          <v-list-item
            v-for="p in target.params" :key="`${target.stepId}.${p.key}`"
            :title="`${target.stepName.split('/').pop()} · ${p.key}`" :subtitle="p.value"
            @click="emit('pick', target.stepId, p.key)">
            <template #append>
              <v-icon icon="mdi-link-plus" size="16" class="muted" />
            </template>
          </v-list-item>
        </template>
      </template>
    </v-list>
  </v-menu>
  </span>
</template>

<style scoped>
.pill-btn :deep(.v-icon) {
  color: white;
  font-size: 15px;
}
.reference-list {
  max-height: 340px;
  min-width: 260px;
}
</style>

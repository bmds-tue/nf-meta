<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { INPUT_COLOR, REF_COLOR } from '../store'
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

// Two stages: pick a step (connected ones first), then one of its params
const open = ref(false)
const stepId = ref<string>()
watch(open, (isOpen) => { if (!isOpen) stepId.value = undefined })

const connected = computed(() => props.references.filter(t => t.connected))
const unconnected = computed(() => props.references.filter(t => !t.connected))
const step = computed(() => props.references.find(t => t.stepId === stepId.value))

function shortName(target: ReferenceTarget) {
  return target.stepName.split('/').pop()
}

function pick(key: string) {
  if (step.value) emit('pick', step.value.stepId, key)
  open.value = false
}
</script>

<template>
  <!-- a wrapper element, so spacing classes from the parent apply -->
  <span class="d-inline-flex">
    <v-menu v-model="open" :location="location ?? 'bottom start'" :close-on-content-click="false">
      <template #activator="{ props: menuProps }">
        <v-btn
          v-bind="menuProps"
          icon="mdi-transit-connection-variant" :size="size" variant="flat" class="pill-btn"
          :color="REF_COLOR" :title="`Fill '${param}' with a param of another step`"
          @click.stop />
      </template>

      <!-- stage 1: steps -->
      <v-list v-if="!step" density="compact" class="reference-list">
        <v-list-item v-if="!references.length" disabled title="No other step to reference yet" />
        <template v-for="group in [{ title: 'Connected', targets: connected }, { title: 'Not connected yet: saving adds an edge', targets: unconnected }]" :key="group.title">
          <template v-if="group.targets.length">
            <v-list-subheader>{{ group.title }}</v-list-subheader>
            <v-list-item
              v-for="target in group.targets" :key="target.stepId"
              :title="`${shortName(target)} (${target.stepId})`"
              :subtitle="target.params.length ? `${target.params.length} param${target.params.length === 1 ? '' : 's'}` : 'no params with a value'"
              :disabled="!target.params.length"
              append-icon="mdi-chevron-right"
              @click="stepId = target.stepId" />
          </template>
        </template>
      </v-list>

      <!-- stage 2: params of the chosen step -->
      <v-list v-else density="compact" class="reference-list">
        <v-list-item prepend-icon="mdi-chevron-left" :title="`${shortName(step)} (${step.stepId})`" class="back-row" @click="stepId = undefined" />
        <v-divider />
        <v-list-item
          v-for="p in step.params" :key="p.key"
          :title="p.key"
          @click="pick(p.key)">
          <template #subtitle>
            <span v-if="p.input" :style="{ color: INPUT_COLOR }">← input {{ p.input }}</span>
            <span v-else>{{ p.value }}</span>
          </template>
        </v-list-item>
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
.back-row {
  font-weight: 600;
}
</style>

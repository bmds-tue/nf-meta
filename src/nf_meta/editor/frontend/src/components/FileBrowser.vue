<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useApiStore } from '../store'
import type { FolderEntry, FolderListing } from '../types'
import { pathCrumbs } from '../utils'

// Browses the folders of the machine running the editor (which may be remote)
const props = defineProps<{
  // Where to start: a folder or a file (its folder is shown); none for the backend's default
  start?: string
  // The file currently chosen, highlighted in the list
  selected?: string
}>()

const emit = defineEmits<{
  // a file was clicked
  select: [path: string],
  // a file was double-clicked
  open: [path: string],
  // another folder is shown
  folder: [path: string],
}>()

const apiStore = useApiStore()

const listing = ref<FolderListing>()
const problem = ref<string>()
const loading = ref(false)
const allFiles = ref(false)

async function show(path?: string) {
  loading.value = true
  try {
    const result = await apiStore.listFolder(path, allFiles.value)
    if (result.ok) {
      listing.value = result.data
      problem.value = undefined
      emit('folder', result.data.path)
    } else {
      problem.value = result.message
    }
  } finally {
    loading.value = false
  }
}

function enter(entry: FolderEntry) {
  if (entry.kind === 'folder') show(entry.path)
  else emit('select', entry.path)
}

function toggleAllFiles() {
  allFiles.value = !allFiles.value
  show(listing.value?.path)
}

onMounted(async () => {
  await show(props.start || undefined)
  // a start that doesn't exist (e.g. a file name being typed): fall back to the default folder
  if (problem.value && props.start) await show()
})
</script>

<template>
  <div class="file-browser">
    <div class="d-flex align-center ga-1 browser-bar">
      <v-btn
        icon="mdi-arrow-up" size="small" variant="text" density="comfortable" title="Parent folder"
        :disabled="!listing?.parent" @click="show(listing?.parent ?? undefined)" />
      <div class="crumbs">
        <template v-for="(crumb, i) in pathCrumbs(listing?.path ?? '')" :key="crumb.path">
          <span v-if="i > 1" class="muted">/</span>
          <button type="button" class="crumb" @click="show(crumb.path)">{{ crumb.label }}</button>
        </template>
      </div>
      <v-spacer />
      <v-btn
        size="x-small" variant="text" :active="allFiles" title="Show every file, not only .yaml/.yml"
        @click="toggleAllFiles">
        All files
      </v-btn>
    </div>
    <v-progress-linear v-if="loading" indeterminate height="2" />
    <p v-if="problem" class="field-error px-2 my-1">{{ problem }}</p>
    <v-list density="compact" class="browser-list">
      <v-list-item
        v-for="entry in listing?.entries ?? []" :key="entry.path"
        :prepend-icon="entry.kind === 'folder' ? 'mdi-folder-outline' : 'mdi-file-document-outline'"
        :title="entry.name"
        :active="entry.kind === 'file' && entry.path === selected"
        color="primary"
        @click="enter(entry)"
        @dblclick="entry.kind === 'file' && emit('open', entry.path)" />
      <v-list-item v-if="listing && !listing.entries.length" disabled title="No folders or config files here" />
    </v-list>
  </div>
</template>

<style scoped>
.file-browser {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.15);
  border-radius: 6px;
  overflow: hidden;
}
.browser-bar {
  padding: 2px 4px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.1);
}
.crumbs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px;
  min-width: 0;
  font-size: 0.85rem;
}
.crumb {
  padding: 0 4px;
  border: none;
  border-radius: 4px;
  background: none;
  color: inherit;
  font: inherit;
  cursor: pointer;
}
.crumb:hover {
  background: rgba(var(--v-theme-on-surface), 0.08);
}
.browser-list {
  height: 260px;
  overflow-y: auto;
  padding: 0;
}
.field-error {
  color: rgb(var(--v-theme-error));
  font-size: 0.8rem;
}
</style>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { isUrl, pathSeparator, type PathPick } from '../utils'
import FileBrowser from './FileBrowser.vue'

// A button for the end of a path field: browses the folders of the machine running the editor
// and picks a file or folder (as an absolute path). The field itself stays free text, e.g. for URLs.
const props = defineProps<{
  pick: PathPick
  // The field's current value: where browsing starts, if it is a local path
  value?: string | null
  size?: number
}>()

const emit = defineEmits<{
  pick: [path: string],
}>()

const open = ref(false)
const path = ref('')
const folder = ref('')
const problem = ref<string>()

const TITLES: Record<PathPick, string> = {
  config: 'Choose a YAML file',
  file: 'Choose a file',
  folder: 'Choose a folder',
  path: 'Choose a file or folder',
}
const start = computed(() => (props.value && !isUrl(props.value) ? props.value : undefined))

function show() {
  path.value = start.value ?? ''
  problem.value = undefined
  open.value = true
}

// Browsing to a folder: in folder mode that folder is the choice
function onFolder(shown: string) {
  folder.value = shown
  if (props.pick === 'folder') path.value = shown
}

function choose(target = path.value.trim()) {
  if (!target) {
    problem.value = props.pick === 'folder' ? 'Pick a folder' : 'Pick a file'
    return
  }
  emit('pick', target)
  open.value = false
}

function chooseFolder() {
  choose(folder.value)
}

const folderName = computed(() => folder.value.split(pathSeparator(folder.value)).filter(Boolean).pop() ?? folder.value)
</script>

<template>
  <!-- stop clicks here from focusing the field -->
  <span class="path-picker" @click.stop @mousedown.stop>
    <v-btn
      icon="mdi-folder-open-outline" :size="size ?? 22" variant="text" density="comfortable"
      :title="`${TITLES[pick]} on the machine running the editor`" @click="show" />
    <v-dialog v-model="open" width="640">
      <v-card>
        <v-card-title>{{ TITLES[pick] }}</v-card-title>
        <v-form @submit.prevent="choose()">
          <v-card-text class="d-flex flex-column ga-3">
            <FileBrowser
              v-if="open" :pick="pick" :start="start" :selected="path"
              @select="(file) => path = file" @open="(file) => choose(file)" @folder="onFolder" />
            <v-text-field
              v-model="path"
              :label="pick === 'folder' ? 'Folder' : 'Path'"
              hint="Absolute path on the machine running 'nf-meta editor'"
              persistent-hint
              variant="outlined"
              :error-messages="problem" />
          </v-card-text>
          <v-card-actions>
            <v-btn
              v-if="pick === 'path' && folder" variant="text" prepend-icon="mdi-folder-outline"
              :title="folder" @click="chooseFolder">
              Choose folder “{{ folderName }}”
            </v-btn>
            <v-spacer />
            <v-btn @click="open = false">Cancel</v-btn>
            <v-btn type="submit" color="primary" variant="flat">
              {{ pick === 'folder' ? 'Choose this folder' : 'Choose' }}
            </v-btn>
          </v-card-actions>
        </v-form>
      </v-card>
    </v-dialog>
  </span>
</template>

<style scoped>
.path-picker {
  display: inline-flex;
  align-items: center;
}
</style>

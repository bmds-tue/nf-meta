<script setup lang="ts">
import { ref } from 'vue';
import CustomFileInput from './CustomFileInput.vue';
import YamlEditor from './YamlEditor.vue';
import { useGraphStore } from '../store';
import { extractFieldErrors } from '../utils';

const graphStore = useGraphStore()
const saving = ref(false)
const errors = ref<Record<string, string[]>>({})

async function save() {
    errors.value = {}
    saving.value = true
    try {
        const result = await graphStore.updateGlobalOptions(graphStore.globalOptions)
        if (!result.ok && result.fieldErrors) {
            errors.value = extractFieldErrors(result.fieldErrors, '')
        }
    } finally {
        saving.value = false
    }
}

</script>

<template>
    <v-card class="pa-0 mb-1 mt-0 flex-grow-1 d-flex flex-column">
    <v-card-title>
        Global Config
    </v-card-title>
    <v-form class="flex-grow-1 d-flex flex-column">
        <v-card-text class="flex-grow-1 d-flex flex-column h-100 min-h-100">
            <v-text-field
                label="Global Nextflow profile(s)"
                v-model="graphStore.globalOptions.profile"
                :error-messages="errors.nf_profile"
                variant="outlined"
                density="compact">
            </v-text-field>
            <CustomFileInput
                label="Global Nextflow Config File"
                :error-messages="errors.nf_config_file"
                v-model="graphStore.globalOptions.config_file">
            </CustomFileInput>
            <strong>
                Global Params:
            </strong>
            <YamlEditor
                v-model="graphStore.globalOptions.params"
                node-id=""
                @save="save"
                :server-error="errors['params']?.join('; ')">
            </YamlEditor>
        </v-card-text>
    </v-form>
    </v-card>
</template>
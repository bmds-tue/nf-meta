<script setup lang="ts">
import { ref } from 'vue';
import CustomFileInput from './CustomFileInput.vue';
import YamlEditor from './YamlEditor.vue';
import { useGraphStore } from '../store';

const graphStore = useGraphStore()
const errors = ref<Record<string, string[]>>({})

function save() {
    errors.value = {}
    graphStore.updateGlobalOptions(graphStore.globalOptions)
        .then(result => {
            if (!result.ok) {
                if (result?.fieldErrors) {
                    errors.value = graphStore.extractFieldErrors(result.fieldErrors, "")
                }
            }
        })
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
                @save="save">
            </YamlEditor>
        </v-card-text>
    </v-form>
    </v-card>
</template>
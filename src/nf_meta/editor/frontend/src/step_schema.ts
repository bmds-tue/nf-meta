import { ref, watch, type Ref } from 'vue'
import { useApiStore } from './store'
import type { StepSchema } from './types'

export type StepSchemaSource =
  | { kind: 'pipeline', url?: string, version?: string }
  | { kind: 'module', name?: string, version?: string }

/**
 * The param schema of the pipeline or module described by `source`, fetched
 * again whenever it changes (cached per version). `schema` is null until both
 * the pipeline's url (or module's name) and the version are set.
 */
export function useStepSchema(source: () => StepSchemaSource): {
    schema: Ref<StepSchema | null>, loading: Ref<boolean>, error: Ref<string | undefined>,
} {
    const apiStore = useApiStore()
    const schema = ref<StepSchema | null>(null)
    const loading = ref(false)
    const error = ref<string>()
    let latest = 0

    watch(source, async (s) => {
        const request = ++latest
        schema.value = null
        error.value = undefined
        const id = s.kind === 'pipeline' ? s.url : s.name
        if (!id || !s.version) return
        loading.value = true
        try {
            const result = s.kind === 'pipeline'
                ? await apiStore.getPipelineSchema(id, s.version)
                : await apiStore.getModuleSchema(id, s.version)
            if (request !== latest) return
            if (result.ok) schema.value = result.data
            else error.value = result.message
        } finally {
            if (request === latest) loading.value = false
        }
    }, { immediate: true, deep: true })

    return { schema, loading, error }
}

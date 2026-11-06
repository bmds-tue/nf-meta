import { ref, watch, type Ref } from 'vue'
import { useApiStore } from './store'
import type { StepSchema } from './types'

// How long typing has to pause before a schema is fetched
const FETCH_PAUSE_MS = 400

export type StepSchemaSource =
  | { kind: 'pipeline', url?: string, version?: string, path?: string, main_script?: string }
  | { kind: 'module', name?: string, version?: string }

/**
 * The param schema of the pipeline or module described by `source`, fetched
 * again whenever it changes (cached per version). `schema` is null until both
 * the pipeline's url (or module's name) and the version are set, or a local
 * pipeline's path.
 */
export function useStepSchema(source: () => StepSchemaSource): {
    schema: Ref<StepSchema | null>, loading: Ref<boolean>, error: Ref<string | undefined>,
} {
    const apiStore = useApiStore()
    const schema = ref<StepSchema | null>(null)
    const loading = ref(false)
    const error = ref<string>()
    let latest = 0

    // Typed values (a URL, a local path) change on every keystroke: fetch after a short pause,
    // and keep showing the current schema meanwhile, so the form doesn't jump
    let timer: ReturnType<typeof setTimeout> | undefined
    watch(source, (s) => {
        const request = ++latest
        clearTimeout(timer)
        const id = s.kind === 'pipeline' ? s.url : s.name
        const local = s.kind === 'pipeline' ? s.path : undefined
        if (!local && (!id || !s.version)) {
            schema.value = null
            error.value = undefined
            loading.value = false
            return
        }
        // a spinner only when there is nothing to show yet (no schema, no message)
        loading.value = schema.value === null && error.value === undefined
        timer = setTimeout(async () => {
            try {
                const result = local
                    ? await apiStore.getLocalPipelineSchema(local, s.kind === 'pipeline' ? s.main_script : undefined)
                    : s.kind === 'pipeline'
                        ? await apiStore.getPipelineSchema(id!, s.version!, s.main_script)
                        : await apiStore.getModuleSchema(id!, s.version!)
                if (request !== latest) return
                schema.value = result.ok ? result.data : null
                error.value = result.ok ? undefined : result.message
            } finally {
                if (request === latest) loading.value = false
            }
        }, schema.value === null && !local ? 0 : FETCH_PAUSE_MS)
    }, { immediate: true, deep: true })

    return { schema, loading, error }
}

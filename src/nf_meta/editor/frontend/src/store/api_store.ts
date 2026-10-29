import { ref } from 'vue'
import { defineStore } from 'pinia'
import type {
    ApiResult, APIGraph, APICommandResponse,
    APINodeData, APIEdgeData, APIGlobalOptions, APIInputSave, Selection, StepSchema,
    NfCorePipelineInfo, NfCoreModuleInfo, NfCoreModuleVersionInfo,
} from '../types'

export const useApiStore = defineStore('api', () => {
    async function request<T>(endpoint: string, options: RequestInit): Promise<ApiResult<T>> {
        try {
            const response = await fetch(endpoint, {
                headers: { 'Content-Type': 'application/json' },
                ...options,
            })
            const data = await response.json()
            if (!response.ok) {
                if (response.status === 422) {
                    return {
                        ok: false,
                        status: 422,
                        message: 'Validation error',
                        fieldErrors: data.field_errors ?? [],
                        graphErrors: data.graph_errors ?? [],
                    }
                }
                return { ok: false, status: response.status, message: data?.detail ?? 'Request failed' }
            }
            return { ok: true, data }
        } catch (e) {
            console.error(e)
            return { ok: false, status: 0, message: 'Error while making request' }
        }
    }

    function getGraph() {
        return request<APIGraph>('/api/graph/', { method: 'GET' })
    }

    function saveGraph(config: string) {
        return request<void>('/api/graph/save/', { method: 'POST', body: JSON.stringify({ config }) })
    }

    function loadGraph(config: string) {
        return request<void>('/api/graph/load/', { method: 'POST', body: JSON.stringify({ config }) })
    }

    function undoGraph() {
        return request<APICommandResponse>('/api/graph/undo/', { method: 'GET' })
    }

    function redoGraph() {
        return request<APICommandResponse>('/api/graph/redo/', { method: 'GET' })
    }

    function addNode(wf: APINodeData) {
        return request<APICommandResponse>('/api/node/add/', { method: 'POST', body: JSON.stringify(wf) })
    }

    function updateNode(wf: APINodeData) {
        return request<APICommandResponse>('/api/node/update/', { method: 'POST', body: JSON.stringify(wf) })
    }

    function deleteSelection(selection: Selection) {
        return request<APICommandResponse>('/api/delete/', { method: 'DELETE', body: JSON.stringify(selection) })
    }

    function addEdge(tr: APIEdgeData) {
        return request<APICommandResponse>('/api/edge/add/', { method: 'POST', body: JSON.stringify(tr) })
    }

    function updateGlobalOptions(globals: APIGlobalOptions) {
        return request<APICommandResponse>('/api/globals/update/', { method: 'POST', body: JSON.stringify(globals) })
    }

    function saveInput(input: APIInputSave) {
        return request<APICommandResponse>('/api/inputs/save/', { method: 'POST', body: JSON.stringify(input) })
    }

    function setInputsStyle(inParams: boolean) {
        return request<APICommandResponse>('/api/inputs/style/', { method: 'POST', body: JSON.stringify({ in_params: inParams }) })
    }

    function declareStepInputs(nodeId: string) {
        return request<APICommandResponse>(`/api/node/${encodeURIComponent(nodeId)}/declare-inputs/`, { method: 'POST' })
    }

    function deleteInput(name: string) {
        return request<APICommandResponse>('/api/inputs/delete/', { method: 'DELETE', body: JSON.stringify({ name }) })
    }

    function getNodeSchema(nodeId: string) {
        return request<StepSchema>(`/api/node/${encodeURIComponent(nodeId)}/schema/`, { method: 'GET' })
    }

    // Param schemas of pipelines and modules that may not be in the graph yet, cached per version
    const schemaCache = new Map<string, Promise<ApiResult<StepSchema>>>()

    function getPipelineSchema(url: string, version: string) {
        const key = `pipeline ${url} ${version}`
        if (!schemaCache.has(key)) {
            const query = new URLSearchParams({ url, version })
            schemaCache.set(key, request<StepSchema>(`/api/nfcore/pipelines/schema/?${query}`, { method: 'GET' }))
        }
        return schemaCache.get(key)!
    }

    function getModuleSchema(name: string, version: string) {
        const key = `module ${name} ${version}`
        if (!schemaCache.has(key)) {
            const short = encodeURIComponent(name.replace(/^nf-core\//, ''))
            const query = new URLSearchParams({ version })
            schemaCache.set(key, request<StepSchema>(`/api/nfcore/modules/${short}/schema/?${query}`, { method: 'GET' }))
        }
        return schemaCache.get(key)!
    }

    return {
        getGraph, saveGraph, loadGraph,
        undoGraph, redoGraph,
        addNode, updateNode, deleteSelection, addEdge, updateGlobalOptions,
        saveInput, deleteInput, declareStepInputs, setInputsStyle,
        getNodeSchema, getPipelineSchema, getModuleSchema,
    }
})

export const usePipelineStore = defineStore('pipeline', () => {
    const nfCorePipelines = ref<NfCorePipelineInfo[]>()
    const initError = ref<string>()

    async function initialize() {
        try {
            const r = await fetch('/api/nfcore/pipelines/', { method: 'GET', headers: { 'Content-Type': 'application/json' } })
            if (!r.ok) throw new Error(`HTTP ${r.status}`)
            nfCorePipelines.value = await r.json()
        } catch {
            initError.value = 'Failed to load nf-core pipelines'
        }
    }

    return { initialize, nfCorePipelines, initError }
})

export const useModuleStore = defineStore('module', () => {
    const nfCoreModules = ref<NfCoreModuleInfo[]>()
    const initError = ref<string>()

    async function initialize() {
        try {
            const r = await fetch('/api/nfcore/modules/', { method: 'GET', headers: { 'Content-Type': 'application/json' } })
            if (!r.ok) throw new Error(`HTTP ${r.status}`)
            nfCoreModules.value = await r.json()
        } catch {
            initError.value = 'Failed to load nf-core modules'
        }
    }

    async function fetchModuleVersions(shortName: string): Promise<NfCoreModuleVersionInfo[]> {
        const response = await fetch(`/api/nfcore/modules/${shortName}/versions/`, { method: 'GET' })
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json() as Promise<NfCoreModuleVersionInfo[]>
    }

    return { initialize, nfCoreModules, initError, fetchModuleVersions }
})
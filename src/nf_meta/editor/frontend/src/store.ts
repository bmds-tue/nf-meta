import type { ApiResult, APINodeData, APIEdgeData, APIGraph, APICommandResponse, APIEvent, Selection, SideBarDetail, NfCorePipelineInfo, NfCoreModuleInfo, NfCoreModuleVersionInfo, APIGlobalOptions, FieldError, NewNodeData } from './types'
import { WorkflowType } from './types'
import type { Node, Edge } from '@vue-flow/core'
import { MarkerType } from '@vue-flow/core'
import { ref, computed, watch } from 'vue'
import { defineStore } from 'pinia'

import { useLayout } from './layout_graph.ts'

export const useMessageStore = defineStore("message", () => {
    interface Message {
        text: string,
        color: string,
        timeout?: number,
    }
    const queue = ref<Message[]>([])

    function add(text: string, color = "success") {
        if (!["success", "error", "warning"].includes(color)) {
            console.warn("Message store: Invalid color received:", color, text)
        }
        queue.value.push({
            text: text,
            color: color,
            timeout: 2000,
        })
    }

    return {
        queue,
        add
    }
})

export const useEditorStore = defineStore("editor", () => {
    // read from local browser storage and default to true
    const _sideBarOpen = ref(localStorage.getItem("showSideBar") == "true")
    const sideBarOpen = computed(() => _sideBarOpen.value)

    const sideBarTab = ref('nodes')
    const sideBarActiveDetailId = ref(0)
    const _nextSideBarId = ref(1)
    const _sideBarNodes = ref<SideBarDetail<APINodeData | NewNodeData>[]>([])
    const sideBarNodes = computed(() => _sideBarNodes.value)

    const _saveDialogOpen = ref<boolean>(false)
    const saveDialogOpen = computed(() => _saveDialogOpen.value)

    const _loadDialogOpen = ref<boolean>(false)
    const loadDialogOpen = computed(() => _loadDialogOpen.value)

    function openLoadDialog() {
        closeSaveDialog()
        _loadDialogOpen.value = true
    }

    function closeLoadDialog() {
        _loadDialogOpen.value = false
    }

    function openSaveDialog() {
        closeLoadDialog()
        _saveDialogOpen.value = true
    }

    function closeSaveDialog() {
        _saveDialogOpen.value = false
    }

    function toggleSidebar() {
        _sideBarOpen.value = !_sideBarOpen.value
        localStorage.setItem("showSideBar", String(_sideBarOpen.value))
    }

    function setActiveSidebarDetailId(id: number) {
        sideBarActiveDetailId.value = id
    }

    function createSideBarDetailWithId<T>(detailData: T): SideBarDetail<T> {
        _nextSideBarId.value++
        return { id: _nextSideBarId.value, detailData: detailData }
    }

    function addNodeToSideBar(node: APINodeData | NewNodeData) {
        // If the node is not new (i.e. has an id)
        // -> Check if it is already opened in the side bar and jump there instead
        // If it is new, there should only be one being created at a time.
        const nodeId = 'id' in node ? node.id : undefined
        const existingDetail = sideBarNodes.value.find((sideBarDetail) => {
            const detailId = 'id' in sideBarDetail.detailData ? sideBarDetail.detailData.id : undefined
            return detailId == nodeId
        })
        if (existingDetail) {
            setActiveSidebarDetailId(existingDetail.id)
            return
        }

        const newDetail = createSideBarDetailWithId(node)
        if (!('id' in newDetail.detailData)) {
            _sideBarNodes.value = [newDetail, ..._sideBarNodes.value]
        } else {
            _sideBarNodes.value = [..._sideBarNodes.value, newDetail]
        }
        setActiveSidebarDetailId(newDetail.id)
    }

    function removeSidebarDetail(id: number) {
        _sideBarNodes.value = _sideBarNodes.value.filter(
            (sideBarDetail) => sideBarDetail.id != id)
    }

    function collapseSidebarDetail(id: number) {
        if (id == sideBarActiveDetailId.value) {
            console.log("Active Status changing!")
            sideBarActiveDetailId.value = 0
        }
    }

    return {
        showSidebar: sideBarOpen, sideBarOpen, toggleSidebar,
        sideBarActiveDetailId, setActiveSidebarDetailId,
        sideBarTab, sideBarNodes, addNodeToSideBar,
        removeSidebarDetail, collapseSidebarDetail,
        saveDialogOpen, openSaveDialog, closeSaveDialog,
        loadDialogOpen, openLoadDialog, closeLoadDialog
    }
})

export const useActivityStore = defineStore("activity", () => {
    interface LogEntry {
        event: APIEvent
        timestamp: Date
    }

    const log = ref<LogEntry[]>([])
    const drawerOpen = ref(false)

    function pushEvents(events: APIEvent[]) {
        const entries = events.map(event => ({ event, timestamp: new Date() }))
        log.value = [...entries, ...log.value]
    }

    function clear() {
        log.value = []
    }

    function toggleDrawer() {
        drawerOpen.value = !drawerOpen.value
    }

    return { log, pushEvents, clear, drawerOpen, toggleDrawer }
})

export const useGraphStore = defineStore('graph', () => {

    const { layoutOptions } = useLayout()
    const messageStore = useMessageStore()
    const activityStore = useActivityStore()

    // Track the API retruned Data for internal use
    // to avoid buggy resolution of the 
    // deep Node and Edge types from VueFlow
    const _edgeData = ref<APIEdgeData[]>([])
    const _nodeData = ref<APINodeData[]>([])

    const _edges = ref<Edge<APIEdgeData>[]>([])
    const _nodes = ref<Node<APINodeData>[]>([])

    const edges = computed(() => {
        return _edges.value
    })

    const nodes = computed(() => {
        return _nodes.value
    })

    const globalOptions = ref<APIGlobalOptions>({
        params: {},
        config_file: "",
        profile: "",
    })

    const _filename = ref<string>()
    const filename = computed(() => _filename.value)
    watch(_filename, updatePageTitle)

    const _redoable = ref<boolean>(false)
    const redoable = computed(() => _redoable.value)
    const _undoable = ref<boolean>(false)
    const undoable = computed(() => _undoable.value)

    const _isHorizontalLayout = ref(localStorage.getItem("isHorizontalLayout") == "true")
    const isHorizontalLayout = computed(() => _isHorizontalLayout.value)
    const layoutDirection = computed(() => (_isHorizontalLayout.value ? layoutOptions.horizontal : layoutOptions.vertical))

    async function switchLayout() {
        _isHorizontalLayout.value = !_isHorizontalLayout.value
        localStorage.setItem("isHorizontalLayout", String(isHorizontalLayout.value))
    }

    async function updatePageTitle() {
        document.title = _filename.value ? `nf-meta - ${_filename.value}` : "nf-meta"
    }

    function createNodeWithDefaults(nodeData: APINodeData): Node<APINodeData> {
        console.log("createNodeWithDefaults: Setting id:", nodeData?.id)
        return {
            data: nodeData,
            label: nodeData.name,
            // required attributes for Node
            id: nodeData?.id || "",
            position: nodeData?.position ?? { x: 0, y: 0 },
            // apply common node attributes (e.g. our custom node type)
            type: "workflow-node"
        } as Node<APINodeData>
    }

    function createEdgeWithDefaults(edgeData: APIEdgeData): Edge<APIEdgeData> {
        return {
            id: edgeData?.id || `${edgeData.source}->${edgeData.target}`,
            source: edgeData.source,
            target: edgeData.target,
            data: edgeData,
            // apply common default edge attributes
            animated: false,
            markerEnd: MarkerType.ArrowClosed
        }
    }

    async function apiRequest<T>(endpoint: string, options: RequestInit): Promise<ApiResult<T>> {
        try {
            const response = await fetch(endpoint, { headers: { 'Content-Type': 'application/json' }, ...options })
            const data = await response.json()
            if (!response.ok) {
                if (response.status === 422) {
                    return {
                        ok: false,
                        status: 422,
                        message: "Validation error",
                        fieldErrors: data.field_errors ?? [],
                        graphErrors: data.graph_errors ?? []
                    }
                }

                return {
                    ok: false,
                    status: response.status,
                    message: data?.detail ?? "Request failed"
                }
            }

            return { ok: true, data: data }

        } catch (e) {
            console.error(e)
            return {
                ok: false,
                status: 0,
                message: "Error while making request"
            }
        }
    }

    function extractFieldErrors(fieldErrors: FieldError[], workflowId: string): Record<string, string[]> {
        const result: Record<string, string[]> = {}
        const discriminators = new Set<string>(Object.values(WorkflowType))
        for (const err of fieldErrors.filter(e => e.workflow_id === workflowId || e.workflow_id === null)) {
            // Strip discriminated-union prefix: "nf-pipeline.url" → "url"
            const parts = err.field.split(".")
            const field = parts.length > 1 && discriminators.has(parts[0]!)
                ? parts.slice(1).join(".")
                : err.field
            if (!result[field]) result[field] = []
            result[field]!.push(err.message)
        }
        return result
    }

    async function handleErrors<T>(result: ApiResult<T>) {
        if (!result.ok) {
            // TODO: Persist these errors somewhere in a status bar?
            if (result.status == 422) {
                for (const err of result.graphErrors ?? []) {
                    messageStore.add(err, "error")
                }

            } else {
                messageStore.add(result.message ?? "Request failed", "error")
            }
        }
        return result
    }

    async function addOrUpdate<T>(endpoint: string, data: T) {
        const result = await apiRequest<APICommandResponse>(endpoint, {
            method: "POST",
            body: JSON.stringify(data)
        })

        if (!result.ok) {
            handleErrors(result)
        } else {
            activityStore.pushEvents(result.data.events ?? [])
            await getAndUpdateGraph()
            messageStore.add("Saved", "success")
        }
        return result
    }

    async function remove<T>(endpoint: string, data: T) {
        const result = await apiRequest<APICommandResponse>(endpoint, {
            method: "DELETE",
            body: JSON.stringify(data)
        })

        if (!result.ok) {
            handleErrors(result)
        } else {
            activityStore.pushEvents(result.data.events ?? [])
            await getAndUpdateGraph()
        }

        return result
    }

    async function getAndUpdateGraph() {
        const endpoint = "/api/graph/"
        const requestOptions = { method: "GET" }
        await apiRequest<APIGraph>(endpoint, requestOptions)
            .then((response) => {
                if (!response.ok) {
                    messageStore.add("Unable to fetch Graph Data", "error")
                    _edges.value = []
                    _nodes.value = []
                    _edgeData.value = []
                    _nodeData.value = []
                } else {
                    _edgeData.value = response.data.transitions
                    _nodeData.value = response.data.nodes
                    _edges.value = response.data.transitions.map(createEdgeWithDefaults)
                    _nodes.value = response.data.nodes.map(createNodeWithDefaults)
                    _undoable.value = response.data.undoable
                    _redoable.value = response.data.redoable
                    _filename.value = response.data.filename
                    globalOptions.value = response.data.globals ?? { params: null, config_file: null, profile: null }
                }
            })
    }

    async function addOrUpdateEdge(edgeData: APIEdgeData) {
        const endpoint = edgeData?.id ? '/api/edge/update/' : '/api/edge/add/'
        return addOrUpdate<APIEdgeData>(endpoint, edgeData)
    }

    async function addOrUpdateNode(nodeData: APINodeData) {
        const endpoint = nodeData?.id ? '/api/node/update/' : '/api/node/add/'
        return await addOrUpdate<APINodeData>(endpoint, nodeData)
    }

    async function updateGlobalOptions(globals: APIGlobalOptions) {
        const endpoint = "/api/globals/update/"
        return await addOrUpdate<APIGlobalOptions>(endpoint, globals)
    }

    async function removeEdgeById(edgeId: string) {
        await removeSelectionById({ edges: [edgeId], nodes: [] })
    }

    async function removeNodeById(nodeId: string) {
        await removeSelectionById({ edges: [], nodes: [nodeId] })
    }

    async function removeSelectionById(selection: Selection) {
        const endpoint = "/api/delete/"
        return await remove(endpoint, selection)
    }

    function getPredecessors(nodeId: string | undefined | null) {
        if (!nodeId) {
            return []
        }

        const predecessorIds = _edgeData.value
            .filter(e => e.target === nodeId)
            .map(e => e.source)

        return _nodeData.value.filter(n => predecessorIds.includes(n.id ?? ""))
    }

    async function getParams(nodeId: string | undefined | null) {
        if (!nodeId) {
            return {}
        }
        const node = _nodeData.value.find(n => n.id === nodeId)
        return node?.params ?? {}
    }

    async function undo() {
        if (!undoable.value) {
            console.warn("Undo not possible")
            return
        }
        const endpoint = "/api/graph/undo/"
        const options = { method: "GET" }
        await apiRequest<APICommandResponse>(endpoint, options)
            .then((response) => {
                if (!response.ok) {
                    const detail = response.graphErrors?.length
                        ? response.graphErrors[0]
                        : response.message
                    messageStore.add(`Undo failed: ${detail}`, "error")
                    return
                }
                activityStore.pushEvents(response.data.events ?? [])
                getAndUpdateGraph()
            })
    }

    async function redo() {
        if (!redoable.value) {
            console.warn("Redo not possible")
            return
        }
        const endpoint = "/api/graph/redo/"
        const options = { method: "GET" }
        await apiRequest<APICommandResponse>(endpoint, options)
            .then((response) => {
                if (!response.ok) {
                    const detail = response.graphErrors?.length
                        ? response.graphErrors[0]
                        : response.message
                    messageStore.add(`Redo failed: ${detail}`, "error")
                    return
                }
                activityStore.pushEvents(response.data.events ?? [])
                getAndUpdateGraph()
            })
    }

    async function save() {
        if (!filename.value) {
            messageStore.add("No save destination specified!", "error")
            return
        }

        const endpoint = "/api/graph/save/"
        const options = {
            method: "POST",
            body: JSON.stringify({ config: filename.value })
        }
        return await apiRequest(endpoint, options)
            .then((response) => {
                if (!response.ok) {
                    messageStore.add(`Saving failed: ${response.message}`, "error")
                } else {
                    messageStore.add("Saved", "success")
                }
            })
    }

    async function saveAs(filename: string) {
        _filename.value = filename
        save()
    }

    async function loadConfig(filename: string) {
        const endpoint = "/api/graph/load/"
        const options = {
            method: "POST",
            body: JSON.stringify({ config: filename })
        }
        return await apiRequest(endpoint, options)
            .then((response) => {
                if (!response.ok) {
                    messageStore.add(`Loading config failed: ${response.message}`, "error")
                    return
                }
                getAndUpdateGraph()
                    .then(() => {
                        if (response.ok) {
                            messageStore.add(`Config Loaded`, "success")
                        }
                    })
            })
    }

    return {
        nodes, edges,
        isHorizontalLayout, layoutDirection, switchLayout,
        getAndUpdateGraph,
        getPredecessors, getParams,
        saveNode: addOrUpdateNode, saveEdge: addOrUpdateEdge, updateGlobalOptions,
        removeSelectionById, removeNodeById, removeEdgeById,
        undo, redo, redoable, undoable,
        loadConfig, save, saveAs, filename, globalOptions,
        extractFieldErrors
    }
})

export const usePipelineStore = defineStore("pipeline", () => {

    const nfCorePipelines = ref<NfCorePipelineInfo[]>()
    const isInitialized = ref(false)

    async function updateNfCorePipelines() {
        const endpoint = '/api/nfcore/pipelines/'
        const requestOptions = {
            method: "GET",
            headers: { 'Content-Type': 'application/json' },
        }
        fetch(endpoint, requestOptions)
            .then((response) => {
                if (!response.ok) {
                    // TODO: Handle errors 
                }
                return response.json()
            }).then((response: NfCorePipelineInfo[]) => {
                nfCorePipelines.value = response
            })
    }

    async function initialize() {
        updateNfCorePipelines()
        isInitialized.value = true
    }

    return {
        initialize,
        nfCorePipelines,
    }
})

export const useModuleStore = defineStore("module", () => {
    const nfCoreModules = ref<NfCoreModuleInfo[]>()

    async function initialize() {
        const endpoint = '/api/nfcore/modules/'
        fetch(endpoint, { method: "GET", headers: { 'Content-Type': 'application/json' } })
            .then(r => r.ok ? r.json() : null)
            .then((data: NfCoreModuleInfo[] | null) => {
                if (data) nfCoreModules.value = data
            })
    }

    async function fetchModuleVersions(shortName: string): Promise<NfCoreModuleVersionInfo[]> {
        const endpoint = `/api/nfcore/modules/${shortName}/versions/`
        const response = await fetch(endpoint, { method: "GET" })
        if (!response.ok) return []
        return response.json() as Promise<NfCoreModuleVersionInfo[]>
    }

    return {
        initialize,
        nfCoreModules,
        fetchModuleVersions,
    }
})
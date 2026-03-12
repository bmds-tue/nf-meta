import { type ApiResult, type APINodeData, type APIEdgeData, type APIGraph, type Selection, type SideBarDetail, type NfCorePipelineInfo, type APIGlobalOptions  } from './types'
import type { Node, Edge } from '@vue-flow/core'
import { MarkerType } from '@vue-flow/core'
import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

import { useLayout } from './layout_graph.ts'

export const useMessageStore = defineStore("message", () => {
    interface Message {
        text: string,
        color: string,
        timeout?: number,
    }
    const queue = ref<Message[]>([])

    function add(text: string, color="success") {
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
    const _sideBarNodes = ref<SideBarDetail<APINodeData>[]>([])
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
        _nextSideBarId.value ++
        return {id: _nextSideBarId.value, detailData: detailData}
    }

    function addNodeToSideBar(node: APINodeData) {
        // If the node is not new (i.e. has an id)
        // -> Check if it is already opened in the side bar and jump there instead
        // If it is new, there should only be one being created at a time.
        const existingDetail = sideBarNodes.value.find(
            (sideBarDetail) => sideBarDetail.detailData?.id == node?.id
        )
        if (existingDetail) {
            setActiveSidebarDetailId(existingDetail.id)
            return
        }

        const newDetail = createSideBarDetailWithId(node)
        _sideBarNodes.value = [..._sideBarNodes.value, newDetail]
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

export const useGraphStore = defineStore('graph', () => {

    const { layout, layoutOptions } = useLayout()
    const messageStore = useMessageStore()
    const _edges = ref<Edge<APIEdgeData>[]>([])
    const _nodes = ref<Node<APINodeData>[]>([])

    const edges = computed(() => {
        return _edges.value
    })

    const nodes = computed(() => {
        return _nodes.value
    })

    const globalOptions = ref<APIGlobalOptions>({
        nf_params: {},
        nf_config_file: "",
        nf_profile: "",
    })

    const _filename = ref<string>()
    const filename = computed(() => _filename.value)

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
        // recalculate node positions in new Layout
        _nodes.value = layout(_nodes.value, _edges.value, layoutDirection.value) as Node<APINodeData>[]
    }

    function createNodeWithDefaults(nodeData: APINodeData): Node<APINodeData> {
        return {
            data: nodeData,
            label: nodeData.name,
            // required attributes for Node
            id: nodeData?.id || "",
            position: nodeData?.position ?? {x: 0, y: 0},
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
    
    function mapPydanticErrors(detail: any[]): Record<string, string[]> {
        const errors: Record<string, string[]> = {}

        for (const err of detail) {
            const field = err.loc[err.loc.length - 1]
            if (!errors[field]) errors[field] = []
            errors[field].push(err.msg)
        }

        return errors
        }

    async function apiRequest<T>(endpoint: string, options: RequestInit): Promise<ApiResult<T>> {
        try {
            const response = await fetch(endpoint, { headers: { 'Content-Type': 'application/json' }, ...options})
            const data = await response.json()
            if (!response.ok) {
                if (response.status === 422 && data.detail) {
                    return {
                        ok: false,
                        status: 422,
                        message: "Validation error",
                        fieldErrors: mapPydanticErrors(data.detail)
                    }
                }

                return {
                    ok: false,
                    status: response.status,
                    message: data?.detail ?? "Request failed"
                }
            }

            return { ok: true, data: data }

        } catch (err) {
            return {
                ok: false,
                status: 0,
                message: "Error while making request"
            }
        }
    }

    async function addOrUpdate<T>(endpoint: string, data: T) {
        const result = await apiRequest(endpoint, {
            method: "POST",
            body: JSON.stringify(data)
        })

        if (!result.ok) {
            // Validation erros can be printed right in the form
            if (result.status != 422) {
                messageStore.add(result.message, "error")
            }
        } else {
            await getAndUpdateGraph()
        }
        return result
    }

    async function remove<T>(endpoint: string, data: T) {
        const result = await apiRequest(endpoint, {
            method: "DELETE",
            body: JSON.stringify(data)
        })

        if (!result.ok) {
            messageStore.add(`Delete failed: ${result.message}`, "error")
        } else {
            await getAndUpdateGraph()
        }

        return result
    }

    async function getAndUpdateGraph() {
        const endpoint = "/api/graph/"
        const requestOptions = { method: "GET"}
        await apiRequest<APIGraph>(endpoint, requestOptions)
            .then((response) => {
                if (!response.ok) { 
                    messageStore.add("Unable to fetch Graph Data", "error")
                    _edges.value = []
                    _nodes.value = []
                } else {
                    _edges.value = response.data.transitions.map(edgeData => createEdgeWithDefaults(edgeData as any) as any)
    
                    _nodes.value = layout(
                        response.data.nodes.map(nodeData => createNodeWithDefaults(nodeData)),
                        _edges.value,
                        layoutDirection.value
                        )
                    
                    _undoable.value = response.data.undoable
                    _redoable.value = response.data.redoable
                    _filename.value = response.data.filename
                    globalOptions.value = response.data.globals
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
        await removeSelectionById({edges: [edgeId], nodes: []})
    }

    async function removeNodeById(nodeId: string) {
        await removeSelectionById({edges: [], nodes: [nodeId]})
    }

    async function removeSelectionById(selection: Selection) {
        const endpoint = "/api/delete/"
        return await remove(endpoint, selection)
    }

    async function undo() {
        if (!undoable.value) {
            console.warn("Undo not possible")
            return
        }
        const endpoint = "/api/graph/undo/"
        const options = { method: "GET" }
        await apiRequest(endpoint, options)
            .then((response) => {
                if (!response.ok) {
                    messageStore.add(`Undo failed: ${response.message}`, "error")
                    return
                }
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
        await apiRequest(endpoint, options)
            .then((response) => {
                if (!response.ok) {
                    messageStore.add(`Redo failed: ${response.message}`, "error")
                    return
                }
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
            body: JSON.stringify({config: filename.value})
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
            body: JSON.stringify({config: filename})
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
                        }})
            })
    }

    return {
        nodes, edges,
        isHorizontalLayout, layoutDirection, switchLayout,
        getAndUpdateGraph,
        saveNode: addOrUpdateNode, saveEdge: addOrUpdateEdge, updateGlobalOptions,
        removeSelectionById, removeNodeById, removeEdgeById,
        undo, redo, redoable, undoable, 
        loadConfig, save, saveAs, filename, globalOptions
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
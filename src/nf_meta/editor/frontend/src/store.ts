import { type ApiResult, type APINodeData, type APIEdgeData, type APIGraph, type SideBarDetail, type NfCorePipelineInfo  } from './types'
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

    const _sideBarActiveDetailId = ref(0)
    const sideBarActiveDetailId = computed(() => _sideBarActiveDetailId.value)
    const _nextSideBarId = ref(1)
    const _sideBarNodes = ref<SideBarDetail<APINodeData>[]>([])
    const sideBarNodes = computed(() => _sideBarNodes.value)
    
    function toggleSidebar() {
        _sideBarOpen.value = !_sideBarOpen.value
        localStorage.setItem("showSideBar", String(_sideBarOpen.value))
    }

    function setActiveSidebarDetailId(id: number) {
        _sideBarActiveDetailId.value = id
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
        console.log("Trying to collapse Sidebar detail with id:", id)
        console.log("All SidebarDetails: ", sideBarNodes.value)
        console.log("ACTIVE:", _sideBarActiveDetailId.value, sideBarActiveDetailId.value)
        if (id == _sideBarActiveDetailId.value) {
            console.log("Active Status changing!")
            _sideBarActiveDetailId.value = 0            
        }
        console.log("ACTIVE:", _sideBarActiveDetailId.value, sideBarActiveDetailId.value)
    }

    return {
        showSidebar: sideBarOpen, sideBarOpen, toggleSidebar,
        sideBarActiveDetailId, setActiveSidebarDetailId,
        sideBarNodes, addNodeToSideBar,
        removeSidebarDetail, collapseSidebarDetail
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

    const _isHorizontalLayout = ref(localStorage.getItem("isHorizontalLayout") == "true")
    const isHorizontalLayout = computed(() => _isHorizontalLayout.value)
    const layoutDirection = computed(() => (_isHorizontalLayout.value ? layoutOptions.horizontal : layoutOptions.vertical))

    async function switchLayout() {
        _isHorizontalLayout.value = !_isHorizontalLayout.value
        localStorage.setItem("isHorizontalLayout", String(isHorizontalLayout.value))
        // recalculate node positions in new Layout
        // TODO: Is there a better fix than using any?
        _nodes.value = layout(_nodes.value as any, _edges.value as any, layoutDirection.value)
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
        }
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
            console.log("graphStore:apiRequest: Before request")
            const response = await fetch(endpoint, { headers: { 'Content-Type': 'application/json' }, ...options})
            const data = await response.json()

            console.log("graphStore:apiRequest: After request")

            if (!response.ok) {
                console.log("graphStore:apiRequest: Error Response received")

                if (response.status === 422 && data.detail) {
                    console.log("graphStore:apiRequest: 422 HTTP Error")
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
            console.log("graphStore:apiRequest: Handling Error while making request during request")

            return {
                ok: false,
                status: 0,
                message: "Network error"
            }
        }
    }

    async function addOrUpdate<T>(endpoint: string, data: T) {
        const result = await apiRequest(endpoint, {
            method: "POST",
            body: JSON.stringify(data)
        })

        if (!result.ok) {
            messageStore.add(result.message, "error")
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
            messageStore.add("Delete failed: ", result.message)
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
                    // TODO: Can we fix this some other way? "Excessively deep recursion"
                    _edges.value = response.data.transitions.map(edgeData => createEdgeWithDefaults(edgeData as any) as any)
    
                    _nodes.value = layout(
                        response.data.nodes.map(nodeData => createNodeWithDefaults(nodeData)),
                        _edges.value,
                        layoutDirection.value
                        )

                }
            })
    }

    function saveEdge(edgeData: APIEdgeData) {
        const endpoint = edgeData?.id ? '/api/edge/update/' : '/api/edge/add/'
        return addOrUpdate<APIEdgeData>(endpoint, edgeData)
    }

    async function saveNode(nodeData: APINodeData) {
        const endpoint = nodeData?.id ? '/api/node/update/' : '/api/node/add/'
        return await addOrUpdate<APINodeData>(endpoint, nodeData)
    }

    function removeEdge(edgeData: APIEdgeData) {
        const endpoint = '/api/edge/'
        return remove<APIEdgeData>(endpoint, edgeData)
    }

    function removeNode(nodeData: APINodeData) {
        const endpoint = '/api/edge/'
        return remove<APINodeData>(endpoint, nodeData)
    }

    return {
        nodes, edges,
        isHorizontalLayout, layoutDirection, switchLayout,
        getAndUpdateGraph,
        saveNode, saveEdge,
        removeNode, removeEdge 
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
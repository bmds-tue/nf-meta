import { type APINodeData, type APIEdgeData, type APIGraph, type SideBarDetail  } from './types'
import type { Node, Edge } from '@vue-flow/core'
import { MarkerType } from '@vue-flow/core'
import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

import { useLayout } from './layout_graph.ts'

export const useEventStore = defineStore("event", () => {

})

export const useEditorStore = defineStore("editor", () => {
    // read from local browser storage and default to true
    const _sideBarOpen = ref(localStorage.getItem("showSideBar") == "true")
    const sideBarOpen = computed(() => _sideBarOpen.value)

    const _sideBarActiveDetailId = ref()
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

    return {
        showSidebar: sideBarOpen, sideBarOpen, toggleSidebar,
        sideBarActiveDetailId, setActiveSidebarDetailId,
        sideBarNodes, addNodeToSideBar
    }
})

export const useGraphStore = defineStore('graph', () => {

    const { layout, layoutOptions } = useLayout()

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
        _nodes.value = layout(_nodes.value, _edges.value, layoutDirection.value)
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
    
    async function get<T>(endpoint: string): Promise<T> {
        const requestOptions = {
            method: "GET",
            headers: { 'Content-Type': 'application/json' },
        }
        return fetch(endpoint, requestOptions)
            .then((response) => {
                if (!response.ok) {
                    // TODO: Handle errors 
                }
                return response.json()
            })
    }

    async function addOrUpdate<T>(endpoint: string, data: T) {
        const requestOptions = {
            method: "POST",
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        }
        return fetch(endpoint, requestOptions)
            .then((response) => {
                if (!response.ok) {
                    // TODO: Handle errors 
                }
                getAndUpdateGraph()
            })
    }

    async function remove<T>(endpoint: string, data: T) {
        const requestOptions = {
            method: "DELETE",
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        }
        return fetch(endpoint, requestOptions)
            .then((response) => {
                if (!response.ok) {
                    // TODO: Handle errors 
                }
                getAndUpdateGraph()
            })
    }

    async function getAndUpdateGraph() {
        const endpoint = '/api/graph/'
        await get<APIGraph>(endpoint)
            .then((graph) => {
                _edges.value = graph.transitions.map(edgeData => createEdgeWithDefaults(edgeData))

                _nodes.value = layout(
                    graph.nodes.map(nodeData => createNodeWithDefaults(nodeData)),
                    _edges.value,
                    layoutDirection.value
                    )
            })
    }

    async function saveEdge(edgeData: APIEdgeData) {
        const endpoint = edgeData?.id ? '/api/edge/add/' : '/api/edge/update'
        await addOrUpdate<APIEdgeData>(endpoint, edgeData)
    }

    async function saveNode(nodeData: APINodeData) {
        const endpoint = nodeData?.id ? '/api/node/add/' : '/api/node/update/'
        await addOrUpdate<APINodeData>(endpoint, nodeData)
    }

    async function removeEdge(edgeData: APIEdgeData) {
        const endpoint = '/api/edge/'
        await remove<APIEdgeData>(endpoint, edgeData)
    }

    async function removeNode(nodeData: APINodeData) {
        const endpoint = '/api/edge/'
        await remove<APINodeData>(endpoint, nodeData)
    }


    return {
        nodes, edges,
        isHorizontalLayout, layoutDirection, switchLayout,
        getAndUpdateGraph,
        saveNode, saveEdge,
        removeNode, removeEdge 
    } 
})

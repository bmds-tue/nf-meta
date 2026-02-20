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

    function nodeDefaults(node: Node<APINodeData>) {
        return {
            ...node,
            // apply common node attributes (e.g. our custom node type)
            type: "workflow-node"
        }
    }

    function edgeDefaults(edge: Edge<APIEdgeData>) {
        return {
            ...edge,
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

    async function add<T>(endpoint: string, data: T) {
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
                updateGraph()
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
                updateGraph()
            })
    }

    async function updateGraph() {
        const endpoint = '/api/graph/'
        await get<APIGraph>(endpoint)
            .then((graph) => {
                _edges.value = graph.transitions.map(t => edgeDefaults(t))

                _nodes.value = layout(
                    graph.nodes.map(n => nodeDefaults(n)),
                    _edges.value,
                    layoutDirection.value
                    )
            })
    }

    async function addEdge(edge: Edge<APIEdgeData>) {
        const endpoint = '/api/edge/add/'
        await add<Edge<APIEdgeData>>(endpoint, edge)
            // .then((newEdge) => {
            //     _edges.value.push(edgeDefaults(newEdge))
            // })
    }

    async function addNode(node: Node<APINodeData>, updateLayout=true) {
        const endpoint = '/api/node/add/'
        await add<Node<APINodeData>>(endpoint, node)
            // .then((newNode) => {
            //     _nodes.value.push(nodeDefaults(newNode))

            //     if (updateLayout) {
            //         _nodes.value = layout(_nodes.value, _edges.value, layoutDirection.value)
            //     }
            // })
    }

    async function removeEdge(edge: Edge<APIEdgeData>) {
        const endpoint = '/api/edge/'
        await remove<Edge<APIEdgeData>>(endpoint, edge)
            // .then((_) => {
            //     _edges.value = _edges.value.filter((e) => e.id != edge.id)
            // })
    }

    async function removeNode(node: Node<APINodeData>) {
        const endpoint = '/api/edge/'
        await remove<Node<APINodeData>>(endpoint, node)
            // .then((_) => {
            //     _nodes.value = _nodes.value.filter((n) => n.id != node.id)
            // })
    }


    return { 
        nodes, edges,
        isHorizontalLayout, layoutDirection, switchLayout,
        updateGraph,
        addNode, removeNode, 
        addEdge, removeEdge 
    } 
})

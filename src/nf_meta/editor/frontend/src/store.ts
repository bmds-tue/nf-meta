import { type APINodeData, type APIEdgeData, type APIGraph  } from './types'
import type { Node, Edge } from '@vue-flow/core'
import { MarkerType } from '@vue-flow/core'
import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

import { useLayout } from './layout_graph.ts'

export const useEventStore = defineStore("event", () => {

})

export const useEditorStore = defineStore("editor", () => {
    // read from local browser storage and default to true
    const _showSideBar = ref(localStorage.getItem("showSideBar") == "true")

    const showSidebar = computed(() => _showSideBar.value)

    function toggleSidebar() {
        _showSideBar.value = !_showSideBar.value
        localStorage.setItem("showSideBar", String(_showSideBar.value))
    }

    return {
        showSidebar, toggleSidebar
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
            animated: true,
            markerEnd: MarkerType.Arrow
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

    async function add<T>(endpoint: string, data: T): Promise<T> {
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
                return response.json()
            })
    }

    async function remove<T>(endpoint: string, data: T): Promise<T> {
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
                return response.json()
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
            .then((newEdge) => {
                _edges.value.push(edgeDefaults(newEdge))
            })
    }

    async function addNode(node: Node<APINodeData>, updateLayout=true) {
        const endpoint = '/api/node/add/'
        await add<Node<APINodeData>>(endpoint, node)
            .then((newNode) => {
                _nodes.value.push(nodeDefaults(newNode))

                if (updateLayout) {
                    _nodes.value = layout(_nodes.value, _edges.value, layoutDirection.value)
                }
            })
    }

    async function removeEdge(edge: Edge<APIEdgeData>) {
        const endpoint = '/api/edge/'
        await remove<Edge<APIEdgeData>>(endpoint, edge)
            .then((_) => {
                _edges.value = _edges.value.filter((e) => e.id != edge.id)
            })
    }

    async function removeNode(node: Node<APINodeData>) {
        const endpoint = '/api/edge/'
        await remove<Node<APINodeData>>(endpoint, node)
            .then((_) => {
                _nodes.value = _nodes.value.filter((n) => n.id != node.id)
            })
    }


    return { 
        nodes, edges,
        isHorizontalLayout, layoutDirection, switchLayout,
        updateGraph,
        addNode, removeNode, 
        addEdge, removeEdge 
    } 
})

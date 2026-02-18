import { type APINodeData, type APIEdgeData, type APIGraph  } from './types'
import type { Node, Edge } from '@vue-flow/core'
import { MarkerType, useVueFlow } from '@vue-flow/core'
import { ref, computed, nextTick } from 'vue'
import { defineStore } from 'pinia'

import { useLayout } from './layout_graph.ts'

const { fitView } = useVueFlow()

function fitVueFlowGraph() {
    // update vue-flow graph
    nextTick(() => { setTimeout(fitView, 50) })
}

export const useEventStore = defineStore("event", () => {

})

export const useEditorStore = defineStore("editor", () => {
    const showSidebar = computed(() => (
        // read from local browser storage and default to false
        Boolean(localStorage.getItem("show-sidebar") == "true")
    ))

    function toggleSidebar() {
        const show = !showSidebar
        localStorage.setItem("show-sidebar", String(show))

        fitVueFlowGraph()
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

    const getLayoutDirection = computed(() => {
        const cachedLayoutDirection = String(localStorage.getItem("layoutDirection"))
        if (cachedLayoutDirection
            && cachedLayoutDirection != layoutOptions.horizontal
            && cachedLayoutDirection != layoutOptions.vertical){
            console.log("[WARN] Invalid layoutDirection read from local storage: ", cachedLayoutDirection)
            return layoutOptions.horizontal
        }
        return cachedLayoutDirection
    })

    function setLayoutDirection (layoutDirection: string) {
        localStorage.setItem("layoutDirection", layoutDirection)
    }

    async function switchLayout() {
        const inverseLayout = 
            ( getLayoutDirection.value == layoutOptions.vertical) 
            ? layoutOptions.horizontal 
            : layoutOptions.vertical

        setLayoutDirection(inverseLayout)
        _nodes.value = layout(_nodes.value, _edges.value, getLayoutDirection.value)
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
                _edges.value = graph.transitions.map(t => ({
                    ...t,
                    // apply common default edge attributes
                    animated: true,
                    markerEnd: MarkerType.Arrow
                }))

                _nodes.value = layout(
                    graph.nodes.map(n => ({
                        ...n,
                        // apply common node attributes (e.g. our custom node type)
                        type: "workflow-node"
                    })), 
                    _edges.value,
                    getLayoutDirection.value)

                fitVueFlowGraph()
            })
    }

    async function addEdge(edge: Edge<APIEdgeData>) {
        const endpoint = '/api/edge/'
        await add<Edge<APIEdgeData>>(endpoint, edge)
            .then((newEdge) => {
                _edges.value.push(newEdge)
            })
    }

    async function addNode(node: Node<APINodeData>, updateLayout=true) {
        const endpoint = '/api/node/'
        await add<Node<APINodeData>>(endpoint, node)
            .then((newNode) => {
                _nodes.value.push(newNode)

                if (updateLayout) {
                    _nodes.value = layout(_nodes.value, _edges.value, getLayoutDirection.value)
                    fitVueFlowGraph()
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
        getLayoutDirection, setLayoutDirection, switchLayout,
        updateGraph,
        addNode, removeNode, 
        addEdge, removeEdge 
    } 
})

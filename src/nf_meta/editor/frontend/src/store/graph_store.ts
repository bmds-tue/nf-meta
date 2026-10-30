import { ref, computed, watch } from 'vue'
import { defineStore } from 'pinia'
import type { Node, Edge } from '@vue-flow/core'
import { MarkerType } from '@vue-flow/core'
import type {
    ApiResult, APINodeData, APIEdgeData, APICommandResponse,
    APIGlobalOptions, APIInput, APIInputSave, Selection,
} from '../types'
import { useLayout } from '../layout_graph'
import { useMessageStore, useActivityStore } from './ui_store'
import { useApiStore } from './api_store'
import { referencableParams, referenceTargets } from '../utils'

export const INPUTS_NODE_ID = '__inputs__'
// Inputs in the graph and the params editor (oneDark's purple)
export const INPUT_COLOR = '#c678dd'
// References to other steps' params (oneDark's blue, as in the params editor)
export const REF_COLOR = '#61afef'
// Edges between steps: solid, in the theme's edge color (input edges are dashed purple)
const EDGE_COLOR = 'rgb(var(--v-theme-edge))'

export const useGraphStore = defineStore('graph', () => {
    const { layoutOptions } = useLayout()
    const messageStore = useMessageStore()
    const activityStore = useActivityStore()
    const apiStore = useApiStore()

    const _inputs = ref<APIInput[]>([])
    const inputs = computed(() => _inputs.value)
    const _edgeData = ref<APIEdgeData[]>([])
    const _nodeData = ref<APINodeData[]>([])
    const _edges = ref<Edge<APIEdgeData>[]>([])
    const _nodes = ref<Node<APINodeData>[]>([])

    // A node standing for the config's inputs, with an edge to every step they fill.
    // Only in the view: it isn't part of the graph; it can be selected, not connected or deleted.
    const _showInputsNode = ref(localStorage.getItem('showInputsNode') !== 'false')
    const showInputsNode = computed(() => _showInputsNode.value)

    function toggleInputsNode() {
        _showInputsNode.value = !_showInputsNode.value
        localStorage.setItem('showInputsNode', String(_showInputsNode.value))
    }

    const inputsNode = computed<Node[]>(() => {
        if (!_showInputsNode.value || !_inputs.value.length) return []
        return [{
            id: INPUTS_NODE_ID,
            type: 'inputs-node',
            position: { x: 0, y: 0 },
            data: { inputs: _inputs.value },
            selectable: true,
            connectable: false,
            deletable: false,
        }]
    })

    const inputsEdges = computed<Edge[]>(() => {
        if (!inputsNode.value.length) return []
        const steps = new Set(_inputs.value.flatMap(i => i.bindings.map(b => b.slice(0, b.indexOf('.')))))
        return [...steps].filter(id => _nodeData.value.some(n => n.id === id)).map(id => ({
            id: `${INPUTS_NODE_ID}->${id}`,
            source: INPUTS_NODE_ID,
            target: id,
            selectable: false,
            deletable: false,
            class: 'inputs-edge',
            style: { stroke: INPUT_COLOR, strokeDasharray: '6 4', strokeWidth: 1.5 },
            markerEnd: { type: MarkerType.ArrowClosed, color: INPUT_COLOR },
        }))
    })

    const edges = computed(() => [..._edges.value, ...inputsEdges.value] as Edge<APIEdgeData>[])
    const nodes = computed(() => [..._nodes.value, ...inputsNode.value] as Node<APINodeData>[])

    const globalOptions = ref<APIGlobalOptions>({ params: {}, nf_config: '', nf_profile: '' })

    const _filename = ref<string>()
    const filename = computed(() => _filename.value)
    watch(_filename, () => {
        document.title = _filename.value ? `nf-meta - ${_filename.value}` : 'nf-meta'
    })

    const _undoable = ref<boolean>(false)
    const undoable = computed(() => _undoable.value)
    const _redoable = ref<boolean>(false)
    const redoable = computed(() => _redoable.value)

    const _isHorizontalLayout = ref(localStorage.getItem('isHorizontalLayout') == 'true')
    const isHorizontalLayout = computed(() => _isHorizontalLayout.value)
    const layoutDirection = computed(() =>
        _isHorizontalLayout.value ? layoutOptions.horizontal : layoutOptions.vertical
    )

    function switchLayout() {
        _isHorizontalLayout.value = !_isHorizontalLayout.value
        localStorage.setItem('isHorizontalLayout', String(isHorizontalLayout.value))
    }

    function createNodeWithDefaults(nodeData: APINodeData): Node<APINodeData> {
        return {
            data: nodeData,
            label: nodeData.name,
            id: nodeData?.id || '',
            position: nodeData?.position ?? { x: 0, y: 0 },
            type: 'workflow-node',
        } as Node<APINodeData>
    }

    function createEdgeWithDefaults(edgeData: APIEdgeData): Edge<APIEdgeData> {
        return {
            id: edgeData?.id || `${edgeData.source}->${edgeData.target}`,
            source: edgeData.source,
            target: edgeData.target,
            data: edgeData,
            animated: false,
            style: { stroke: EDGE_COLOR, strokeWidth: 1.5 },
            markerEnd: { type: MarkerType.ArrowClosed, color: EDGE_COLOR },
        }
    }

    function handleErrors<T>(result: ApiResult<T>) {
        if (!result.ok) {
            if (result.status === 422) {
                for (const err of result.graphErrors ?? []) {
                    messageStore.add(err, 'error')
                }
                if (result.fieldErrors?.length) {
                    messageStore.add('Validation failed. See highlighted fields', 'error')
                }
            } else {
                messageStore.add(result.message ?? 'Request failed', 'error')
            }
        }
        return result
    }

    async function getAndUpdateGraph() {
        const response = await apiStore.getGraph()
        if (!response.ok) {
            messageStore.add('Unable to fetch Graph Data', 'error')
            _edges.value = []
            _nodes.value = []
            _edgeData.value = []
            _nodeData.value = []
            _inputs.value = []
        } else {
            _edgeData.value = response.data.transitions
            _nodeData.value = response.data.nodes
            _edges.value = response.data.transitions.map(createEdgeWithDefaults)
            _nodes.value = response.data.nodes.map(createNodeWithDefaults)
            _undoable.value = response.data.undoable
            _redoable.value = response.data.redoable
            _filename.value = response.data.filename
            globalOptions.value = response.data.globals ?? { params: null, nf_config: null, nf_profile: null }
            _inputs.value = response.data.inputs ?? []
        }
    }

    // With `quiet`, a refused change shows no message: the caller explains it where it happened
    async function applyMutation(result: ApiResult<APICommandResponse>, successMessage?: string, quiet = false) {
        if (!result.ok) {
            if (!quiet || result.status !== 422) handleErrors(result)
        } else {
            activityStore.pushEvents(result.data.events ?? [])
            await getAndUpdateGraph()
            if (successMessage) messageStore.add(successMessage, 'success')
        }
        return result
    }

    async function saveNode(nodeData: APINodeData) {
        const result = await (nodeData?.id ? apiStore.updateNode(nodeData) : apiStore.addNode(nodeData))
        return applyMutation(result, 'Saved')
    }

    async function saveEdge(edgeData: APIEdgeData) {
        const result = await apiStore.addEdge(edgeData)
        return applyMutation(result, 'Saved')
    }

    async function updateGlobalOptions(globals: APIGlobalOptions) {
        const result = await apiStore.updateGlobalOptions(globals)
        return applyMutation(result, 'Saved')
    }

    async function saveInput(input: APIInputSave) {
        return applyMutation(await apiStore.saveInput(input), 'Saved')
    }

    async function setInputsStyle(inParams: boolean) {
        return applyMutation(await apiStore.setInputsStyle(inParams), 'Saved')
    }

    async function declareStepInputs(nodeId: string) {
        return applyMutation(await apiStore.declareStepInputs(nodeId), 'Inputs moved to the inputs: section')
    }

    async function removeInput(name: string) {
        return applyMutation(await apiStore.deleteInput(name), undefined, true)
    }

    async function removeSelectionById(selection: Selection) {
        const result = await apiStore.deleteSelection(selection)
        return applyMutation(result)
    }

    async function removeNodeById(nodeId: string) {
        return removeSelectionById({ edges: [], nodes: [nodeId] })
    }

    async function removeEdgeById(edgeId: string) {
        return removeSelectionById({ edges: [edgeId], nodes: [] })
    }

    async function undo() {
        if (!undoable.value) return
        const result = await apiStore.undoGraph()
        if (!result.ok) {
            const detail = result.graphErrors?.length ? result.graphErrors[0] : result.message
            messageStore.add(`Undo failed: ${detail}`, 'error')
            return
        }
        activityStore.pushEvents(result.data.events ?? [])
        await getAndUpdateGraph()
    }

    async function redo() {
        if (!redoable.value) return
        const result = await apiStore.redoGraph()
        if (!result.ok) {
            const detail = result.graphErrors?.length ? result.graphErrors[0] : result.message
            messageStore.add(`Redo failed: ${detail}`, 'error')
            return
        }
        activityStore.pushEvents(result.data.events ?? [])
        await getAndUpdateGraph()
    }

    // Save to the current file; returns the error message if it failed
    async function save(): Promise<string | undefined> {
        if (!filename.value) {
            messageStore.add('No save destination specified!', 'error')
            return 'No file to save to'
        }
        return saveTo(filename.value)
    }

    // Save to `target`, which becomes the current file only if saving worked
    async function saveAs(target: string): Promise<string | undefined> {
        const problem = await saveTo(target)
        if (!problem) _filename.value = target
        return problem
    }

    async function saveTo(target: string): Promise<string | undefined> {
        const result = await apiStore.saveGraph(target)
        if (!result.ok) {
            messageStore.add(`Saving failed: ${result.message}`, 'error')
            return result.message
        }
        messageStore.add('Saved', 'success')
        return undefined
    }

    // Load the config at `path`; returns the error message if it failed
    async function loadConfig(path: string): Promise<string | undefined> {
        const result = await apiStore.loadGraph(path)
        if (!result.ok) {
            messageStore.add(`Loading config failed: ${result.message}`, 'error')
            return result.message
        }
        await getAndUpdateGraph()
        messageStore.add('Config loaded', 'success')
        return undefined
    }

    function getPredecessors(nodeId: string | undefined | null) {
        if (!nodeId) return []
        const predecessorIds = _edgeData.value.filter(e => e.target === nodeId).map(e => e.source)
        return _nodeData.value.filter(n => predecessorIds.includes(n.id ?? ''))
    }

    async function getParams(nodeId: string | undefined | null) {
        if (!nodeId) return {}
        const node = _nodeData.value.find(n => n.id === nodeId)
        return node?.params ?? {}
    }

    const nodeData = computed(() => _nodeData.value)

    // The steps step `nodeId` can reference (see `referenceTargets`); every step for an unsaved one
    function getReferenceTargets(nodeId: string | undefined | null) {
        return referenceTargets(_nodeData.value, _edgeData.value, nodeId ?? undefined, _inputs.value)
    }

    // The params of step `nodeId` another step can reference: set ones and ones an input fills
    function getReferencableParams(nodeId: string | undefined | null): string[] {
        const node = _nodeData.value.find(n => n.id === nodeId)
        return node ? referencableParams(node, _inputs.value).map(p => p.key) : []
    }

    return {
        nodes, nodeData, edges, globalOptions, inputs, filename,
        isHorizontalLayout, layoutDirection, switchLayout,
        undoable, redoable,
        getAndUpdateGraph,
        saveNode, saveEdge, updateGlobalOptions, saveInput, removeInput, declareStepInputs, setInputsStyle,
        showInputsNode, toggleInputsNode,
        removeSelectionById, removeNodeById, removeEdgeById,
        undo, redo, save, saveAs, loadConfig,
        getPredecessors, getParams, getReferenceTargets, getReferencableParams,
    }
})

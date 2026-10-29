import dagre from '@dagrejs/dagre'
import { Position, type GraphNode, type GraphEdge } from '@vue-flow/core'
import { ref } from 'vue'
import type { APINodeData, APIEdgeData } from './types'

// Gap between the inputs node and the step(s) next to it
const INPUTS_NODE_GAP = 60


export function useLayout() {

  const graph = ref(new dagre.graphlib.Graph())

  const layoutOptions = {
    horizontal: 'LR',
    vertical: 'TD'
  }
  const previousDirection = ref(layoutOptions.horizontal)


  // Nodes of type 'inputs-node' are left out of the layout and placed
  // before (above / left of) the first root step instead.
  function layout(allNodes: GraphNode<APINodeData>[], allEdges: GraphEdge<APIEdgeData>[], direction: string): GraphNode<APINodeData>[] {
    const nodes = allNodes.filter(n => n.type !== 'inputs-node')
    const extra = allNodes.filter(n => n.type === 'inputs-node')
    const ids = new Set(nodes.map(n => n.id))
    const edges = allEdges.filter(e => ids.has(e.source) && ids.has(e.target))
    console.log("[INFO] Calculating node layout")
    // we create a new graph instance, in case some nodes/edges were removed, otherwise dagre would act as if they were still there
    const dagreGraph = new dagre.graphlib.Graph()

    graph.value = dagreGraph

    dagreGraph.setDefaultEdgeLabel(() => ({}))

    const isHorizontal = direction === layoutOptions.horizontal
    dagreGraph.setGraph({ rankdir: direction })

    previousDirection.value = direction

    for (const node of nodes) {
      dagreGraph.setNode(node.id, { width: node?.dimensions.width || 250, height: node?.dimensions.height || 100 })
    }

    for (const edge of edges) {
      dagreGraph.setEdge(edge.source, edge.target)
    }

    dagre.layout(dagreGraph)

    const targetPosition = isHorizontal ? Position.Left : Position.Top
    const sourcePosition = isHorizontal ? Position.Right : Position.Bottom

    // set nodes with updated positions
    const placed = nodes.map((node) => {
      const { x, y } = dagreGraph.node(node.id)
      return { ...node, position: { x: x, y: y }, targetPosition, sourcePosition }
    })

    // the inputs node goes before the first root step (fewest incoming edges, then left/top-most)
    const targets = new Set(edges.map(e => e.target))
    const roots = placed.filter(n => !targets.has(n.id))
    const anchor = (roots.length ? roots : placed)
      .sort((a, b) => isHorizontal ? a.position.y - b.position.y : a.position.x - b.position.x)[0]
    const first = Math.min(...placed.map(n => isHorizontal ? n.position.x : n.position.y))
    const before = extra.map((node) => {
      const width = node.dimensions?.width || 160
      const height = node.dimensions?.height || 60
      const position = !anchor
        ? { x: 0, y: 0 }
        : isHorizontal
          ? { x: first - width - INPUTS_NODE_GAP, y: anchor.position.y }
          : { x: anchor.position.x, y: first - height - INPUTS_NODE_GAP }
      return { ...node, position, targetPosition, sourcePosition }
    })
    return [...placed, ...before]
  }

  return { layoutOptions, graph, layout, previousDirection }
}
import dagre from '@dagrejs/dagre'
import { Position, type GraphNode, type GraphEdge } from '@vue-flow/core'
import { ref } from 'vue'
import type { APINodeData, APIEdgeData } from './types'


export function useLayout() {

  const graph = ref(new dagre.graphlib.Graph())

  const layoutOptions = {
    horizontal: 'LR',
    vertical: 'TD'
  }
  const previousDirection = ref(layoutOptions.horizontal)


  function layout(nodes: GraphNode<APINodeData>[], edges: GraphEdge<APIEdgeData>[], direction: string): GraphNode<APINodeData>[] {
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

    // set nodes with updated positions
    return nodes.map((node) => {
      const { x, y } = dagreGraph.node(node.id)
      return {
        ...node,
        position: { x: x, y: y },
        targetPosition: isHorizontal ? Position.Left : Position.Top,
        sourcePosition: isHorizontal ? Position.Right : Position.Bottom
      }
    })
  }

  return { layoutOptions, graph, layout, previousDirection }
}
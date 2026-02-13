import dagre from '@dagrejs/dagre'
import { Position, useVueFlow, type Node, type Edge } from '@vue-flow/core'
import { ref } from 'vue'


export function useLayout() {
  const { findNode } = useVueFlow()

  const graph = ref(new dagre.graphlib.Graph())

  const layoutOptions = {
    horizontal: 'LR',
    vertical: 'TD'
  }
  const previousDirection = ref(layoutOptions.horizontal)


  function layout(nodes: Node[], edges: Edge[], direction: string) {
    // we create a new graph instance, in case some nodes/edges were removed, otherwise dagre would act as if they were still there
    const dagreGraph = new dagre.graphlib.Graph()

    graph.value = dagreGraph

    dagreGraph.setDefaultEdgeLabel(() => ({}))

    const isHorizontal = direction === layoutOptions.horizontal
    dagreGraph.setGraph({ rankdir: direction })

    previousDirection.value = direction

    for (const node of nodes) {
      // if you need width+height of nodes for your layout, you can use the dimensions property of the internal node (`GraphNode` type)
      const graphNode = findNode(node.id)

      dagreGraph.setNode(node.id, { width: graphNode?.dimensions.width || 350, height: graphNode?.dimensions.height || 100 })
    }

    for (const edge of edges) {
      dagreGraph.setEdge(edge.source, edge.target)
    }

    dagre.layout(dagreGraph)

    // set nodes with updated positions
    return nodes.map((node) => {
      const nodeWithPosition = dagreGraph.node(node.id)

      return {
        ...node,
        targetHandlePosition: isHorizontal ? Position.Left : Position.Top,
        sourceHandlePosition: isHorizontal ? Position.Right : Position.Bottom,
        position: { x: nodeWithPosition.x, y: nodeWithPosition.y },
      }
    })
  }

  return { layoutOptions, graph, layout, previousDirection }
}
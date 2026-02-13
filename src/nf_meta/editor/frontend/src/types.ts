import type { Edge, Node, Position } from "@vue-flow/core"

export type APIEdgeData = {}


export type APINodeData = {
    name?: string,
    pipeline_location?: string,
    is_nfcore?: boolean,
    targetHandlePosition?: Position,
    sourceHandlePosition?: Position,
}

export type APIGraph = {
  nodes: Node<APINodeData>[],
  transitions: Edge<APIEdgeData>[]
}
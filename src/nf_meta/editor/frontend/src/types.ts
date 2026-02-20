import type { Edge, Node } from "@vue-flow/core"

export type SideBarDetail<T> = {
  id: number,
  detailData: T
}

export type APIEdgeData = {
  id?: string,
  source: string,
  target: string,
}

export type APINodeData = {
    id?: string,
    name?: string,
    pipeline_location?: string,
    is_nfcore?: boolean,
}

export type APIGraph = {
  nodes: Node<APINodeData>[],
  transitions: Edge<APIEdgeData>[]
}
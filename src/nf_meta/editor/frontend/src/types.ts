import type { Edge, Node, XYPosition } from "@vue-flow/core"

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
    pipeline_description?: string,
    pipeline_location?: string,
    pipeline_version?: string,
    position?: XYPosition,
    is_nfcore?: boolean,
}

export type APIGraph = {
  nodes: Node<APINodeData>[],
  transitions: Edge<APIEdgeData>[]
}

export type NfCorePipelineReleaseInfo = {
  tag_name: string,
  published_at: string,
  tag_sha: string
}

export type NfCorePipelineInfo = {
  name: string
  full_name: string,
  description: string,
  url: string,
  releases: NfCorePipelineReleaseInfo[]
}

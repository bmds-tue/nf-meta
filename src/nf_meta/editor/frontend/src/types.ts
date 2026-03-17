import type { Edge, Node, XYPosition } from "@vue-flow/core"

export type Selection = {
  nodes: string[],
  edges: string[]
}

export type ApiResult<T> = 
  | { ok: true; data: T }
  | { ok: false; status: number; message: string; fieldErrors?: Record<string, string[]> }

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
    description?: string,
    url?: string,
    version?: string,
    position?: XYPosition,
    is_nfcore?: boolean,
    config_file?: string,
    params_file?: string,
    params?: object
}

export type APIGlobalOptions = {
  nf_profile?: string,
  nf_config_file?: string,
  nf_params?: object
}

export type APIGraph = {
  redoable: boolean,
  undoable: boolean,
  filename: string,
  nodes: Node<APINodeData>[],
  transitions: Edge<APIEdgeData>[],
  globals: APIGlobalOptions
}

export type NfCorePipelineReleaseInfo = {
  tag_name: string,
  published_at: string,
  tag_sha: string
}

export type NfCorePipelineInfo = {
  name: string
  description: string,
  repository_url: string,
  releases: NfCorePipelineReleaseInfo[]
}

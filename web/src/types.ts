export type Finding = {
  prim: string
  attribute: string
  desired: unknown
  rendered: unknown
  observed: unknown
  status: string
  severity: string
  message: string
}

export type TimelineItem = {
  id: number
  type: string
  timestamp: string
  summary: string
  payload: Record<string, unknown>
}

export type ScenePrim = {
  prim: string
  label: string
  status: string
  highlight: {
    enabled: boolean
    color: number[]
    intensity: number
  }
  findings: Finding[]
}

export type LiveMetrics = {
  twin?: string
  hasDrift: boolean
  summary: Record<string, number>
  highlightedPrims: number
  timelineEvents: number
  reconciled: boolean
  mqttPublishEnabled: boolean
  mqttIngestReceived: number
  robotTemp?: number
}

export type SceneSnapshot = {
  twin: string
  generatedAt?: string | null
  hasDrift: boolean
  prims: ScenePrim[]
  protocol: {
    name: string
    description?: string
  }
}

export type TwinSnapshot = {
  twin: {
    name?: string
    variant?: string
    stage?: string
    reconciled?: boolean
  }
  simulator: Record<string, unknown>
  observed: Record<string, unknown> | null
  drift: {
    status?: {
      hasDrift?: boolean
      summary?: Record<string, number>
      findings?: Finding[]
    }
    metadata?: {
      generatedAt?: string
    }
  } | null
  proposal: {
    spec?: {
      changes?: Array<Record<string, unknown>>
    }
    status?: {
      applied?: boolean
      driftAfter?: Record<string, number>
    }
  } | null
  timeline: TimelineItem[]
}

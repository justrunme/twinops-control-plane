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

export type TwinSnapshot = {
  twin: {
    name?: string
    variant?: string
    stage?: string
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
  timeline: TimelineItem[]
}

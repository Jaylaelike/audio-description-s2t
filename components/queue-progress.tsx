"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Button } from "@/components/ui/button"
import { RefreshCw, Clock, CheckCircle, XCircle, Loader2 } from "lucide-react"

interface QueueStatus {
  queue_size: number
  timestamp: string
}

interface TaskStatus {
  task_id: string
  status: string
  progress: number
  created_at: string
  started_at?: string
  completed_at?: string
  result?: any
  error_message?: string
}

export function QueueProgress() {
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)

  const fetchQueueStatus = async () => {
    try {
      const response = await fetch('http://localhost:8000/queue/status')
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      const data = await response.json()
      setQueueStatus(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch queue status')
      console.error('Error fetching queue status:', err)
    } finally {
      setIsLoading(false)
    }
  }

  const fetchHealthCheck = async () => {
    try {
      const response = await fetch('http://localhost:8000/health')
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      const data = await response.json()
      return data
    } catch (err) {
      console.error('Health check failed:', err)
      return null
    }
  }

  useEffect(() => {
    fetchQueueStatus()
  }, [])

  useEffect(() => {
    if (!autoRefresh) return

    const interval = setInterval(() => {
      fetchQueueStatus()
    }, 3000) // Refresh every 3 seconds

    return () => clearInterval(interval)
  }, [autoRefresh])

  const handleRefresh = () => {
    setIsLoading(true)
    fetchQueueStatus()
  }

  const toggleAutoRefresh = () => {
    setAutoRefresh(!autoRefresh)
  }

  if (isLoading && !queueStatus) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Loader2 className="h-5 w-5 animate-spin" />
            Queue Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center p-4">
            <Loader2 className="h-8 w-8 animate-spin" />
          </div>
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive">
            <XCircle className="h-5 w-5" />
            Queue Status - Error
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Unable to connect to the transcription server
            </p>
            <p className="text-sm text-destructive">{error}</p>
            <Button onClick={handleRefresh} variant="outline" size="sm">
              <RefreshCw className="h-4 w-4 mr-2" />
              Retry Connection
            </Button>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Clock className="h-5 w-5" />
              Queue Status
            </CardTitle>
            <CardDescription>
              Real-time transcription queue monitoring
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Button
              onClick={toggleAutoRefresh}
              variant={autoRefresh ? "default" : "outline"}
              size="sm"
            >
              {autoRefresh ? "Auto Refresh ON" : "Auto Refresh OFF"}
            </Button>
            <Button onClick={handleRefresh} variant="outline" size="sm">
              <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-6">
          {/* Queue Size Status */}
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <p className="text-sm font-medium">Tasks in Queue</p>
              <p className="text-2xl font-bold">
                {queueStatus?.queue_size || 0}
              </p>
            </div>
            <div className="text-right">
              <Badge variant={queueStatus?.queue_size === 0 ? "secondary" : "default"}>
                {queueStatus?.queue_size === 0 ? "Queue Empty" : `${queueStatus?.queue_size} Pending`}
              </Badge>
            </div>
          </div>

          {/* Server Status */}
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <p className="text-sm font-medium">Server Status</p>
              <div className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-green-500" />
                <span className="text-sm text-green-600 font-medium">Online</span>
              </div>
            </div>
            <div className="text-right">
              <p className="text-xs text-muted-foreground">
                Last updated: {queueStatus?.timestamp ? 
                  new Date(queueStatus.timestamp).toLocaleTimeString() : '--'}
              </p>
            </div>
          </div>

          {/* Queue Activity Indicator */}
          {queueStatus?.queue_size > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium">Queue Activity</p>
                <Badge variant="outline">
                  <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                  Processing
                </Badge>
              </div>
              <Progress value={100} className="h-2" />
              <p className="text-xs text-muted-foreground">
                Queue is actively processing tasks
              </p>
            </div>
          )}

          {/* Help Text */}
          <div className="text-xs text-muted-foreground space-y-1">
            <p>• Tasks are processed in LIFO order (Last In, First Out)</p>
            <p>• Auto-refresh updates every 3 seconds when enabled</p>
            <p>• WebSocket connections provide real-time updates for individual tasks</p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { RefreshCw, Clock, CheckCircle, XCircle, Loader2, Activity, Database, Server, AlertTriangle } from "lucide-react"

interface QueueStats {
  total_tasks: number
  queued_tasks: number
  processing_tasks: number
  completed_tasks: number
  failed_tasks: number
  uptime_seconds: number
  last_backup?: string
  redis_connected: boolean
}

interface QueueStatus {
  queue_size: number
  timestamp: string
  // Extended stats from separated queue service
  total_tasks?: number
  queued_tasks?: number
  processing_tasks?: number
  completed_tasks?: number
  failed_tasks?: number
  uptime_seconds?: number
  last_backup?: string
  redis_connected?: boolean
}

interface HealthStatus {
  status: string
  timestamp: string
  queue_service?: {
    url: string
    healthy: boolean
    stats: QueueStats
  }
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
  const [healthStatus, setHealthStatus] = useState<HealthStatus | null>(null)
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
    }
  }

  const fetchHealthCheck = async () => {
    try {
      const response = await fetch('http://localhost:8000/health')
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      const data = await response.json()
      setHealthStatus(data)
      return data
    } catch (err) {
      console.error('Health check failed:', err)
      setHealthStatus(null)
      return null
    }
  }

  const fetchAllData = async () => {
    setIsLoading(true)
    try {
      await Promise.all([
        fetchQueueStatus(),
        fetchHealthCheck()
      ])
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchAllData()
  }, [])

  useEffect(() => {
    if (!autoRefresh) return

    const interval = setInterval(() => {
      fetchAllData()
    }, 5000) // Refresh every 5 seconds

    return () => clearInterval(interval)
  }, [autoRefresh])

  const handleRefresh = () => {
    fetchAllData()
  }

  const toggleAutoRefresh = () => {
    setAutoRefresh(!autoRefresh)
  }

  const formatUptime = (seconds: number) => {
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    const secs = Math.floor(seconds % 60)
    
    if (hours > 0) {
      return `${hours}h ${minutes}m`
    } else if (minutes > 0) {
      return `${minutes}m ${secs}s`
    } else {
      return `${secs}s`
    }
  }

  const calculateSuccessRate = (completed: number, failed: number) => {
    const total = completed + failed
    if (total === 0) return 0
    return Math.round((completed / total) * 100)
  }

  // Get stats from either queue status or health check
  const stats = healthStatus?.queue_service?.stats || queueStatus
  const isQueueServiceHealthy = healthStatus?.queue_service?.healthy !== false
  const isRedisConnected = stats?.redis_connected !== false

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
              <Activity className="h-5 w-5" />
              Queue Status
            </CardTitle>
            <CardDescription>
              Real-time transcription queue monitoring & system health
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
          {/* System Health Status */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Server className="h-4 w-4" />
                <p className="text-sm font-medium">API Service</p>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-green-500" />
                <span className="text-sm text-green-600 font-medium">Online</span>
              </div>
            </div>
            
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Activity className="h-4 w-4" />
                <p className="text-sm font-medium">Queue Service</p>
              </div>
              <div className="flex items-center gap-2">
                {isQueueServiceHealthy ? (
                  <>
                    <CheckCircle className="h-4 w-4 text-green-500" />
                    <span className="text-sm text-green-600 font-medium">Healthy</span>
                  </>
                ) : (
                  <>
                    <AlertTriangle className="h-4 w-4 text-yellow-500" />
                    <span className="text-sm text-yellow-600 font-medium">Degraded</span>
                  </>
                )}
              </div>
            </div>
            
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Database className="h-4 w-4" />
                <p className="text-sm font-medium">Redis Storage</p>
              </div>
              <div className="flex items-center gap-2">
                {isRedisConnected ? (
                  <>
                    <CheckCircle className="h-4 w-4 text-green-500" />
                    <span className="text-sm text-green-600 font-medium">Connected</span>
                  </>
                ) : (
                  <>
                    <XCircle className="h-4 w-4 text-red-500" />
                    <span className="text-sm text-red-600 font-medium">Disconnected</span>
                  </>
                )}
              </div>
            </div>
          </div>

          <Separator />

          {/* Queue Statistics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="space-y-1">
              <p className="text-sm font-medium text-blue-600">Queued</p>
              <p className="text-2xl font-bold">
                {stats?.queued_tasks ?? queueStatus?.queue_size ?? 0}
              </p>
              <Badge variant="outline" className="text-xs">
                Waiting
              </Badge>
            </div>
            
            <div className="space-y-1">
              <p className="text-sm font-medium text-orange-600">Processing</p>
              <p className="text-2xl font-bold">
                {stats?.processing_tasks ?? 0}
              </p>
              <Badge variant="outline" className="text-xs">
                {stats?.processing_tasks > 0 ? (
                  <>
                    <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                    Active
                  </>
                ) : (
                  'Idle'
                )}
              </Badge>
            </div>
            
            <div className="space-y-1">
              <p className="text-sm font-medium text-green-600">Completed</p>
              <p className="text-2xl font-bold">
                {stats?.completed_tasks ?? 0}
              </p>
              <Badge variant="outline" className="text-xs">
                Success
              </Badge>
            </div>
            
            <div className="space-y-1">
              <p className="text-sm font-medium text-red-600">Failed</p>
              <p className="text-2xl font-bold">
                {stats?.failed_tasks ?? 0}
              </p>
              <Badge variant="outline" className="text-xs">
                Errors
              </Badge>
            </div>
          </div>

          {/* Success Rate & Performance */}
          {stats && (stats.completed_tasks > 0 || stats.failed_tasks > 0) && (
            <div className="space-y-4">
              <Separator />
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium">Success Rate</p>
                    <span className="text-lg font-bold text-green-600">
                      {calculateSuccessRate(stats.completed_tasks, stats.failed_tasks)}%
                    </span>
                  </div>
                  <Progress 
                    value={calculateSuccessRate(stats.completed_tasks, stats.failed_tasks)} 
                    className="h-2"
                  />
                </div>
                
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium">Total Processed</p>
                    <span className="text-lg font-bold">
                      {stats.total_tasks ?? 0}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Lifetime task count
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* System Information */}
          <Separator />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <p className="text-sm font-medium">System Uptime</p>
              <p className="text-lg font-semibold">
                {stats?.uptime_seconds ? formatUptime(stats.uptime_seconds) : 'Unknown'}
              </p>
              <p className="text-xs text-muted-foreground">
                Queue service running time
              </p>
            </div>
            
            <div className="space-y-2">
              <p className="text-sm font-medium">Last Backup</p>
              <p className="text-lg font-semibold">
                {stats?.last_backup ? 
                  new Date(stats.last_backup).toLocaleString() : 
                  'No backup yet'
                }
              </p>
              <p className="text-xs text-muted-foreground">
                Queue state backup time
              </p>
            </div>
          </div>

          {/* Queue Activity Indicator */}
          {(stats?.processing_tasks ?? 0) > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium">Current Activity</p>
                <Badge variant="outline">
                  <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                  {stats?.processing_tasks} task{stats?.processing_tasks !== 1 ? 's' : ''} processing
                </Badge>
              </div>
              <Progress value={100} className="h-2" />
              <p className="text-xs text-muted-foreground">
                Workers are actively processing tasks
              </p>
            </div>
          )}

          {/* System Information & Help */}
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">
              Last updated: {queueStatus?.timestamp ? 
                new Date(queueStatus.timestamp).toLocaleTimeString() : 
                healthStatus?.timestamp ? new Date(healthStatus.timestamp).toLocaleTimeString() : '--'
              }
            </p>
            
            <div className="text-xs text-muted-foreground space-y-1">
              <p>• Tasks processed with priority ordering (higher priority first)</p>
              <p>• Auto-refresh updates every 5 seconds when enabled</p>
              <p>• Automatic backup and recovery on system restart</p>
              <p>• WebSocket connections provide real-time task updates</p>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
"use client"

import { useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Loader2 } from "lucide-react"
import { Progress } from "@/components/ui/progress"

interface ProcessingStatusProps {
  status: string
  jobId: string
}

export function ProcessingStatus({ status, jobId }: ProcessingStatusProps) {
  const [progress, setProgress] = useState(0)
  const [currentStatus, setCurrentStatus] = useState(status)

  // Simulate progress for pending/processing statuses
  useEffect(() => {
    if (currentStatus !== "pending" && currentStatus !== "processing") return

    // Start with different progress based on status
    setProgress(currentStatus === "pending" ? 0 : 15)

    const interval = setInterval(() => {
      setProgress((prev) => {
        // Slow down progress as it gets higher to simulate real processing
        const increment = Math.max(1, 10 - Math.floor(prev / 10))

        // Cap at 95% - the final 5% happens when actually complete
        const newProgress = Math.min(95, prev + increment)

        // If we're at 95%, switch to "processing" if we were "pending"
        if (newProgress >= 95 && currentStatus === "pending") {
          setCurrentStatus("processing")
        }

        return newProgress
      })
    }, 800)

    return () => clearInterval(interval)
  }, [currentStatus])

  // In a real app, you would poll the server for status updates
  // This is just a simulation for the UI
  useEffect(() => {
    setCurrentStatus(status)
    if (status === "completed") {
      setProgress(100)
    } else if (status === "failed") {
      setProgress(0)
    }
  }, [status])

  const getStatusColor = (status: string) => {
    switch (status) {
      case "completed":
        return "success"
      case "processing":
        return "warning"
      case "pending":
        return "secondary"
      case "failed":
        return "destructive"
      default:
        return "secondary"
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Badge variant={getStatusColor(currentStatus)}>
          {currentStatus === "pending" || currentStatus === "processing" ? (
            <Loader2 className="mr-1 h-3 w-3 animate-spin" />
          ) : null}
          {currentStatus.charAt(0).toUpperCase() + currentStatus.slice(1)}
        </Badge>
      </div>

      {(currentStatus === "pending" || currentStatus === "processing") && (
        <Progress value={progress} className="h-1.5 w-full" />
      )}
    </div>
  )
}

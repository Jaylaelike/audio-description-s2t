"use client"

import { useState } from "react"
import { formatDistanceToNow, format } from "date-fns"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import Link from "next/link"
import { FileAudio, ChevronDown, ChevronUp } from "lucide-react"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent } from "@/components/ui/card"

type TranscriptionJob = {
  id: string
  title: string
  originalAudioFileName: string
  status: string
  createdAt: Date
  updatedAt: Date
  transcriptionResultJson: any
}

interface TranscriptionsListProps {
  transcriptions: TranscriptionJob[]
}

export function TranscriptionsList({ transcriptions }: TranscriptionsListProps) {
  const [expandedRow, setExpandedRow] = useState<string | null>(null)

  const getStatusColor = (status: string) => {
    switch (status) {
      case "completed":
        return "success"
      case "processing":
        return "warning"
      case "failed":
        return "destructive"
      default:
        return "secondary"
    }
  }

  const StatusBadge = ({ status }: { status: string }) => {
    return (
      <div className="flex items-center gap-2">
        <Badge variant={getStatusColor(status)}>
          {status === "processing" && <span className="mr-1 h-2 w-2 rounded-full bg-background animate-pulse"></span>}
          {status.charAt(0).toUpperCase() + status.slice(1)}
        </Badge>
      </div>
    )
  }

  const toggleRow = (id: string) => {
    if (expandedRow === id) {
      setExpandedRow(null)
    } else {
      setExpandedRow(id)
    }
  }

  const getTranscriptionText = (job: TranscriptionJob) => {
    if (job.status !== "completed" || !job.transcriptionResultJson) {
      return job.status === "processing"
        ? "Transcription in progress..."
        : job.status === "failed"
          ? "Transcription failed"
          : "Waiting to start..."
    }

    try {
      const result =
        typeof job.transcriptionResultJson === "string"
          ? JSON.parse(job.transcriptionResultJson)
          : job.transcriptionResultJson

      return result.text || "No text available"
    } catch (error) {
      console.error("Error parsing transcription result:", error)
      return "Error displaying transcription"
    }
  }

  return (
    <div className="rounded-md border">
      {transcriptions.length === 0 ? (
        <div className="flex flex-col items-center justify-center p-8 text-center">
          <FileAudio className="h-10 w-10 text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold">No transcriptions yet</h3>
          <p className="text-muted-foreground mt-2">Upload an audio file to get started with transcription.</p>
          <Link href="/upload" className="mt-4">
            <Button>Upload Audio</Button>
          </Link>
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[30px]"></TableHead>
              <TableHead>Title</TableHead>
              <TableHead>Audio File</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Created</TableHead>
              <TableHead>Updated</TableHead>
              <TableHead>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {transcriptions.map((job) => (
              <>
                <TableRow key={job.id} className="cursor-pointer" onClick={() => toggleRow(job.id)}>
                  <TableCell>
                    {expandedRow === job.id ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  </TableCell>
                  <TableCell className="font-medium">{job.title}</TableCell>
                  <TableCell className="truncate max-w-[200px]">{job.originalAudioFileName}</TableCell>
                  <TableCell>
                    <StatusBadge status={job.status} />
                  </TableCell>
                  <TableCell title={format(new Date(job.createdAt), "PPpp")}>
                    {formatDistanceToNow(new Date(job.createdAt), { addSuffix: true })}
                  </TableCell>
                  <TableCell title={format(new Date(job.updatedAt), "PPpp")}>
                    {formatDistanceToNow(new Date(job.updatedAt), { addSuffix: true })}
                  </TableCell>
                  <TableCell>
                    <Link href={`/transcriptions/${job.id}`} onClick={(e) => e.stopPropagation()}>
                      <Button variant="outline" size="sm">
                        View Details
                      </Button>
                    </Link>
                  </TableCell>
                </TableRow>
                {expandedRow === job.id && (
                  <TableRow>
                    <TableCell colSpan={7} className="p-0">
                      <Card className="m-2 border-0 shadow-none">
                        <CardContent className="p-4">
                          <h4 className="text-sm font-medium mb-2">Transcription Text</h4>
                          <Textarea value={getTranscriptionText(job)} readOnly className="min-h-[100px] resize-none" />
                        </CardContent>
                      </Card>
                    </TableCell>
                  </TableRow>
                )}
              </>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}

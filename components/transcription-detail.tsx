"use client"

import { useState, useRef, useEffect } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { formatDistanceToNow, format } from "date-fns"
import { ProcessingStatus } from "@/components/ui/progressing-status"

interface Word {
  text: string
  start: number
  end: number
  confidence: number
}

interface Segment {
  id: number
  start: number
  end: number
  text: string
  words: Word[]
}

interface TranscriptionResult {
  text: string
  segments: Segment[]
  language?: string
}

interface TranscriptionJob {
  id: string
  title: string
  description: string | null
  originalAudioFileName: string
  status: string
  transcriptionResultJson: TranscriptionResult | null
  createdAt: Date
  updatedAt: Date
}

interface TranscriptionDetailProps {
  transcription: TranscriptionJob
}

export function TranscriptionDetail({ transcription }: TranscriptionDetailProps) {
  const [selectedSegmentId, setSelectedSegmentId] = useState<number | null>(null)
  const [activeWordIndex, setActiveWordIndex] = useState<{ segmentId: number; wordIndex: number } | null>(null)
  const audioRef = useRef<HTMLAudioElement>(null)
  const segmentRefs = useRef<Map<number, HTMLDivElement>>(new Map())

  // Track audio playback time to highlight current word
  useEffect(() => {
    const audio = audioRef.current
    if (!audio || !transcription.transcriptionResultJson) return

    const updateHighlight = () => {
      if (!transcription.transcriptionResultJson) return

      const currentTime = audio.currentTime

      // Find the segment and word that corresponds to the current time
      for (const segment of transcription.transcriptionResultJson.segments) {
        if (currentTime >= segment.start && currentTime <= segment.end) {
          // Find the specific word in this segment
          for (let i = 0; i < segment.words.length; i++) {
            const word = segment.words[i]
            if (currentTime >= word.start && currentTime <= word.end) {
              setActiveWordIndex({ segmentId: segment.id, wordIndex: i })

              // Scroll the segment into view if it's not already visible
              if (segment.id !== selectedSegmentId) {
                setSelectedSegmentId(segment.id)
                const segmentElement = segmentRefs.current.get(segment.id)
                segmentElement?.scrollIntoView({ behavior: "smooth", block: "nearest" })
              }

              return
            }
          }
        }
      }
    }

    // Update every 100ms for smoother highlighting
    const interval = setInterval(updateHighlight, 100)
    audio.addEventListener("timeupdate", updateHighlight)

    return () => {
      clearInterval(interval)
      audio.removeEventListener("timeupdate", updateHighlight)
    }
  }, [transcription.transcriptionResultJson, selectedSegmentId])

  const handleWordClick = (segmentId: number, wordIndex: number, startTime: number) => {
    setSelectedSegmentId(segmentId)
    setActiveWordIndex({ segmentId, wordIndex })

    if (audioRef.current) {
      audioRef.current.currentTime = startTime
      audioRef.current.play()
    }
  }

  // Format confidence as percentage
  const formatConfidence = (confidence: number): string => {
    return `${(confidence * 100).toFixed(0)}%`
  }

  return (
    <div className="flex flex-col space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">{transcription.title}</h1>
        <ProcessingStatus status={transcription.status} jobId={transcription.id} />
      </div>

      {transcription.description && <p className="text-muted-foreground">{transcription.description}</p>}

      <div className="flex flex-col sm:flex-row gap-4 text-sm text-muted-foreground">
        <p>
          Created:{" "}
          <span title={format(new Date(transcription.createdAt), "PPpp")}>
            {formatDistanceToNow(new Date(transcription.createdAt), { addSuffix: true })}
          </span>
        </p>
        <p>
          Last Updated:{" "}
          <span title={format(new Date(transcription.updatedAt), "PPpp")}>
            {formatDistanceToNow(new Date(transcription.updatedAt), { addSuffix: true })}
          </span>
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column: Audio Player */}
        <div className="lg:col-span-2 space-y-4">
          <div className="p-4 border rounded-lg">
            <audio
              ref={audioRef}
              controls
              className="w-full"
              src={`/uploads/audio/${transcription.originalAudioFileName}`}
            />
          </div>
        </div>

        {/* Right column: Transcript */}
        <div className="lg:col-span-1">
          <Card className="h-full">
            <CardContent className="p-0">
              <div className="p-4 border-b bg-muted/50">
                <h2 className="text-lg font-semibold">Transcript</h2>
              </div>

              {transcription.status === "completed" && transcription.transcriptionResultJson ? (
                <ScrollArea className="h-[500px]">
                  <div className="p-4 space-y-2">
                    {(transcription.transcriptionResultJson as TranscriptionResult).segments.map((segment) => (
                      <div
                        key={segment.id}
                        ref={(el) => {
                          if (el) segmentRefs.current.set(segment.id, el)
                        }}
                        className={`p-2 rounded-md transition-colors ${
                          selectedSegmentId === segment.id ? "bg-muted" : "hover:bg-muted/50"
                        }`}
                        onClick={() => {
                          setSelectedSegmentId(segment.id)
                          if (segment.words.length > 0) {
                            handleWordClick(segment.id, 0, segment.start)
                          }
                        }}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs text-muted-foreground">{formatTime(segment.start)}</span>
                          <span className="text-xs text-muted-foreground">
                            {segment.confidence ? formatConfidence(segment.confidence) : ""}
                          </span>
                        </div>
                        <p>
                          {segment.words.map((word, idx) => (
                            <span
                              key={`${segment.id}-${idx}`}
                              onClick={(e) => {
                                e.stopPropagation()
                                handleWordClick(segment.id, idx, word.start)
                              }}
                              className={`cursor-pointer inline-block ${
                                activeWordIndex?.segmentId === segment.id && activeWordIndex?.wordIndex === idx
                                  ? "bg-primary text-primary-foreground px-0.5 rounded"
                                  : ""
                              }`}
                              title={`Confidence: ${formatConfidence(word.confidence)}`}
                            >
                              {word.text}{" "}
                            </span>
                          ))}
                        </p>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              ) : transcription.status === "pending" || transcription.status === "processing" ? (
                <div className="p-6 flex flex-col items-center justify-center space-y-4">
                  <div className="relative w-16 h-16">
                    <div className="absolute inset-0 rounded-full border-4 border-muted"></div>
                    <div className="absolute inset-0 rounded-full border-4 border-t-warning animate-spin"></div>
                  </div>
                  <div className="text-center space-y-2">
                    <p className="font-medium">Transcription in progress</p>
                    <p className="text-sm text-muted-foreground">
                      {transcription.status === "pending" ? "Waiting to start..." : "Processing audio..."}
                    </p>
                  </div>
                </div>
              ) : (
                <div className="p-6 text-center">
                  <p>Transcription failed or not available.</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}

// Helper function to format time in MM:SS format
function formatTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = Math.floor(seconds % 60)
  return `${minutes}:${remainingSeconds.toString().padStart(2, "0")}`
}

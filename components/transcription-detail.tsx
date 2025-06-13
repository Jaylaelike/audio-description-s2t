"use client"

import { useState, useRef, useEffect } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { formatDistanceToNow, format } from "date-fns"
import { ProcessingStatus } from "@/components/ui/progressing-status"
import { AlertTriangle, Shield, Loader2, AlertCircle } from "lucide-react"

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
  riskDetectionStatus: string
  riskDetectionResult: string | null
  riskDetectionResponse: string | null
  riskAnalyzedAt: Date | null
  createdAt: Date
  updatedAt: Date
}

interface TranscriptionDetailProps {
  transcription: TranscriptionJob
}

export function TranscriptionDetail({ transcription }: TranscriptionDetailProps) {
  const [selectedSegmentId, setSelectedSegmentId] = useState<number | null>(null)
  const [activeWordIndex, setActiveWordIndex] = useState<{ segmentId: number; wordIndex: number } | null>(null)
  const [isAnalyzingRisk, setIsAnalyzingRisk] = useState(false)
  const [riskAnalysisError, setRiskAnalysisError] = useState<string | null>(null)
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

  // Parse Ollama response to extract Thinking, Summary, and Final Answer sections
  const parseOllamaResponse = (response: string) => {
    const sections = {
      thinking: '',
      summary: '',
      finalAnswer: ''
    }

    // Extract Thinking section from <think>...</think> tags
    const thinkTagMatch = response.match(/<think>([\s\S]*?)<\/think>/i)
    if (thinkTagMatch) {
      sections.thinking = thinkTagMatch[1].trim()
      
      // Extract the final answer after </think> tag
      const afterThinkMatch = response.match(/<\/think>\s*([\s\S]*?)$/i)
      if (afterThinkMatch) {
        sections.finalAnswer = afterThinkMatch[1].trim()
      }
    } else {
      // Fallback: Extract Thinking section (between "Thinking..." and "...done thinking.")
      const thinkingMatch = response.match(/Thinking\.\.\.([\s\S]*?)\.\.\.done thinking\./i)
      if (thinkingMatch) {
        sections.thinking = thinkingMatch[1].trim()
      }

      // Extract Summary section - handle both **Summary:** and Summary: formats
      const summaryMatch = response.match(/\*\*Summary:\*\*\s*([\s\S]*?)(?=\*\*Final Answer:\*\*|Final Answer:|$)/i) ||
                          response.match(/Summary:\s*([\s\S]*?)(?=\*\*Final Answer:\*\*|Final Answer:|$)/i)
      if (summaryMatch) {
        sections.summary = summaryMatch[1].trim()
      }

      // Extract Final Answer - handle both **Final Answer:** and Final Answer: formats
      const finalAnswerMatch = response.match(/\*\*Final Answer:\*\*\s*([\s\S]*?)$/i) ||
                               response.match(/Final Answer:\s*([\s\S]*?)$/i)
      if (finalAnswerMatch) {
        let finalText = finalAnswerMatch[1].trim()
        
        // Check for boxed answer
        const boxedMatch = finalText.match(/\\?boxed\s*\{\s*([^}]+)\s*\}/i)
        if (boxedMatch) {
          sections.finalAnswer = boxedMatch[1].trim()
        } else {
          sections.finalAnswer = finalText
        }
      }
    }

    return sections
  }

  // Handle risk detection with proper waiting for Ollama processing
  const handleRiskDetection = async () => {
    if (!transcription.transcriptionResultJson) {
      setRiskAnalysisError('No transcription available for analysis')
      return
    }

    setIsAnalyzingRisk(true)
    setRiskAnalysisError(null)

    try {
      const fullText = transcription.transcriptionResultJson.text
      
      // Start the analysis
      const response = await fetch('/api/detect-risk', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          transcriptionId: transcription.id,
          text: fullText
        })
      })

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.error || 'Risk analysis failed')
      }

      // Poll for completion instead of refreshing
      await pollForRiskAnalysisCompletion(transcription.id)

    } catch (error) {
      setRiskAnalysisError(error instanceof Error ? error.message : 'Unknown error occurred')
      setIsAnalyzingRisk(false)
    }
  }

  // Poll for risk analysis completion
  const pollForRiskAnalysisCompletion = async (transcriptionId: string) => {
    const maxAttempts = 30 // 30 attempts * 2 seconds = 60 seconds max wait
    let attempts = 0

    const poll = async (): Promise<void> => {
      try {
        attempts++
        
        const response = await fetch(`/api/detect-risk?transcriptionId=${transcriptionId}`)
        const data = await response.json()

        if (response.ok && data.success) {
          const status = data.riskDetection.status
          
          if (status === 'completed') {
            // Analysis completed, refresh the page to show results
            window.location.reload()
            return
          } else if (status === 'failed') {
            setRiskAnalysisError('Risk analysis failed on server')
            setIsAnalyzingRisk(false)
            return
          } else if (status === 'analyzing') {
            // Still processing, continue polling
            if (attempts < maxAttempts) {
              setTimeout(() => poll(), 2000) // Wait 2 seconds before next poll
            } else {
              setRiskAnalysisError('Analysis timed out. Please try again.')
              setIsAnalyzingRisk(false)
            }
            return
          }
        }
        
        // If we get here, something went wrong
        if (attempts < maxAttempts) {
          setTimeout(() => poll(), 2000)
        } else {
          setRiskAnalysisError('Unable to get analysis status. Please try again.')
          setIsAnalyzingRisk(false)
        }
        
      } catch (error) {
        if (attempts < maxAttempts) {
          setTimeout(() => poll(), 2000)
        } else {
          setRiskAnalysisError('Network error while checking analysis status')
          setIsAnalyzingRisk(false)
        }
      }
    }

    // Start polling
    setTimeout(() => poll(), 2000) // Initial delay of 2 seconds
  }

  // Get risk status badge
  const getRiskStatusBadge = () => {
    switch (transcription.riskDetectionStatus) {
      case 'completed':
        if (transcription.riskDetectionResult === 'เข้าข่ายผิด') {
          return (
            <Badge variant="destructive" className="gap-1">
              <AlertTriangle className="h-3 w-3" />
              <span className="thai-text">เข้าข่ายผิดกฎหมาย</span>
            </Badge>
          )
        } else if (transcription.riskDetectionResult === 'ไม่ผิด') {
          return (
            <Badge variant="secondary" className="gap-1">
              <Shield className="h-3 w-3" />
              <span className="thai-text">ไม่มีความเสี่ยง</span>
            </Badge>
          )
        } else {
          return (
            <Badge variant="outline" className="gap-1">
              <AlertCircle className="h-3 w-3" />
              <span className="thai-text">ไม่สามารถวิเคราะห์ได้</span>
            </Badge>
          )
        }
      case 'analyzing':
        return (
          <Badge variant="outline" className="gap-1">
            <Loader2 className="h-3 w-3 animate-spin" />
            <span className="thai-text">กำลังวิเคราะห์...</span>
          </Badge>
        )
      case 'failed':
        return (
          <Badge variant="destructive" className="gap-1">
            <AlertCircle className="h-3 w-3" />
            <span className="thai-text">วิเคราะห์ไม่สำเร็จ</span>
          </Badge>
        )
      default:
        return (
          <Badge variant="outline">
            <span className="thai-text">ยังไม่ได้วิเคราะห์</span>
          </Badge>
        )
    }
  }

  return (
    <div className="flex flex-col space-y-4 thai-content">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold thai-text">{transcription.title}</h1>
        <div className="flex items-center gap-3">
          {getRiskStatusBadge()}
          <ProcessingStatus status={transcription.status} jobId={transcription.id} />
        </div>
      </div>

      {/* Risk Detection Section */}
      {transcription.status === "completed" && (
        <Card className="border-l-4 border-l-orange-400">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <h3 className="text-sm font-medium thai-text">การตรวจสอบความเสี่ยงทางกฎหมาย</h3>
                <p className="text-xs text-muted-foreground thai-text">
                  ตรวจสอบเนื้อหาที่อาจเสี่ยงต่อการฝ่าฝืนกฎหมาย
                </p>
              </div>
              <div className="flex items-center gap-2">
                {transcription.riskDetectionStatus === 'not_analyzed' && (
                  <Button
                    onClick={handleRiskDetection}
                    disabled={isAnalyzingRisk}
                    size="sm"
                    variant="outline"
                  >
                    {isAnalyzingRisk ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin mr-2" />
                        <span className="thai-text">กำลังวิเคราะห์...</span>
                      </>
                    ) : (
                      <>
                        <AlertTriangle className="h-4 w-4 mr-2" />
                        <span className="thai-text">ตรวจสอบความเสี่ยง</span>
                      </>
                    )}
                  </Button>
                )}
                {transcription.riskDetectionStatus === 'failed' && (
                  <Button
                    onClick={handleRiskDetection}
                    disabled={isAnalyzingRisk}
                    size="sm"
                    variant="outline"
                  >
                    <AlertCircle className="h-4 w-4 mr-2" />
                    <span className="thai-text">ลองใหม่</span>
                  </Button>
                )}
              </div>
            </div>
            
            {/* Show analysis result */}
            {transcription.riskDetectionStatus === 'completed' && transcription.riskAnalyzedAt && transcription.riskDetectionResponse && (
              <div className="mt-3 space-y-3">
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span className="thai-text">ผลการวิเคราะห์:</span>
                  <span>
                    {format(new Date(transcription.riskAnalyzedAt), "dd/MM/yyyy HH:mm")}
                  </span>
                </div>
                
                {(() => {
                  const parsedResponse = parseOllamaResponse(transcription.riskDetectionResponse)
                  
                  return (
                    <div className="space-y-3">
                      {/* Debug: Show database result vs parsed result */}
                      <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-md">
                        <h4 className="text-sm font-semibold text-yellow-700 mb-2 thai-text">🔍 ข้อมูลการวิเคราะห์</h4>
                        <div className="space-y-1 text-xs">
                          <p><span className="font-medium">ผลจากฐานข้อมูล:</span> <span className="thai-text">{transcription.riskDetectionResult}</span></p>
                          <p><span className="font-medium">ผลที่แยกได้จากการตอบ:</span> <span className="thai-text">{parsedResponse.finalAnswer}</span></p>
                        </div>
                      </div>

                      {/* Final Answer - Most Important */}
                      {parsedResponse.finalAnswer && (
                        <div className="p-3 bg-primary/10 border border-primary/20 rounded-md">
                          <h4 className="text-sm font-semibold text-primary mb-2 thai-text">📋 คำตอบสุดท้าย</h4>
                          <p className="text-sm font-medium thai-text">{parsedResponse.finalAnswer}</p>
                        </div>
                      )}
                      
                      {/* Summary */}
                      {parsedResponse.summary && (
                        <div className="p-3 bg-blue-50 border border-blue-200 rounded-md">
                          <h4 className="text-sm font-semibold text-blue-700 mb-2 thai-text">📝 สรุป</h4>
                          <p className="text-sm text-blue-800 thai-text">{parsedResponse.summary}</p>
                        </div>
                      )}
                      
                      {/* Thinking Process - Collapsible */}
                      {parsedResponse.thinking && (
                        <details className="group">
                          <summary className="cursor-pointer p-3 bg-gray-50 border border-gray-200 rounded-md hover:bg-gray-100 transition-colors">
                            <span className="text-sm font-semibold text-gray-700 thai-text">🤔 กระบวนการคิด (คลิกเพื่อดู)</span>
                          </summary>
                          <div className="mt-2 p-3 bg-gray-50 border border-gray-200 rounded-md">
                            <p className="text-sm text-gray-700 whitespace-pre-wrap thai-text">{parsedResponse.thinking}</p>
                          </div>
                        </details>
                      )}
                      
                      {/* Raw Response - Collapsible for debugging */}
                      <details className="group">
                        <summary className="cursor-pointer p-2 bg-muted/50 border border-muted rounded-md hover:bg-muted transition-colors">
                          <span className="text-xs text-muted-foreground thai-text">🔍 คำตอบแบบเต็ม (สำหรับการตรวจสอบ)</span>
                        </summary>
                        <div className="mt-2 p-3 bg-muted/30 border border-muted rounded-md">
                          <pre className="text-xs text-muted-foreground whitespace-pre-wrap font-mono overflow-x-auto thai-text">
                            {transcription.riskDetectionResponse}
                          </pre>
                        </div>
                      </details>
                    </div>
                  )
                })()}
              </div>
            )}

            {/* Show error */}
            {riskAnalysisError && (
              <div className="mt-3 p-3 bg-destructive/10 border border-destructive/20 rounded-md">
                <p className="text-sm text-destructive thai-text">{riskAnalysisError}</p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {transcription.description && <p className="text-muted-foreground thai-text">{transcription.description}</p>}

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
                        </div>
                        <p>
                          {segment.words.map((word, idx) => (
                            <span
                              key={`${segment.id}-${idx}`}
                              onClick={(e) => {
                                e.stopPropagation()
                                handleWordClick(segment.id, idx, word.start)
                              }}
                              className={`cursor-pointer inline-block thai-text ${
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

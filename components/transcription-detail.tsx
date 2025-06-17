"use client"

import { useState, useRef, useEffect } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { formatDistanceToNow, format } from "date-fns"
import { ProcessingStatus } from "@/components/ui/progressing-status"
import { AlertTriangle, Shield, Loader2, AlertCircle, ChevronDown, Clock, Zap } from "lucide-react"

// Add custom styles for animations
const styles = `
  @keyframes wordHighlight {
    0% { background-color: transparent; transform: scale(1); }
    50% { background-color: hsl(var(--primary)); color: hsl(var(--primary-foreground)); transform: scale(1.05); }
    100% { background-color: hsl(var(--primary)); color: hsl(var(--primary-foreground)); transform: scale(1.05); }
  }
  
  .word-active {
    animation: wordHighlight 0.3s ease-in-out;
  }
  
  .segment-pulse {
    animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
  }
  
  @keyframes slideInLeft {
    0% { transform: translateX(-20px); opacity: 0; }
    100% { transform: translateX(0); opacity: 1; }
  }
  
  .segment-enter {
    animation: slideInLeft 0.3s ease-out;
  }
`;

// Inject styles
if (typeof document !== 'undefined') {
  const styleElement = document.createElement('style');
  styleElement.textContent = styles;
  if (!document.head.querySelector('style[data-transcript-styles]')) {
    styleElement.setAttribute('data-transcript-styles', 'true');
    document.head.appendChild(styleElement);
  }
}

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
  const [isPlaying, setIsPlaying] = useState(false)
  const audioRef = useRef<HTMLAudioElement>(null)
  const segmentRefs = useRef<Map<number, HTMLDivElement>>(new Map())

  // Track audio play/pause state
  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return

    const handlePlay = () => setIsPlaying(true)
    const handlePause = () => setIsPlaying(false)
    const handleEnded = () => setIsPlaying(false)

    audio.addEventListener("play", handlePlay)
    audio.addEventListener("pause", handlePause)
    audio.addEventListener("ended", handleEnded)

    return () => {
      audio.removeEventListener("play", handlePlay)
      audio.removeEventListener("pause", handlePause)
      audio.removeEventListener("ended", handleEnded)
    }
  }, [])

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
          // Update selected segment if changed
          if (segment.id !== selectedSegmentId) {
            setSelectedSegmentId(segment.id)
            const segmentElement = segmentRefs.current.get(segment.id)
            segmentElement?.scrollIntoView({ behavior: "smooth", block: "center" })
          }

          // Find the specific word in this segment
          if (segment.words && segment.words.length > 0) {
            for (let i = 0; i < segment.words.length; i++) {
              const word = segment.words[i]
              if (currentTime >= word.start && currentTime <= word.end) {
                setActiveWordIndex({ segmentId: segment.id, wordIndex: i })
                return
              }
            }
          }
          
          // If no specific word is found but we're in the segment, clear active word
          setActiveWordIndex(null)
          return
        }
      }

      // If we're not in any segment, clear highlights
      setActiveWordIndex(null)
      setSelectedSegmentId(null)
    }

    // Update every 50ms for smoother highlighting and progress bars
    const interval = setInterval(updateHighlight, 50)
    audio.addEventListener("timeupdate", updateHighlight)
    audio.addEventListener("play", updateHighlight)
    audio.addEventListener("pause", updateHighlight)

    return () => {
      clearInterval(interval)
      audio.removeEventListener("timeupdate", updateHighlight)
      audio.removeEventListener("play", updateHighlight)
      audio.removeEventListener("pause", updateHighlight)
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

  // New dedicated handler for segment clicks
  const handleSegmentClick = (segment: Segment) => {
    console.log(`Clicking segment ${segment.id} at timestamp ${segment.start}s`); // Debug log
    
    setSelectedSegmentId(segment.id)
    setActiveWordIndex(null) // Clear word-level highlighting when clicking segment
    
    if (audioRef.current) {
      try {
        audioRef.current.currentTime = segment.start
        audioRef.current.play().catch(error => {
          console.log("Auto-play failed (this is normal for some browsers):", error)
          // Auto-play might be blocked by browser, that's OK
        })
      } catch (error) {
        console.error("Error setting audio time:", error)
      }
    } else {
      console.warn("Audio ref not available")
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

  // Handle risk detection using backend queue system
  const handleRiskDetection = async (priority: number = 0) => {
    if (!transcription.transcriptionResultJson) {
      setRiskAnalysisError('No transcription available for analysis')
      return
    }

    setIsAnalyzingRisk(true)
    setRiskAnalysisError(null)

    try {
      const fullText = transcription.transcriptionResultJson.text
      
      // Submit to backend queue with priority
      const response = await fetch(`http://localhost:8000/detect-risk/?priority=${priority}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          transcription_id: transcription.id,
          text: fullText
        })
      })

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.error || 'Risk analysis failed')
      }

      const taskId = data.task_id
      console.log(`Risk detection task queued with ID: ${taskId} (priority: ${priority})`)

      // Poll for completion using backend API
      await pollForBackendRiskAnalysisCompletion(taskId)

    } catch (error) {
      setRiskAnalysisError(error instanceof Error ? error.message : 'Unknown error occurred')
      setIsAnalyzingRisk(false)
    }
  }

  // Poll for backend risk analysis completion
  const pollForBackendRiskAnalysisCompletion = async (taskId: string) => {
    const maxAttempts = 60 // 60 attempts * 3 seconds = 3 minutes max wait
    let attempts = 0

    const poll = async (): Promise<void> => {
      try {
        attempts++
        
        const response = await fetch(`http://localhost:8000/task/${taskId}`)
        const data = await response.json()

        if (response.ok) {
          const status = data.status
          
          if (status === 'completed') {
            // Risk analysis completed, now update database via the API
            const result = data.result
            try {
              // Update the database with the results
              const updateResponse = await fetch('/api/detect-risk', {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                  transcriptionId: result.transcription_id,
                  text: 'dummy', // This won't be used since we're providing results
                  overrideResults: {
                    riskResult: result.risk_result,
                    ollamaResponse: result.ollama_response
                  }
                })
              })
              
              if (updateResponse.ok) {
                // Analysis completed, refresh the page to show results
                window.location.reload()
              } else {
                setRiskAnalysisError('Analysis completed but failed to update database')
                setIsAnalyzingRisk(false)
              }
            } catch (updateError) {
              setRiskAnalysisError('Analysis completed but failed to save results')
              setIsAnalyzingRisk(false)
            }
            return
          } else if (status === 'failed') {
            setRiskAnalysisError(data.error_message || 'Risk analysis failed on server')
            setIsAnalyzingRisk(false)
            return
          } else if (status === 'processing' || status === 'queued') {
            // Still processing, continue polling
            if (attempts < maxAttempts) {
              setTimeout(() => poll(), 3000) // Wait 3 seconds before next poll
            } else {
              setRiskAnalysisError('Analysis timed out. Please try again.')
              setIsAnalyzingRisk(false)
            }
            return
          }
        }
        
        // If we get here, something went wrong
        if (attempts < maxAttempts) {
          setTimeout(() => poll(), 3000)
        } else {
          setRiskAnalysisError('Unable to get analysis status. Please try again.')
          setIsAnalyzingRisk(false)
        }
        
      } catch (error) {
        if (attempts < maxAttempts) {
          setTimeout(() => poll(), 3000)
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
                {(transcription.riskDetectionStatus === 'not_analyzed' || !transcription.riskDetectionStatus) && (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        disabled={isAnalyzingRisk}
                        size="sm"
                        variant="outline"
                        className="gap-1"
                      >
                        {isAnalyzingRisk ? (
                          <>
                            <Loader2 className="h-4 w-4 animate-spin" />
                            <span className="thai-text">กำลังวิเคราะห์...</span>
                          </>
                        ) : (
                          <>
                            <AlertTriangle className="h-4 w-4" />
                            <span className="thai-text">ตรวจสอบความเสี่ยง</span>
                            <ChevronDown className="h-3 w-3" />
                          </>
                        )}
                      </Button>
                    </DropdownMenuTrigger>
                    {!isAnalyzingRisk && (
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => handleRiskDetection(0)} className="gap-2">
                          <Clock className="h-4 w-4" />
                          <span className="thai-text">ปกติ (Normal)</span>
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => handleRiskDetection(1)} className="gap-2">
                          <AlertTriangle className="h-4 w-4" />
                          <span className="thai-text">สำคัญ (High)</span>
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => handleRiskDetection(2)} className="gap-2">
                          <Zap className="h-4 w-4" />
                          <span className="thai-text">เร่งด่วน (Urgent)</span>
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    )}
                  </DropdownMenu>
                )}
                {(transcription.riskDetectionStatus === 'failed' || transcription.riskDetectionStatus === 'completed') && (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        disabled={isAnalyzingRisk}
                        size="sm"
                        variant="outline"
                        className="gap-1"
                      >
                        {isAnalyzingRisk ? (
                          <>
                            <Loader2 className="h-4 w-4 animate-spin" />
                            <span className="thai-text">กำลังวิเคราะห์...</span>
                          </>
                        ) : (
                          <>
                            <AlertCircle className="h-4 w-4" />
                            <span className="thai-text">{transcription.riskDetectionStatus === 'failed' ? 'ลองใหม่' : 'วิเคราะห์ใหม่'}</span>
                            <ChevronDown className="h-3 w-3" />
                          </>
                        )}
                      </Button>
                    </DropdownMenuTrigger>
                    {!isAnalyzingRisk && (
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => handleRiskDetection(0)} className="gap-2">
                          <Clock className="h-4 w-4" />
                          <span className="thai-text">ปกติ (Normal)</span>
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => handleRiskDetection(1)} className="gap-2">
                          <AlertTriangle className="h-4 w-4" />
                          <span className="thai-text">สำคัญ (High)</span>
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => handleRiskDetection(2)} className="gap-2">
                          <Zap className="h-4 w-4" />
                          <span className="thai-text">เร่งด่วน (Urgent)</span>
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    )}
                  </DropdownMenu>
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
          <div className={`p-4 border rounded-lg transition-all duration-300 ${
            isPlaying ? "border-primary shadow-md bg-primary/5" : "hover:border-muted-foreground/50"
          }`}>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium text-muted-foreground">Audio Player</h3>
              <div className={`w-2 h-2 rounded-full transition-all duration-300 ${
                isPlaying ? "bg-green-500 animate-pulse" : "bg-muted"
              }`} />
            </div>
            <audio
              ref={audioRef}
              controls
              className="w-full"
              src={`/uploads/audio/${transcription.originalAudioFileName}`}
            />
            {selectedSegmentId && (
              <div className="mt-2 text-xs text-muted-foreground">
                Currently playing: Segment {selectedSegmentId}
              </div>
            )}
          </div>
        </div>

        {/* Right column: Transcript */}
        <div className="lg:col-span-1">
          <Card className="h-full">
            <CardContent className="p-0">
              <div className={`p-4 border-b transition-colors duration-300 ${
                isPlaying ? "bg-primary/10 border-primary/20" : "bg-muted/50"
              }`}>
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold">Transcript</h2>
                  <div className="flex items-center gap-2">
                    {selectedSegmentId && (
                      <span className="text-xs text-muted-foreground bg-primary/10 px-2 py-1 rounded">
                        Segment {selectedSegmentId}
                      </span>
                    )}
                    <div className={`w-2 h-2 rounded-full transition-all duration-300 ${
                      isPlaying ? "bg-green-500 animate-pulse" : "bg-muted"
                    }`} />
                  </div>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  Click on segments or words to jump to timestamp
                </p>
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
                        className={`group p-3 rounded-lg transition-all duration-300 cursor-pointer segment-enter ${
                          selectedSegmentId === segment.id 
                            ? "bg-primary/10 border-l-4 border-l-primary shadow-sm scale-[1.02] segment-pulse" 
                            : "hover:bg-muted/50 hover:shadow-sm hover:scale-[1.01]"
                        }`}
                        onClick={() => handleSegmentClick(segment)} // Use the new handler here
                      >
                        <div className="flex items-center justify-between mb-2">
                          <span className={`text-xs font-medium transition-colors ${
                            selectedSegmentId === segment.id ? "text-primary" : "text-muted-foreground"
                          }`}>
                            {formatTime(segment.start)} - {formatTime(segment.end)}
                          </span>
                          <div className="flex items-center gap-2">
                            {/* Play icon that appears on hover */}
                            <svg 
                              className={`w-3 h-3 transition-all duration-200 ${
                                selectedSegmentId === segment.id 
                                  ? "opacity-100 text-primary" 
                                  : "opacity-0 group-hover:opacity-100 text-muted-foreground"
                              }`}
                              fill="currentColor" 
                              viewBox="0 0 24 24"
                            >
                              <path d="M8 5v14l11-7z"/>
                            </svg>
                            <div className={`w-2 h-2 rounded-full transition-all duration-300 ${
                              selectedSegmentId === segment.id 
                                ? "bg-primary animate-pulse" 
                                : "bg-transparent"
                            }`} />
                          </div>
                        </div>
                        <p className="leading-relaxed">
                          {segment.words && segment.words.length > 0 ? (
                            segment.words.map((word, idx) => (
                              <span
                                key={`${segment.id}-${idx}`}
                                onClick={(e) => {
                                  e.stopPropagation()
                                  handleWordClick(segment.id, idx, word.start)
                                }}
                                className={`cursor-pointer inline-block thai-text transition-all duration-200 mx-0.5 px-1 py-0.5 rounded ${
                                  activeWordIndex?.segmentId === segment.id && activeWordIndex?.wordIndex === idx
                                    ? "bg-primary text-primary-foreground shadow-md transform scale-105 word-active"
                                    : selectedSegmentId === segment.id
                                    ? "hover:bg-primary/20 hover:scale-105 hover:shadow-sm"
                                    : "hover:bg-muted hover:scale-105"
                                }`}
                                title={`Confidence: ${formatConfidence(word.confidence)} | Click to play`}
                                style={{
                                  animationDelay: activeWordIndex?.segmentId === segment.id && activeWordIndex?.wordIndex === idx 
                                    ? '0ms' 
                                    : `${idx * 50}ms`
                                }}
                              >
                                {word.text}
                              </span>
                            ))
                          ) : (
                            <span className="thai-text">{segment.text}</span>
                          )}
                        </p>
                        
                        {/* Progress bar for active segment */}
                        {selectedSegmentId === segment.id && (
                          <div className="mt-2 w-full bg-muted h-1 rounded-full overflow-hidden">
                            <div 
                              className="h-full bg-primary transition-all duration-300 ease-out rounded-full"
                              style={{
                                width: audioRef.current 
                                  ? `${Math.min(100, Math.max(0, 
                                      ((audioRef.current.currentTime - segment.start) / (segment.end - segment.start)) * 100
                                    ))}%`
                                  : '0%'
                              }}
                            />
                          </div>
                        )}
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

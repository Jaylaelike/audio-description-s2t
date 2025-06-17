import { type NextRequest, NextResponse } from "next/server"
import prisma from "@/lib/prisma"
import { writeFile } from "fs/promises"
import { join } from "path"
import { mkdir } from "fs/promises"
import { v4 as uuidv4 } from "uuid"

// Queue-based transcription service URL
const TRANSCRIPTION_SERVICE_URL = "http://localhost:8002"

// Configure API route for long-running operations 20 minutes 
export const maxDuration =  20 * 60 // 20 minutes in seconds
export const dynamic = 'force-dynamic'

// Alternative fetch function to handle long-running requests
async function fetchWithCustomTimeout(url: string, options: any, timeoutMs: number) {
  try {
    return await fetch(url, {
      ...options,
      signal: AbortSignal.timeout(timeoutMs),
      // @ts-ignore - Undici-specific options for Node.js
      headersTimeout: 0,
      bodyTimeout: 0,
      keepAlive: true,
    })
  } catch (error) {
    if (error instanceof Error && (
      error.name === 'HeadersTimeoutError' || 
      error.message.includes('UND_ERR_HEADERS_TIMEOUT')
    )) {
      console.log('Headers timeout detected, retrying with different approach...')
      // Fallback: try again with no timeout restrictions
      return await fetch(url, {
        method: options.method,
        body: options.body,
        // No signal, no timeouts - let it run as long as needed
      })
    }
    throw error
  }
}

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData()

    const title = formData.get("title") as string
    const description = formData.get("description") as string | null
    const language = formData.get("language") as string || "th"
    const priority = parseInt(formData.get("priority") as string || "0")
    const audioFile = formData.get("audioFile") as File

    if (!title || !audioFile) {
      return NextResponse.json({ error: "Title and audio file are required" }, { status: 400 })
    }

    // Create directories if they don't exist
    const audioDir = join(process.cwd(), "public", "uploads", "audio")
    await mkdir(audioDir, { recursive: true })

    // Generate unique filenames
    const audioFileName = `${uuidv4()}-${audioFile.name}`
    const audioPath = join(audioDir, audioFileName)

    // Save audio file
    const audioBuffer = Buffer.from(await audioFile.arrayBuffer())
    await writeFile(audioPath, audioBuffer)

    // Create transcription job in database with pending status
    const transcriptionJob = await prisma.transcriptionJob.create({
      data: {
        title,
        description,
        originalAudioFileName: audioFileName,
        status: "pending",
      },
    })

    // Create form data for the queue-based transcription service
    const transcriptionFormData = new FormData()
    transcriptionFormData.append("file", new Blob([audioBuffer], { type: audioFile.type }), audioFile.name)
    transcriptionFormData.append("language", language)

    // Process transcription asynchronously using queue with priority
    processTranscriptionQueue(transcriptionJob.id, transcriptionFormData, priority).catch(error => {
      console.error(`Background transcription failed for job ${transcriptionJob.id}:`, error)
    })

    return NextResponse.json({
      success: true,
      transcriptionId: transcriptionJob.id,
      message: "Transcription job queued successfully"
    })

  } catch (error) {
    console.error("Error creating transcription job:", error)
    return NextResponse.json(
      { error: "Failed to create transcription job" },
      { status: 500 }
    )
  }
}

async function processTranscriptionQueue(transcriptionId: string, transcriptionFormData: FormData, priority: number = 0) {
  try {
    // Set job status to processing
    await prisma.transcriptionJob.update({
      where: { id: transcriptionId },
      data: { status: "processing" },
    })

    // Submit to queue-based transcription service with priority  
    console.log(`Submitting to queue-based transcription service: ${TRANSCRIPTION_SERVICE_URL}/tasks/transcription (priority: ${priority})`)
    
    // Add priority to form data
    transcriptionFormData.append("priority", priority.toString())
    
    const queueResponse = await fetch(`${TRANSCRIPTION_SERVICE_URL}/tasks/transcription`, {
      method: "POST",
      body: transcriptionFormData,
    })

    if (!queueResponse.ok) {
      throw new Error(`Transcription queue service returned ${queueResponse.status}`)
    }

    const queueResult = await queueResponse.json()
    const taskId = queueResult.task_id

    console.log(`Task queued with ID: ${taskId}`)

    // Poll for completion
    await pollTranscriptionCompletion(transcriptionId, taskId)

  } catch (error) {
    console.error("Error in transcription queue:", error)
    
    let errorMessage = "Unknown error"
    if (error instanceof Error) {
      errorMessage = error.message
    }

    // Update job status to failed
    await prisma.transcriptionJob.update({
      where: { id: transcriptionId },
      data: {
        status: "failed",
        transcriptionResultJson: { error: errorMessage }
      },
    })
  }
}

async function pollTranscriptionCompletion(transcriptionId: string, taskId: string) {
  const maxAttempts = 60 // 60 attempts * 10 seconds = 10 minutes max polling
  let attempts = 0

  while (attempts < maxAttempts) {
    try {
      attempts++
      
      const statusResponse = await fetch(`${TRANSCRIPTION_SERVICE_URL}/tasks/${taskId}`)
      
      if (!statusResponse.ok) {
        throw new Error(`Status check failed: ${statusResponse.status}`)
      }

      const statusData = await statusResponse.json()
      console.log(`Task ${taskId} status: ${statusData.status}, progress: ${statusData.progress}`)

      if (statusData.status === 'completed') {
        // Transcription completed successfully
        await prisma.transcriptionJob.update({
          where: { id: transcriptionId },
          data: {
            status: "completed",
            transcriptionResultJson: statusData.result,
          },
        })
        
        console.log(`Transcription completed for job: ${transcriptionId}`)
        
        // Auto trigger risk detection
        await triggerAutoRiskDetection(transcriptionId, statusData.result)
        
        return

      } else if (statusData.status === 'failed') {
        // Transcription failed
        throw new Error(statusData.error_message || 'Transcription failed')

      } else if (statusData.status === 'processing') {
        // Still processing, continue polling
        await new Promise(resolve => setTimeout(resolve, 10000)) // Wait 10 seconds
        continue

      } else if (statusData.status === 'queued') {
        // Still in queue, continue polling
        await new Promise(resolve => setTimeout(resolve, 5000)) // Wait 5 seconds
        continue
      }

    } catch (error) {
      console.error(`Error polling transcription status (attempt ${attempts}):`, error)
      
      if (attempts >= maxAttempts) {
        throw error
      }
      
      // Wait before retrying
      await new Promise(resolve => setTimeout(resolve, 10000))
    }
  }

  // If we get here, polling timed out
  throw new Error('Transcription polling timed out')
}

async function triggerAutoRiskDetection(transcriptionId: string, transcriptionResult: any) {
  try {
    // Extract text from transcription result
    const text = transcriptionResult.text || ""
    
    if (!text.trim()) {
      console.log(`No text found in transcription ${transcriptionId}, skipping risk detection`)
      return
    }

    console.log(`Starting auto risk detection for transcription: ${transcriptionId}`)
    
    // Update risk detection status to analyzing
    await prisma.transcriptionJob.update({
      where: { id: transcriptionId },
      data: { 
        // @ts-ignore - Temporary until types are updated
        riskDetectionStatus: 'analyzing' 
      }
    })

    // Submit to backend risk detection queue with priority 0 (normal) for auto-analysis
    const riskDetectionResponse = await fetch(`${TRANSCRIPTION_SERVICE_URL}/tasks/risk-detection`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        transcription_id: transcriptionId,
        text: text,
        priority: 0
      }),
    })

    if (!riskDetectionResponse.ok) {
      throw new Error(`Risk detection queue service returned ${riskDetectionResponse.status}`)
    }

    const riskQueueResult = await riskDetectionResponse.json()
    const riskTaskId = riskQueueResult.task_id

    console.log(`Risk detection task queued with ID: ${riskTaskId}`)

    // Poll for risk detection completion
    await pollRiskDetectionCompletion(transcriptionId, riskTaskId)

  } catch (error) {
    console.error(`Error in auto risk detection for ${transcriptionId}:`, error)
    
    // Update risk detection status to failed
    await prisma.transcriptionJob.update({
      where: { id: transcriptionId },
      data: { 
        // @ts-ignore - Temporary until types are updated
        riskDetectionStatus: 'failed',
        riskDetectionResponse: error instanceof Error ? error.message : 'Unknown error'
      }
    })
  }
}

async function pollRiskDetectionCompletion(transcriptionId: string, taskId: string) {
  const maxAttempts = 30 // 30 attempts * 5 seconds = 2.5 minutes max polling
  let attempts = 0

  while (attempts < maxAttempts) {
    try {
      attempts++
      
      const statusResponse = await fetch(`${TRANSCRIPTION_SERVICE_URL}/tasks/${taskId}`)
      
      if (!statusResponse.ok) {
        throw new Error(`Risk detection status check failed: ${statusResponse.status}`)
      }

      const statusData = await statusResponse.json()
      console.log(`Risk detection task ${taskId} status: ${statusData.status}, progress: ${statusData.progress}`)

      if (statusData.status === 'completed') {
        // Risk detection completed successfully
        const result = statusData.result
        
        await prisma.transcriptionJob.update({
          where: { id: transcriptionId },
          data: {
            // @ts-ignore - Temporary until types are updated
            riskDetectionStatus: 'completed',
            riskDetectionResult: result.risk_result,
            riskDetectionResponse: result.ollama_response,
            riskAnalyzedAt: new Date()
          },
        })
        
        console.log(`Risk detection completed for transcription: ${transcriptionId} - Result: ${result.risk_result}`)
        return

      } else if (statusData.status === 'failed') {
        // Risk detection failed
        throw new Error(statusData.error_message || 'Risk detection failed')

      } else if (statusData.status === 'processing' || statusData.status === 'queued') {
        // Still processing/queued, continue polling
        await new Promise(resolve => setTimeout(resolve, 5000)) // Wait 5 seconds
        continue
      }

    } catch (error) {
      console.error(`Error polling risk detection status (attempt ${attempts}):`, error)
      
      if (attempts >= maxAttempts) {
        throw error
      }
      
      // Wait before retrying
      await new Promise(resolve => setTimeout(resolve, 5000))
    }
  }

  // If we get here, polling timed out
  throw new Error('Risk detection polling timed out')
}

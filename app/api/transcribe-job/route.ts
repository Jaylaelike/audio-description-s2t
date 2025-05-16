import { type NextRequest, NextResponse } from "next/server"
import prisma from "@/lib/prisma"
import { writeFile } from "fs/promises"
import { join } from "path"
import { mkdir } from "fs/promises"
import { v4 as uuidv4 } from "uuid"

// Transcription service URL
const TRANSCRIPTION_SERVICE_URL = "http://localhost:8000/transcribe/"

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData()

    const title = formData.get("title") as string
    const description = formData.get("description") as string | null
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

    // Prepare form data for the transcription service
    const transcriptionFormData = new FormData()
    transcriptionFormData.append("file", audioFile)

    try {
      // Set job status to processing
      await prisma.transcriptionJob.update({
        where: { id: transcriptionJob.id },
        data: { status: "processing" },
      })

      // Send audio file to transcription service
      console.log(`Sending audio file to transcription service: ${TRANSCRIPTION_SERVICE_URL}`)
      const transcriptionResponse = await fetch(TRANSCRIPTION_SERVICE_URL, {
        method: "POST",
        body: transcriptionFormData,
      })

      if (!transcriptionResponse.ok) {
        throw new Error(
          `Transcription service returned ${transcriptionResponse.status}: ${transcriptionResponse.statusText}`,
        )
      }

      // Get the transcription result
      const transcriptionResult = await transcriptionResponse.json()

      // Update the job with the transcription result
      await prisma.transcriptionJob.update({
        where: { id: transcriptionJob.id },
        data: {
          status: "completed",
          transcriptionResultJson: transcriptionResult,
        },
      })

      console.log(`Transcription completed for job: ${transcriptionJob.id}`)
    } catch (error) {
      console.error("Error processing transcription:", error)

      // Update job status to failed
      await prisma.transcriptionJob.update({
        where: { id: transcriptionJob.id },
        data: {
          status: "failed",
        },
      })

      // Don't throw here - we still want to return the job ID
      console.error(`Transcription failed for job: ${transcriptionJob.id}`)
    }

    return NextResponse.json({
      success: true,
      message: "Transcription job created",
      jobId: transcriptionJob.id,
    })
  } catch (error) {
    console.error("Error creating transcription job:", error)
    return NextResponse.json({ error: "Failed to create transcription job" }, { status: 500 })
  }
}

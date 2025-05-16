import { NextResponse } from "next/server"
import prisma from "@/lib/prisma"

export async function GET(request: Request, { params }: { params: { id: string } }) {
  try {
    const transcription = await prisma.transcriptionJob.findUnique({
      where: {
        id: params.id,
      },
    })

    if (!transcription) {
      return NextResponse.json({ error: "Transcription not found" }, { status: 404 })
    }

    return NextResponse.json(transcription)
  } catch (error) {
    console.error("Error fetching transcription:", error)
    return NextResponse.json({ error: "Failed to fetch transcription" }, { status: 500 })
  }
}

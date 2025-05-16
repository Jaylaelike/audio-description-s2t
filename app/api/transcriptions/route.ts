import { NextResponse } from "next/server"
import prisma from "@/lib/prisma"

export async function GET() {
  try {
    const transcriptions = await prisma.transcriptionJob.findMany({
      orderBy: {
        createdAt: "desc",
      },
    })

    return NextResponse.json(transcriptions)
  } catch (error) {
    console.error("Error fetching transcriptions:", error)
    return NextResponse.json({ error: "Failed to fetch transcriptions" }, { status: 500 })
  }
}

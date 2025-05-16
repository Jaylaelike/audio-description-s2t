"use client"

import { TranscriptionDetail } from "@/components/transcription-detail"
import { useParams } from "next/navigation"
import { useQuery } from "@tanstack/react-query"

export default function TranscriptionPage() {
  const params = useParams()
  const id = params.id as string

  const {
    data: transcription,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["transcription", id],
    queryFn: async () => {
      const response = await fetch(`/api/transcriptions/${id}`)
      if (!response.ok) {
        throw new Error("Failed to fetch transcription")
      }
      return response.json()
    },
    refetchInterval: 10000, // Refetch every 10 seconds
  })

  if (isLoading) {
    return <div className="flex justify-center py-10">Loading transcription details...</div>
  }

  if (error) {
    return <div className="text-destructive py-10">Error loading transcription details</div>
  }

  if (!transcription) {
    return <div className="text-destructive py-10">Transcription not found</div>
  }

  return <TranscriptionDetail transcription={transcription} />
}

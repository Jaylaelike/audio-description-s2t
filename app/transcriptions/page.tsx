"use client"

import { TranscriptionsList } from "@/components/transcriptions-list"
import { useQuery } from "@tanstack/react-query"

export default function TranscriptionsPage() {
  const {
    data: transcriptions,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["transcriptions"],
    queryFn: async () => {
      const response = await fetch("/api/transcriptions")
      if (!response.ok) {
        throw new Error("Failed to fetch transcriptions")
      }
      return response.json()
    },
    refetchInterval: 10000, // Refetch every 10 seconds
  })

  if (isLoading) {
    return <div className="flex justify-center py-10">Loading transcriptions...</div>
  }

  if (error) {
    return <div className="text-destructive py-10">Error loading transcriptions</div>
  }

  return (
    <div className="container mx-auto py-6">
      <h1 className="text-3xl font-bold mb-6">Transcriptions</h1>
      <TranscriptionsList transcriptions={transcriptions} />
    </div>
  )
}

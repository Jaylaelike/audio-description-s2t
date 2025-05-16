import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import Link from "next/link"
import { ArrowRight, FileAudio, ListMusic } from "lucide-react"

export default function Home() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[calc(100vh-120px)]">
      <Card className="w-full max-w-2xl">
        <CardHeader className="text-center">
          <CardTitle className="text-3xl">RRS Audio Transcriber</CardTitle>
          <CardDescription>Upload your audio files and get accurate transcriptions</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Link href="/upload" className="w-full">
              <Button variant="outline" className="w-full h-32 flex flex-col gap-2">
                <FileAudio className="h-8 w-8" />
                <span>Upload Audio</span>
              </Button>
            </Link>
            <Link href="/transcriptions" className="w-full">
              <Button variant="outline" className="w-full h-32 flex flex-col gap-2">
                <ListMusic className="h-8 w-8" />
                <span>View Transcriptions</span>
              </Button>
            </Link>
          </div>
          <Link href="/upload">
            <Button className="w-full">
              Get Started
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </Link>
        </CardContent>
      </Card>
    </div>
  )
}

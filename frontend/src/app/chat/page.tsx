"use client";

import { useRouter } from "next/navigation";
import { GitBranch, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AppShell } from "@/components/layout/app-shell";

export default function ChatRedirectPage() {
  const router = useRouter();

  return (
    <AppShell>
      <div className="flex items-center justify-center min-h-[calc(100vh-8rem)]">
        <div className="text-center space-y-6 max-w-md">
          <div className="flex justify-center">
            <div className="rounded-full bg-muted p-6">
              <GitBranch className="h-12 w-12 text-muted-foreground" />
            </div>
          </div>
          
          <div className="space-y-2">
            <h1 className="text-2xl font-bold">Select a Repository First</h1>
            <p className="text-muted-foreground">
              Chat is available for individual repositories. Please select a repository from the dashboard to start chatting.
            </p>
          </div>

          <Button 
            onClick={() => router.push("/")}
            className="gap-2"
          >
            Go to Dashboard
            <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </AppShell>
  );
}
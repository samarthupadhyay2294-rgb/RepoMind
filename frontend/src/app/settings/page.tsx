"use client";

import { AppShell } from "@/components/layout/app-shell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

export default function SettingsPage() {
  return (
    <AppShell>
      <div className="mx-auto max-w-3xl p-6 space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Configure RepoMind.
          </p>
        </div>
        <Separator />
        <Card>
          <CardHeader>
            <CardTitle className="text-base">About</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              RepoMind uses AI to analyze your repositories and answer questions about
              architecture, dependencies, and code structure.
            </p>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}

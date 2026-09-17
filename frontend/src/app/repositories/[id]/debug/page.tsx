"use client";

import { useRef, useState, type FormEvent } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Bug, Loader2 } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { ApiError, createInvestigation } from "@/lib/api";
import { buildInvestigationInput } from "@/lib/debug-form";
import type { Investigation } from "@/lib/debug-types";

const PHASES = ["Understanding", "Searching", "Inspecting", "Evaluating", "Reporting"];

function VerdictBadge({ verdict }: { verdict: Investigation["verdict"] }) {
  if (!verdict) return <Badge variant="outline">no verdict</Badge>;
  const variant = verdict === "confirmed" ? "default" : verdict === "likely" ? "secondary" : "outline";
  return <Badge variant={variant}>{verdict}</Badge>;
}

export default function DebugPage() {
  const params = useParams();
  const id = params.id as string;

  const [errorText, setErrorText] = useState("");
  const [filePath, setFilePath] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<Investigation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [disabled, setDisabled] = useState(false);
  const errorRef = useRef<HTMLTextAreaElement>(null);

  async function handleStart(e?: FormEvent) {
    e?.preventDefault();
    if (running) return;
    if (!errorText.trim()) {
      setValidationError("Paste an error to start the investigation.");
      errorRef.current?.focus();
      return;
    }
    setValidationError(null);
    setRunning(true);
    setError(null);
    setDisabled(false);
    setResult(null);
    try {
      const inv = await createInvestigation(
        id,
        buildInvestigationInput(errorText, filePath),
      );
      setResult(inv);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.code === "INVESTIGATION_DISABLED") {
        setDisabled(true);
      } else {
        setError(err instanceof Error ? err.message : "Investigation failed.");
      }
    } finally {
      setRunning(false);
    }
  }

  return (
    <AppShell>
      <div className="mx-auto max-w-3xl p-6 space-y-6">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Link href={`/repositories/${id}`} className="hover:text-foreground">
            Repository
          </Link>
          <span>/</span>
          <span className="text-foreground font-medium">Debug an issue</span>
        </div>

        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <Bug className="h-6 w-6" /> Debug an issue
        </h1>
        <p className="text-sm text-muted-foreground">
          Paste an error and optionally tell RepoMind where it happens.
        </p>

        {disabled && (
          <Card role="alert">
            <CardContent className="pt-6 text-sm">
              The debug investigator is disabled for this deployment. Chat and retrieval remain available.
            </CardContent>
          </Card>
        )}
        {error && (
          <Card role="alert">
            <CardContent className="pt-6 text-sm">
              {error}
              <Button variant="outline" size="sm" className="ml-2" onClick={() => handleStart()}>
                Retry
              </Button>
            </CardContent>
          </Card>
        )}

        <Card>
          <CardContent className="pt-6">
            <form onSubmit={handleStart} className="space-y-4">
              <p className="text-xs text-muted-foreground">
                Do not paste passwords, API keys, or tokens.
              </p>
              <div className="space-y-1.5">
                <Label htmlFor="dbg-error">Paste the error</Label>
                <Textarea
                  id="dbg-error"
                  ref={errorRef}
                  value={errorText}
                  onChange={(e) => setErrorText(e.target.value)}
                  placeholder="Example: 401 Unauthorized when signing in"
                  rows={5}
                  required
                  aria-invalid={validationError ? true : undefined}
                  aria-describedby={validationError ? "dbg-error-hint" : undefined}
                />
                {validationError && (
                  <p id="dbg-error-hint" role="alert" className="text-xs text-destructive">
                    {validationError}
                  </p>
                )}
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="dbg-file">File name or path (optional)</Label>
                <Input
                  id="dbg-file"
                  value={filePath}
                  onChange={(e) => setFilePath(e.target.value)}
                  placeholder="Example: backend/app/auth.py"
                  autoComplete="off"
                />
              </div>
              <Button type="submit" disabled={running}>
                {running && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {running ? "Investigating…" : "Investigate"}
              </Button>
            </form>
          </CardContent>
        </Card>

        {running && (
          <Card role="status" aria-live="polite">
            <CardContent className="pt-6">
              <ol className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                {PHASES.map((p) => (
                  <li key={p} className="border rounded px-2 py-1">
                    {p}…
                  </li>
                ))}
              </ol>
              <p className="text-xs text-muted-foreground mt-2">
                Running a bounded evidence-first investigation. Progress reflects real backend work, not a timer.
              </p>
            </CardContent>
          </Card>
        )}

        {result && (
          <div className="space-y-4" aria-live="polite">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 flex-wrap">
                  Verdict: <VerdictBadge verdict={result.verdict} />
                  {result.confidence && (
                    <span className="text-xs font-normal text-muted-foreground">
                      confidence: {result.confidence}
                    </span>
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent className="text-sm space-y-2">
                <p>{result.summary || "No summary produced."}</p>
                <p className="text-xs text-muted-foreground">
                  snapshot {result.snapshot_id.slice(0, 8)}
                  {result.snapshot_active ? " (active)" : " (pinned)"} · stop:{" "}
                  {result.stop_reason || "unknown"} · {result.tool_calls} tool calls ·{" "}
                  {result.llm_calls} LLM calls · {Math.round(result.duration_ms)}ms
                  {result.evidence_truncated ? " · evidence truncated" : ""}
                </p>
              </CardContent>
            </Card>

            {result.findings.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Findings</CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="text-sm space-y-2">
                    {result.findings.map((f, i) => (
                      <li key={i}>
                        <p>
                          <Badge variant="outline" className="mr-2">
                            {f.confidence}
                          </Badge>
                          {f.claim}
                        </p>
                        {f.evidence_refs.length > 0 && (
                          <p className="font-mono text-xs text-muted-foreground mt-1">
                            {f.evidence_refs.join(", ")}
                          </p>
                        )}
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}

            {result.next_steps.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Next steps</CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="text-sm space-y-1 list-disc ml-5">
                    {result.next_steps.map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}

            <Card>
              <CardHeader>
                <CardTitle>Evidence & citations</CardTitle>
              </CardHeader>
              <CardContent>
                {result.citations.length === 0 && (
                  <p className="text-sm text-muted-foreground">
                    No validated citations — treat all claims as unresolved hypotheses.
                  </p>
                )}
                <ul className="text-sm space-y-1">
                  {result.citations.map((c, i) => (
                    <li key={i} className="font-mono text-xs">
                      {c.file_path}:{c.start_line}-{c.end_line}
                      {c.reason && <span className="text-muted-foreground"> — {c.reason}</span>}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>

            {result.actions.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Investigation trail</CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="text-xs space-y-1 max-h-48 overflow-auto">
                    {result.actions.map((a) => (
                      <li key={a.sequence}>
                        <span className="font-mono">{a.tool}</span> —{" "}
                        {a.ok ? `${a.result_count} result(s)` : `failed (${a.warning || "error"})`} ·{" "}
                        {Math.round(a.duration_ms)}ms
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}

            {result.limitations.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Limitations</CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="text-sm space-y-1 list-disc ml-5">
                    {result.limitations.map((l, i) => (
                      <li key={i}>{l}</li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}

            <Separator />
            <div className="flex gap-3 text-sm">
              <Link href={`/repositories/${id}/graph`} className="underline">
                Open dependency graph
              </Link>
              <Link href={`/repositories/${id}/chat`} className="underline">
                Ask follow-up in chat
              </Link>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}

import type { InvestigationInput } from "./debug-types";

export function buildInvestigationInput(
  errorText: string,
  filePath: string,
): InvestigationInput {
  const input: InvestigationInput = { error_text: errorText.trim() };
  const file = filePath.trim();
  // The API has no dedicated file field; affected_route is the supported
  // optional "where it happens" slot and is redacted server-side.
  if (file) {
    input.affected_route = file;
  }
  return input;
}

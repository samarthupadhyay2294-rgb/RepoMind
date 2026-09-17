import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  classifyIndexingFailure,
  isRetryEnabled,
  parseErrorCode,
  stripErrorCode,
} from "./indexing-error-state.ts";

describe("parseErrorCode", () => {
  it("extracts a leading code", () => {
    assert.equal(
      parseErrorCode("[EMBEDDING_NOT_CONFIGURED] MISTRAL_API_KEY is not configured."),
      "EMBEDDING_NOT_CONFIGURED",
    );
  });

  it("returns null without a code", () => {
    assert.equal(parseErrorCode("plain failure"), null);
    assert.equal(parseErrorCode(null), null);
    assert.equal(parseErrorCode(undefined), null);
  });
});

describe("stripErrorCode", () => {
  it("removes the prefix only", () => {
    assert.equal(
      stripErrorCode("[EMBEDDING_AUTH_FAILED] bad key"),
      "bad key",
    );
  });
});

describe("classifyIndexingFailure", () => {
  it("missing provider when backend still unconfigured", () => {
    assert.equal(
      classifyIndexingFailure("[EMBEDDING_NOT_CONFIGURED] MISTRAL_API_KEY is not configured.", false),
      "not_configured",
    );
    assert.equal(
      classifyIndexingFailure("[EMBEDDING_NOT_CONFIGURED] MISTRAL_API_KEY is not configured.", null),
      "not_configured",
    );
  });

  it("stale failure when diagnostics report configured", () => {
    assert.equal(
      classifyIndexingFailure("[EMBEDDING_NOT_CONFIGURED] MISTRAL_API_KEY is not configured.", true),
      "stale_not_configured",
    );
  });

  it("invalid key", () => {
    assert.equal(
      classifyIndexingFailure("[EMBEDDING_AUTH_FAILED] rejected", true),
      "auth_failed",
    );
  });

  it("provider unreachable", () => {
    assert.equal(
      classifyIndexingFailure("[EMBEDDING_PROVIDER_UNAVAILABLE] down", true),
      "provider_unreachable",
    );
    assert.equal(
      classifyIndexingFailure("[EMBEDDING_PROVIDER_ERROR] boom", true),
      "provider_unreachable",
    );
  });

  it("generic failure", () => {
    assert.equal(classifyIndexingFailure("boom", true), "generic");
    assert.equal(classifyIndexingFailure(null, true), null);
  });
});

describe("isRetryEnabled", () => {
  it("re-enables retry for missing provider once configured", () => {
    assert.equal(isRetryEnabled("not_configured", true), true);
    assert.equal(isRetryEnabled("not_configured", false), false);
    assert.equal(isRetryEnabled("not_configured", null), false);
  });

  it("stale failures always allow retry", () => {
    assert.equal(isRetryEnabled("stale_not_configured", true), true);
  });

  it("auth/provider failures allow retry", () => {
    assert.equal(isRetryEnabled("auth_failed", true), true);
    assert.equal(isRetryEnabled("provider_unreachable", false), true);
    assert.equal(isRetryEnabled("generic", null), true);
  });

  it("busy disables retry", () => {
    assert.equal(isRetryEnabled("generic", null, true), false);
  });
});

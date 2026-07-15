import { describe, expect, it } from "vitest";
import { doctor } from "../src/doctor.js";

describe("doctor", () => {
  it("reports missing uvx with install hint", async () => {
    const result = await doctor("definitely-not-a-real-binary-xyz");
    expect(result.uvxAvailable).toBe(false);
    expect(result.hint).toMatch(/uv/);
  });
});

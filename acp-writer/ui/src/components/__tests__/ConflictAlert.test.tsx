import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConflictAlert } from "../ConflictAlert";

describe("ConflictAlert", () => {
  it("renders description with a severity-mapped variant", () => {
    const { container } = render(
      <ConflictAlert conflict={{ id: "c1", severity: "critical", description: "Renal dosing conflict" }} />,
    );
    expect(screen.getByText("Renal dosing conflict")).toBeInTheDocument();
    expect(container.querySelector(".pf-m-danger")).toBeTruthy();
  });

  it("defaults to a warning variant when severity is absent", () => {
    const { container } = render(
      <ConflictAlert conflict={{ id: "c2", description: "Overlapping recommendation" }} />,
    );
    expect(container.querySelector(".pf-m-warning")).toBeTruthy();
  });

  it("varies the title by category", () => {
    render(
      <ConflictAlert
        conflict={{ id: "c3", category: "divergent_target", description: "Different BP targets" }}
      />,
    );
    expect(screen.getByText(/Conflicting goal targets/)).toBeInTheDocument();
  });

  it("uses the overlap title", () => {
    render(<ConflictAlert conflict={{ id: "c3b", category: "overlap", description: "x" }} />);
    expect(screen.getByText(/Overlapping activities/)).toBeInTheDocument();
  });

  it("falls back to a generic title for an unknown category", () => {
    render(<ConflictAlert conflict={{ id: "c4", description: "Something" }} />);
    expect(screen.getByText(/Recommendation conflict/)).toBeInTheDocument();
  });

  it("lists the source CPGs on a From line, de-duplicated", () => {
    render(
      <ConflictAlert
        conflict={{
          id: "c5",
          category: "contradiction",
          description: "Conflicting advice",
          sources: [
            { cpgId: "SYN-HTN-2026-001", recommendationId: "rec-1" },
            { cpgId: "SYN-HTN-2026-001", recommendationId: "rec-3" },
            { cpgId: "SYN-DM2-2026-001", recommendationId: "rec-2" },
          ],
        }}
      />,
    );
    expect(screen.getByText(/SYN-HTN-2026-001 · SYN-DM2-2026-001/)).toBeInTheDocument();
  });

  it("omits the From line when there are no sources", () => {
    render(<ConflictAlert conflict={{ id: "c7", description: "no sources" }} />);
    expect(screen.queryByText(/From:/)).not.toBeInTheDocument();
  });
});

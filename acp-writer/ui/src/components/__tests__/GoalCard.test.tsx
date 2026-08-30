import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { GoalCard } from "../GoalCard";

describe("GoalCard", () => {
  it("renders description, rationale, target, and sources", () => {
    render(
      <GoalCard
        goal={{
          id: "g1",
          description: "Achieve HbA1c < 7%",
          rationale: "Glycemic control per ADA 2024",
          target: "HbA1c < 7 %",
          sourceCpgId: "ada-2024",
          sourceRecommendationId: "rec-1",
        }}
      />,
    );
    expect(screen.getByText("Achieve HbA1c < 7%")).toBeInTheDocument();
    expect(screen.getByText("Glycemic control per ADA 2024")).toBeInTheDocument();
    expect(screen.getByText("HbA1c < 7 %")).toBeInTheDocument();
    expect(screen.getByText("ada-2024")).toBeInTheDocument();
    expect(screen.getByText("rec-1")).toBeInTheDocument();
  });

  it("renders only the description when no provenance is present", () => {
    render(<GoalCard goal={{ id: "g2", description: "Bare goal" }} />);
    expect(screen.getByText("Bare goal")).toBeInTheDocument();
    expect(screen.queryByText("Target")).not.toBeInTheDocument();
  });
});

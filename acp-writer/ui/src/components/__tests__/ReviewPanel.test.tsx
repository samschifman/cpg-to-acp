import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReviewPanel } from "../ReviewPanel";
import { carePlanView } from "@app/mocks/fixtures";

describe("ReviewPanel", () => {
  it("submits an approve decision", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<ReviewPanel carePlan={carePlanView} onSubmit={onSubmit} />);
    await userEvent.click(screen.getByRole("button", { name: /approve/i }));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ decision: "approve" }));
  });

  it("submits request_changes with a comment", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<ReviewPanel carePlan={carePlanView} onSubmit={onSubmit} />);
    await userEvent.click(screen.getByRole("button", { name: /request changes/i }));
    await userEvent.type(screen.getByLabelText(/overall comment/i), "Tighten the HbA1c target");
    await userEvent.click(screen.getByRole("button", { name: /submit changes/i }));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ decision: "request_changes", comment: "Tighten the HbA1c target" }),
    );
  });

  it("shows a persistent acknowledgment and hides the buttons after submit", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<ReviewPanel carePlan={carePlanView} onSubmit={onSubmit} />);
    await userEvent.click(screen.getByRole("button", { name: /approve/i }));
    expect(await screen.findByText(/review submitted/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /request changes/i })).not.toBeInTheDocument();
  });

  it("surfaces the server error and re-enables the buttons on a failed submit", async () => {
    const onSubmit = vi
      .fn()
      .mockRejectedValue(new Error("Workflow engine temporarily unavailable — please try again."));
    render(<ReviewPanel carePlan={carePlanView} onSubmit={onSubmit} />);
    await userEvent.click(screen.getByRole("button", { name: /approve/i }));
    expect(await screen.findByText(/temporarily unavailable/i)).toBeInTheDocument();
    const approve = screen.getByRole("button", { name: /approve/i });
    expect(approve).toBeEnabled();
  });

  it("disables the button while a submit is in flight", async () => {
    let resolve: () => void = () => {};
    const onSubmit = vi.fn(() => new Promise<void>((r) => { resolve = r; }));
    render(<ReviewPanel carePlan={carePlanView} onSubmit={onSubmit} />);
    await userEvent.click(screen.getByRole("button", { name: /approve/i }));
    expect(screen.getByRole("button", { name: /approve/i })).toBeDisabled();
    resolve();
    expect(await screen.findByText(/review submitted/i)).toBeInTheDocument();
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });
});

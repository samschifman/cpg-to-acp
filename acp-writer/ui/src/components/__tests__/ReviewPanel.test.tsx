import { describe, it, expect, vi } from "vitest";
import { render, screen, act, fireEvent } from "@testing-library/react";
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

  it("binds the submission to the review round on screen", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<ReviewPanel carePlan={carePlanView} reviewIteration={2} onSubmit={onSubmit} />);
    await userEvent.click(screen.getByRole("button", { name: /approve/i }));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ decision: "approve", reviewRound: 2 }),
    );
  });

  it("offers a retry after ~30s and re-submits the same round-bound action", async () => {
    vi.useFakeTimers();
    try {
      const onSubmit = vi.fn().mockResolvedValue(undefined);
      render(<ReviewPanel carePlan={carePlanView} reviewIteration={1} onSubmit={onSubmit} />);
      // fireEvent (sync) + act flush avoids userEvent's own timer waits clashing
      // with fake timers — this is the fiddly interaction the plan flagged.
      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: /approve/i }));
      });
      expect(screen.getByText(/waiting for the pipeline/i)).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /retry/i })).not.toBeInTheDocument();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(30_000);
      });
      expect(screen.getByText(/you can retry/i)).toBeInTheDocument();

      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: /retry/i }));
      });
      expect(onSubmit).toHaveBeenCalledTimes(2);
      expect(onSubmit).toHaveBeenLastCalledWith(
        expect.objectContaining({ decision: "approve", reviewRound: 1 }),
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it("remounts fresh when the round advances (no state bleed across gates)", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const { rerender } = render(
      <ReviewPanel key={0} carePlan={carePlanView} reviewIteration={0} onSubmit={onSubmit} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /approve/i }));
    expect(await screen.findByText(/review submitted/i)).toBeInTheDocument();

    // Round N+1 gate arms: RunDetailPage keys the panel by reviewIteration, so a
    // new key remounts a fresh idle panel — round N's submitted state is gone.
    rerender(
      <ReviewPanel key={1} carePlan={carePlanView} reviewIteration={1} onSubmit={onSubmit} />,
    );
    expect(screen.getByRole("button", { name: /approve/i })).toBeInTheDocument();
    expect(screen.queryByText(/review submitted/i)).not.toBeInTheDocument();
  });
});

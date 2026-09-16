import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Gallery } from "./Gallery";

describe("theme gallery", () => {
  it("renders seeded review states without a provider", () => {
    render(<Gallery />);
    expect(screen.getByRole("heading", { name: "Harpy theme gallery" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Changes" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Unified diff" })).toBeInTheDocument();
    expect(screen.getByText("Your edit")).toBeInTheDocument();
    expect(screen.getByText("Current shared value")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("GitHub credentials are not provisioned");
    expect(screen.getByText("None found within assessed context.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start analysis" })).toBeDisabled();
    expect(screen.getByRole("group", { name: "Theme" })).toBeInTheDocument();
  });
});

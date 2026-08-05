import type {
  CarePlanSummary,
  CarePlanStatusUpdate,
  ServiceStatus,
} from "@cpg-to-acp/ui-shared";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new ApiError(res.status, text);
  }
  return res.json();
}

export async function generateCarePlan(
  ipsBundle: Record<string, unknown>,
): Promise<{ run_id: string; careplan_id?: string }> {
  return request("/api/v1/careplans", {
    method: "POST",
    body: JSON.stringify(ipsBundle),
  });
}

export async function listCarePlans(filters?: {
  patient?: string;
  status?: string;
}): Promise<CarePlanSummary[]> {
  const params = new URLSearchParams();
  if (filters?.patient) params.set("patient", filters.patient);
  if (filters?.status) params.set("status", filters.status);
  const qs = params.toString();
  return request(`/api/v1/careplans${qs ? `?${qs}` : ""}`);
}

export async function getCarePlan(
  id: string,
): Promise<Record<string, unknown>> {
  return request(`/api/v1/careplans/${id}`);
}

export async function updateCarePlanStatus(
  id: string,
  update: CarePlanStatusUpdate,
): Promise<CarePlanSummary> {
  return request(`/api/v1/careplans/${id}/status`, {
    method: "PUT",
    body: JSON.stringify(update),
  });
}

export async function getSystemStatus(): Promise<ServiceStatus> {
  return request("/api/v1/status");
}

export async function healthCheck(): Promise<{ status: string }> {
  return request("/health");
}

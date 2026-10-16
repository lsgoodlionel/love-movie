export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(detail);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...init.headers,
    },
  });
  if (!response.ok) {
    let detail = "请求失败，请稍后重试";
    try {
      const body = (await response.json()) as { detail?: string | Array<{ msg: string }> };
      detail = Array.isArray(body.detail) ? body.detail[0]?.msg ?? detail : body.detail ?? detail;
    } catch {
      // Only expose the stable client message for malformed upstream responses.
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

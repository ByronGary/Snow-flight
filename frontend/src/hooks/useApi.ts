import { useEffect, useState } from "react";
import { ApiError, apiGet } from "../api/client";

export interface FetchState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
}

/** GET `url` whenever it changes; pass null to skip. Stale requests are aborted. */
export function useApi<T>(url: string | null): FetchState<T> {
  const [state, setState] = useState<FetchState<T> & { url: string | null }>({
    url: null,
    data: null,
    error: null,
    loading: false,
  });

  useEffect(() => {
    if (!url) return;
    const controller = new AbortController();
    setState({ url, data: null, error: null, loading: true });
    apiGet<T>(url, controller.signal).then(
      (data) => setState({ url, data, error: null, loading: false }),
      (e) => {
        if (controller.signal.aborted) return;
        const error = e instanceof ApiError ? e : new ApiError(0, "unknown", String(e));
        setState({ url, data: null, error, loading: false });
      },
    );
    return () => controller.abort();
  }, [url]);

  if (!url) return { data: null, error: null, loading: false };
  // Until the effect runs for a new URL, report loading rather than the previous result.
  if (state.url !== url) return { data: null, error: null, loading: true };
  return { data: state.data, error: state.error, loading: state.loading };
}

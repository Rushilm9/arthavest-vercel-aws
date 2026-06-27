import { useQuery } from "@tanstack/react-query";
import { apiService } from "../services/api";

export function useDispatchStatus(runId?: string | null, enabled: boolean = false) {
  return useQuery({
    queryKey: ["dispatchStatus", runId],
    queryFn: async () => {
      if (!runId) return null;
      return apiService.getDispatchStatus(runId);
    },
    enabled: !!runId && enabled,
    refetchInterval: (query) => {
      // Poll every 5 seconds until complete is true
      const data = query.state.data;
      if (data && data.complete) {
        return false;
      }
      return 5000;
    },
    refetchOnWindowFocus: false,
  });
}

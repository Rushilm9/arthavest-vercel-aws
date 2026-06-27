import { useQuery } from "@tanstack/react-query";
import { apiService } from "../services/api";

export function useQuota() {
  return useQuery({
    queryKey: ["quota"],
    queryFn: async () => {
      try {
        return await apiService.getQuota();
      } catch (error) {
        console.warn("Quota usage endpoint is not available yet or failed.", error);
        return null;
      }
    },
    refetchInterval: 60000, // Poll every 60 seconds
    refetchOnWindowFocus: false,
  });
}

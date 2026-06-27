import { useQuery } from "@tanstack/react-query";
import { apiService } from "../services/api";
import type { DiscoveryResponse } from "../types";

export function useDiscovery() {
  return useQuery<DiscoveryResponse | null>({
    queryKey: ["discovery"],
    queryFn: async () => {
      try {
        const cachedData = await apiService.discoverCached();
        if (cachedData) return cachedData;
        // Fallback if cache is empty
        const todayData = await apiService.discoverToday();
        return todayData;
      } catch (error: any) {
        // If cached fails or today's discovery returns 404
        if (error.response?.status === 404) {
          try {
             const todayData = await apiService.discoverToday();
             return todayData;
          } catch (e) {
             console.warn("discoverToday fallback failed", e);
             return null;
          }
        }
        console.error("Discovery fetch failed", error);
        return null;
      }
    },
    staleTime: Infinity, // Ensure memory-only cache; no automatic background refetches
    refetchOnWindowFocus: false,
  });
}

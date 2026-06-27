import { useQuery } from "@tanstack/react-query";
import { apiService } from "../services/api";

export function useMarketContext() {
  return useQuery({
    queryKey: ["marketContext"],
    queryFn: async () => {
      try {
        const data = await apiService.getMarketContext();
        if (data) {
          localStorage.setItem("cached_market_context", JSON.stringify(data));
        }
        return data;
      } catch (error) {
        console.warn("Market context endpoint is not available yet or failed.", error);
        const cached = localStorage.getItem("cached_market_context");
        if (cached) {
          try {
            return JSON.parse(cached);
          } catch (e) {
            return null;
          }
        }
        return null;
      }
    },
    staleTime: 60000 * 5, // Stale after 5 minutes
    refetchOnWindowFocus: false,
    initialData: () => {
      const cached = localStorage.getItem("cached_market_context");
      if (cached) {
        try {
          return JSON.parse(cached);
        } catch (e) {
          return undefined;
        }
      }
      return undefined;
    }
  });
}

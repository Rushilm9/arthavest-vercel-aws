import { useQuery } from "@tanstack/react-query";
import { apiService } from "../services/api";

export function useSymbolSearch(q: string) {
  const queryStr = q.trim();
  return useQuery({
    queryKey: ["symbolSearch", queryStr],
    queryFn: async () => {
      if (!queryStr) return [];
      try {
        return await apiService.searchSymbols(queryStr);
      } catch (error) {
        console.warn("Symbol autocomplete search failed", error);
        return [];
      }
    },
    enabled: queryStr.length > 0,
    staleTime: 60000 * 5, // Cache for 5 minutes
    refetchOnWindowFocus: false,
  });
}

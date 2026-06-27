import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { apiService } from "../services/api";
import { StockDetail } from "../components/analysis/StockDetail";
import { Spinner } from "../components/shared/Spinner";
import type { AnalyzeResponse } from "../types";
import { ArrowLeft } from "lucide-react";

export function AnalyseDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<AnalyzeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    apiService.getHistoryDetail(id)
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message || "Failed to load analysis");
        setLoading(false);
      });
  }, [id]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center p-20 space-y-4">
        <Spinner size="lg" />
        <p className="text-sm font-medium text-muted">Fetching analysis record...</p>
      </div>
    );
  }
  
  if (error || !data) {
    return (
      <div className="p-8 text-center bg-red-50 text-red-600 rounded-xl border border-red-100">
        <h3 className="font-bold text-lg mb-2">Error Loading Analysis</h3>
        <p className="text-sm opacity-80">{error || "Analysis not found"}</p>
        <button 
          onClick={() => navigate(-1)} 
          className="mt-6 px-4 py-2 bg-white text-red-600 border border-red-200 hover:bg-red-50 rounded-lg text-sm font-bold shadow-sm transition-colors"
        >
          Go Back
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4 animate-in fade-in duration-300">
      <div className="flex justify-between items-center bg-white p-3 rounded-xl border border-border shadow-sm">
        <button 
          onClick={() => navigate(-1)} 
          className="flex items-center gap-2 text-sm font-bold text-muted hover:text-primary transition-colors hover:bg-neutral-50 px-3 py-1.5 rounded-lg"
        >
          <ArrowLeft size={16} /> Back
        </button>
        <div className="text-xs font-mono font-bold text-muted px-3 py-1 bg-neutral-100 rounded">
          ID: {id}
        </div>
      </div>

      <StockDetail
        data={data}
        isLoading={false}
        isAnalysing={false}
        symbolName={data.symbol || "Unknown"}
      />
    </div>
  );
}

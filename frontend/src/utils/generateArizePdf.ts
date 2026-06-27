import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";

const COLORS = {
  primary: "#0F172A",
  muted: "#475569",
  accent: "#2563EB",
  violet: "#7C3AED",
  emerald: "#059669",
  amber: "#D97706",
  red: "#DC2626",
  border: "#E2E8F0",
  cream: "#F8FAFC",
};

export function generateArizePdf(
  heroMetrics: any,
  groundednessStat: any,
  agents: any[],
  expEvals: any
) {
  // Use Landscape for wide tables
  const doc = new jsPDF({
    orientation: "landscape",
    unit: "mm",
    format: "a4",
  });

  const pageWidth = doc.internal.pageSize.getWidth();
  const margin = 15;
  let cursorY = margin;

  // -- 1. HEADER --
  doc.setFont("helvetica", "bold");
  doc.setFontSize(24);
  doc.setTextColor(COLORS.primary);
  doc.text("Arize AI", margin, cursorY + 5);
  
  doc.setFontSize(10);
  doc.setTextColor(COLORS.muted);
  doc.text("Evaluation & Telemetry Report", margin, cursorY + 12);
  
  // Right side info
  const formattedDate = new Date().toLocaleString("en-IN", {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit"
  });
  
  doc.setFont("helvetica", "bold");
  doc.setFontSize(10);
  doc.setTextColor(COLORS.primary);
  doc.text(`Generated: ${formattedDate}`, pageWidth - margin, cursorY + 5, { align: "right" });
  
  cursorY += 25;

  // -- 2. HERO METRICS --
  doc.setFont("helvetica", "bold");
  doc.setFontSize(14);
  doc.setTextColor(COLORS.primary);
  doc.text("Core Telemetry Metrics", margin, cursorY);
  cursorY += 8;

  const metricsData = [
    [
      "Total Evaluations",
      heroMetrics.total_evaluations?.toString() || "0",
      `${heroMetrics.total_runs || 0} pipeline runs`
    ],
    [
      "Hallucination Rate",
      groundednessStat.hallucPct != null ? `${groundednessStat.hallucPct}%` : "N/A",
      groundednessStat.judged ? `${groundednessStat.judged} rationales judged` : "no judged evals yet"
    ],
    [
      "Groundedness Score",
      groundednessStat.groundedPct != null ? `${groundednessStat.groundedPct}%` : "N/A",
      "via rationale_groundedness judge"
    ],
    [
      "Safety Triggers",
      heroMetrics.safety_triggers_prevented?.toString() || "0",
      `${heroMetrics.total_retries || 0} auto-retries`
    ]
  ];

  autoTable(doc, {
    startY: cursorY,
    head: [["Metric", "Value", "Context"]],
    body: metricsData,
    theme: 'grid',
    headStyles: { fillColor: COLORS.violet, textColor: "#ffffff", fontStyle: "bold" },
    styles: { fontSize: 9, cellPadding: 4, textColor: COLORS.primary },
    margin: { left: margin, right: margin }
  });
  
  cursorY = (doc as any).lastAutoTable.finalY + 15;

  // -- 3. AGENT PERFORMANCE --
  doc.setFont("helvetica", "bold");
  doc.setFontSize(14);
  doc.setTextColor(COLORS.primary);
  doc.text("Agent Performance Breakdown", margin, cursorY);
  cursorY += 8;

  const agentBody = agents.map(a => [
    a.agent_name,
    a.invocations?.toString() || "0",
    `${a.success_rate || 0}%`,
    a.p50_latency_ms ? `${Math.round(a.p50_latency_ms)} ms` : "-",
    a.total_tokens?.toLocaleString() || "0",
    a.avg_confidence != null ? `${Math.round(a.avg_confidence * 100)}%` : "-"
  ]);

  autoTable(doc, {
    startY: cursorY,
    head: [["Agent", "Calls", "Success Rate", "p50 Latency", "Tokens", "Avg Confidence"]],
    body: agentBody.length ? agentBody : [["No agent data available.", "-", "-", "-", "-", "-"]],
    theme: 'grid',
    headStyles: { fillColor: COLORS.accent, textColor: "#ffffff", fontStyle: "bold" },
    styles: { fontSize: 9, cellPadding: 4, textColor: COLORS.primary },
    margin: { left: margin, right: margin }
  });

  cursorY = (doc as any).lastAutoTable.finalY + 15;

  // -- 4. LLM-AS-JUDGE VERDICTS --
  // Check if we need a new page
  if (cursorY > doc.internal.pageSize.getHeight() - 40) {
    doc.addPage();
    cursorY = margin;
  }

  doc.setFont("helvetica", "bold");
  doc.setFontSize(14);
  doc.setTextColor(COLORS.primary);
  doc.text("LLM-as-Judge Experiment Verdicts", margin, cursorY);
  cursorY += 8;

  const evaluators = expEvals?.evaluators || [];
  const headRow = ["Stock", "Action", "Expected", ...evaluators.map((e: string) => e.replace(/_/g, " "))];
  
  const verdictsBody = (expEvals?.rows || []).map((row: any) => {
    return [
      row.ticker,
      row.action,
      row.expected_action,
      ...evaluators.map((name: string) => {
        const v = row.evals?.[name];
        if (!v) return "-";
        return v.label ? v.label : (v.score != null ? v.score.toString() : "-");
      })
    ];
  });

  autoTable(doc, {
    startY: cursorY,
    head: [headRow],
    body: verdictsBody.length ? verdictsBody : [["No experiment rows available."]],
    theme: 'grid',
    headStyles: { fillColor: COLORS.primary, textColor: "#ffffff", fontStyle: "bold", cellPadding: 3 },
    styles: { fontSize: 8, cellPadding: 3, textColor: COLORS.muted },
    margin: { left: margin, right: margin }
  });

  // Save the PDF
  const filename = `Arize_Eval_Report_${formattedDate.replace(/[: ]/g, "_")}.pdf`;
  doc.save(filename);
}

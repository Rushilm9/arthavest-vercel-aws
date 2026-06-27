import React from 'react';
import { pdf } from '@react-pdf/renderer';
import type { AnalyzeResponse } from '../types';
import { AnalysisReportPdf } from '../components/pdf/AnalysisReportPdf';

export async function generateAnalysisPdf(data: AnalyzeResponse) {
  try {
    // Generate the PDF blob using @react-pdf/renderer
    // Use React.createElement instead of JSX to avoid syntax errors in a .ts file
    // and cast to any to satisfy strict DocumentProps checking from @react-pdf/renderer
    const element = React.createElement(AnalysisReportPdf, { data }) as any;
    const blob = await pdf(element).toBlob();
    
    const dateStr = data.timestamp || data.created_at || new Date().toISOString();
    const d = new Date(dateStr);
    const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    const dateFmt = `${String(d.getDate()).padStart(2, '0')}${months[d.getMonth()]}${d.getFullYear()}_${String(d.getHours()).padStart(2, '0')}${String(d.getMinutes()).padStart(2, '0')}`;
    const filename = `${data.symbol}_Analysis_${dateFmt}.pdf`;

    // Create a temporary object URL and trigger download
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    
  } catch (err) {
    console.error("Error generating PDF:", err);
    alert("Failed to generate PDF. Please try again.");
  }
}

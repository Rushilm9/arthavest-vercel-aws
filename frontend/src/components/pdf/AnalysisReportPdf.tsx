
import { Document, Page, Text, View, StyleSheet } from '@react-pdf/renderer';
import type { AnalyzeResponse } from '../../types';

// Create styles
const styles = StyleSheet.create({
  page: {
    flexDirection: 'column',
    backgroundColor: '#FFFFFF',
    padding: 30,
    fontFamily: 'Helvetica',
  },
  header: {
    borderBottomWidth: 2,
    borderBottomColor: '#E2E8F0',
    paddingBottom: 15,
    marginBottom: 20,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-end',
  },
  headerTitle: {
    fontSize: 28,
    color: '#0F172A',
    fontWeight: 'bold',
  },
  headerSubtitle: {
    fontSize: 12,
    color: '#475569',
    marginTop: 4,
  },
  headerDate: {
    fontSize: 10,
    color: '#475569',
  },
  stockHeader: {
    marginBottom: 20,
  },
  symbol: {
    fontSize: 24,
    color: '#0F172A',
    fontWeight: 'bold',
    marginBottom: 4,
  },
  companyName: {
    fontSize: 12,
    color: '#475569',
    marginBottom: 12,
  },
  signalRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 15,
  },
  signalBadge: {
    paddingVertical: 4,
    paddingHorizontal: 12,
    borderRadius: 4,
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: 'bold',
  },
  metaText: {
    fontSize: 10,
    color: '#0F172A',
  },
  table: {
    width: '100%',
    marginBottom: 20,
  },
  tableHeaderRow: {
    flexDirection: 'row',
    backgroundColor: '#F8FAFC',
    borderBottomWidth: 1,
    borderBottomColor: '#E2E8F0',
    borderTopWidth: 1,
    borderTopColor: '#E2E8F0',
  },
  tableRow: {
    flexDirection: 'row',
    borderBottomWidth: 1,
    borderBottomColor: '#E2E8F0',
  },
  tableHeaderCell: {
    flex: 1,
    padding: 8,
    fontSize: 10,
    fontWeight: 'bold',
    color: '#0F172A',
    textAlign: 'center',
    borderRightWidth: 1,
    borderRightColor: '#E2E8F0',
    borderLeftWidth: 1,
    borderLeftColor: '#E2E8F0',
  },
  tableCell: {
    flex: 1,
    padding: 8,
    fontSize: 10,
    color: '#0F172A',
    textAlign: 'center',
    borderRightWidth: 1,
    borderRightColor: '#E2E8F0',
    borderLeftWidth: 1,
    borderLeftColor: '#E2E8F0',
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: 'bold',
    color: '#0F172A',
    marginBottom: 8,
  },
  paragraph: {
    fontSize: 10,
    lineHeight: 1.5,
    color: '#0F172A',
    marginBottom: 8,
  },
  boxContainer: {
    flexDirection: 'row',
    gap: 15,
    marginBottom: 20,
  },
  box: {
    flex: 1,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 4,
  },
  boxHeader: {
    backgroundColor: '#0F172A',
    color: '#FFFFFF',
    padding: 6,
    fontSize: 10,
    fontWeight: 'bold',
  },
  boxContent: {
    padding: 10,
  },
  listItem: {
    fontSize: 9,
    lineHeight: 1.4,
    color: '#0F172A',
    marginBottom: 4,
  },
  footer: {
    position: 'absolute',
    bottom: 20,
    left: 30,
    right: 30,
    textAlign: 'center',
    color: '#94A3B8',
    fontSize: 8,
    borderTopWidth: 1,
    borderTopColor: '#E2E8F0',
    paddingTop: 10,
  },
  synthesisLabel: {
    fontSize: 11,
    fontWeight: 'bold',
    color: '#0F172A',
    marginTop: 8,
    marginBottom: 4,
  },
  specialistBlock: {
    marginBottom: 15,
  },
  specialistHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 6,
  },
  specialistTitle: {
    fontSize: 12,
    fontWeight: 'bold',
    color: '#0F172A',
    marginRight: 8,
  },
  specialistBadge: {
    paddingVertical: 2,
    paddingHorizontal: 6,
    borderRadius: 3,
    color: '#FFFFFF',
    fontSize: 8,
    fontWeight: 'bold',
  }
});

const COLORS = {
  buy: "#059669",
  sell: "#DC2626",
  wait: "#D97706",
  hold: "#4F46E5",
  muted: "#475569",
};

function getSignalColor(signal?: string | null) {
  switch (signal) {
    case "BUY": return COLORS.buy;
    case "SELL": return COLORS.sell;
    case "WAIT": return COLORS.wait;
    case "HOLD": return COLORS.hold;
    default: return COLORS.muted;
  }
}

// Simple HTML to text converter for PDF text nodes
function stripHtml(html?: string) {
  if (!html) return '';
  // Replace <br> and <p> with newlines, remove other tags, decode common entities
  return html
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/p>/gi, '\n\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .trim();
}

export const AnalysisReportPdf = ({ data }: { data: AnalyzeResponse }) => {
  const signalColor = getSignalColor(data.recommendation);
  const dateStr = data.timestamp || data.created_at || new Date().toISOString();
  const formattedDate = new Date(dateStr).toLocaleString("en-IN", {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit"
  });

  return (
    <Document>
      <Page size="A4" style={styles.page}>
        {/* Header */}
        <View style={styles.header}>
          <View>
            <Text style={styles.headerTitle}>ArthaVest</Text>
            <Text style={styles.headerSubtitle}>Specialist AI Analysis Report</Text>
          </View>
          <View>
            <Text style={styles.headerDate}>Analyzed: {formattedDate}</Text>
          </View>
        </View>

        {/* Stock Info */}
        <View style={styles.stockHeader}>
          <Text style={styles.symbol}>{data.symbol}</Text>
          <Text style={styles.companyName}>{data.company_name || "Indian Equity Market Asset"}</Text>
          <View style={styles.signalRow}>
            <View style={[styles.signalBadge, { backgroundColor: signalColor }]}>
              <Text>{data.recommendation || "N/A"}</Text>
            </View>
            <Text style={styles.metaText}>Confidence: {data.confidence || 0}%</Text>
            <Text style={styles.metaText}>Horizon: {data.horizon || "MID"}</Text>
          </View>
          <Text style={[styles.metaText, { marginTop: 6, color: '#64748B', fontWeight: 'bold' }]}>
            Analysis Date: {formattedDate}
          </Text>
        </View>

        {/* Tables */}
        <View style={styles.table}>
          <View style={styles.tableHeaderRow}>
            <Text style={styles.tableHeaderCell}>Entry Price</Text>
            <Text style={styles.tableHeaderCell}>Target Price</Text>
            <Text style={styles.tableHeaderCell}>Stop Loss</Text>
            <Text style={styles.tableHeaderCell}>Risk/Reward</Text>
          </View>
          <View style={styles.tableRow}>
            <Text style={styles.tableCell}>{data.entry_price ? 'INR ' + data.entry_price : '—'}</Text>
            <Text style={styles.tableCell}>{data.target_price ? 'INR ' + data.target_price : '—'}</Text>
            <Text style={styles.tableCell}>{data.stop_loss ? 'INR ' + data.stop_loss : '—'}</Text>
            <Text style={styles.tableCell}>{data.risk_reward ? data.risk_reward.toFixed(1) + 'x' : '—'}</Text>
          </View>
        </View>

        <View style={styles.table}>
          <View style={styles.tableHeaderRow}>
            <Text style={styles.tableHeaderCell}>Est. Return</Text>
            <Text style={styles.tableHeaderCell}>Target Duration</Text>
            <Text style={styles.tableHeaderCell}>Position Size</Text>
          </View>
          <View style={styles.tableRow}>
            <Text style={styles.tableCell}>{data.upside_pct ? '+' + data.upside_pct.toFixed(1) + '%' : '—'}</Text>
            <Text style={styles.tableCell}>{data.timeframe || (data.horizon_days ? data.horizon_days + ' days' : '30 days')}</Text>
            <Text style={styles.tableCell}>{data.position_size_pct ? data.position_size_pct + '%' : '—'}</Text>
          </View>
        </View>

        {/* Narrative */}
        <View style={{ marginBottom: 15 }}>
          <Text style={styles.sectionTitle}>Decision &amp; Catalysts</Text>
          <Text style={styles.paragraph}>{stripHtml(data.narrative)}</Text>
        </View>

        {/* Catalysts & Risks */}
        {(data.key_catalysts?.length || data.key_risks?.length) && (
          <View style={styles.boxContainer} wrap={false}>
            <View style={styles.box}>
              <Text style={styles.boxHeader}>Key Catalysts</Text>
              <View style={styles.boxContent}>
                {data.key_catalysts?.length ? data.key_catalysts.map((c, i) => (
                  <Text key={i} style={styles.listItem}>• {stripHtml(c)}</Text>
                )) : <Text style={styles.listItem}>None specified.</Text>}
              </View>
            </View>
            <View style={styles.box}>
              <Text style={styles.boxHeader}>Key Risks</Text>
              <View style={styles.boxContent}>
                {data.key_risks?.length ? data.key_risks.map((r, i) => (
                  <Text key={i} style={styles.listItem}>• {stripHtml(r)}</Text>
                )) : <Text style={styles.listItem}>None flagged.</Text>}
              </View>
            </View>
          </View>
        )}

        {/* Consensus Debate */}
        {data.debate_summary && (
          <View style={{ marginBottom: 20 }} wrap={false}>
            <Text style={styles.sectionTitle}>Consensus Debate</Text>
            <View style={styles.boxContainer}>
              <View style={[styles.box, { backgroundColor: '#F8FAFC' }]}>
                <Text style={[styles.sectionTitle, { fontSize: 11, padding: 8, marginBottom: 0 }]}>Bull Case</Text>
                <View style={styles.boxContent}>
                  <Text style={styles.paragraph}>{stripHtml(data.debate_summary.bull_case || "N/A")}</Text>
                </View>
              </View>
              <View style={[styles.box, { backgroundColor: '#F8FAFC' }]}>
                <Text style={[styles.sectionTitle, { fontSize: 11, padding: 8, marginBottom: 0 }]}>Bear Case</Text>
                <View style={styles.boxContent}>
                  <Text style={styles.paragraph}>{stripHtml(data.debate_summary.bear_case || "N/A")}</Text>
                </View>
              </View>
            </View>
            <Text style={styles.synthesisLabel}>Synthesis:</Text>
            <Text style={styles.paragraph}>{stripHtml(data.debate_summary.synthesis || "N/A")}</Text>
          </View>
        )}

        {/* Specialist Summaries */}
        <View wrap={false} style={styles.specialistBlock}>
          <View style={styles.specialistHeader}>
            <Text style={styles.specialistTitle}>Technical Analysis</Text>
            <View style={[styles.specialistBadge, { backgroundColor: getSignalColor(data.technical_summary?.signal) }]}>
              <Text>{data.technical_summary?.signal || "N/A"}</Text>
            </View>
          </View>
          <Text style={styles.paragraph}>{stripHtml(data.technical_summary?.narrative || "N/A")}</Text>
        </View>

        <View wrap={false} style={styles.specialistBlock}>
          <View style={styles.specialistHeader}>
            <Text style={styles.specialistTitle}>Fundamental Analysis</Text>
            <View style={[styles.specialistBadge, { backgroundColor: getSignalColor(data.fundamental_summary?.signal) }]}>
              <Text>{data.fundamental_summary?.signal || "N/A"}</Text>
            </View>
          </View>
          <Text style={styles.paragraph}>{stripHtml(data.fundamental_summary?.narrative || "N/A")}</Text>
        </View>

        <View wrap={false} style={styles.specialistBlock}>
          <View style={styles.specialistHeader}>
            <Text style={styles.specialistTitle}>Sentiment Analysis</Text>
            <View style={[styles.specialistBadge, { backgroundColor: getSignalColor(data.sentiment_summary?.signal) }]}>
              <Text>{data.sentiment_summary?.signal || "N/A"}</Text>
            </View>
          </View>
          <Text style={styles.paragraph}>{stripHtml(data.sentiment_summary?.narrative || "N/A")}</Text>
        </View>

        <Text style={styles.footer} fixed>Generated by ArthaVest AI · Not financial advice</Text>
      </Page>
    </Document>
  );
};

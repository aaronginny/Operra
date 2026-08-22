import { useEffect, useRef, useMemo } from "react";
import {
  Chart,
  BarController, BarElement,
  DoughnutController, ArcElement,
  CategoryScale, LinearScale,
  Tooltip, Legend,
} from "chart.js";
import { CURRENCIES, formatMoney } from "../constants";

Chart.register(BarController, BarElement, DoughnutController, ArcElement, CategoryScale, LinearScale, Tooltip, Legend);

const NAVY  = "#050E1E";
const GOLD  = "#D4A84A";
const GOLD2 = "#E5C374";
const GREY  = "#8590A0";

const LABEL_COLORS = {
  hot:    "#B33A26",
  active: "#0F7A4D",
  warm:   "#BC9237",
  cold:   "#345582",
  closed: "#5C6776",
};

const MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

function useChart(canvasRef, config, deps) {
  const chartRef = useRef(null);
  useEffect(() => {
    if (!canvasRef.current) return;
    if (chartRef.current) chartRef.current.destroy();
    chartRef.current = new Chart(canvasRef.current, config);
    return () => { if (chartRef.current) { chartRef.current.destroy(); chartRef.current = null; } };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

function ChartCard({ title, subtitle, highlight, highlightLabel, children }) {
  return (
    <div style={S.card}>
      <div style={S.cardHead}>
        <div>
          <div style={S.cardTitle}>{title}</div>
          {subtitle && <div style={S.cardSub}>{subtitle}</div>}
        </div>
        {highlight != null && (
          <div style={{ textAlign: "right" }}>
            <div style={S.highlight}>{highlight}</div>
            {highlightLabel && <div style={S.highlightLabel}>{highlightLabel}</div>}
          </div>
        )}
      </div>
      <div style={S.cardBody}>{children}</div>
    </div>
  );
}

// Bar chart: buyers+sellers added per month for last 6 months
function DealsOverTime({ buyers, sellers }) {
  const ref = useRef();
  const { labels, buyerData, sellerData } = useMemo(() => {
    const now = new Date();
    const labels = [];
    const buyerData = [];
    const sellerData = [];
    for (let i = 5; i >= 0; i--) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      labels.push(MONTH_NAMES[d.getMonth()]);
      const y = d.getFullYear(), m = d.getMonth();
      buyerData.push(buyers.filter((b) => {
        const bd = new Date(b.createdAt);
        return bd.getFullYear() === y && bd.getMonth() === m;
      }).length);
      sellerData.push(sellers.filter((s) => {
        const sd = new Date(s.createdAt);
        return sd.getFullYear() === y && sd.getMonth() === m;
      }).length);
    }
    return { labels, buyerData, sellerData };
  }, [buyers, sellers]);

  useChart(ref, {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "Buyers", data: buyerData, backgroundColor: NAVY, borderRadius: 5, borderSkipped: false },
        { label: "Sellers", data: sellerData, backgroundColor: GOLD, borderRadius: 5, borderSkipped: false },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: "top", labels: { color: GREY, font: { size: 11 }, padding: 12 } }, tooltip: { mode: "index", intersect: false } },
      scales: {
        x: { ticks: { color: GREY, font: { size: 11 } }, grid: { display: false } },
        y: { ticks: { color: GREY, font: { size: 11 }, stepSize: 1 }, grid: { color: "rgba(0,0,0,.05)" } },
      },
    },
  }, [buyers, sellers]);

  const totalAdded = buyers.length + sellers.length;
  return (
    <ChartCard title="Contacts over time" subtitle="Buyers & sellers added per month" highlight={totalAdded} highlightLabel="total contacts">
      <div style={{ height: 200 }}><canvas ref={ref} /></div>
    </ChartCard>
  );
}

// Donut: match conversion rate
function MatchConversion({ matches, connectedSet }) {
  const ref = useRef();
  const connected = matches.filter((m) => connectedSet.has(m.id)).length;
  const total = matches.length;
  const pct = total > 0 ? Math.round((connected / total) * 100) : 0;

  useChart(ref, {
    type: "doughnut",
    data: {
      labels: ["Connected", "Not connected"],
      datasets: [{ data: [connected, Math.max(total - connected, 0)], backgroundColor: [GOLD, "#E8ECF2"], borderWidth: 0, hoverOffset: 4 }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: "72%",
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => ` ${ctx.label}: ${ctx.raw}` } } },
    },
  }, [connected, total, matches, connectedSet]);

  return (
    <ChartCard title="Match conversion" subtitle="% of matches marked connected" highlight={`${pct}%`} highlightLabel={`${connected} of ${total} matched`}>
      <div style={{ height: 160, position: "relative" }}>
        <canvas ref={ref} />
        <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
          <div style={{ fontFamily: "Fraunces, serif", fontSize: 28, fontWeight: 700, color: NAVY, lineHeight: 1 }}>{pct}%</div>
          <div style={{ fontSize: 10, color: GREY, marginTop: 2 }}>connected</div>
        </div>
      </div>
    </ChartCard>
  );
}

// Horizontal bar: top areas
function TopAreas({ buyers, sellers }) {
  const ref = useRef();
  const { labels, data } = useMemo(() => {
    const counts = {};
    [...buyers, ...sellers].forEach((p) => { if (p.area) counts[p.area] = (counts[p.area] || 0) + 1; });
    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 7);
    return { labels: sorted.map(([k]) => k), data: sorted.map(([, v]) => v) };
  }, [buyers, sellers]);

  useChart(ref, {
    type: "bar",
    data: {
      labels,
      datasets: [{ label: "Contacts", data, backgroundColor: NAVY, borderRadius: 4, borderSkipped: false }],
    },
    options: {
      indexAxis: "y",
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => ` ${ctx.raw} contacts` } } },
      scales: {
        x: { ticks: { color: GREY, font: { size: 11 }, stepSize: 1 }, grid: { color: "rgba(0,0,0,.05)" } },
        y: { ticks: { color: GREY, font: { size: 11 } }, grid: { display: false } },
      },
    },
  }, [buyers, sellers]);

  return (
    <ChartCard title="Top areas" subtitle="Most listings by location" highlight={labels[0] || "—"} highlightLabel="most active area">
      <div style={{ height: Math.max(labels.length * 32 + 20, 140) }}><canvas ref={ref} /></div>
    </ChartCard>
  );
}

// Donut: property type breakdown
function PropertyTypeBreakdown({ buyers, sellers }) {
  const ref = useRef();
  const { labels, data, colors } = useMemo(() => {
    const counts = {};
    [...buyers, ...sellers].forEach((p) => { if (p.type) counts[p.type] = (counts[p.type] || 0) + 1; });
    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 6);
    const palette = [NAVY, GOLD, "#345582", "#E5C374", "#8590A0", "#1A3A66"];
    return { labels: sorted.map(([k]) => k), data: sorted.map(([, v]) => v), colors: sorted.map((_, i) => palette[i % palette.length]) };
  }, [buyers, sellers]);

  useChart(ref, {
    type: "doughnut",
    data: {
      labels,
      datasets: [{ data, backgroundColor: colors, borderWidth: 2, borderColor: "#fff", hoverOffset: 4 }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: "55%",
      plugins: { legend: { position: "right", labels: { color: GREY, font: { size: 11 }, padding: 10 } } },
    },
  }, [buyers, sellers]);

  const top = labels[0];
  return (
    <ChartCard title="Property type mix" subtitle="Distribution across all listings" highlight={top || "—"} highlightLabel="most listed type">
      <div style={{ height: 200 }}><canvas ref={ref} /></div>
    </ChartCard>
  );
}

// Donut: lead status breakdown
function LeadStatusBreakdown({ buyers, sellers }) {
  const ref = useRef();
  const { labels, data, colors } = useMemo(() => {
    const counts = {};
    [...buyers, ...sellers].forEach((p) => { const l = p.label || "active"; counts[l] = (counts[l] || 0) + 1; });
    const order = ["hot", "active", "warm", "cold", "closed"];
    const entries = order.filter((k) => counts[k]).map((k) => [k, counts[k]]);
    return {
      labels: entries.map(([k]) => k.charAt(0).toUpperCase() + k.slice(1)),
      data: entries.map(([, v]) => v),
      colors: entries.map(([k]) => LABEL_COLORS[k] || GREY),
    };
  }, [buyers, sellers]);

  useChart(ref, {
    type: "doughnut",
    data: {
      labels,
      datasets: [{ data, backgroundColor: colors, borderWidth: 2, borderColor: "#fff", hoverOffset: 4 }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: "55%",
      plugins: { legend: { position: "right", labels: { color: GREY, font: { size: 11 }, padding: 10 } } },
    },
  }, [buyers, sellers]);

  const hotCount = buyers.filter((b) => b.label === "hot").length + sellers.filter((s) => s.label === "hot").length;
  return (
    <ChartCard title="Lead status" subtitle="Distribution by pipeline stage" highlight={hotCount} highlightLabel="🔥 hot leads">
      <div style={{ height: 200 }}><canvas ref={ref} /></div>
    </ChartCard>
  );
}

// International vs local
function IntlVsLocal({ buyers, sellers }) {
  const ref = useRef();
  const all = [...buyers, ...sellers];
  const intl = all.filter((p) => p.intl).length;
  const local = all.length - intl;
  const pct = all.length > 0 ? Math.round((intl / all.length) * 100) : 0;

  useChart(ref, {
    type: "doughnut",
    data: {
      labels: ["International", "Local"],
      datasets: [{ data: [intl, local], backgroundColor: [GOLD, NAVY], borderWidth: 0, hoverOffset: 4 }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: "68%",
      plugins: { legend: { position: "right", labels: { color: GREY, font: { size: 11 }, padding: 10 } } },
    },
  }, [buyers, sellers]);

  return (
    <ChartCard title="International vs local" subtitle="Client origin breakdown" highlight={`${pct}%`} highlightLabel="international">
      <div style={{ height: 160, position: "relative" }}>
        <canvas ref={ref} />
        <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
          <div style={{ fontFamily: "Fraunces, serif", fontSize: 26, fontWeight: 700, color: NAVY, lineHeight: 1 }}>{pct}%</div>
          <div style={{ fontSize: 10, color: GREY, marginTop: 2 }}>intl</div>
        </div>
      </div>
    </ChartCard>
  );
}

// Top referrers list
function TopReferrers({ buyers, sellers }) {
  const { sorted, max } = useMemo(() => {
    const counts = {};
    [...buyers, ...sellers].forEach((p) => {
      const k = (p.referredBy || "").trim();
      if (k) counts[k] = (counts[k] || 0) + 1;
    });
    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 10);
    return { sorted, max: sorted[0]?.[1] || 1 };
  }, [buyers, sellers]);

  if (sorted.length === 0) return null;

  return (
    <ChartCard title="Top referrers" subtitle="Most leads by source" highlight={sorted[0]?.[0] || "—"} highlightLabel={`${sorted[0]?.[1] || 0} leads`}>
      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 4 }}>
        {sorted.map(([name, count]) => (
          <div key={name} style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ flex: 1, minWidth: 0, fontSize: 12.5, fontWeight: 600, color: "var(--navy-900)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{name}</div>
            <div style={{ width: 80, height: 6, background: "#E8ECF2", borderRadius: 3, flexShrink: 0, overflow: "hidden" }}>
              <div style={{ width: `${Math.round((count / max) * 100)}%`, height: "100%", background: GOLD, borderRadius: 3 }} />
            </div>
            <div style={{ fontSize: 12, fontWeight: 700, color: GOLD, minWidth: 22, textAlign: "right" }}>{count}</div>
          </div>
        ))}
      </div>
    </ChartCard>
  );
}

// Division split bar
function DivisionSplit({ buyers, sellers }) {
  const ref = useRef();
  const salesB   = buyers.filter((b)  => b.division === "sales").length;
  const rentalsB = buyers.filter((b)  => b.division === "rentals").length;
  const salesS   = sellers.filter((s) => s.division === "sales").length;
  const rentalsS = sellers.filter((s) => s.division === "rentals").length;

  useChart(ref, {
    type: "bar",
    data: {
      labels: ["Buyers", "Sellers"],
      datasets: [
        { label: "Sales", data: [salesB, salesS], backgroundColor: NAVY, borderRadius: 5, borderSkipped: false },
        { label: "Rentals", data: [rentalsB, rentalsS], backgroundColor: GOLD, borderRadius: 5, borderSkipped: false },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: "top", labels: { color: GREY, font: { size: 11 }, padding: 10 } } },
      scales: {
        x: { ticks: { color: GREY }, grid: { display: false } },
        y: { ticks: { color: GREY, stepSize: 1 }, grid: { color: "rgba(0,0,0,.05)" } },
      },
    },
  }, [buyers, sellers]);

  return (
    <ChartCard title="Sales vs Rentals" subtitle="Division split across all contacts">
      <div style={{ height: 180 }}><canvas ref={ref} /></div>
    </ChartCard>
  );
}

export default function AnalyticsPage({ buyers, sellers, matches, connectedSet, displayCur }) {
  const all = [...buyers, ...sellers];
  const totalContacts = all.length;
  const hotLeads = all.filter((p) => p.label === "hot").length;
  const intlCount = all.filter((p) => p.intl).length;

  return (
    <div className="main fade-in">
      <div className="page-head">
        <div>
          <div className="pre">// analytics</div>
          <h1>Analytics <em>dashboard.</em></h1>
          <div className="sub">Real-time insights from your book of business.</div>
        </div>
      </div>

      {/* KPI row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14, marginBottom: 22 }}>
        {[
          { label: "Total contacts",  value: totalContacts, color: "var(--navy-900)" },
          { label: "Total matches",   value: matches.length, color: "var(--navy-900)" },
          { label: "Hot leads",       value: hotLeads,   color: "#B33A26" },
          { label: "Intl clients",    value: intlCount,  color: "#BC9237" },
        ].map((k) => (
          <div key={k.label} style={{ background: "var(--paper)", border: "1px solid var(--line-2)", borderRadius: 12, padding: "14px 18px" }}>
            <div style={{ fontSize: 10.5, fontFamily: "JetBrains Mono, monospace", textTransform: "uppercase", letterSpacing: "0.12em", color: "var(--ink-400)", marginBottom: 6 }}>{k.label}</div>
            <div style={{ fontFamily: "Fraunces, serif", fontSize: 32, fontWeight: 600, color: k.color, lineHeight: 1 }}>{k.value}</div>
          </div>
        ))}
      </div>

      {/* Charts grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <DealsOverTime buyers={buyers} sellers={sellers} />
        <MatchConversion matches={matches} connectedSet={connectedSet || new Set()} />
        <TopAreas buyers={buyers} sellers={sellers} />
        <PropertyTypeBreakdown buyers={buyers} sellers={sellers} />
        <LeadStatusBreakdown buyers={buyers} sellers={sellers} />
        <IntlVsLocal buyers={buyers} sellers={sellers} />
        <div style={{ gridColumn: "1 / -1" }}>
          <DivisionSplit buyers={buyers} sellers={sellers} />
        </div>
        <TopReferrers buyers={buyers} sellers={sellers} />
      </div>
    </div>
  );
}

const S = {
  card: { background: "var(--paper)", border: "1px solid var(--line-2)", borderRadius: 12, padding: "18px 20px", display: "flex", flexDirection: "column", gap: 12 },
  cardHead: { display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 },
  cardTitle: { fontFamily: "Fraunces, serif", fontWeight: 600, fontSize: 16, color: "var(--navy-900)", marginBottom: 2 },
  cardSub: { fontSize: 11.5, color: "var(--ink-400)" },
  cardBody: {},
  highlight: { fontFamily: "Fraunces, serif", fontSize: 26, fontWeight: 700, color: GOLD, lineHeight: 1 },
  highlightLabel: { fontSize: 11, color: GREY, marginTop: 2 },
};

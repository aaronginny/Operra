import { useState, useRef } from "react";
import { I } from "./icons";
import { COUNTRIES, PROPERTY_TYPES, divisionMeta, propertyTypesFor } from "./constants";
import { readExcelFile, detectColumnMapping, parseRows } from "./excel";

const BATCH_SIZE = 50;

const FIELD_LABELS = {
  name:    "Full Name",
  phone:   "Phone",
  area:    "Area / City",
  country: "Country",
  type:    "Property Type",
  min:     "Min Budget",
  max:     "Max Budget",
  price:   "Asking Price",
  cur:     "Currency",
  notes:   "Notes",
  label:   "Status",
  intl:    "International",
};

// onBulkImport(records[]) -> { inserted, duplicates, failed, errors }
export default function ImportModal({ kind, division, onClose, onBulkImport }) {
  const isBuyer = kind === "buyer";
  const meta = divisionMeta(division);
  const roleName = isBuyer ? meta.buyerRole : meta.sellerRole;

  const [step, setStep] = useState("upload"); // upload | mapping | preview | importing | done
  const [rawRows, setRawRows] = useState([]);
  const [headers, setHeaders] = useState([]);
  const [mapping, setMapping] = useState({});
  const [parsed, setParsed] = useState([]);
  const [dragOver, setDragOver] = useState(false);
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [result, setResult] = useState(null);
  const fileRef = useRef();

  const buyerFields  = ["name","phone","area","country","type","min","max","cur","notes","label","intl"];
  const sellerFields = ["name","phone","area","country","type","price","cur","notes","label","intl"];
  const activeFields = isBuyer ? buyerFields : sellerFields;

  async function handleFile(file) {
    if (!file) return;
    try {
      const rows = await readExcelFile(file);
      if (rows.length < 2) { alert("File has no data rows."); return; }
      const hdrs = rows[0].map(String);
      const dataRows = rows.slice(1).filter((r) => r.some((c) => c !== ""));
      const detected = detectColumnMapping(hdrs);
      setHeaders(hdrs);
      setRawRows(dataRows);
      setMapping(detected);
      setStep("mapping");
    } catch (err) {
      alert(err.message);
    }
  }

  function applyMapping() {
    const result = parseRows(rawRows, headers, mapping, kind, division);
    setParsed(result);
    setStep("preview");
  }

  async function doImport() {
    const valid = parsed.filter((r) => r._valid);
    const invalidRows = parsed.filter((r) => !r._valid);
    const total = valid.length;

    setProgress({ done: 0, total });
    setStep("importing");

    // Strip bookkeeping fields before sending
    const cleanRecords = valid.map(({ _row, _errors, _valid, ...data }) => data);

    let totalInserted = 0, totalDuplicates = 0, totalFailed = 0;
    const allErrors = [];

    // Send in batches of BATCH_SIZE
    for (let i = 0; i < cleanRecords.length; i += BATCH_SIZE) {
      const batch = cleanRecords.slice(i, i + BATCH_SIZE);
      try {
        const res = await onBulkImport(batch);
        totalInserted += res.inserted || 0;
        totalDuplicates += res.duplicates || 0;
        totalFailed += res.failed || 0;
        if (res.errors) allErrors.push(...res.errors);
      } catch (e) {
        // Whole batch failed — count each row as failed
        totalFailed += batch.length;
        allErrors.push(`Batch ${Math.floor(i / BATCH_SIZE) + 1} failed: ${e.message}`);
      }
      setProgress({ done: Math.min(i + BATCH_SIZE, total), total });
    }

    setResult({
      inserted: totalInserted,
      duplicates: totalDuplicates,
      failed: totalFailed,
      invalidRows,
      errors: allErrors,
    });
    setStep("done");
  }

  const validCount = parsed.filter((r) => r._valid).length;
  const invalidCount = parsed.filter((r) => !r._valid).length;
  const pct = progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0;

  return (
    <div style={S.overlay} onClick={(e) => e.target === e.currentTarget && step !== "importing" && onClose()}>
      <div style={S.modal}>
        {/* Header */}
        <div style={S.header}>
          <div>
            <div style={S.eyebrow}>// Import from Excel / CSV</div>
            <h2 style={S.title}>Import {roleName}s</h2>
          </div>
          {step !== "importing" && (
            <button style={S.closeBtn} onClick={onClose}><I.x width="16" height="16" /></button>
          )}
        </div>

        {/* Step: Upload */}
        {step === "upload" && (
          <div style={S.body}>
            <div
              style={{ ...S.dropzone, ...(dragOver ? S.dropzoneActive : {}) }}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFile(e.dataTransfer.files[0]); }}
              onClick={() => fileRef.current.click()}
            >
              <div style={S.dropIcon}>📂</div>
              <div style={S.dropTitle}>Drop your file here or click to browse</div>
              <div style={S.dropSub}>Accepts .xlsx and .csv files · up to 10,000 rows</div>
              <input ref={fileRef} type="file" accept=".xlsx,.csv" style={{ display: "none" }}
                onChange={(e) => handleFile(e.target.files[0])} />
            </div>

            <div style={S.tipBox}>
              <div style={S.tipTitle}>Expected columns (any order, flexible naming):</div>
              <div style={S.tipGrid}>
                {activeFields.map((f) => (
                  <span key={f} style={S.tipChip}>{FIELD_LABELS[f]}</span>
                ))}
              </div>
              <div style={{ fontSize: 11.5, color: "var(--ink-400)", marginTop: 8 }}>
                Column names are matched intelligently — e.g. "Mobile", "Contact", "Cell" all map to Phone.
                Duplicate contacts (same phone number) are skipped automatically.
              </div>
            </div>
          </div>
        )}

        {/* Step: Column Mapping */}
        {step === "mapping" && (
          <div style={S.body}>
            <div style={S.stepNote}>
              <b>{rawRows.length.toLocaleString()}</b> data rows detected. Confirm how your columns map to DealKnot fields:
            </div>
            <div style={S.mappingGrid}>
              {activeFields.map((field) => (
                <div key={field} style={S.mappingRow}>
                  <div style={S.mappingLabel}>{FIELD_LABELS[field]}</div>
                  <select style={S.mappingSelect}
                    value={mapping[field] ?? ""}
                    onChange={(e) => setMapping((m) => ({ ...m, [field]: e.target.value === "" ? undefined : Number(e.target.value) }))}>
                    <option value="">— not mapped —</option>
                    {headers.map((h, i) => (
                      <option key={i} value={i}>{h || `Column ${i + 1}`}</option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
            <div style={{ marginTop: 4, fontSize: 11.5, color: "var(--ink-400)" }}>
              Your file headers: {headers.map((h) => `"${h}"`).join(", ")}
            </div>
            <div style={S.footer}>
              <button style={S.btnGhost} onClick={() => setStep("upload")}>← Back</button>
              <button style={S.btnPrimary} onClick={applyMapping}>Preview data →</button>
            </div>
          </div>
        )}

        {/* Step: Preview */}
        {step === "preview" && (
          <div style={{ ...S.body, padding: 0 }}>
            <div style={{ padding: "16px 24px 0" }}>
              <div style={S.stepNote}>
                <b style={{ color: "var(--green)" }}>{validCount.toLocaleString()} valid</b>
                {invalidCount > 0 && (
                  <> · <b style={{ color: "var(--red)" }}>{invalidCount.toLocaleString()} with errors</b></>
                )}
                {" "}rows found.
                {validCount > 0 && (
                  <span style={{ color: "var(--ink-400)", fontSize: 12, marginLeft: 6 }}>
                    Will send in {Math.ceil(validCount / BATCH_SIZE)} batch{Math.ceil(validCount / BATCH_SIZE) !== 1 ? "es" : ""} of {BATCH_SIZE}.
                  </span>
                )}
              </div>
            </div>
            <div style={S.tableWrap}>
              <table style={S.table}>
                <thead>
                  <tr>
                    <th style={S.th}>#</th>
                    <th style={S.th}>Name</th>
                    <th style={S.th}>Phone</th>
                    <th style={S.th}>Area</th>
                    <th style={S.th}>Type</th>
                    <th style={S.th}>{isBuyer ? "Budget" : "Price"}</th>
                    <th style={S.th}>Cur</th>
                    <th style={S.th}>Status</th>
                    <th style={{ ...S.th, minWidth: 160 }}>Issues</th>
                  </tr>
                </thead>
                <tbody>
                  {parsed.map((r) => (
                    <tr key={r._row} style={r._valid ? {} : { background: "rgba(179,58,38,0.06)" }}>
                      <td style={S.td}>{r._row}</td>
                      <td style={S.td}>{r.name || <span style={{ color: "var(--red)" }}>—</span>}</td>
                      <td style={{ ...S.td, fontFamily: "JetBrains Mono, monospace", fontSize: 11 }}>{r.dial} {r.phone || <span style={{ color: "var(--red)" }}>—</span>}</td>
                      <td style={S.td}>{r.area || <span style={{ color: "var(--red)" }}>—</span>}</td>
                      <td style={S.td}>{r.type || <span style={{ color: "var(--ink-400)" }}>?</span>}</td>
                      <td style={S.td}>
                        {isBuyer
                          ? (r.min || r.max ? `${r.min}–${r.max}` : "—")
                          : (r.price || "—")}
                      </td>
                      <td style={S.td}>{r.cur}</td>
                      <td style={S.td}>{r.label}</td>
                      <td style={{ ...S.td, fontSize: 11, color: r._valid ? "var(--green)" : "var(--red)" }}>
                        {r._valid ? "✓ OK" : r._errors.join(" · ")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ ...S.footer, padding: "12px 24px" }}>
              <button style={S.btnGhost} onClick={() => setStep("mapping")}>← Back</button>
              <button style={{ ...S.btnPrimary, ...(validCount === 0 ? { opacity: 0.5, cursor: "not-allowed" } : {}) }}
                disabled={validCount === 0}
                onClick={doImport}>
                Import {validCount.toLocaleString()} {roleName.toLowerCase()}s →
              </button>
            </div>
          </div>
        )}

        {/* Step: Importing (progress) */}
        {step === "importing" && (
          <div style={{ ...S.body, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 24, minHeight: 260 }}>
            <div style={{ fontSize: 44 }}>⏳</div>
            <div style={{ fontFamily: "Fraunces, serif", fontSize: 20, fontWeight: 600, color: "var(--navy-900)" }}>
              Importing…
            </div>
            <div style={{ width: "100%", maxWidth: 400 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--ink-500)", marginBottom: 8 }}>
                <span>Importing {Math.min(progress.done + BATCH_SIZE, progress.total).toLocaleString()} of {progress.total.toLocaleString()} contacts</span>
                <span>{pct}%</span>
              </div>
              <div style={S.progressTrack}>
                <div style={{ ...S.progressBar, width: `${pct}%` }} />
              </div>
            </div>
            <div style={{ fontSize: 12.5, color: "var(--ink-400)", textAlign: "center", maxWidth: 340 }}>
              Please don't close this page. Contacts are being saved in batches of {BATCH_SIZE}.
            </div>
          </div>
        )}

        {/* Step: Done */}
        {step === "done" && result && (
          <div style={S.body}>
            <div style={S.successBox}>
              <div style={S.successIcon}>✅</div>
              <div style={S.successTitle}>Import complete</div>
              <div style={S.successMsg}>
                <b style={{ color: "var(--green)" }}>{result.inserted.toLocaleString()}</b> {roleName.toLowerCase()}{result.inserted !== 1 ? "s" : ""} imported successfully.
                {result.duplicates > 0 && <> · <b>{result.duplicates.toLocaleString()}</b> duplicates skipped.</>}
                {result.failed > 0 && <> · <b style={{ color: "var(--red)" }}>{result.failed.toLocaleString()}</b> rows failed.</>}
              </div>
            </div>

            {result.invalidRows.length > 0 && (
              <div style={S.errorList}>
                <div style={{ fontWeight: 700, marginBottom: 8, fontSize: 13 }}>Rows that need manual entry ({result.invalidRows.length}):</div>
                {result.invalidRows.slice(0, 20).map((r) => (
                  <div key={r._row} style={S.errorRow}>
                    <b>Row {r._row}</b>{r.name ? ` · ${r.name}` : ""} — {r._errors.join(", ")}
                  </div>
                ))}
                {result.invalidRows.length > 20 && (
                  <div style={{ fontSize: 11.5, color: "var(--ink-400)", marginTop: 6 }}>
                    …and {result.invalidRows.length - 20} more
                  </div>
                )}
              </div>
            )}

            {result.errors.length > 0 && (
              <div style={S.errorList}>
                <div style={{ fontWeight: 700, marginBottom: 8, fontSize: 13, color: "var(--red)" }}>Save errors ({result.errors.length}):</div>
                {result.errors.slice(0, 10).map((e, i) => <div key={i} style={S.errorRow}>{e}</div>)}
                {result.errors.length > 10 && (
                  <div style={{ fontSize: 11.5, color: "var(--ink-400)", marginTop: 6 }}>…and {result.errors.length - 10} more</div>
                )}
              </div>
            )}

            <div style={{ ...S.footer, justifyContent: "center" }}>
              <button style={S.btnPrimary} onClick={onClose}>Done</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const S = {
  overlay: {
    position: "fixed", inset: 0, background: "rgba(5,14,30,0.72)", zIndex: 9000,
    display: "flex", alignItems: "center", justifyContent: "center",
    backdropFilter: "blur(4px)", padding: 20,
  },
  modal: {
    background: "var(--paper)", borderRadius: 18, width: "100%", maxWidth: 780,
    maxHeight: "88vh", display: "flex", flexDirection: "column",
    boxShadow: "0 32px 80px rgba(0,0,0,0.35), 0 0 0 1px rgba(255,255,255,0.06)",
    overflow: "hidden",
  },
  header: {
    display: "flex", alignItems: "flex-start", justifyContent: "space-between",
    padding: "22px 24px 18px", borderBottom: "1px solid var(--line-2)", flexShrink: 0,
  },
  eyebrow: { fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--ink-400)", textTransform: "uppercase", letterSpacing: "0.14em", marginBottom: 4 },
  title: { fontFamily: "Fraunces, serif", fontSize: 22, fontWeight: 600, color: "var(--navy-900)", letterSpacing: "-0.01em", margin: 0 },
  closeBtn: { background: "none", border: "1px solid var(--line)", borderRadius: 8, width: 32, height: 32, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", color: "var(--ink-500)" },
  body: { flex: 1, overflowY: "auto", padding: "20px 24px 24px" },
  dropzone: {
    border: "2px dashed var(--line)", borderRadius: 14, padding: "48px 24px",
    textAlign: "center", cursor: "pointer", transition: "all .2s",
    background: "var(--stone-50)",
  },
  dropzoneActive: { borderColor: "var(--gold-600)", background: "rgba(212,168,74,0.05)" },
  dropIcon: { fontSize: 36, marginBottom: 12 },
  dropTitle: { fontWeight: 700, fontSize: 15, color: "var(--navy-900)", marginBottom: 6 },
  dropSub: { fontSize: 13, color: "var(--ink-400)" },
  tipBox: { marginTop: 20, background: "var(--stone-50)", border: "1px solid var(--line-2)", borderRadius: 12, padding: "14px 16px" },
  tipTitle: { fontSize: 12, fontWeight: 700, color: "var(--ink-700)", marginBottom: 8, fontFamily: "JetBrains Mono, monospace" },
  tipGrid: { display: "flex", flexWrap: "wrap", gap: 6 },
  tipChip: { background: "rgba(212,168,74,0.1)", border: "1px solid rgba(212,168,74,0.2)", borderRadius: 6, padding: "3px 10px", fontSize: 11.5, fontFamily: "JetBrains Mono, monospace", color: "var(--ink-700)" },
  stepNote: { fontSize: 13.5, color: "var(--ink-700)", marginBottom: 16 },
  mappingGrid: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px 24px", marginBottom: 16 },
  mappingRow: { display: "flex", flexDirection: "column", gap: 4 },
  mappingLabel: { fontSize: 11, fontWeight: 700, color: "var(--ink-500)", textTransform: "uppercase", letterSpacing: "0.07em" },
  mappingSelect: { padding: "8px 10px", borderRadius: 8, border: "1px solid var(--line)", background: "var(--paper)", fontFamily: "inherit", fontSize: 13, color: "var(--ink-900)", cursor: "pointer" },
  tableWrap: { overflowX: "auto", borderTop: "1px solid var(--line-2)", borderBottom: "1px solid var(--line-2)", maxHeight: 380 },
  table: { width: "100%", borderCollapse: "collapse", fontSize: 12.5 },
  th: { padding: "9px 12px", textAlign: "left", fontWeight: 700, fontSize: 11, background: "var(--navy-900)", color: "var(--gold-500)", position: "sticky", top: 0, whiteSpace: "nowrap", fontFamily: "JetBrains Mono, monospace" },
  td: { padding: "8px 12px", borderBottom: "1px solid var(--line-2)", verticalAlign: "top", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  footer: { display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, borderTop: "1px solid var(--line-2)", padding: "14px 0 0", flexShrink: 0 },
  btnGhost: { padding: "9px 18px", borderRadius: 9, border: "1px solid var(--line)", background: "transparent", fontFamily: "inherit", fontSize: 13, fontWeight: 600, cursor: "pointer", color: "var(--ink-700)" },
  btnPrimary: { padding: "9px 22px", borderRadius: 9, border: "none", background: "var(--navy-900)", fontFamily: "inherit", fontSize: 13, fontWeight: 700, cursor: "pointer", color: "var(--gold-400)" },
  successBox: { textAlign: "center", padding: "24px 0 20px" },
  successIcon: { fontSize: 44, marginBottom: 10 },
  successTitle: { fontFamily: "Fraunces, serif", fontSize: 22, fontWeight: 600, color: "var(--navy-900)", marginBottom: 6 },
  successMsg: { fontSize: 14, color: "var(--ink-500)", lineHeight: 1.6 },
  errorList: { background: "var(--stone-50)", border: "1px solid var(--line-2)", borderRadius: 10, padding: "14px 16px", marginTop: 16 },
  errorRow: { fontSize: 12.5, color: "var(--ink-700)", padding: "4px 0", borderBottom: "1px solid var(--line-2)" },
  progressTrack: { width: "100%", height: 10, background: "var(--line-2)", borderRadius: 99, overflow: "hidden" },
  progressBar: { height: "100%", background: "linear-gradient(90deg, var(--gold-600), var(--gold-400))", borderRadius: 99, transition: "width 0.3s ease" },
};

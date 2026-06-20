const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");

const ROOT = path.resolve(__dirname, "../..");
const REPORT_DIR = __dirname;
const METRICS_PATH = path.join(REPORT_DIR, "local_metrics_may_2026.json");
const STACK_PATH = path.join(ROOT, "data", "processed", "jepx_offer_stack_depth.csv");

const metrics = JSON.parse(fs.readFileSync(METRICS_PATH, "utf8"));

const COLORS = {
  bg: "071219",
  panel: "101922",
  panel2: "15212B",
  grid: "273744",
  text: "E8EEF5",
  muted: "9AA8B4",
  cyan: "54C7EC",
  blue: "6A8FFF",
  amber: "F4B844",
  orange: "F9734D",
  green: "4AC18E",
  red: "F26D7D",
  purple: "A277F2",
  white: "FFFFFF",
};

function csvRows(filePath) {
  const lines = fs.readFileSync(filePath, "utf8").trim().split(/\r?\n/);
  const header = lines.shift().split(",");
  return lines.map((line) => {
    const cells = line.split(",");
    const row = {};
    header.forEach((h, i) => {
      const value = cells[i];
      const num = Number(value);
      row[h] = Number.isFinite(num) && value !== "" ? num : value;
    });
    return row;
  });
}

function mean(values) {
  const nums = values.filter((value) => Number.isFinite(value));
  return nums.length ? nums.reduce((a, b) => a + b, 0) / nums.length : null;
}

function pct(conditionRows, fn) {
  if (!conditionRows.length) return 0;
  return (conditionRows.filter(fn).length / conditionRows.length) * 100;
}

function fmt(value, digits = 1) {
  if (!Number.isFinite(value)) return "n/a";
  return value.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function market(name) {
  return metrics.market_summary.find((row) => row.market === name) || {};
}

function supply(area, type) {
  return metrics.supply_mix_summary.find((row) => row.area === area && row.generation_type === type);
}

function stackStats(areaGroup) {
  const rows = csvRows(STACK_PATH).filter((row) => row.area_group === areaGroup);
  return {
    records: rows.length,
    clearing: mean(rows.map((row) => row.clearing_price_estimate)),
    depth: mean(rows.map((row) => row.tightest_depth_mw)),
    thin: pct(rows, (row) => row.stack_regime === "Thin stack"),
    scarcity: pct(rows, (row) => row.stack_regime === "Scarcity stack"),
    balanced: pct(rows, (row) => row.stack_regime === "Balanced stack"),
  };
}

const systemStack = stackStats("System Price");
const eastStack = stackStats("Hokkaido / Tohoku / Tokyo");
const westStack = stackStats("Hokuriku / Kansai / Chugoku / Shikoku / Kyushu");

const pptx = new pptxgen();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "Codex / Japan Fuel & Power Market Dashboard";
pptx.subject = "Japan power market review, May 2026";
pptx.title = "Japan Power Market Review - May 2026";
pptx.company = "Japan Fuel & Power Market Dashboard";
pptx.lang = "en-US";
pptx.theme = {
  headFontFace: "Aptos Display",
  bodyFontFace: "Aptos",
  lang: "en-US",
};
pptx.defineLayout({ name: "LAYOUT_WIDE", width: 13.333, height: 7.5 });

function addBg(slide) {
  slide.background = { color: COLORS.bg };
  slide.addShape(pptx.ShapeType.rect, {
    x: 0,
    y: 0,
    w: 13.333,
    h: 0.12,
    fill: { color: COLORS.cyan, transparency: 18 },
    line: { color: COLORS.cyan, transparency: 100 },
  });
}

function addTitle(slide, title, subtitle = "") {
  slide.addText(title, {
    x: 0.45,
    y: 0.32,
    w: 12.45,
    h: 0.38,
    fontFace: "Aptos Display",
    fontSize: 20,
    bold: true,
    color: COLORS.text,
    margin: 0,
  });
  if (subtitle) {
    slide.addText(subtitle, {
      x: 0.45,
      y: 0.77,
      w: 12.45,
      h: 0.35,
      fontSize: 9.5,
      color: COLORS.muted,
      margin: 0,
      breakLine: false,
    });
  }
}

function addFooter(slide) {
  slide.addText("Japan Fuel & Power Market Dashboard | May 2026 report | Public / sample-data screening deck", {
    x: 0.45,
    y: 7.15,
    w: 9.0,
    h: 0.18,
    fontSize: 7.2,
    color: COLORS.muted,
    margin: 0,
  });
  slide.addText("Generated 2026-06-10", {
    x: 10.85,
    y: 7.15,
    w: 2.05,
    h: 0.18,
    fontSize: 7.2,
    align: "right",
    color: COLORS.muted,
    margin: 0,
  });
}

function addPanel(slide, x, y, w, h, title = "") {
  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w,
    h,
    rectRadius: 0.06,
    fill: { color: COLORS.panel },
    line: { color: COLORS.grid, width: 0.8 },
  });
  if (title) {
    slide.addText(title, {
      x: x + 0.14,
      y: y + 0.12,
      w: w - 0.28,
      h: 0.18,
      fontSize: 8.5,
      bold: true,
      color: COLORS.text,
      margin: 0,
    });
  }
}

function addKpi(slide, x, y, w, h, label, value, detail, accent = COLORS.cyan) {
  addPanel(slide, x, y, w, h);
  slide.addShape(pptx.ShapeType.rect, {
    x,
    y,
    w: 0.045,
    h,
    fill: { color: accent },
    line: { color: accent, transparency: 100 },
  });
  slide.addText(label, {
    x: x + 0.16,
    y: y + 0.13,
    w: w - 0.32,
    h: 0.2,
    fontSize: 8.5,
    color: COLORS.muted,
    bold: true,
    margin: 0,
  });
  slide.addText(value, {
    x: x + 0.16,
    y: y + 0.42,
    w: w - 0.32,
    h: 0.38,
    fontSize: 18,
    color: COLORS.text,
    bold: true,
    margin: 0,
    fit: "shrink",
  });
  slide.addText(detail, {
    x: x + 0.16,
    y: y + 0.88,
    w: w - 0.32,
    h: h - 0.95,
    fontSize: 7.6,
    color: COLORS.muted,
    margin: 0,
    fit: "shrink",
  });
}

function addBullets(slide, bullets, x, y, w, h, options = {}) {
  slide.addText(
    bullets.map((text) => ({ text, options: { bullet: { type: "bullet" }, breakLine: true } })),
    {
      x,
      y,
      w,
      h,
      fontSize: options.fontSize || 10.2,
      color: options.color || COLORS.text,
      margin: 0,
      breakLine: true,
      fit: "shrink",
      paraSpaceAfterPt: 7,
    }
  );
}

function addBar(slide, x, y, w, label, value, maxValue, color, suffix = "%") {
  const pctWidth = maxValue > 0 ? Math.max(0.02, Math.min(1, value / maxValue)) : 0;
  slide.addText(label, {
    x,
    y,
    w: 1.9,
    h: 0.18,
    fontSize: 8.5,
    color: COLORS.text,
    margin: 0,
    fit: "shrink",
  });
  slide.addShape(pptx.ShapeType.rect, {
    x: x + 2.05,
    y: y + 0.03,
    w,
    h: 0.12,
    fill: { color: "23313D" },
    line: { color: "23313D", transparency: 100 },
  });
  slide.addShape(pptx.ShapeType.rect, {
    x: x + 2.05,
    y: y + 0.03,
    w: w * pctWidth,
    h: 0.12,
    fill: { color },
    line: { color, transparency: 100 },
  });
  slide.addText(`${fmt(value, value >= 10 ? 1 : 2)}${suffix}`, {
    x: x + 2.05 + w + 0.14,
    y: y - 0.01,
    w: 0.72,
    h: 0.18,
    fontSize: 8,
    color: COLORS.muted,
    margin: 0,
  });
}

function addSource(slide, text) {
  slide.addText(text, {
    x: 0.55,
    y: 6.82,
    w: 12.1,
    h: 0.18,
    fontSize: 6.8,
    color: COLORS.muted,
    margin: 0,
    fit: "shrink",
  });
}

function newSlide(title, subtitle = "") {
  const slide = pptx.addSlide();
  addBg(slide);
  addTitle(slide, title, subtitle);
  addFooter(slide);
  return slide;
}

// 1. Title
{
  const slide = pptx.addSlide();
  addBg(slide);
  slide.addText("Japan Power Market Review", {
    x: 0.55,
    y: 0.55,
    w: 9.6,
    h: 0.62,
    fontSize: 30,
    fontFace: "Aptos Display",
    bold: true,
    color: COLORS.text,
    margin: 0,
  });
  slide.addText("May 2026 | JEPX structure, Tokyo/Kansai supply shape, fuel proxy screen", {
    x: 0.58,
    y: 1.25,
    w: 9.5,
    h: 0.35,
    fontSize: 13,
    color: COLORS.cyan,
    margin: 0,
  });
  addPanel(slide, 0.58, 2.05, 5.65, 2.05, "Desk read");
  slide.addText(
    "May screened as a shoulder-season easing month in the sample price data, but the operational read is more nuanced: Tokyo remained more thermal-exposed, while public JEPX stack data showed broad system balance with pockets of thin East/West area-group depth.",
    { x: 0.78, y: 2.48, w: 5.25, h: 0.9, fontSize: 13, bold: true, color: COLORS.text, margin: 0, fit: "shrink" }
  );
  addKpi(slide, 6.65, 2.05, 1.9, 1.25, "System sample avg", `${fmt(market("JEPX_SYSTEM").may_avg, 2)}`, "JPY/kWh, May", COLORS.cyan);
  addKpi(slide, 8.78, 2.05, 1.9, 1.25, "Tokyo premium", `+${fmt(metrics.spreads.tokyo_minus_kansai_may_avg, 2)}`, "JPY/kWh vs Kansai", COLORS.amber);
  addKpi(slide, 10.92, 2.05, 1.9, 1.25, "Stack scarcity", `${metrics.offer_stack_summary.scarcity_blocks}`, "System blocks", COLORS.red);
  addKpi(slide, 6.65, 3.55, 1.9, 1.25, "Tokyo residual", `${fmt(metrics.residual_thermal_summary.find((r) => r.area === "Tokyo").residual_thermal_share_pct, 1)}%`, "Thermal share", COLORS.orange);
  addKpi(slide, 8.78, 3.55, 1.9, 1.25, "Kansai nuclear", `${fmt(supply("Kansai", "Nuclear").share_pct, 1)}%`, "Generation share", COLORS.green);
  addKpi(slide, 10.92, 3.55, 1.9, 1.25, "Intraday volume", `${fmt(metrics.intraday_summary.avg_daily_volume_mwh / 1000, 1)}`, "GWh/day", COLORS.purple);
  slide.addText("Core evidence: processed JEPX offer-stack / intraday data and Tokyo-Kansai generation mix. Fuel, SRMC, futures, and weather are dashboard sample/proxy inputs unless replaced by vendor/uploaded data.", {
    x: 0.6,
    y: 5.7,
    w: 11.9,
    h: 0.36,
    fontSize: 8.5,
    color: COLORS.muted,
    margin: 0,
  });
  addFooter(slide);
}

// 2. Scope and confidence
{
  const slide = newSlide("Scope and Evidence Map", "May 1-31, 2026; offer-stack coverage begins May 3 in the processed public cache.");
  addPanel(slide, 0.55, 1.35, 3.85, 4.75, "Tier 1: report backbone");
  addBullets(slide, [
    "JEPX public day-ahead offer-stack depth and regime screens.",
    "JEPX public intraday trade, volume, contract, and range data.",
    "Processed Tokyo/Kansai generation mix, residual thermal, and daily shape.",
  ], 0.78, 1.83, 3.35, 2.25, { fontSize: 10 });
  slide.addText("Use for directional market-structure conclusions.", { x: 0.78, y: 5.3, w: 3.25, h: 0.25, fontSize: 8.6, color: COLORS.green, bold: true, margin: 0 });

  addPanel(slide, 4.75, 1.35, 3.85, 4.75, "Tier 2: dashboard proxy context");
  addBullets(slide, [
    "Sample historical power, fuel, FX, SRMC, and forward curves.",
    "Useful for workflow and relationship testing.",
    "Not settlement-grade marks or a substitute for broker/vendor curves.",
  ], 4.98, 1.83, 3.35, 2.55, { fontSize: 10 });
  slide.addText("Use for caveated screening only.", { x: 4.98, y: 5.3, w: 3.2, h: 0.25, fontSize: 8.6, color: COLORS.amber, bold: true, margin: 0 });

  addPanel(slide, 8.95, 1.35, 3.85, 4.75, "Tier 3: excluded from hard claims");
  addBullets(slide, [
    "Participant-level bidding behavior.",
    "Plant-level outage attribution unless linked to verified news/vendor data.",
    "Live order-book or current tradable futures levels.",
  ], 9.18, 1.83, 3.35, 2.55, { fontSize: 10 });
  slide.addText("Flag as future pipeline upgrades.", { x: 9.18, y: 5.3, w: 3.25, h: 0.25, fontSize: 8.6, color: COLORS.red, bold: true, margin: 0 });
  addSource(slide, "Sources referenced: JEPX day-ahead/intraday market data, JapanesePower.org regional datasets, OCCTO, METI/ANRE Strategic Energy Plan.");
}

// 3. Executive summary
{
  const slide = newSlide("Executive Summary", "Three analyst conclusions from the May dashboard run.");
  addPanel(slide, 0.55, 1.33, 3.9, 4.95, "1. System was buffered, not broadly scarce");
  addBullets(slide, [
    `System offer-stack scarcity flags were limited: ${metrics.offer_stack_summary.scarcity_blocks} scarcity blocks and ${metrics.offer_stack_summary.thin_blocks} thin blocks across ${metrics.offer_stack_summary.records.toLocaleString("en-US")} records.`,
    `Average system clearing estimate was ${fmt(metrics.offer_stack_summary.avg_clearing_estimate, 2)} JPY/kWh; average upside depth was ${fmt(metrics.offer_stack_summary.avg_upside_depth_mw / 1000, 1)} GW.`,
    "Market implication: focus on block-level scarcity, not a blanket May tightness story.",
  ], 0.78, 1.83, 3.4, 3.65, { fontSize: 9.8 });

  addPanel(slide, 4.75, 1.33, 3.9, 4.95, "2. Tokyo remained structurally tighter");
  addBullets(slide, [
    `Tokyo residual thermal share was ${fmt(metrics.residual_thermal_summary.find((r) => r.area === "Tokyo").residual_thermal_share_pct, 1)}% versus Kansai ${fmt(metrics.residual_thermal_summary.find((r) => r.area === "Kansai").residual_thermal_share_pct, 1)}%.`,
    `Tokyo evening thermal ramp averaged ${fmt(metrics.daily_shape_summary.find((r) => r.area === "Tokyo").avg_evening_thermal_ramp_mw / 1000, 1)} GW versus Kansai ${fmt(metrics.daily_shape_summary.find((r) => r.area === "Kansai").avg_evening_thermal_ramp_mw / 1000, 1)} GW.`,
    "Market implication: Tokyo area premia deserve monitoring into hotter load conditions.",
  ], 4.98, 1.83, 3.4, 3.65, { fontSize: 9.8 });

  addPanel(slide, 8.95, 1.33, 3.9, 4.95, "3. Fuel easing was not the whole story");
  addBullets(slide, [
    `Sample JKM fell ${fmt(market("JKM").mom_change_pct, 1)}% m/m and CFR Japan coal fell ${fmt(market("CFR_JAPAN_COAL").mom_change_pct, 1)}% m/m.`,
    `JEPX system sample averaged ${fmt(metrics.srmc_summary.jepx_vs_coal_srmc, 1)} JPY/kWh above coal SRMC and ${fmt(metrics.srmc_summary.jepx_vs_jkm_gas_srmc, 1)} above JKM gas SRMC.`,
    "Market implication: use the SRMC screen as a richness flag, then validate with real curves.",
  ], 9.18, 1.83, 3.4, 3.65, { fontSize: 9.8 });
}

// 4. Price and SRMC screen
{
  const slide = newSlide("Price and Fuel Screen", "Dashboard sample values indicate May fuel easing and softer average power, but these are proxy marks.");
  addKpi(slide, 0.55, 1.25, 2.25, 1.12, "JEPX system", `${fmt(market("JEPX_SYSTEM").may_avg, 2)}`, `${fmt(market("JEPX_SYSTEM").mom_change_pct, 1)}% m/m`, COLORS.cyan);
  addKpi(slide, 3.0, 1.25, 2.25, 1.12, "Tokyo", `${fmt(market("JEPX_TOKYO").may_avg, 2)}`, `${fmt(market("JEPX_TOKYO").mom_change_pct, 1)}% m/m`, COLORS.amber);
  addKpi(slide, 5.45, 1.25, 2.25, 1.12, "Kansai", `${fmt(market("JEPX_KANSAI").may_avg, 2)}`, `${fmt(market("JEPX_KANSAI").mom_change_pct, 1)}% m/m`, COLORS.green);
  addKpi(slide, 7.9, 1.25, 2.25, 1.12, "JKM", `${fmt(market("JKM").may_avg, 2)}`, `${fmt(market("JKM").mom_change_pct, 1)}% m/m`, COLORS.purple);
  addKpi(slide, 10.35, 1.25, 2.25, 1.12, "CFR Japan coal", `${fmt(market("CFR_JAPAN_COAL").may_avg, 1)}`, `${fmt(market("CFR_JAPAN_COAL").mom_change_pct, 1)}% m/m`, COLORS.orange);

  addPanel(slide, 0.55, 2.75, 5.85, 3.35, "SRMC richness screen");
  addBar(slide, 0.88, 3.3, 2.7, "Coal SRMC", metrics.srmc_summary.coal_srmc, 25, COLORS.orange, " JPY/kWh");
  addBar(slide, 0.88, 3.82, 2.7, "JKM gas SRMC", metrics.srmc_summary.jkm_gas_srmc, 25, COLORS.purple, " JPY/kWh");
  addBar(slide, 0.88, 4.34, 2.7, "JEPX system", metrics.srmc_summary.jepx_system, 25, COLORS.cyan, " JPY/kWh");
  slide.addText(`Screened premium: +${fmt(metrics.srmc_summary.jepx_vs_coal_srmc, 1)} JPY/kWh vs coal SRMC and +${fmt(metrics.srmc_summary.jepx_vs_jkm_gas_srmc, 1)} JPY/kWh vs JKM gas SRMC. Treat this as a relationship flag, not a dispatch claim.`, {
    x: 0.88,
    y: 5.04,
    w: 5.25,
    h: 0.45,
    fontSize: 9.2,
    color: COLORS.text,
    margin: 0,
    fit: "shrink",
  });

  addPanel(slide, 6.75, 2.75, 5.85, 3.35, "Analyst read");
  addBullets(slide, [
    "May fuel sample data points to lower variable-cost pressure, helped by softer LNG/coal and a firmer yen.",
    "Power averages fell m/m, but Tokyo stayed at a premium to Kansai.",
    "The useful trade question is not simply whether fuel fell, but which hours/areas failed to reprice as stack depth changed.",
  ], 7.0, 3.25, 5.3, 2.15, { fontSize: 10.5 });
}

// 5. Supply mix
{
  const slide = newSlide("Tokyo vs Kansai Supply Shape", "Processed monthly generation mix shows a structurally different residual thermal exposure.");
  addPanel(slide, 0.55, 1.25, 5.95, 4.9, "Monthly generation share");
  const types = ["Gas", "Coal", "Nuclear", "Solar", "Hydro", "Biomass", "Oil", "Wind"];
  const colorByType = { Gas: COLORS.blue, Coal: COLORS.orange, Nuclear: COLORS.green, Solar: COLORS.amber, Hydro: COLORS.cyan, Biomass: COLORS.red, Oil: COLORS.muted, Wind: COLORS.purple };
  ["Tokyo", "Kansai"].forEach((area, idx) => {
    const y = 2.0 + idx * 1.9;
    slide.addText(area, { x: 0.85, y: y - 0.28, w: 0.8, h: 0.2, fontSize: 9, bold: true, color: COLORS.text, margin: 0 });
    let x = 1.55;
    types.forEach((type) => {
      const row = supply(area, type);
      const share = row ? row.share_pct : 0;
      const width = Math.max(0.02, share / 100 * 4.25);
      slide.addShape(pptx.ShapeType.rect, {
        x,
        y,
        w: width,
        h: 0.42,
        fill: { color: colorByType[type] },
        line: { color: colorByType[type], transparency: 100 },
      });
      if (share > 9) {
        slide.addText(`${type} ${fmt(share, 0)}%`, { x: x + 0.04, y: y + 0.12, w: Math.max(0.3, width - 0.08), h: 0.15, fontSize: 6.5, color: COLORS.white, margin: 0, fit: "shrink" });
      }
      x += width;
    });
  });
  let lx = 0.85;
  types.forEach((type) => {
    slide.addShape(pptx.ShapeType.rect, { x: lx, y: 5.4, w: 0.12, h: 0.12, fill: { color: colorByType[type] }, line: { color: colorByType[type], transparency: 100 } });
    slide.addText(type, { x: lx + 0.16, y: 5.36, w: 0.55, h: 0.18, fontSize: 6.8, color: COLORS.muted, margin: 0, fit: "shrink" });
    lx += 0.68;
  });

  addPanel(slide, 6.85, 1.25, 5.75, 4.9, "Thermal reliance and shape risk");
  addBar(slide, 7.15, 2.0, 2.35, "Tokyo residual thermal", metrics.residual_thermal_summary.find((r) => r.area === "Tokyo").residual_thermal_share_pct, 70, COLORS.orange, "%");
  addBar(slide, 7.15, 2.52, 2.35, "Kansai residual thermal", metrics.residual_thermal_summary.find((r) => r.area === "Kansai").residual_thermal_share_pct, 70, COLORS.green, "%");
  addBar(slide, 7.15, 3.35, 2.35, "Tokyo solar midday", metrics.daily_shape_summary.find((r) => r.area === "Tokyo").avg_solar_midday_share_pct, 50, COLORS.amber, "%");
  addBar(slide, 7.15, 3.87, 2.35, "Kansai solar midday", metrics.daily_shape_summary.find((r) => r.area === "Kansai").avg_solar_midday_share_pct, 50, COLORS.amber, "%");
  slide.addText(`Tokyo evening thermal ramp averaged ${fmt(metrics.daily_shape_summary.find((r) => r.area === "Tokyo").avg_evening_thermal_ramp_mw / 1000, 1)} GW versus Kansai ${fmt(metrics.daily_shape_summary.find((r) => r.area === "Kansai").avg_evening_thermal_ramp_mw / 1000, 1)} GW. Kansai also carried ${fmt(metrics.daily_shape_summary.find((r) => r.area === "Kansai").total_renewable_curtailment_mwh / 1000, 1)} GWh of renewable curtailment in the processed shape file.`, {
    x: 7.15,
    y: 4.72,
    w: 5.0,
    h: 0.55,
    fontSize: 9.3,
    color: COLORS.text,
    margin: 0,
    fit: "shrink",
  });
  addSource(slide, "Source: processed Tokyo/Kansai generation monthly, residual thermal, and daily shape tables from JapanesePower.org regional public data.");
}

// 6. Offer stack
{
  const slide = newSlide("JEPX Offer-Stack Read", "Ex-post public stack curves show where depth was thin around clearing.");
  addKpi(slide, 0.55, 1.22, 2.6, 1.18, "System clearing estimate", `${fmt(systemStack.clearing, 2)}`, "JPY/kWh average", COLORS.cyan);
  addKpi(slide, 3.35, 1.22, 2.6, 1.18, "System tightest depth", `${fmt(systemStack.depth / 1000, 1)} GW`, "Average around clearing", COLORS.green);
  addKpi(slide, 6.15, 1.22, 2.6, 1.18, "Thin system blocks", `${fmt(systemStack.thin, 1)}%`, `${metrics.offer_stack_summary.thin_blocks} records`, COLORS.amber);
  addKpi(slide, 8.95, 1.22, 2.6, 1.18, "Scarcity system blocks", `${fmt(systemStack.scarcity, 2)}%`, `${metrics.offer_stack_summary.scarcity_blocks} records`, COLORS.red);

  addPanel(slide, 0.55, 2.72, 6.0, 3.35, "Selected benchmark area groups");
  addBar(slide, 0.9, 3.25, 2.5, "System avg clearing", systemStack.clearing, 25, COLORS.cyan, " JPY/kWh");
  addBar(slide, 0.9, 3.77, 2.5, "East/Tokyo group", eastStack.clearing, 25, COLORS.amber, " JPY/kWh");
  addBar(slide, 0.9, 4.29, 2.5, "West/Kansai group", westStack.clearing, 25, COLORS.green, " JPY/kWh");
  addBar(slide, 0.9, 5.03, 2.5, "East thin share", eastStack.thin, 65, COLORS.red, "%");
  addBar(slide, 0.9, 5.55, 2.5, "West thin share", westStack.thin, 65, COLORS.orange, "%");

  addPanel(slide, 6.9, 2.72, 5.7, 3.35, "Market interpretation");
  addBullets(slide, [
    "System balance was broadly adequate in May, but selected East/Tokyo and West/Kansai-linked area groups showed materially thinner local depth.",
    "Thin-stack flags matter most when they cluster in evening ramp or high-load blocks, because small demand/fuel/weather shocks can move clearing more sharply.",
    "For trading use, pair this view with block-level spreads and intraday convergence rather than treating one daily average as the signal.",
  ], 7.15, 3.22, 5.15, 2.45, { fontSize: 10.2 });
  addSource(slide, "Source: JEPX public bidding-curve/price-sensitivity data processed into offer-stack depth and regime screens.");
}

// 7. Intraday
{
  const slide = newSlide("Intraday Liquidity and Convergence", "Processed JEPX intraday data gives the best public read on short-term balancing behavior.");
  addKpi(slide, 0.55, 1.25, 2.5, 1.2, "Average price", `${fmt(metrics.intraday_summary.avg_price, 2)}`, "JPY/kWh, processed intraday", COLORS.cyan);
  addKpi(slide, 3.35, 1.25, 2.5, 1.2, "Daily volume", `${fmt(metrics.intraday_summary.avg_daily_volume_mwh / 1000, 1)} GWh`, "Average May session", COLORS.green);
  addKpi(slide, 6.15, 1.25, 2.5, 1.2, "Daily contracts", `${fmt(metrics.intraday_summary.avg_daily_contracts, 0)}`, "Average count", COLORS.purple);
  addKpi(slide, 8.95, 1.25, 2.5, 1.2, "High-low range", `${fmt(metrics.intraday_summary.avg_high_low_range, 1)}`, "JPY/kWh average", COLORS.amber);
  addPanel(slide, 0.55, 2.95, 5.85, 2.95, "Trading read");
  addBullets(slide, [
    "Healthy intraday volume means convergence signals are more useful than pure screen averages.",
    "Wide block ranges indicate pockets of balancing stress even when daily averages look benign.",
    "Next upgrade: chart block-level spot-intraday spread by hour group and flag repeated late-day divergence.",
  ], 0.85, 3.43, 5.25, 1.9, { fontSize: 10.3 });
  addPanel(slide, 6.75, 2.95, 5.85, 2.95, "Data note");
  slide.addText("The deck uses processed intraday public data for this page. The sample historical table contains a different JEPX intraday average, so it should not be mixed with this public-data metric until the pipeline is reconciled.", {
    x: 7.05,
    y: 3.43,
    w: 5.25,
    h: 1.35,
    fontSize: 11,
    color: COLORS.text,
    margin: 0,
    fit: "shrink",
  });
  addSource(slide, "Source: JEPX public intraday CSV processed into daily price, volume, contracts, and high-low range summary.");
}

// 8. Weather and policy setup
{
  const slide = newSlide("Weather and Early Summer Setup", "May was more a shoulder-season structure month than a heat-load stress month.");
  addKpi(slide, 0.55, 1.25, 2.45, 1.18, "Tokyo temp", `${fmt(metrics.weather_summary.find((r) => r.region === "Tokyo").avg_temp_c, 1)} C`, "Average sample weather", COLORS.cyan);
  addKpi(slide, 3.25, 1.25, 2.45, 1.18, "Kansai temp", `${fmt(metrics.weather_summary.find((r) => r.region === "Kansai").avg_temp_c, 1)} C`, "Average sample weather", COLORS.green);
  addKpi(slide, 5.95, 1.25, 2.45, 1.18, "Tokyo CDD", `${fmt(metrics.weather_summary.find((r) => r.region === "Tokyo").cooling_degree_days, 1)}`, "Low heat signal", COLORS.amber);
  addKpi(slide, 8.65, 1.25, 2.45, 1.18, "Kansai CDD", `${fmt(metrics.weather_summary.find((r) => r.region === "Kansai").cooling_degree_days, 1)}`, "Low heat signal", COLORS.amber);
  addPanel(slide, 0.55, 2.95, 5.9, 3.05, "Why this matters for June-August");
  addBullets(slide, [
    "May did not yet test summer cooling load, so stack-depth and ramp screens are the better early warning tools.",
    "OCCTO's public materials point to peak-demand/capacity monitoring as the key summer reliability frame.",
    "METI's energy plan reinforces the importance of thermal capacity for balancing renewable volatility, even as Japan targets more renewables and nuclear.",
  ], 0.85, 3.42, 5.25, 2.1, { fontSize: 9.8 });
  addPanel(slide, 6.75, 2.95, 5.85, 3.05, "Analyst watchlist");
  addBullets(slide, [
    "Tokyo evening ramp depth versus weather-normal demand.",
    "Kansai nuclear availability and renewable curtailment risk.",
    "Spot-intraday convergence during high solar and late-day ramp blocks.",
    "Fuel curve repricing if LNG/coal softness reverses.",
  ], 7.05, 3.42, 5.2, 2.1, { fontSize: 10.2 });
  addSource(slide, "Sources: dashboard weather proxy, OCCTO public supply-demand role/outlook, METI/ANRE 7th Strategic Energy Plan outline.");
}

// 9. Trading interpretation
{
  const slide = newSlide("Trading Interpretation", "Actionable themes to monitor, without making black-box predictive claims.");
  addPanel(slide, 0.55, 1.25, 3.9, 4.95, "Relative value");
  addBullets(slide, [
    "System price screened rich to fuel SRMC proxies despite softer fuel inputs.",
    "Do not trade the sample SRMC level directly; use it to prioritize spread checks after loading real curves.",
    "Watch for power underreaction if LNG/coal rallies into early summer.",
  ], 0.8, 1.72, 3.35, 3.15, { fontSize: 10.2 });
  slide.addText("Trader takeaway: validate fuel-to-power transmission with real fuel curves and hour/block power marks.", { x: 0.8, y: 5.25, w: 3.25, h: 0.42, fontSize: 8.5, color: COLORS.cyan, bold: true, margin: 0, fit: "shrink" });

  addPanel(slide, 4.75, 1.25, 3.9, 4.95, "Regional structure");
  addBullets(slide, [
    "Tokyo premium persisted and the area is more residual-thermal exposed.",
    "Kansai has more nuclear support, but renewable curtailment and evening ramp still matter.",
    "Monitor Tokyo-Kansai spread against East/West area-stack thinness.",
  ], 5.0, 1.72, 3.35, 3.15, { fontSize: 10.2 });
  slide.addText("Trader takeaway: regional spread risk should be read through supply shape, not just daily average prices.", { x: 5.0, y: 5.25, w: 3.25, h: 0.42, fontSize: 8.5, color: COLORS.amber, bold: true, margin: 0, fit: "shrink" });

  addPanel(slide, 8.95, 1.25, 3.9, 4.95, "Market structure");
  addBullets(slide, [
    "System offer-stack was mostly balanced, but local thin-stack flags were meaningful.",
    "Intraday range remained wide enough to justify block-level convergence monitoring.",
    "The better signal is a repeated pattern: thin stack + wide intraday range + weather/ramp stress.",
  ], 9.2, 1.72, 3.35, 3.15, { fontSize: 10.2 });
  slide.addText("Trader takeaway: escalate from daily dashboards to block-level review when those three conditions align.", { x: 9.2, y: 5.25, w: 3.25, h: 0.42, fontSize: 8.5, color: COLORS.green, bold: true, margin: 0, fit: "shrink" });
}

// 10. Upgrade path
{
  const slide = newSlide("Caveats and Upgrade Path", "What must be strengthened before this is treated as a production trading pack.");
  addPanel(slide, 0.55, 1.25, 5.9, 4.9, "Limitations");
  addBullets(slide, [
    "Fuel, SRMC, power futures, and forward curves are sample/proxy values unless replaced by uploaded/vendor/broker data.",
    "Offer-stack analytics are ex-post public aggregate curves; they are not participant-level bids or a live order book.",
    "No May 2026 baseload trade-date rows were found in the current processed baseload cache.",
    "News pipeline did not return May rows in the local sample news table.",
  ], 0.85, 1.78, 5.25, 3.35, { fontSize: 10.1 });
  addPanel(slide, 6.75, 1.25, 5.85, 4.9, "Highest-value next improvements");
  addBullets(slide, [
    "Load JSCC/JEPX futures or broker curves for Tokyo/Kansai baseload and peakload.",
    "Add verified plant availability, nuclear restart/outage, and solar/renewables pipeline news tagging.",
    "Reconcile intraday metrics so the sample historical table and processed public table use one definition.",
    "Publish a monthly pack template with automated data confidence flags.",
  ], 7.05, 1.78, 5.25, 3.35, { fontSize: 10.1 });
}

// 11. Source notes
{
  const slide = newSlide("Sources", "Public references and local files used in the May review.");
  addPanel(slide, 0.55, 1.25, 12.05, 5.45, "References");
  addBullets(slide, [
    "JEPX day-ahead market data: public price/volume, bidding curve, price sensitivity, and download pages.",
    "JEPX intraday market data: public intraday price, volume, contracts, and download pages.",
    "JapanesePower.org: public regional half-hourly demand and generation mix archives used by the processed dashboard tables.",
    "OCCTO: public role and supply-demand monitoring context, including system reliability and capacity-market framing.",
    "METI/ANRE 7th Strategic Energy Plan outline: 2040 electricity demand, renewable, nuclear, and thermal policy context.",
    "Local dashboard files: local_metrics_may_2026.json, processed JEPX offer-stack/intraday tables, and Tokyo/Kansai supply mix tables.",
  ], 0.9, 1.78, 11.2, 3.75, { fontSize: 10.2 });
  slide.addText("This slide deck is a market-intelligence screen, not investment advice and not a settlement-grade price publication.", {
    x: 0.9,
    y: 6.08,
    w: 11.2,
    h: 0.28,
    fontSize: 8.5,
    color: COLORS.amber,
    bold: true,
    margin: 0,
  });
}

const md = `# Japan Power Market Review - May 2026

Generated: 2026-06-10

## Headline

May screened as a shoulder-season easing month in the dashboard sample price data, but the operational read is more nuanced: Tokyo remained more thermal-exposed, while public JEPX stack data showed broad system balance with pockets of thin East/West area-group depth.

## Core conclusions

- System offer-stack scarcity flags were limited: ${metrics.offer_stack_summary.scarcity_blocks} scarcity blocks and ${metrics.offer_stack_summary.thin_blocks} thin blocks across ${metrics.offer_stack_summary.records.toLocaleString("en-US")} system records.
- Tokyo stayed structurally tighter than Kansai: residual thermal share was ${fmt(metrics.residual_thermal_summary.find((r) => r.area === "Tokyo").residual_thermal_share_pct, 1)}% versus Kansai ${fmt(metrics.residual_thermal_summary.find((r) => r.area === "Kansai").residual_thermal_share_pct, 1)}%.
- Processed intraday data showed ${fmt(metrics.intraday_summary.avg_daily_volume_mwh / 1000, 1)} GWh/day of average volume and a ${fmt(metrics.intraday_summary.avg_high_low_range, 1)} JPY/kWh average high-low range, supporting block-level convergence monitoring.
- Dashboard sample fuel data eased in May: JKM ${fmt(market("JKM").mom_change_pct, 1)}% m/m and CFR Japan coal ${fmt(market("CFR_JAPAN_COAL").mom_change_pct, 1)}% m/m. Treat this as proxy context unless replaced by vendor/uploaded curves.

## Caveats

- Fuel, SRMC, weather, power futures, and forward curves are sample/proxy values unless explicitly replaced by uploaded or vendor data.
- Offer-stack analytics are ex-post public aggregate curves and do not identify participants or plant-level bidding behavior.
- No May 2026 baseload trade-date rows were found in the processed baseload cache.
- The local news sample table did not contain May 2026 rows.

## Sources

- JEPX day-ahead market data: https://www.jepx.jp/en/electricpower/market-data/spot/
- JEPX intraday market data: https://www.jepx.jp/en/electricpower/market-data/intraday/
- JapanesePower.org: https://japanesepower.org/
- OCCTO: https://www.occto.or.jp/en/
- OCCTO articles/business plans: https://www.occto.or.jp/en/about_occto/articles/index.html
- METI/ANRE Strategic Energy Plan: https://www.enecho.meti.go.jp/en/category/others/basic_plan/
`;

const sourceNotes = `Japan Power Market Review - May 2026 source notes

Public web references used:
- JEPX spot/day-ahead market data: https://www.jepx.jp/en/electricpower/market-data/spot/
- JEPX intraday market data: https://www.jepx.jp/en/electricpower/market-data/intraday/
- JapanesePower.org regional public datasets: https://japanesepower.org/
- OCCTO English site: https://www.occto.or.jp/en/
- OCCTO articles/business plans: https://www.occto.or.jp/en/about_occto/articles/index.html
- METI/ANRE Strategic Energy Plan page: https://www.enecho.meti.go.jp/en/category/others/basic_plan/

Local files used:
- reports/japan_power_may_2026/local_metrics_may_2026.json
- data/processed/jepx_offer_stack_depth.csv
- data/processed/jepx_intraday_latest.csv
- data/processed/tokyo_kansai_generation_monthly.csv
- data/processed/tokyo_kansai_residual_thermal.csv
- data/processed/tokyo_kansai_generation_daily_shape.csv
- data/sample_historical_prices.csv
- data/sample_forward_curves.csv
- data/sample_power_futures.csv
`;

fs.writeFileSync(path.join(REPORT_DIR, "japan_power_market_may_2026_report.md"), md);
fs.writeFileSync(path.join(REPORT_DIR, "source_notes.md"), sourceNotes);

pptx
  .writeFile({ fileName: path.join(REPORT_DIR, "japan_power_market_may_2026_report.pptx") })
  .then(() => {
    console.log("Wrote japan_power_market_may_2026_report.pptx");
  });

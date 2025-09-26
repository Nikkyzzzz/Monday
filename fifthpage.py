import streamlit as st
import streamlit_antd_components as sac
import pandas as pd
import altair as alt
from io import BytesIO
from pathlib import Path
import base64
import streamlit.components.v1 as components

import logic6

LEFT_LOGO_PATH = "logo.png"
CATEGORIES_ORDER = ("P2P", "O2C", "H2R")


# ---------------- Utility helpers (copied from secondpage) ---------------- #

def _data_uri(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    suffix = p.suffix.lower()
    mime = "image/png" if suffix == ".png" else ("image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png")
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"

def _scroll_to_brand_if_needed(s):
    if s.pop("_force_scroll_top", False):
        components.html(
            """
            <script>
            (function(){
              function go(){
                try{
                  const doc = window.parent && window.parent.document ? window.parent.document : document;
                  const el = doc.getElementById("__ab_header__");
                  if(el && el.scrollIntoView){
                    el.scrollIntoView({block:"start", inline:"nearest"});
                  } else {
                    (window.parent||window).scrollTo(0,0);
                  }
                }catch(e){ (window.parent||window).scrollTo(0,0); }
              }
              go(); setTimeout(go, 50); setTimeout(go, 150); setTimeout(go, 300); setTimeout(go, 600);
            })();
            </script>
            """,
            height=0,
        )

# ---------------- Existing helpers (unchanged) ---------------- #

def _codes_for_category(cat: str):
    return [code for code, (c, _) in logic6.PROCESS_TITLES.items() if c == cat]

def _present_categories_from_selection(selected_codes: list[str]) -> list[str]:
    if not selected_codes:
        return []
    cats = {logic6.PROCESS_TITLES[c][0] for c in selected_codes if c in logic6.PROCESS_TITLES}
    return [c for c in CATEGORIES_ORDER if c in cats]

def _dynamic_menu_items_selected(cats_present: list[str], selected_codes: set[str]):
    items = [sac.MenuItem("All", icon="grid")]
    for cat in cats_present:
        children = [sac.MenuItem(f"All ({cat})")]
        for code, (c, pname) in logic6.PROCESS_TITLES.items():
            if c != cat:
                continue
            if selected_codes and code not in selected_codes:
                continue
            children.append(sac.MenuItem(pname))
        icon = "layers" if cat == "P2P" else ("truck" if cat == "O2C" else "person")
        items.append(sac.MenuItem(cat, icon=icon, children=children))
    return items

def _parse_choice(choice: str):
    if choice in (None, "", "All"):
        return ("all", None)
    if choice in (f"All ({c})" for c in CATEGORIES_ORDER):
        cat = choice.split("(")[-1].split(")")[0]
        return ("category", cat)
    if choice in CATEGORIES_ORDER:
        return ("category", choice)
    code = logic6.PROC_BY_NAME.get(choice)
    if code:
        return ("bot", code)
    return ("all", None)

def _ensure_bot_col(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    if "Bot" in df.columns:
        return df
    if "Bots" in df.columns:
        return df.rename(columns={"Bots": "Bot"})
    return df

def _build_enriched_summary(proc_status: dict, results: dict, cats_present: list[str], only_codes: set[str] | None) -> pd.DataFrame:
    LOGIC_DESCRIPTIONS = {
        "P2P1": "Identified rows where vendor fields (PAN, GST, Bank Account) were missing and marked them in an Exception Noted column.",
        "P2P2": "Detected quantity and amount mismatches between PO, GRN, and Invoice records and computed financial impact per PO.",
        "P2P3": "Extracted POs where PO Date was later than Invoice Date, marking them as invalid.",
        "P2P4": "Flagged cases where a vendor had multiple POs for the same item on the same date with combined invoice value above the threshold.",
        "P2P5": "Detected duplicate vendor records by PAN, GST, Name, or Bank Account and listed row pairs with exceptions.",
        "O2C1": "Flagged sales orders where delivery was delayed beyond the allowed threshold.",
        "O2C2": "Detected cases where goods were dispatched but no invoice was issued.",
        "O2C3": "Identified customers with missing GST, PAN, or Credit Limit and flagged them.",
        "H2R1": "Identified employees with attendance records but no entry in the Employee Master, i.e., ghost employees.",
        "H2R2": "Flagged employees who continued to appear as present after their recorded exit date.",
    }
    DATA_USED = {
        "P2P1": "Vendor Master",
        "P2P2": "P2P Sample",
        "P2P3": "P2P Sample",
        "P2P4": "P2P Sample",
        "P2P5": "Vendor Master",
        "O2C1": "O2C Sample",
        "O2C2": "O2C Sample",
        "O2C3": "Customer Master",
        "H2R1": "Employee Master, Attendance Register",
        "H2R2": "Employee Master, Attendance Register",
    }

    rows = []
    allowed = set(only_codes or [])
    for code, (cat, bot_name) in logic6.PROCESS_TITLES.items():
        if cat not in cats_present:
            continue
        if allowed and code not in allowed:
            continue
        cnt = logic6.issues_count_for(code, results.get(code))
        rows.append({
            "Bot": bot_name,
            "Category": cat,
            "Data Used": DATA_USED.get(code, ""),
            "Logic Description": LOGIC_DESCRIPTIONS.get(code, ""),
            "Issues Found": int(cnt),
            "Status": proc_status.get(code, "Pending"),
            "_code": code,
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df[["Bot", "Category", "Data Used", "Logic Description", "Issues Found", "Status", "_code"]]
    return df

def _build_detailed_report_excel(
    cats_present: list[str],
    proc_status: dict,
    results: dict,
    vendor_raw: pd.DataFrame | None,
    p2p_raw: pd.DataFrame | None,
    emp_raw: pd.DataFrame | None,
    file_bytes: bytes | None,
    only_codes: set[str] | None
) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        summary_df = _build_enriched_summary(proc_status, results, cats_present, only_codes)
        if summary_df is None or summary_df.empty:
            summary_df = logic6.build_summary_df(proc_status, results)
            summary_df = _ensure_bot_col(summary_df)
            if summary_df is not None and not summary_df.empty:
                summary_df = summary_df[summary_df["Category"].isin(cats_present)]
                if only_codes:
                    wanted_names = {logic6.PROCESS_TITLES[c][1] for c in only_codes if c in logic6.PROCESS_TITLES}
                    summary_df = summary_df[summary_df["Bot"].isin(wanted_names)]
        if summary_df is None:
            summary_df = pd.DataFrame()
        summary_df.to_excel(writer, sheet_name="Summary", index=False)

        for cat in cats_present:
            for code in _codes_for_category(cat):
                if only_codes and code not in only_codes:
                    continue
                df = results.get(code)
                if df is not None and not df.empty:
                    _, pname = logic6.PROCESS_TITLES[code]
                    sheet_name = f"{cat}_{pname[:20]}"
                    pd.DataFrame([{"Total Records": len(df)}]).to_excel(writer, sheet_name=sheet_name, index=False, startrow=0)
                    df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=2)

                    if code == "P2P1" and vendor_raw is not None and p2p_raw is not None:
                        try:
                            logic6.anomalies_by_creator(vendor_raw).to_excel(writer, sheet_name="P2P1_Anomalies", index=False)
                        except Exception:
                            pass
                        try:
                            logic6.merge_missing_with_duplicates(vendor_raw, p2p_raw).to_excel(writer, sheet_name="P2P1_MissingDup", index=False)
                        except Exception:
                            pass

                    if code == "P2P2" and results.get("P2P2") is not None and p2p_raw is not None and emp_raw is not None:
                        try:
                            item_sum, dept_sum = logic6.summarize_mismatches(results["P2P2"], p2p_raw, emp_raw)
                            item_sum.to_excel(writer, sheet_name="P2P2_ItemSummary", index=False)
                            dept_sum.to_excel(writer, sheet_name="P2P2_DeptSummary", index=False)
                        except Exception:
                            pass
                        try:
                            logic6.calculate_financial_impact_df(results["P2P2"]).to_excel(writer, sheet_name="P2P2_FinImpact", index=False)
                        except Exception:
                            pass

                    if code == "P2P3" and results.get("P2P3") is not None:
                        try:
                            item_counts, creator_counts = logic6.next_level_analytics(results["P2P3"])
                            item_counts.to_excel(writer, sheet_name="P2P3_ItemIssues", index=False)
                            creator_counts.to_excel(writer, sheet_name="P2P3_CreatorIssues", index=False)
                        except Exception:
                            pass
                        try:
                            logic6.financial_impact(results["P2P3"]).to_excel(writer, sheet_name="P2P3_FinImpact", index=False)
                        except Exception:
                            pass

                    if code == "P2P5" and file_bytes is not None:
                        try:
                            detailed = df
                            # FIX: pass variable3 instead of 'threshold'
                            fy_sum, fy_detail = logic6.vendor_year_threshold_alerts(
                                detailed,
                                BytesIO(file_bytes),
                                sheet_name="P2P_Sample (Bots 1-20)",
                                variable3=50_000
                            )
                            day_sum, day_detail = logic6.vendor_daily_threshold_alerts(
                                detailed,
                                BytesIO(file_bytes),
                                sheet_name="P2P_Sample (Bots 1-20)",
                                variable4=10_000
                            )
                            fy_sum.to_excel(writer, sheet_name="P2P5_FY_Summary", index=False)
                            if fy_detail is not None and not fy_detail.empty:
                                fy_detail.to_excel(writer, sheet_name="P2P5_FY_Detail", index=False)
                            day_sum.to_excel(writer, sheet_name="P2P5_Daily_Summary", index=False)
                            if day_detail is not None and not day_detail.empty:
                                day_detail.to_excel(writer, sheet_name="P2P5_Daily_Detail", index=False)
                        except Exception:
                            pass

    output.seek(0)
    return output.getvalue()

def render_fifth():
    s = st.session_state
    st.set_page_config(layout="wide")

    # Apply CSS branding like secondpage.py
    st.markdown(
        """
        <style>
          .ab-wrap * { font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial !important; }
          .ab-title { font-weight:860; letter-spacing:.02em; background:linear-gradient(90deg,#1e3a8a 0%,#60a5fa 100%);
                      -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; color:transparent;
                      font-size:clamp(30px,3.2vw,38px); line-height:1.05; }
          .ab-underline { height:8px; border-radius:9999px; background:#ff7636; margin-top:8px; width:320px; max-width:30vw; }
          .ab-subtitle { margin-top:10px; font-weight:700; color:#0f172a; font-size:clamp(16px,1.6vw,20px); }
          .ab-section-title { margin-top:20px; font-weight:700; color:#0f172a; font-size:20px; }
          .ab-spacer { height: 1.2em; }
          .hdr-grid { display:grid; grid-template-columns:268px 1fr; align-items:center; column-gap:16px; margin-bottom:8px; }
          .hdr-brand { display:flex; justify-content:flex-end; align-items:center; height:168px; position:relative; }
          #__ab_header__ { scroll-margin-top: 96px; }
          @media (max-width: 640px){ #__ab_header__{ scroll-margin-top: 120px; } }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="ab-wrap">', unsafe_allow_html=True)

    logo_src = _data_uri(LEFT_LOGO_PATH)
    st.markdown(
        f"""
        <div id="__ab_header__">
          <div class="hdr-grid">
            <div class="hdr-logo" style="width:268px;">
              {'<img src="' + logo_src + '" width="154" height="100" alt="Logo" style="display:block;" />' if logo_src else ''}
            </div>
            <div class="hdr-brand" style="text-align:right;">
              <div>
                <div class="ab-title">Audit&nbsp;Bots</div>
                <div class="ab-underline" style="margin-left:auto;"></div>
                <div class="ab-subtitle">Dashboard</div>
              </div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="ab-spacer"></div>', unsafe_allow_html=True)
    _scroll_to_brand_if_needed(s)

    if not s.get("processing_done"):
        st.warning("No processed results found. Please run processing first.")
        if st.button("⟵ Back to Processing", key="go_processing_btn"):
            s.page = "processpage"; st.rerun()
        return

    results     = s.get("results", {})
    proc_status = s.get("proc_status", {})

    selected_codes = list(s.get("selected_bots", []) or [])
    selected_set   = set(selected_codes)

    cats_from_mapping = [c for c in CATEGORIES_ORDER if c in (s.sheet_mapping_pairs or {})]
    if selected_set:
        cats_present = _present_categories_from_selection(selected_codes)
    else:
        cats_present = cats_from_mapping

    if not cats_present:
        st.info("No categories/bots were selected to display.")
        if st.button("⟵ Back to Selection"):
            s.page = "selectionpage"; st.rerun()
        return

    menu_items = _dynamic_menu_items_selected(cats_present, selected_set)
    with st.sidebar:
        choice = sac.menu(items=menu_items, open_all=True, indent=16)

    sel_mode, sel_value = _parse_choice(choice)

    tabs = st.tabs(["Analysis", "Output", "Report"])

    with tabs[0]:
        st.subheader("Summary Overview")
        summary = _build_enriched_summary(proc_status, results, cats_present, only_codes=selected_set if selected_set else None)
        if sel_mode == "category" and sel_value:
            summary = summary[summary["Category"] == sel_value]
        elif sel_mode == "bot" and sel_value:
            summary = summary[summary["_code"] == sel_value]
        cols = [c for c in summary.columns if c != "_code"]
        st.dataframe(summary[cols].reset_index(drop=True), use_container_width=True)

        st.subheader("Issues Per Bot")
        if not summary.empty:
            chart = (
                alt.Chart(summary)
                .mark_bar()
                .encode(
                    x=alt.X("Issues Found:Q", title="Issues Found"),
                    y=alt.Y("Bot:N", sort=None, title="Bots", axis=alt.Axis(labelAngle=0)),
                    color="Category:N",
                    tooltip=["Bot", "Category", "Data Used", "Logic Description", "Issues Found", "Status"],
                )
                .properties(height=350)
            )
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No data to plot for the current selection.")

    def _render_bot_output(code: str):
        cat, pname = logic6.PROCESS_TITLES[code]
        status = proc_status.get(code, "Pending")
        st.markdown(f"### {cat} — {pname}")
        if status == "Failed":
            st.warning("Process Failed")
            return

        raw = s.get("raw_dfs") or {}
        vendor_raw = raw.get("VENDOR_RAW")
        p2p_raw    = raw.get("P2P_RAW")
        emp_p2p    = raw.get("EMP_P2P_RAW")
        emp_legacy = raw.get("EMP_RAW")
        emp_raw    = emp_p2p if emp_p2p is not None else emp_legacy

        df = results.get(code, pd.DataFrame())
        if df is None or df.empty:
            st.info("No issues found.")
        else:
            st.markdown(f"**Total records:** {len(df)}")
            st.dataframe(df, use_container_width=True)

        if code == "P2P1":
            sub_tabs = st.tabs(["**Anomalies by Creator**", "**Missing Vendors × Duplicate Invoices**"])
            with sub_tabs[0]:
                if vendor_raw is not None:
                    try:
                        a1 = logic6.anomalies_by_creator(vendor_raw)
                        st.dataframe(a1 if not a1.empty else pd.DataFrame({"Info":["No anomalies by Creator_ID."]}), use_container_width=True)
                    except Exception as e:
                        st.error(str(e))
                else:
                    st.info("Raw Vendor sheet not available for analysis.")
            with sub_tabs[1]:
                if vendor_raw is not None and p2p_raw is not None:
                    try:
                        a2 = logic6.merge_missing_with_duplicates(vendor_raw, p2p_raw)
                        st.dataframe(a2 if not a2.empty else pd.DataFrame({"Info":["No intersection between missing vendors and duplicate invoices."]}), use_container_width=True)
                    except Exception as e:
                        st.error(str(e))
                else:
                    st.info("Required raw sheets not available for analysis.")

        if code == "P2P2":
            sub_tabs = st.tabs(["**Item & Department Summary**", "**Financial Impact**"])
            with sub_tabs[0]:
                if results.get("P2P2") is not None and not results["P2P2"].empty and p2p_raw is not None and emp_raw is not None:
                    try:
                        item_sum, dept_sum = logic6.summarize_mismatches(results["P2P2"], p2p_raw, emp_raw)
                        st.write("Item-wise Summary")
                        st.dataframe(item_sum if not item_sum.empty else pd.DataFrame({"Info":["No item-wise mismatches."]}), use_container_width=True)
                        st.write("Department-wise Summary")
                        st.dataframe(dept_sum if not dept_sum.empty else pd.DataFrame({"Info":["No department-wise mismatches or missing Department mapping."]}), use_container_width=True)
                    except Exception as e:
                        st.error(str(e))
                else:
                    st.info("Mismatch result or required raw sheets (P2P, Employee Master) not available.")
            with sub_tabs[1]:
                if results.get("P2P2") is not None and not results["P2P2"].empty:
                    try:
                        fi = logic6.calculate_financial_impact_df(results["P2P2"])
                        st.dataframe(fi, use_container_width=True)
                    except Exception as e:
                        st.error(str(e))
                else:
                    st.info("Mismatch result not available.")

        if code == "P2P3":
            inv = results.get("P2P3")
            sub_tabs = st.tabs(["**Item-wise & Creator-wise Issues**", "**Total Financial Impact**"])
            with sub_tabs[0]:
                if inv is not None and not inv.empty:
                    try:
                        item_counts, creator_counts = logic6.next_level_analytics(inv)
                        st.write("Item-wise Issues")
                        st.dataframe(item_counts if not item_counts.empty else pd.DataFrame({"Info":["No item-wise issues."]}), use_container_width=True)
                        st.write("Creator-wise Issues")
                        st.dataframe(creator_counts if not creator_counts.empty else pd.DataFrame({"Info":["No creator-wise issues."]}), use_container_width=True)
                    except Exception as e:
                        st.error(str(e))
                else:
                    st.info("No invalid rows available for analysis.")
            with sub_tabs[1]:
                if inv is not None and not inv.empty:
                    try:
                        st.dataframe(logic6.financial_impact(inv), use_container_width=True)
                    except Exception as e:
                        st.error(str(e))
                else:
                    st.info("No invalid rows available for analysis.")

        if code == "P2P4":
            sub_tabs = st.tabs(["**Self-Approved Over Threshold**"])
            with sub_tabs[0]:
                if p2p_raw is not None and not p2p_raw.empty:
                    try:
                        res = logic6.generate_self_approved_over_threshold(p2p_raw)
                        st.dataframe(res if not res.empty else pd.DataFrame({"Info":["No self-approved POs over threshold."]}), use_container_width=True)
                    except Exception as e:
                        st.error(str(e))
                else:
                    st.info("Raw P2P sheet not available for analysis.")

        if code == "P2P5":
            sub_tabs = st.tabs(["**FY Threshold Alerts**", "**Daily Threshold Alerts**"])
            with sub_tabs[0]:
                detailed = results.get("P2P5", pd.DataFrame())
                if detailed is None or detailed.empty or s.get('file_bytes') is None:
                    st.info("Duplicate pairs or original workbook not available.")
                else:
                    try:
                        # FIX: pass variable3 instead of 'threshold'
                        fy_sum, fy_detail = logic6.vendor_year_threshold_alerts(
                            detailed,
                            BytesIO(s.file_bytes),
                            sheet_name="P2P_Sample (Bots 1-20)",
                            variable3=50_000
                        )
                        st.write("Alerts Summary")
                        st.dataframe(fy_sum if not fy_sum.empty else pd.DataFrame({"Info":["No FY alerts over threshold."]}), use_container_width=True)
                        if fy_detail is not None and not fy_detail.empty:
                            st.write("Alerts Detail")
                            st.dataframe(fy_detail, use_container_width=True)
                    except Exception as e:
                        st.error(str(e))
            with sub_tabs[1]:
                detailed = results.get("P2P5", pd.DataFrame())
                if detailed is None or detailed.empty or s.get('file_bytes') is None:
                    st.info("Duplicate pairs or original workbook not available.")
                else:
                    try:
                        # FIX: pass variable4 instead of 'threshold'
                        day_sum, day_detail = logic6.vendor_daily_threshold_alerts(
                            detailed,
                            BytesIO(s.file_bytes),
                            sheet_name="P2P_Sample (Bots 1-20)",
                            variable4=10_000
                        )
                        st.write("Alerts Summary")
                        st.dataframe(day_sum if not day_sum.empty else pd.DataFrame({"Info":["No daily alerts over threshold."]}), use_container_width=True)
                        if day_detail is not None and not day_detail.empty:
                            st.write("Alerts Detail")
                            st.dataframe(day_detail, use_container_width=True)
                    except Exception as e:
                        st.error(str(e))

    with tabs[1]:
        st.subheader("Output")
        if sel_mode == "all":
            codes = [c for cat in cats_present for c in _codes_for_category(cat)]
            if selected_set:
                codes = [c for c in codes if c in selected_set]
            any_ok = False
            for code in codes:
                if proc_status.get(code) == "Complete":
                    any_ok = True
                    _render_bot_output(code)
            if not any_ok:
                st.info("No completed outputs for the current selection.")
        elif sel_mode == "category" and sel_value:
            codes = [c for c in _codes_for_category(sel_value)]
            if selected_set:
                codes = [c for c in codes if c in selected_set]
            any_ok = False
            for code in codes:
                if proc_status.get(code) == "Complete":
                    any_ok = True
                    _render_bot_output(code)
            if not any_ok:
                st.info("No completed outputs for the current selection.")
        elif sel_mode == "bot" and sel_value:
            _render_bot_output(sel_value)

    with tabs[2]:
        st.subheader("Report")

        def _line_for(code: str):
            cat, pname = logic6.PROCESS_TITLES[code]
            status = proc_status.get(code, "Pending")
            if status == "Failed":
                return f"- **{cat} / {pname}** — Process Failed"
            cnt = logic6.issues_count_for(code, results.get(code))
            msg = "No issues found" if cnt == 0 else f"Issues Found: {cnt}"
            return f"- **{cat} / {pname}** — {msg}"

        if sel_mode == "all":
            codes = [c for cat in cats_present for c in _codes_for_category(cat)]
            if selected_set:
                codes = [c for c in codes if c in selected_set]
            for code in codes:
                st.markdown(_line_for(code))
        elif sel_mode == "category" and sel_value:
            codes = [c for c in _codes_for_category(sel_value)]
            if selected_set:
                codes = [c for c in codes if c in selected_set]
            for code in codes:
                st.markdown(_line_for(code))
        elif sel_mode == "bot" and sel_value:
            st.markdown(_line_for(sel_value))

        raw = s.get("raw_dfs") or {}
        emp_p2p_raw = raw.get("EMP_P2P_RAW")
        emp_legacy_raw = raw.get("EMP_RAW")
        emp_raw = emp_p2p_raw if emp_p2p_raw is not None else emp_legacy_raw

        excel_bytes = _build_detailed_report_excel(
            cats_present=cats_present,
            proc_status=proc_status,
            results=results,
            vendor_raw=raw.get("VENDOR_RAW"),
            p2p_raw=raw.get("P2P_RAW"),
            emp_raw=emp_raw,
            file_bytes=s.get("file_bytes"),
            only_codes=selected_set if selected_set else None,
        )
        st.download_button(
            "Download Detailed Report (Excel)",
            data=excel_bytes,
            file_name="detailed_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_detailed_report_excel",
        )

    st.markdown("---")
    if st.button("⟵ Back to Processing", key="back_to_processing_btn"):
        s.page = "processpage"; st.rerun()

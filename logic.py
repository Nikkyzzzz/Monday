# logic.py
import pandas as pd
import numpy as np
from io import BytesIO
from typing import Dict, Tuple, Any

# We import your existing logic6 (unchanged)
import logic6

# ---------- Canonical field targets that logic6 expects ----------
# Map *Required Field* → *Canonical Column Name in logic6*
CANONICAL_FIELDS = {
    "P2P": {
        "P2P Sample": {
            "Vendor Name": "Vendor_Name",
            "PO No": "PO_No",
            "PO Date": "PO_Date",
            "PO Quantity": "PO_Qty",
            "PO Amount": "PO_Amt",
            "PO Approved By": "PO_Approved_By",
            "GRN No": "GRN_No",
            "GRN Date": "GRN_Date",
            "GRN Quantity": "GRN_Qty",
            "Invoice Date": "Invoice_Date",
            "Invoice Quantity": "Invoice_Qty",
            "Invoice Amount": "Invoice_Amount",
            "Creator ID": "Creator_ID",
        },
        "Vendor Master": {
            "Vendor Name": "Vendor_Name",
            "GST": "GST_No",
            "PAN": "PAN_No",
            "Bank Account": "Bank_Account",
            "Creator ID": "Creator_ID",
        },
        "Employee Master": {
            "Employee ID": "Employee_ID",
            "Employee Name": "Employee_Name",
            "Department": "Department",
            "Creator ID": "Creator_ID",
        },
    },
    "O2C": {
        "O2C Sample": {
            "SO Date": "SO_Date",
            "Delivery Date": "Delivery_Date",
            "Invoice No": "Invoice_No",
            # Delivery_No is used by logic6.check_dispatch_without_invoice;
            # we'll create it empty if not provided.
        },
        "Customer Master": {
            "GST No": "GST_No",
            "PAN No": "PAN_No",
            "Credit Limit": "Credit_Limit",
        },
    },
    "H2R": {
        "Employee Master": {
            "Employee ID": "Employee_ID",
            "Employee Name": "Employee_Name",
            "Exit Date": "Exit_Date",
            "Status": "Status",
        },
        "Attendance Register": {
            "Employee ID": "Employee_ID",
            "Employee Name": "Employee_Name",
            "Month": "Month",
            # Daily D1..D31 columns remain as-is if present
        },
    },
}

def _build_rename_map(required_to_actual: Dict[str, str], req_to_canon: Dict[str, str]) -> Dict[str, str]:
    """
    Convert {Required Field -> Actual Column} to {Actual Column -> Canonical Column}.
    """
    rename = {}
    for req, actual in required_to_actual.items():
        if actual and req in req_to_canon:
            rename[actual] = req_to_canon[req]
    return rename

def _read_sheet_from(bytes_blob: bytes, sheet_name: str) -> pd.DataFrame:
    bio = BytesIO(bytes_blob)
    return pd.read_excel(bio, sheet_name=sheet_name)

def prepare_dataframes(
    file_bytes_map: Dict[str, bytes],
    sheet_mapping_pairs: Dict[str, Dict[str, str]],
    column_mapping_pairs: Dict[str, Dict[str, Dict[str, str]]],
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Returns: (df_vendor, df_p2p, df_emp_p2p, df_o2c, df_cust, df_att)
    Missing ones can be None.
    """
    # Helper: choose bytes per category (prefer category, else master)
    def _cat_bytes(cat: str):
        if cat == "P2P":
            return file_bytes_map.get("P2P") or file_bytes_map.get("MASTER")
        if cat == "O2C":
            return file_bytes_map.get("O2C") or file_bytes_map.get("MASTER")
        if cat == "H2R":
            return file_bytes_map.get("H2R") or file_bytes_map.get("MASTER")
        return None

    # Prepare containers
    df_vendor = df_p2p = df_emp_p2p = df_o2c = df_cust = df_att = None

    # ---------- P2P ----------
    if "P2P" in sheet_mapping_pairs:
        p2p_bytes = _cat_bytes("P2P")
        if p2p_bytes:
            mapping = sheet_mapping_pairs["P2P"]
            fields_map = column_mapping_pairs.get("P2P", {})

            # P2P Sample
            if "P2P Sample" in mapping:
                sheet = mapping["P2P Sample"]
                df = _read_sheet_from(p2p_bytes, sheet)
                rename = _build_rename_map(fields_map.get("P2P Sample", {}), CANONICAL_FIELDS["P2P"]["P2P Sample"])
                if rename: df = df.rename(columns=rename)
                # Fill any missing canonical columns used by logic6
                for c in ["PO_No","PO_Qty","PO_Amt","GRN_Qty","Invoice_Qty","Invoice_Amount",
                          "Vendor_Name","PO_Date","Invoice_Date","PO_Approved_By","PO_Created_By","Item_Code"]:
                    if c not in df.columns: df[c] = np.nan
                df_p2p = df

            # Vendor Master
            if "Vendor Master" in mapping:
                sheet = mapping["Vendor Master"]
                df = _read_sheet_from(p2p_bytes, sheet)
                rename = _build_rename_map(fields_map.get("Vendor Master", {}), CANONICAL_FIELDS["P2P"]["Vendor Master"])
                if rename: df = df.rename(columns=rename)
                for c in ["PAN_No","GST_No","Bank_Account","Vendor_Name","Creator_ID"]:
                    if c not in df.columns: df[c] = np.nan
                df_vendor = df

            # Employee Master (for department lookups in logic6.summarize_mismatches)
            if "Employee Master" in mapping:
                sheet = mapping["Employee Master"]
                df = _read_sheet_from(p2p_bytes, sheet)
                rename = _build_rename_map(fields_map.get("Employee Master", {}), CANONICAL_FIELDS["P2P"]["Employee Master"])
                if rename: df = df.rename(columns=rename)
                df_emp_p2p = df

    # ---------- O2C ----------
    if "O2C" in sheet_mapping_pairs:
        o2c_bytes = _cat_bytes("O2C")
        if o2c_bytes:
            mapping = sheet_mapping_pairs["O2C"]
            fields_map = column_mapping_pairs.get("O2C", {})

            if "O2C Sample" in mapping:
                sheet = mapping["O2C Sample"]
                df = _read_sheet_from(o2c_bytes, sheet)
                rename = _build_rename_map(fields_map.get("O2C Sample", {}), CANONICAL_FIELDS["O2C"]["O2C Sample"])
                if rename: df = df.rename(columns=rename)
                if "Delivery_No" not in df.columns:
                    df["Delivery_No"] = np.nan
                df_o2c = df

            if "Customer Master" in mapping:
                sheet = mapping["Customer Master"]
                df = _read_sheet_from(o2c_bytes, sheet)
                rename = _build_rename_map(fields_map.get("Customer Master", {}), CANONICAL_FIELDS["O2C"]["Customer Master"])
                if rename: df = df.rename(columns=rename)
                df_cust = df

    # ---------- H2R ----------
    if "H2R" in sheet_mapping_pairs:
        h2r_bytes = _cat_bytes("H2R")
        if h2r_bytes:
            mapping = sheet_mapping_pairs["H2R"]
            fields_map = column_mapping_pairs.get("H2R", {})

            if "Employee Master" in mapping:
                df = _read_sheet_from(h2r_bytes, mapping["Employee Master"])
                rename = _build_rename_map(fields_map.get("Employee Master", {}), CANONICAL_FIELDS["H2R"]["Employee Master"])
                if rename: df = df.rename(columns=rename)
                if "Employee_ID" in df.columns:
                    df["Employee_ID"] = df["Employee_ID"].astype(str).str.strip()
                df_emp_h2r = df
            else:
                df_emp_h2r = None

            if "Attendance Register" in mapping:
                df = _read_sheet_from(h2r_bytes, mapping["Attendance Register"])
                rename = _build_rename_map(fields_map.get("Attendance Register", {}), CANONICAL_FIELDS["H2R"]["Attendance Register"])
                if rename: df = df.rename(columns=rename)
                # Derive Present_Days if day columns exist
                day_cols = [c for c in df.columns if str(c).startswith("D") and str(c)[1:].isdigit()]
                if day_cols:
                    s = df[day_cols].astype(str).apply(lambda col: col.str.strip().str.upper())
                    present = (~s.eq("A")).sum(axis=1)
                    df["Present_Days"] = present
                else:
                    if "Present_Days" not in df.columns:
                        df["Present_Days"] = 0
                if "Employee_ID" in df.columns:
                    df["Employee_ID"] = df["Employee_ID"].astype(str).str.strip()
                df_att = df
            else:
                df_att = None

            # Return H2R pair as df_emp (master) and df_attendance
            return df_vendor, df_p2p, df_emp_p2p, df_o2c, df_cust, (df_emp_h2r if 'df_emp_h2r' in locals() else None), df_att

    # If H2R not present, return 6-tuple with last two as None
    return df_vendor, df_p2p, df_emp_p2p, df_o2c, df_cust, None, None


def run_all_bots_with_mappings(
    file_bytes_map: Dict[str, bytes],
    sheet_mapping_pairs: Dict[str, Dict[str, str]],
    column_mapping_pairs: Dict[str, Dict[str, Dict[str, str]]],
) -> Tuple[Dict[str, pd.DataFrame], Dict[str, str], Dict[str, str], Dict[str, pd.DataFrame]]:
    """
    Executes all bots using mapped columns. Returns:
    - results: dict code -> DataFrame
    - proc_status: dict code -> status
    - cat_status: dict category -> status
    - raw_dfs: dict of raw dfs used (for next-level analytics compatibility)
    """
    # Prepare dataframes
    df_vendor, df_p2p, df_emp_p2p, df_o2c, df_cust, df_emp_h2r, df_att = prepare_dataframes(
        file_bytes_map, sheet_mapping_pairs, column_mapping_pairs
    )

    results: Dict[str, pd.DataFrame] = {}
    proc_status = {
        'P2P1':'Pending','P2P2':'Pending','P2P3':'Pending','P2P4':'Pending','P2P5':'Pending',
        'O2C1':'Pending','O2C2':'Pending','O2C3':'Pending',
        'H2R1':'Pending','H2R2':'Pending',
    }

    # ---------- P2P ----------
    if df_vendor is not None:
        try:
            results['P2P1'] = logic6.find_missing_vendor_fields(df_vendor)
            proc_status['P2P1'] = 'Complete'
        except Exception:
            proc_status['P2P1'] = 'Failed'

        try:
            # Duplicate Vendors — run on DF (no workbook dependency)
            results['P2P5'] = _find_matching_rows_from_df(df_vendor)
            proc_status['P2P5'] = 'Complete'
        except Exception:
            proc_status['P2P5'] = 'Failed'

    if df_p2p is not None:
        try:
            results['P2P2'] = logic6.find_po_grn_invoice_mismatches(df_p2p)
            proc_status['P2P2'] = 'Complete'
        except Exception:
            proc_status['P2P2'] = 'Failed'
        try:
            results['P2P3'] = logic6.get_invalid_rows(df_p2p)
            proc_status['P2P3'] = 'Complete'
        except Exception:
            proc_status['P2P3'] = 'Failed'
        try:
            results['P2P4'] = logic6.generate_result(df_p2p)
            proc_status['P2P4'] = 'Complete'
        except Exception:
            proc_status['P2P4'] = 'Failed'

    # ---------- O2C ----------
    if df_o2c is not None:
        try:
            results['O2C1'] = logic6.check_overdue_delivery(df_o2c.copy())
            proc_status['O2C1'] = 'Complete'
        except Exception:
            proc_status['O2C1'] = 'Failed'
        try:
            # ensure columns exist
            if "Delivery_No" not in df_o2c.columns:
                df_o2c = df_o2c.copy(); df_o2c["Delivery_No"] = np.nan
            results['O2C2'] = logic6.check_dispatch_without_invoice(df_o2c.copy())
            proc_status['O2C2'] = 'Complete'
        except Exception:
            proc_status['O2C2'] = 'Failed'

    if df_cust is not None:
        try:
            results['O2C3'] = logic6.get_missing_customer_data(df_cust.copy())
            proc_status['O2C3'] = 'Complete'
        except Exception:
            proc_status['O2C3'] = 'Failed'

    # ---------- H2R ----------
    if (df_emp_h2r is not None) and (df_att is not None):
        try:
            results['H2R1'] = logic6.find_ghost_employees(df_emp_h2r, df_att)
            proc_status['H2R1'] = 'Complete'
        except Exception:
            proc_status['H2R1'] = 'Failed'
        try:
            # Build a temp in-memory workbook for the function that expects file bytes
            bio = BytesIO()
            with pd.ExcelWriter(bio, engine="xlsxwriter") as writer:
                df_emp_h2r.to_excel(writer, sheet_name="Employee_Master", index=False)
                df_att.to_excel(writer, sheet_name="Attendance_Register", index=False)
            bio.seek(0)
            results['H2R2'] = logic6.find_attendance_after_exit(
                bio, employee_sheet="Employee_Master", attendance_sheet="Attendance_Register",
                month_col="Month", year_col=None
            )
            proc_status['H2R2'] = 'Complete'
        except Exception:
            proc_status['H2R2'] = 'Failed'

    # ---------- Category rollups ----------
    cat_status = {
        'P2P': logic6.compute_category_status(proc_status, ['P2P1','P2P2','P2P3','P2P4','P2P5']),
        'O2C': logic6.compute_category_status(proc_status, ['O2C1','O2C2','O2C3']),
        'H2R': logic6.compute_category_status(proc_status, ['H2R1','H2R2']),
    }

    # Raw dfs for optional next-level tabs
    raw_dfs = {
        "VENDOR_RAW": df_vendor,
        "P2P_RAW": df_p2p,
        "EMP_RAW": df_emp_p2p,
        "O2C_RAW": df_o2c,
        "CUST_RAW": df_cust,
        "ATT_RAW": df_att,
    }
    return results, proc_status, cat_status, raw_dfs


def _find_matching_rows_from_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Duplicate Vendors (logic6.find_matching_rows) but working directly on a DF that
    already uses canonical columns (Vendor_Name, PAN_No, GST_No, Bank_Account).
    """
    from itertools import combinations

    d = df.copy().replace(r'^\s*$', pd.NA, regex=True).reset_index(drop=True)
    d.insert(0, "RowNo", d.index + 1)

    keys = {
        "PAN_No": "PAN Match",
        "GST_No": "GST Match",
        "Vendor_Name": "Vendor Name Match",
        "Bank_Account": "Bank Account Match",
    }

    pairs = {}
    for col, label in keys.items():
        if col in d.columns:
            tmp = d.dropna(subset=[col])
            groups = tmp.groupby(col, dropna=True)["RowNo"].apply(list)
            for rows in groups:
                if len(rows) >= 2:
                    for a, b in combinations(sorted(rows), 2):
                        pairs.setdefault((a, b), set()).add(label)

    rows_info = d.set_index("RowNo")
    records = []
    for (a, b), labels in sorted(pairs.items()):
        rec = {"Row_A": a, "Row_B": b, "Exception_Noted": ", ".join(sorted(labels))}
        # flatten
        ra = rows_info.loc[a].to_dict()
        rb = rows_info.loc[b].to_dict()
        for k, v in ra.items(): rec[f"A_{k}"] = v
        for k, v in rb.items(): rec[f"B_{k}"] = v
        records.append(rec)
    return pd.DataFrame(records)

# schemas/generic.py
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


# ─────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────

def _str_values(d: Dict[str, Any]) -> Dict[str, str]:
    """Normalise all values to str; lower-case all keys."""
    result = {}
    for k, v in d.items():
        key = str(k).lower().strip()
        if key == "fields":  # skip the pydantic wrapper key if echoed back
            continue
        result[key] = str(v) if v is not None else ""
    return result


# When the 3b model reverts to old fixed-schema format, remap those keys.
_LEGACY_KEY_MAP = {
    "vendor": "vendor",
    "invoice_number": "invoice no.",
    "date": "date",
    "bill_to": "bill to",
    "terms": "terms",
    "po_number": "po number",
    "tax_registration_number": "tax registration number",
    "tax_registration_type": "tax registration type",
    "check_number": "chk",
    "order_number": "order no",
    "table_number": "tbl",
    "cashier": "cashier",
}


# ─────────────────────────────────────────────
# FORMS
# ─────────────────────────────────────────────

class FormsObject(BaseModel):
    """
    Dynamic forms section. All label:value pairs live in `fields`.

    SERIALISATION: use  forms.to_output_dict()  for JSON output.
    Do NOT use model_dump() directly — that emits {"fields": {...}}.
    """

    fields: Dict[str, str] = Field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FormsObject":
        """
        Accepts any shape the 3b model might return:
          • Dynamic  {"chk": "1033", "tbl": "32/1"}
          • Wrapped  {"fields": {"chk": "1033"}}          ← model echoed schema
          • Legacy   {"vendor": "Acme", "invoice_number": "INV001"}
          • Empty    {}
        """
        if not data:
            return cls(fields={})

        # Case: model echoed our internal {"fields": {...}} structure
        if "fields" in data and isinstance(data["fields"], dict) and len(data) == 1:
            inner = data["fields"]
            return cls(fields=_str_values(inner)) if inner else cls(fields={})

        # Remap any legacy snake_case keys, then normalise
        normalised: Dict[str, str] = {}
        for raw_key, raw_val in data.items():
            key = str(raw_key).lower().strip()
            mapped_key = _LEGACY_KEY_MAP.get(key, key)
            normalised[mapped_key] = str(raw_val) if raw_val is not None else ""

        return cls(fields=normalised)

    def to_output_dict(self) -> Dict[str, str]:
        """Plain {label: value} dict for JSON serialisation."""
        return self.fields

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.fields.get(key.lower(), default)

    def __getitem__(self, key: str) -> Optional[str]:
        return self.fields.get(key.lower())

    def __bool__(self) -> bool:
        return bool(self.fields)

    # ── legacy property shims ────────────────────────────────────────

    @property
    def vendor(self) -> Optional[str]:
        return self.fields.get("vendor") or self.fields.get("vendor name") or None

    @property
    def invoice_number(self) -> Optional[str]:
        for k in ("invoice no.", "invoice no", "invoice number", "invoice #",
                  "bill no.", "bill no"):
            v = self.fields.get(k)
            if v:
                return v
        return None

    @property
    def date(self) -> Optional[str]:
        return self.fields.get("date") or None

    @property
    def bill_to(self) -> Optional[str]:
        return self.fields.get("bill to") or None

    @property
    def terms(self) -> Optional[str]:
        return self.fields.get("terms") or None

    @property
    def po_number(self) -> Optional[str]:
        for k in ("po number", "po no", "po no.", "p.o. number"):
            v = self.fields.get(k)
            if v:
                return v
        return None

    @property
    def tax_registration_number(self) -> Optional[str]:
        for k in ("tax registration number", "gstin", "gst no", "gst no.",
                  "vat no", "vat no.", "tin", "ein"):
            v = self.fields.get(k)
            if v:
                return v
        return None

    @property
    def tax_registration_type(self) -> Optional[str]:
        return self.fields.get("tax registration type") or None

    @property
    def check_number(self) -> Optional[str]:
        return self.fields.get("chk") or self.fields.get("check number") or None

    @property
    def order_number(self) -> Optional[str]:
        for k in ("order no", "order no.", "order number"):
            v = self.fields.get(k)
            if v:
                return v
        return None

    @property
    def table_number(self) -> Optional[str]:
        return self.fields.get("tbl") or self.fields.get("table number") or None

    @property
    def cashier(self) -> Optional[str]:
        return self.fields.get("cashier") or None


# ─────────────────────────────────────────────
# TABLE CELL
# ─────────────────────────────────────────────

class TableCell(BaseModel):
    row: int
    col: int
    text: str = ""


# ─────────────────────────────────────────────
# DOCUMENT TABLE
# ─────────────────────────────────────────────

class DocumentTable(BaseModel):
    cells: List[TableCell] = Field(default_factory=list)

    @classmethod
    def from_cell_list(cls, cell_list: List[Dict[str, Any]]) -> "DocumentTable":
        return cls(cells=[TableCell(**c) for c in cell_list])

    def to_output_list(self) -> List[Dict[str, Any]]:
        return [c.model_dump() for c in self.cells]

    @property
    def num_cols(self) -> int:
        return max((c.col for c in self.cells), default=0)

    @property
    def num_rows(self) -> int:
        return max((c.row for c in self.cells), default=0)

    # ── BACKWARD COMPATIBILITY ────────────────────────────────────────
    # These properties let old code access tables[0].col2 as if it were
    # a TableRow. NOTE: This only works if you're treating the table as
    # a single "row" — if you're iterating rows, use flat_tables instead.

    def _get_col_text(self, col_num: int, row_num: int = 2) -> str:
        """Get text from a specific cell (default to first data row)."""
        for cell in self.cells:
            if cell.row == row_num and cell.col == col_num:
                return cell.text
        return ""

    @property
    def col1(self) -> str:
        """First column of first data row (row 2)."""
        return self._get_col_text(1)

    @property
    def col2(self) -> str:
        """Second column of first data row (row 2)."""
        return self._get_col_text(2)

    @property
    def col3(self) -> str:
        """Third column of first data row (row 2)."""
        return self._get_col_text(3)

    @property
    def col4(self) -> str:
        """Fourth column of first data row (row 2)."""
        return self._get_col_text(4)


# ─────────────────────────────────────────────
# LEGACY TableRow  (kept for netsuite_service)
# ─────────────────────────────────────────────

class TableRow(BaseModel):
    col1: str = ""
    col2: str = ""
    col3: str = ""
    col4: str = ""


# ─────────────────────────────────────────────
# FINANCIAL ANCHORS
# ─────────────────────────────────────────────

class FinancialAnchors(BaseModel):
    subtotal: float = 0.0
    cgst: Optional[float] = None
    sgst: Optional[float] = None
    igst: Optional[float] = None
    tax: float = 0.0
    total: float = 0.0
    invoice_total: float = 0.0


# ─────────────────────────────────────────────
# TOP-LEVEL GenericJSON
# ─────────────────────────────────────────────

class GenericJSON(BaseModel):
    forms: FormsObject
    # _internal_tables: List[DocumentTable] = []
    internal_tables: List[DocumentTable] = Field(default_factory=list)
    anchors: FinancialAnchors
    raw_text: str
    bill_category: Optional[str] = None

    class Config:
        underscore_attrs_are_private = False
        arbitrary_types_allowed = True

    # BACKWARD COMPATIBILITY: make .tables return the legacy flat format
    # so existing code (transformer.py: for row in generic.tables) doesn't break

    @property
    def document_tables(self) -> List[DocumentTable]:
        """Access the full row/col table structures (new code should use this)."""
        return self.internal_tables

    @property
    def tables(self) -> List[TableRow]:
        """
        Legacy property: returns flat TableRow list (col1-col4) for backward compat.
        Converts the line-items table (largest by row count) to flat rows.

        Used by transformer.py which does: for row in generic.tables
        """
        if not self.internal_tables:
            return []
        line_table = max(self.internal_tables, key=lambda t: t.num_rows)
        cell_map: Dict[tuple, str] = {(c.row, c.col): c.text for c in line_table.cells}
        rows: List[TableRow] = []
        for r in range(2, line_table.num_rows + 1):
            col_vals = [cell_map.get((r, c), "") for c in range(1, line_table.num_cols + 1)]
            while len(col_vals) < 4:
                col_vals.append("")
            rows.append(TableRow(col1=col_vals[0], col2=col_vals[1],
                                 col3=col_vals[2], col4=col_vals[3]))
        return rows

    @property
    def flat_tables(self) -> List[TableRow]:
        """Alias for .tables (backward compat)."""
        return self.tables

    def to_output_dict(self) -> Dict[str, Any]:
        """
        Serialise to clean output format.
        forms  → plain {key: value}       (NOT {"fields": {...}})
        tables → list of [{row,col,text}] lists  (full structure, NOT flat)
        """
        return {
            "forms": self.forms.to_output_dict(),
            "tables": [t.to_output_list() for t in self.internal_tables],
            "anchors": self.anchors.model_dump(),
            "raw_text": self.raw_text,
            "bill_category": self.bill_category,
        }
from datetime import date

"""Export des groupes en colonnes, selon le modèle Focus Time fourni."""

from io import BytesIO
import math

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins

from activity_import import activity_name

COLORS = ("83CCEB", "F6C6AD", "84E291", "9EDCF3", "E59DDD", "B7E5A5")


def excel_bytes(session, roster, activities, assignments):
    activity_map = {a["id"]: a for a in activities}
    roster_map = {s["email"]: s for s in roster}
    assigned = {(a["email"], a["period"]) for a in assignments}
    if any((s["email"], p) not in assigned for s in roster for p in (9, 10)):
        raise ValueError("Le planning est incomplet : génération de l'Excel refusée.")
    wb = Workbook()
    wb.remove(wb.active)
    wb.properties.title = "{} — {}".format(
        session["title"], date.fromisoformat(session["event_date"]).strftime("%d/%m/%Y")
    )
    for degree in (1, 2, 3):
        ws = wb.create_sheet(f"D{degree}")
        ws.sheet_view.showGridLines = False
        ws.column_dimensions["A"].width = 10.66
        groups = sorted(
            [a for a in activities if a["degree"] == degree],
            key=lambda a: (activity_name(a["name"]), a["period"]),
        )
        names = list(dict.fromkeys(activity_name(a["name"]) for a in groups))
        if not groups:
            ws["A1"] = f"D{degree} — Aucune activité"
            ws["A1"].font = Font(name="Arial", size=11)
            ws.merge_cells("A1:D1")
            ws.print_area = "A1:D1"
        header_row = 1
        for period in (9, 10) if groups else ():
            members = {}
            by_name = {
                activity_name(a["name"]): a for a in groups if a["period"] == period
            }
            for name, group in by_name.items():
                members[name] = sorted(
                    [
                        roster_map[r["email"]]["name"]
                        for r in assignments
                        if r["activity_id"] == group["id"]
                    ],
                    key=str.casefold,
                )
            row_count = max(12, max((len(v) for v in members.values()), default=0))
            first_row, last_row = header_row + 1, header_row + row_count
            ws.merge_cells(
                start_row=first_row, start_column=1, end_row=last_row, end_column=1
            )
            label = ws.cell(first_row, 1, f"P{period}")
            label.font = Font(name="Arial", size=28, bold=True)
            label.alignment = Alignment(horizontal="center", vertical="center")
            header_height = 76
            for column, name in enumerate(names, 2):
                ws.column_dimensions[get_column_letter(column)].width = 30.66
                group = by_name.get(name)
                header = ws.cell(header_row, column)
                if group:
                    title = "{}\n({} - Local {})".format(
                        group["name"], group["professor"], group["room"]
                    )
                    header.value = title
                    header.data_type = "s"
                    header.fill = PatternFill(
                        "solid", fgColor=COLORS[(column - 2) % len(COLORS)]
                    )
                    lines = sum(
                        max(1, math.ceil(len(part) / 30)) for part in title.split("\n")
                    )
                    header_height = max(header_height, lines * 14 + 16)
                else:
                    header.value = "Non proposée en P{}".format(period)
                    header.fill = PatternFill("solid", fgColor="ECECEC")
                header.font = Font(name="Arial", size=11, bold=True)
                header.alignment = Alignment(
                    horizontal="center", vertical="center", wrap_text=True
                )
                for offset in range(row_count):
                    cell = ws.cell(first_row + offset, column)
                    cell.font = Font(name="Arial", size=11)
                    cell.alignment = Alignment(vertical="center", wrap_text=True)
                    cell.fill = PatternFill(
                        "solid", fgColor="D9D9D9" if offset % 2 == 0 else "FFFFFF"
                    )
                    if offset < len(members.get(name, [])):
                        cell.value = members[name][offset]
                        cell.data_type = "s"
                    if offset == row_count - 1:
                        cell.border = Border(bottom=Side(style="thin", color="808080"))
            ws.row_dimensions[header_row].height = header_height
            for row in range(first_row, last_row + 1):
                values = [
                    str(ws.cell(row, col).value or "")
                    for col in range(2, len(names) + 2)
                ]
                lines = max(
                    (max(1, math.ceil(len(value) / 32)) for value in values), default=1
                )
                ws.row_dimensions[row].height = max(24.9, lines * 14 + 6)
            header_row = last_row + 6
            ws.print_area = "A1:{}{}".format(
                get_column_letter(len(names) + 1), last_row
            )
        ws.page_setup.orientation = "landscape"
        ws.page_setup.paperSize = ws.PAPERSIZE_A3
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_margins = PageMargins(left=0.25, right=0.25, top=0.5, bottom=0.5)
        ws.print_options.horizontalCentered = True
        ws.oddHeader.center.text = "{} — {} — D{}".format(
            session["title"],
            date.fromisoformat(session["event_date"]).strftime("%d/%m/%Y"),
            degree,
        )
        ws.oddFooter.right.text = "Page &P / &N"
    output = BytesIO()
    wb.save(output)
    return output.getvalue()

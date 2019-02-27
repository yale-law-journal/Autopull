from collections import namedtuple, OrderedDict
import csv
from xlsxwriter import Workbook

class Spreadsheet(object):
    def __init__(self, columns=None, rows=[]):
        self.columns = list(columns) if columns is not None else None
        self.columns_set = set(self.columns) if columns is not None else None

        for row in rows:
            assert set(row.keys()) == self.columns_set
        self.rows = rows

    @staticmethod
    def from_namedtuple(nt_cls, rows=[]):
        return Spreadsheet(nt_cls._fields, rows)

    def _append(self, row):
        assert set(row.keys()) == self.columns_set
        self.rows.append(row)

    def append(self, row):
        if isinstance(row, dict):
            self._append(row)
        elif isinstance(row, OrderedDict):
            self._append(dict(row))
        elif isinstance(row, tuple) and hasattr(row, '_fields'):  # namedtuple
            self._append(dict(row._asdict()))

    def extend(self, rows):
        for row in rows:
            self.append(row)

    def write_csv(self, f):
        writer = csv.DictWriter(f, fieldnames=self.columns)

        writer.writeheader()
        writer.writerows(self.rows)

    def write_csv_path(self, filename, encoding='utf-8'):
        with open(filename, 'w', newline='', encoding=encoding) as f:
            self.write_csv(f)

    def write_xlsx_path(self, filename):
        workbook = Workbook(filename)
        worksheet = workbook.add_worksheet()
        bold = workbook.add_format({ 'bold': True })

        column_formats = [workbook.add_format() for _ in self.columns]

        for idx, field in enumerate(self.columns):
            worksheet.write(0, idx, field, bold)
            nonempty_rows = len([r[field] for r in self.rows if r[field]])
            mean_width = sum(len(str(row[field])) for row in self.rows if row[field]) / (nonempty_rows + 0.001)
            if mean_width > 40:
                worksheet.set_column(idx, idx, mean_width / 2)
                column_formats[idx].set_text_wrap()
            elif mean_width > 15:
                worksheet.set_column(idx, idx, 20)

        for row_idx, row in enumerate(self.rows):
            for col_idx, col in enumerate(self.columns):
                if col in row:
                    worksheet.write(row_idx + 1, col_idx, row[col], column_formats[col_idx])

        workbook.close()

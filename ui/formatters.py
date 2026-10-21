"""Terminal-friendly table formatting with an optional tabulate enhancement."""


def render_table(headers, rows):
    try:
        from tabulate import tabulate
        return tabulate(rows, headers=headers, tablefmt="simple")
    except ImportError:
        values = [[str(value) for value in row] for row in rows]
        widths = [len(str(header)) for header in headers]
        for row in values:
            for index, value in enumerate(row):
                widths[index] = max(widths[index], len(value))
        line = "-+-".join("-" * width for width in widths)
        format_row = lambda row: " | ".join(
            str(value).ljust(widths[index]) for index, value in enumerate(row)
        )
        return "\n".join([format_row(headers), line] + [format_row(row) for row in values])


def print_table(headers, rows):
    print(render_table(headers, rows))

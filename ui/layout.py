"""Window sizing in logical pixels, respecting CustomTkinter's DPI scaling."""


def fit_window(window, width, height, min_width=320, min_height=240):
    scale = window._get_window_scaling()
    available_w = max(320, int(window.winfo_screenwidth() / scale) - 40)
    available_h = max(240, int(window.winfo_screenheight() / scale) - 100)
    width, height = min(width, available_w), min(height, available_h)
    window.minsize(min(min_width, width), min(min_height, height))
    window.geometry(f"{width}x{height}")
    return width, height

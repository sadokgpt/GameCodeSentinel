"""Tema desktop per GameCode Sentinel.

Soltanto ttk/Tk standard: nessuna dipendenza o risorsa remota.
Importazione sicura anche nei controlli CLI headless.
"""
from __future__ import annotations

PALETTE = {
    "background": "#0b1220",
    "sidebar": "#101b2d",
    "surface": "#172337",
    "surface_alt": "#1c2b42",
    "border": "#2b3c53",
    "text": "#eef4ff",
    "muted": "#9fb0c8",
    "accent": "#6366f1",
    "accent_hover": "#777af6",
    "positive": "#34d399",
    "warning": "#fbbf24",
    "danger": "#fb7185",
}


def apply_theme(root) -> None:
    """Inizializza uno stile dark coerente per tutte le finestre ttk."""
    from tkinter import ttk

    p = PALETTE
    root.configure(bg=p["background"])
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", font=("Segoe UI", 10), background=p["background"],
                    foreground=p["text"])
    style.configure("TFrame", background=p["background"])
    style.configure("Sidebar.TFrame", background=p["sidebar"])
    style.configure("Surface.TFrame", background=p["surface"])
    style.configure("Metric.TFrame", background=p["surface"])
    style.configure("TLabel", background=p["background"], foreground=p["text"])
    style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"))
    style.configure("Subtitle.TLabel", font=("Segoe UI", 10),
                    foreground=p["muted"])
    style.configure("Brand.TLabel", font=("Segoe UI", 16, "bold"),
                    background=p["sidebar"], foreground=p["text"])
    style.configure("SidebarNote.TLabel", font=("Segoe UI", 9),
                    background=p["sidebar"], foreground=p["muted"])
    style.configure("SidebarHeading.TLabel", font=("Segoe UI", 9, "bold"),
                    background=p["sidebar"], foreground=p["muted"])
    style.configure("MetricTitle.TLabel", font=("Segoe UI", 9, "bold"),
                    background=p["surface"], foreground=p["muted"])
    style.configure("MetricValue.TLabel", font=("Segoe UI", 23, "bold"),
                    background=p["surface"], foreground=p["text"])
    style.configure("TButton", font=("Segoe UI", 10), padding=(13, 9),
                    background=p["surface_alt"], foreground=p["text"],
                    borderwidth=0, relief="flat")
    style.map("TButton",
              background=[("active", p["border"]), ("disabled", p["surface"])],
              foreground=[("disabled", p["muted"])])
    style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"),
                    background=p["accent"], foreground="#ffffff", padding=(17, 11))
    style.map("Primary.TButton",
              background=[("active", p["accent_hover"]), ("disabled", p["border"])],
              foreground=[("disabled", p["muted"])])
    style.configure("Nav.TButton", font=("Segoe UI", 10),
                    background=p["sidebar"], foreground=p["text"],
                    padding=(12, 12), anchor="w")
    style.map("Nav.TButton", background=[("active", p["surface_alt"])])
    style.configure("Danger.TButton", background="#482b3c", foreground="#ffd4dc")
    style.map("Danger.TButton", background=[("active", "#66344b")])
    style.configure("TEntry", padding=(9, 8),
                    fieldbackground=p["surface"], foreground=p["text"],
                    bordercolor=p["border"], lightcolor=p["border"],
                    darkcolor=p["border"], insertcolor=p["text"])
    style.configure("TCombobox", padding=(8, 7),
                    fieldbackground=p["surface"], background=p["surface"],
                    foreground=p["text"], arrowcolor=p["text"])
    style.map("TCombobox",
              fieldbackground=[("readonly", p["surface"])],
              foreground=[("readonly", p["text"])],
              selectbackground=[("readonly", p["surface"])],
              selectforeground=[("readonly", p["text"])])
    style.configure("TCheckbutton", background=p["background"],
                    foreground=p["muted"], padding=4)
    style.map("TCheckbutton",
              background=[("active", p["background"])],
              foreground=[("active", p["text"])])
    style.configure("Treeview", background=p["surface"],
                    fieldbackground=p["surface"], foreground=p["text"],
                    borderwidth=0, relief="flat", rowheight=37,
                    font=("Segoe UI", 10))
    style.configure("Treeview.Heading", background=p["surface_alt"],
                    foreground=p["text"], padding=(10, 12),
                    font=("Segoe UI", 10, "bold"), borderwidth=0, relief="flat")
    style.map("Treeview",
              background=[("selected", p["accent"])],
              foreground=[("selected", "#ffffff")])
    style.map("Treeview.Heading",
              background=[("active", p["border"])])
    style.configure("TScrollbar", background=p["surface_alt"],
                    troughcolor=p["background"], borderwidth=0,
                    arrowcolor=p["muted"])
    style.configure("TSeparator", background=p["border"])
    style.configure("TSpinbox", fieldbackground=p["surface"],
                    foreground=p["text"])
    try:
        root.option_add("*TCombobox*Listbox.background", p["surface"])
        root.option_add("*TCombobox*Listbox.foreground", p["text"])
        root.option_add("*TCombobox*Listbox.selectBackground", p["accent"])
    except Exception:
        pass


def metric_card(parent, title: str, variable, *, padx: int = 14):
    """Card riepilogativa con layout espandibile."""
    from tkinter import ttk

    card = ttk.Frame(parent, style="Metric.TFrame", padding=(padx, 13))
    ttk.Label(card, text=title, style="MetricTitle.TLabel").pack(anchor="w")
    ttk.Label(card, textvariable=variable, style="MetricValue.TLabel").pack(
        anchor="w", pady=(5, 0))
    return card

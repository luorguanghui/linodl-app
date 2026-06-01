"""Shared GUI styling values for the CustomTkinter interface."""

import customtkinter as ctk

PAD_X = 18
PAD_Y = 12
GAP = 8
CARD_RADIUS = 8

COLOR_SUCCESS = "#2f9e44"
COLOR_WARNING = "#f59f00"
COLOR_DANGER = "#e03131"
COLOR_PRIMARY = "#1c7ed6"
COLOR_PRIMARY_HOVER = "#1864ab"
COLOR_MUTED = ("gray35", "gray65")
COLOR_CARD = ("gray92", "gray18")
COLOR_CARD_HOVER = ("gray86", "gray24")
COLOR_SIDEBAR_ACTIVE = ("gray78", "gray24")


def title_font():
    return ctk.CTkFont(size=20, weight="bold")


def section_font():
    return ctk.CTkFont(size=15, weight="bold")


def meta_font():
    return ctk.CTkFont(size=12)


def apply_appearance(theme: str):
    if theme == "dark":
        ctk.set_appearance_mode("dark")
    elif theme == "light":
        ctk.set_appearance_mode("light")
    else:
        ctk.set_appearance_mode("system")

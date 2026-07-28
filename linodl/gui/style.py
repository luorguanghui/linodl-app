"""Shared GUI styling values for the CustomTkinter interface."""

import customtkinter as ctk

PAD_X = 20
PAD_Y = 14
GAP = 10
CARD_RADIUS = 14

COLOR_PRIMARY = "#14A7C8"
COLOR_PRIMARY_HOVER = "#0E8DAA"
COLOR_SUCCESS = "#31B77A"
COLOR_WARNING = "#E7A93F"
COLOR_DANGER = "#E46565"
COLOR_TEXT = ("#17233A", "#F4F7FB")
COLOR_MUTED = ("#657086", "#93A0B7")
COLOR_CARD = ("#F7F9FC", "#111C2F")
COLOR_CARD_ELEVATED = ("#EDF2F7", "#17253B")
COLOR_CARD_HOVER = ("#E5ECF4", "#1D304A")
COLOR_BORDER = ("#DCE4EE", "#253852")
COLOR_BORDER_STRONG = ("#B9C8D8", "#37516F")
COLOR_SIDEBAR = ("#0D1B2E", "#091525")
COLOR_SIDEBAR_ACTIVE = "#173B56"
COLOR_SUCCESS_SOFT = ("#DDF5E9", "#153C31")
COLOR_WARNING_SOFT = ("#FFF0D2", "#49371C")
COLOR_DANGER_SOFT = ("#FBE3E3", "#4A2429")


def title_font():
    return ctk.CTkFont(size=21, weight="bold")


def display_font():
    return ctk.CTkFont(size=27, weight="bold")


def section_font():
    return ctk.CTkFont(size=15, weight="bold")


def body_font():
    return ctk.CTkFont(size=13)


def meta_font():
    return ctk.CTkFont(size=12)


def apply_appearance(theme: str):
    if theme == "dark":
        ctk.set_appearance_mode("dark")
    elif theme == "light":
        ctk.set_appearance_mode("light")
    else:
        ctk.set_appearance_mode("system")

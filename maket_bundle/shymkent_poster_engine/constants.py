"""Mathematical constants — hierarchy, gaps, style (coordinate-free)."""

# Hierarchy — vacancy titles dominant; salary 2nd; phone clear; company medium; instagram footer
HIERARCHY = {
    "company": 0.54,
    "vacancy_title": 1.00,
    "multi_title": 0.38,
    "position_list": 1.00,
    "salary": 0.86,
    "requirements_heading": 0.46,
    "requirements_items": 0.44,
    "responsibilities_heading": 0.46,
    "responsibilities_items": 0.44,
    "conditions_heading": 0.46,
    "conditions_items": 0.44,
    "phone": 0.78,
    "address": 0.40,
    "instagram": 0.36,
}

LINE_HEIGHT_LARGE = 1.10
LINE_HEIGHT_MEDIUM = 1.12
LINE_HEIGHT_BODY = 1.15
LINE_HEIGHT_CONTACT = 1.10

LINE_HEIGHT_BY_BLOCK = {
    "company": LINE_HEIGHT_MEDIUM,
    "vacancy_title": LINE_HEIGHT_LARGE,
    "multi_title": LINE_HEIGHT_LARGE,
    "position_list": LINE_HEIGHT_MEDIUM,
    "salary": LINE_HEIGHT_MEDIUM,
    "requirements_heading": LINE_HEIGHT_MEDIUM,
    "requirements_items": LINE_HEIGHT_BODY,
    "responsibilities_heading": LINE_HEIGHT_MEDIUM,
    "responsibilities_items": LINE_HEIGHT_BODY,
    "conditions_heading": LINE_HEIGHT_MEDIUM,
    "conditions_items": LINE_HEIGHT_BODY,
    "phone": LINE_HEIGHT_CONTACT,
    "address": LINE_HEIGHT_CONTACT,
    "instagram": LINE_HEIGHT_CONTACT,
}

GAP_AFTER = {
    "company": 0.45,
    "vacancy_title": 0.50,
    "multi_title": 0.50,
    "position_list": 0.42,
    "salary": 0.62,
    "requirements": 0.52,
    "responsibilities": 0.62,
    "conditions": 0.52,
    "phone": 0.35,
    "address": 0.25,
}

MULTI_TITLE_TEXT = "ҚЫЗМЕТКЕРЛЕР ҚАЖЕТ"

O_h_min = 0.85
O_h_max = 0.95
O_w_min = 0.70
O_w_max = 0.90

S_low = 10.0
S_high = 120.0
BINARY_SEARCH_ITERATIONS = 30

TEXT_COLOR_RGB = (237, 28, 36)

FONT_CANDIDATES = [
    "/Library/Fonts/Montserrat-ExtraBold.ttf",
    "~/Library/Fonts/Montserrat-ExtraBold.ttf",
    "/System/Library/Fonts/Supplemental/Montserrat-ExtraBold.ttf",
    "fonts/Montserrat-ExtraBold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]

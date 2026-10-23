"""Named wholesale add-ons from the V5 price list.

Area charges (per sqm and percent) use the billable area. Per-item amounts are
added afterwards, so a percentage never magnifies them. Extra installation
choices are recorded; V5 does not price concrete, height or tile.
"""
from decimal import Decimal, ROUND_UP


# Choices the customer and the staff review both offer. Prices stay here.
ADDONS = [
    {'key': 'tracked_bifold', 'label_zh': '轨道对开', 'label_en': 'Tracked bifold',
     'choices': [{'value': 'no', 'label_zh': '不要', 'label_en': 'No'},
                 {'value': 'yes', 'label_zh': '要，+$350/件', 'label_en': 'Yes, +$350 each', 'fixed': '350'}]},
    {'key': 'tracked_sliding', 'label_zh': '轨道推拉', 'label_en': 'Tracked sliding',
     'choices': [{'value': 'no', 'label_zh': '不要', 'label_en': 'No'},
                 {'value': 'yes', 'label_zh': '要，+$400/件', 'label_en': 'Yes, +$400 each', 'fixed': '400'}]},
    # V5: stained colour is N/A for PVC Eco, PVC and Pinewood.
    {'key': 'stained_colour', 'label_zh': '染色', 'label_en': 'Stained colour',
     'exclude': ['Shutters_PVC', 'Shutters_PVC_Eco', 'Shutters_Pinewood'],
     'choices': [{'value': 'no', 'label_zh': '不要', 'label_en': 'No'},
                 {'value': 'yes', 'label_zh': '要，+$20/㎡', 'label_en': 'Yes, +$20/sqm', 'per_sqm': '20'}]},
    {'key': 'stainless_hinges', 'label_zh': '不锈钢合页', 'label_en': 'Stainless hinges',
     'choices': [{'value': 'no', 'label_zh': '不要', 'label_en': 'No'},
                 {'value': 'yes', 'label_zh': '要，+$10/㎡', 'label_en': 'Yes, +$10/sqm', 'per_sqm': '10'}]},
    {'key': 'hidden_hinges', 'label_zh': '隐藏合页', 'label_en': 'Hidden hinges',
     'choices': [{'value': 'no', 'label_zh': '不要', 'label_en': 'No'},
                 {'value': 'yes', 'label_zh': '要，+$40/㎡', 'label_en': 'Yes, +$40/sqm', 'per_sqm': '40'}]},
    {'key': 'hidden_tilt_rod', 'label_zh': '隐藏拉杆', 'label_en': 'Hidden tilt rod',
     'choices': [{'value': 'no', 'label_zh': '不要', 'label_en': 'No'},
                 {'value': 'yes', 'label_zh': '要，+$40/㎡', 'label_en': 'Yes, +$40/sqm', 'per_sqm': '40'}]},
    {'key': 'tier_on_tier', 'label_zh': '上下分段', 'label_en': 'Tier on tier',
     'choices': [{'value': 'no', 'label_zh': '不要', 'label_en': 'No'},
                 {'value': 'yes', 'label_zh': '要，+10%', 'label_en': 'Yes, +10%', 'percent': '10'}]},
    {'key': 'double_closure', 'label_zh': '双闭合', 'label_en': 'Double closure',
     'exclude': ['Shutters_PVC', 'Shutters_PVC_Eco'],
     'choices': [{'value': 'no', 'label_zh': '不要', 'label_en': 'No'},
                 {'value': 'yes', 'label_zh': '要，+$35/㎡', 'label_en': 'Yes, +$35/sqm', 'per_sqm': '35'}]},
    {'key': 'shaped_cutout', 'label_zh': '异形/法式门开孔', 'label_en': 'Shaped / French door cut out',
     'choices': [{'value': 'no', 'label_zh': '不要', 'label_en': 'No'},
                 {'value': 'yes', 'label_zh': '要，+$300/件', 'label_en': 'Yes, +$300 each', 'fixed': '300'}]},
    {'key': 'extra_installation', 'label_zh': '额外安装', 'label_en': 'Extra installation',
     'choices': [{'value': 'none', 'label_zh': '无', 'label_en': 'None'},
                 {'value': 'concrete', 'label_zh': '水泥墙', 'label_en': 'Concrete wall'},
                 {'value': 'height', 'label_zh': '高空', 'label_en': 'High access'},
                 {'value': 'tile', 'label_zh': '瓷砖', 'label_en': 'Tile'}]},
]

ADDON_KEYS = {item['key'] for item in ADDONS}
# Robin, 23 Oct: installation is 50 per shutter panel, and at least 150 on the order.
PANEL_INSTALLATION = Decimal('50')
ORDER_INSTALLATION_MINIMUM = Decimal('150')


def addon_totals(options, source_code=None, addon_definitions=None):
    """Return (per_sqm, percent, fixed) for the selected named add-ons."""
    per_sqm = percent = fixed = Decimal(0)
    selected = options or {}
    for addon in ADDONS if addon_definitions is None else addon_definitions:
        value = selected.get(addon['key']) or ''
        if value in ('', 'no', 'none'):
            continue
        choice = next((item for item in addon['choices'] if item['value'] == value), None)
        if choice is None:
            raise ValueError('Unsupported ' + addon['label_en'])
        priced = Decimal(choice.get('per_sqm', '0')) + Decimal(choice.get('fixed', '0')) + Decimal(choice.get('percent', '0'))
        if priced and source_code in addon.get('exclude', []):
            raise ValueError(addon['label_en'] + ' is not available for this material')
        per_sqm += Decimal(choice.get('per_sqm', '0'))
        percent += Decimal(choice.get('percent', '0'))
        fixed += Decimal(choice.get('fixed', '0'))
    return per_sqm, percent, fixed


def compose_unit(area, rate, per_sqm, percent, fixed, surcharge=0, discount=0):
    """Billable area x rate x (1 + percent) + per-item amounts. Percent does not touch the per-item amounts."""
    area, rate = Decimal(area), Decimal(rate)
    area_part = (area * rate + area * Decimal(per_sqm) + Decimal(surcharge)) * (Decimal(1) - Decimal(discount))
    return (area_part * (1 + Decimal(percent) / 100) + Decimal(fixed)).quantize(Decimal('0.01'), rounding=ROUND_UP)

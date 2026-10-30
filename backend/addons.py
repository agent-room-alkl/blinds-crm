"""Named wholesale add-ons from the V5 price list.

Area charges (per sqm and percent) use the billable area. Per-item amounts are
added afterwards, so a percentage never magnifies them. Extra installation
choices are recorded; V5 does not price concrete, height or tile.
"""
import json
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
    # Robin, 28 Oct: a customised frame adds 10% to the window. The size change itself goes in the special request.
    {'key': 'custom_frame', 'label_zh': '定制边框', 'label_en': 'Customised frame',
     'choices': [{'value': 'no', 'label_zh': '不要', 'label_en': 'No'},
                 {'value': 'yes', 'label_zh': '要，+10%', 'label_en': 'Yes, +10%', 'percent': '10'}]},
    {'key': 'extra_installation', 'label_zh': '额外安装', 'label_en': 'Extra installation',
     'choices': [{'value': 'none', 'label_zh': '无', 'label_en': 'None'},
                 {'value': 'concrete', 'label_zh': '水泥墙', 'label_en': 'Concrete wall'},
                 {'value': 'height', 'label_zh': '高空', 'label_en': 'High access'},
                 {'value': 'tile', 'label_zh': '瓷砖', 'label_en': 'Tile'}]},
]

ADDON_KEYS = {item['key'] for item in ADDONS}


def with_default_addons(addons):
    """Append any supported add-on a stored manifest predates, so older published versions offer it too."""
    present = {item.get('key') for item in addons if isinstance(item, dict)}
    for item in ADDONS:
        if item['key'] not in present:
            addons.append(json.loads(json.dumps(item)))
    return addons


def _amount(value, money=True):
    value = Decimal(str(value))
    if value == value.to_integral_value():
        return str(int(value))
    return f'{value:.2f}' if money else str(value.normalize())


def with_price_labels(addons):
    """Rewrite the text of each priced choice from its amount, so the label always matches what is charged."""
    for addon in addons if isinstance(addons, list) else []:
        choices = addon.get('choices') if isinstance(addon, dict) else None
        for choice in choices if isinstance(choices, list) else []:
            if not isinstance(choice, dict) or not isinstance(choice.get('value'), str) or choice['value'] in ('no', 'none'):
                continue
            charged = [field for field in ('fixed', 'per_sqm', 'percent') if field in choice]
            if len(charged) != 1:
                continue
            field = charged[0]
            try:
                amount = _amount(choice[field], money=field != 'percent')
            except Exception:
                continue  # publish validation reports the bad amount
            suffix_zh, suffix_en = {'fixed': (f'+${amount}/件', f'+${amount} each'),
                                    'per_sqm': (f'+${amount}/㎡', f'+${amount}/sqm'),
                                    'percent': (f'+{amount}%', f'+{amount}%')}[field]
            if choice['value'] == 'yes':
                base_zh, base_en = '要', 'Yes'
            else:
                base_zh = str(choice.get('label_zh') or choice['value']).split('，+')[0]
                base_en = str(choice.get('label_en') or choice['value']).split(', +')[0]
            choice['label_zh'], choice['label_en'] = f'{base_zh}，{suffix_zh}', f'{base_en}, {suffix_en}'
    return addons
# Robin, 23 Oct: installation is 50 per shutter panel, and at least 150 on the order.
PANEL_INSTALLATION = Decimal('50')
ORDER_INSTALLATION_MINIMUM = Decimal('150')


def concealed_rod(options):
    """True when the Control Rod is Internal Concealed, which carries the Hidden tilt rod charge."""
    return str((options or {}).get('control_rod') or '').strip().lower() == 'internal concealed'


# Customer feedback, 30 Oct: the Opening Style decides the track add-on, so a tracked shutter is never priced as hinged.
OPENING_STYLE_ADDONS = {'tracked bifold': 'tracked_bifold', 'tracked sliding': 'tracked_sliding'}


def sync_opening_style(options):
    """Set the track add-on from the Opening Style: Tracked Bifold/Sliding select their add-on and clear the other, Hinged clears both.
    A blank or unknown Opening Style leaves the add-ons as chosen."""
    style = str((options or {}).get('opening_style') or '').strip().lower()
    if style != 'hinged' and style not in OPENING_STYLE_ADDONS:
        return options
    synced = {k: v for k, v in options.items() if k not in OPENING_STYLE_ADDONS.values()}
    if style in OPENING_STYLE_ADDONS:
        synced[OPENING_STYLE_ADDONS[style]] = 'yes'
    return synced


def addon_totals(options, source_code=None, addon_definitions=None):
    """Return (per_sqm, percent, fixed) for the selected named add-ons."""
    per_sqm = percent = fixed = Decimal(0)
    selected = options or {}
    if concealed_rod(selected) and selected.get('hidden_tilt_rod') in (None, '', 'no'):
        selected = {**selected, 'hidden_tilt_rod': 'yes'}  # Robin, 27 Oct: this rod is the V5 Hidden tilt rod, +$40/sqm
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

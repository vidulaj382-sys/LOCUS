"""Asset list for the staff app (mirrors the offline STAFF table in src/app.js; items with live=True follow the live position)."""
STAFF = {
    'hospital': dict(lvl='Level 2', head='Find equipment fast', ph='Search pump, wheelchair, ECG', cats=['All', 'Pumps', 'Wheelchairs', 'ECG', 'Oxygen'], me=[2.5, 12],
                     items=[dict(id='P-12', name='Infusion pump P-12', cat='Pumps', live=True),
                            dict(id='W-3', name='Wheelchair W-3', cat='Wheelchairs', pos=[8.5, 12.3], conf=91),
                            dict(id='E-7', name='ECG machine E-7', cat='ECG', pos=[27, 19.5], conf=88),
                            dict(id='P-07', name='Infusion pump P-07', cat='Pumps', pos=[4.5, 4.5], conf=93),
                            dict(id='W-9', name='Wheelchair W-9', cat='Wheelchairs', pos=[35, 4.8], conf=86),
                            dict(id='O-2', name='Oxygen cylinder O-2', cat='Oxygen', pos=[16.5, 20], conf=94)]),
    'warehouse': dict(lvl='Bay 1', head='Find stock fast', ph='Search forklift, pallet, scanner', cats=['All', 'Vehicles', 'Pallets', 'Tools'], me=[2.5, 12],
                      items=[dict(id='FL-2', name='Forklift FL-2', cat='Vehicles', live=True),
                             dict(id='PJ-4', name='Pallet jack PJ-4', cat='Vehicles', pos=[6, 8], conf=92),
                             dict(id='PL-1042', name='Pallet #1042 (frozen)', cat='Pallets', pos=[20, 18], conf=89),
                             dict(id='PL-0877', name='Pallet #0877', cat='Pallets', pos=[28, 6], conf=90),
                             dict(id='SC-9', name='Handheld scanner SC-9', cat='Tools', pos=[36, 14], conf=85),
                             dict(id='C-11', name='Picking cart C-11', cat='Vehicles', pos=[12.5, 17.5], conf=91)]),
}

with open('src/reasoner/api/streaming.py', encoding='utf-8') as f:
    content = f.read()

old = """        # DEBUG: log a few routing entries so we can verify presets are fresh
        # Defensive: test fakes may use _primary instead of primary (see _stream_direct_answer)
        _primary_for_log = getattr(router, "primary", None) or getattr(router, "_primary", None)
        logger.info(
            "Preset '%s' primary=%s sample_routing=%s",
            effective_preset_name,
            getattr(_primary_for_log, "model", "unknown") if _primary_for_log else "unknown",
            {k: router.routing_table.get(k).model if router.routing_table.get(k) else None for k in list(router.routing_table)[:3]},
        )"""

new = """        # DEBUG: log a few routing entries so we can verify presets are fresh
        # Defensive: test fakes may use _primary instead of primary (see _stream_direct_answer)
        _primary_for_log = getattr(router, "primary", None) or getattr(router, "_primary", None)
        _routing_table = getattr(router, "routing_table", {})
        logger.info(
            "Preset '%s' primary=%s sample_routing=%s",
            effective_preset_name,
            getattr(_primary_for_log, "model", "unknown") if _primary_for_log else "unknown",
            {k: _routing_table.get(k).model if _routing_table.get(k) else None for k in list(_routing_table)[:3]},
        )"""

if old in content:
    content = content.replace(old, new)
    with open('src/reasoner/api/streaming.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('OK')
else:
    print('FAIL: not found')

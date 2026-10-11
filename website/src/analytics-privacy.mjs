export function sanitizeAnalyticsProperties(properties) {
  const denied = /^(?:utm_|gclid$|dclid$|fbclid$|msclkid$|ttclid$|twclid$|gbraid$|wbraid$|li_fat_id$|mc_cid$|mc_eid$|gad_source$|gclsrc$|igshid$|rdt_cid$|epik$|qclid$|sccid$|irclid$|_kx$)/i;
  function clean(value) {
    if (!value || typeof value !== 'object' || value instanceof Date) return value;
    for (const key of Object.keys(value)) {
      const normalizedKey = (key.startsWith('$') ? key.slice(1) : key).replace(/^(?:initial|session_entry|session_exit)_/i, '');
      if (denied.test(normalizedKey)) {
        delete value[key];
        continue;
      }
      const item = value[key];
      if (typeof item === 'string' && /(?:url|referrer|href|destination)/i.test(key)) {
        try {
          const url = new URL(item);
          value[key] = url.origin + url.pathname;
        } catch {}
      } else if (item && typeof item === 'object') clean(item);
    }
    return value;
  }
  return clean(properties);
}

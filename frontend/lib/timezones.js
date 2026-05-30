/** IANA timezone helpers using built-in Intl (no dependencies). */

export function browserTimezone() {
  if (typeof Intl === "undefined") return "UTC";
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

export function utcOffsetLabel(timeZone, date = new Date()) {
  try {
    const part = new Intl.DateTimeFormat("en-US", {
      timeZone,
      timeZoneName: "shortOffset",
    })
      .formatToParts(date)
      .find((p) => p.type === "timeZoneName");
    return part?.value ?? "UTC";
  } catch {
    return "UTC";
  }
}

function utcOffsetMinutes(timeZone, date = new Date()) {
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).formatToParts(date);
    const get = (type) => Number(parts.find((p) => p.type === type)?.value);
    const asUtc = Date.UTC(
      get("year"),
      get("month") - 1,
      get("day"),
      get("hour"),
      get("minute"),
      get("second")
    );
    return (asUtc - date.getTime()) / 60000;
  } catch {
    return 0;
  }
}

export function formatTimezoneLabel(timeZone, date = new Date()) {
  const offset = utcOffsetLabel(timeZone, date);
  const name = timeZone.replace(/_/g, " ");
  return `(${offset}) ${name}`;
}

/** Sorted IANA zones with UTC offset labels for dropdowns. */
export function getTimezoneOptions(date = new Date()) {
  const zones =
    typeof Intl !== "undefined" && Intl.supportedValuesOf
      ? Intl.supportedValuesOf("timeZone")
      : ["UTC"];

  return zones
    .map((value) => ({
      value,
      label: formatTimezoneLabel(value, date),
      offsetMinutes: utcOffsetMinutes(value, date),
    }))
    .sort(
      (a, b) =>
        a.offsetMinutes - b.offsetMinutes || a.value.localeCompare(b.value)
    );
}
